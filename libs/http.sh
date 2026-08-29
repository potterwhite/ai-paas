#!/bin/bash
##
## Copyright (c) 2026 PotterWhite
##
## Permission is hereby granted, free of charge, to any person obtaining a copy
## of this software and associated documentation files (the "Software"), to deal
## in the Software without restriction, including without limitation the rights
## to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
## copies of the Software, and to permit persons to whom the Software is
## furnished to do so, subject to the following conditions:
##
## The above copyright notice and this permission notice shall be included in all
## copies or substantial portions of the Software.
##
## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
## IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
## FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
## AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
## LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
## OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
## SOFTWARE.
##

# shellcheck shell=bash
#
# http.sh -- Transport. Move a URL's bytes to a path.
#
# Knows how to talk to an HTTP server and nothing else. It does not know what a
# model is, whether a file is worth downloading, or how to tell a good file from
# a bad one. Callers decide that and call here only once they have decided.
#
# Specifically NOT here:
#   - "is this file already complete?"   -> caller's decision, see fileinfo.sh
#   - checksum verification              -> fileinfo.sh reports, caller decides
#   - skip/redownload counters           -> the caller's bookkeeping
#
# Every function is named libhttp_*, so a call site names the file it came from
# without a search.
#
# Source-only. Not executable.

# ---------------------------------------------------------------------------
# Downloader selection
# ---------------------------------------------------------------------------

# libhttp_require: fail unless aria2c is on PATH.
#
# Deliberately a hard requirement with no fallback to wget or curl. A single
# stream to HF measures ~236 KB/s from here against aria2c's ~19 MB/s over 16
# connections -- 26 GB of models is 32 hours versus 23 minutes. A silent
# fallback would look identical to the stall it replaces, which is exactly the
# failure this file exists to remove. Better to stop and say so.
libhttp_require() {
    if ! command -v aria2c >/dev/null 2>&1; then
        echo "ERROR: aria2c not found on PATH." >&2
        echo "" >&2
        echo "  This script downloads tens of GB and requires aria2c's multi-connection" >&2
        echo "  transfers. A single-stream wget takes ~32 hours for what aria2c does in" >&2
        echo "  ~23 minutes, so there is no fallback on purpose." >&2
        echo "" >&2
        echo "  Install it:" >&2
        echo "    dnf install -y aria2      # Rocky / RHEL  (the ai_comfyui image)" >&2
        echo "    apt-get install -y aria2  # Debian / Ubuntu hosts" >&2
        return 1
    fi

    if ! aria2c --help 2>&1 | grep -q -- '--checksum'; then
        echo "ERROR: aria2c does not support --checksum." >&2
        echo "" >&2
        echo "  This script requires aria2c with --checksum support for" >&2
        echo "  SHA-256 verification. Your version does not have it." >&2
        echo "" >&2
        echo "  Install a recent build: https://aria2.github.io/" >&2
        return 1
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------

# libhttp_get: download $1 to the exact path $2.
#
# $1 -- url
# $2 -- destination path (created; parent directories are made)
# $3 -- optional: SHA-256 hex digest. When non-empty, aria2c verifies the
#       downloaded file matches this hash via --checksum=sha-256=<digest>.
# $4 -- optional: "quiet" to suppress the progress bar
#
# Returns aria2c's exit status. With $3 set, a checksum mismatch causes aria2c
# to exit non-zero, which the caller's retry loop handles.
#
# aria2c takes a directory and a bare filename rather than a full path, so the
# destination is split. -o with a path component would be interpreted relative
# to -d and silently nest.
#
# Flag notes, since several are load-bearing:
#   -x16 -s16   16 connections over 16 file segments -- the whole point.
#   -k1M        1 MB minimum per segment, so small files do not get split into
#               pieces whose per-connection overhead exceeds the transfer.
#   --continue  resume a previous partial transfer rather than restart it.
#   --timeout / --lowest-speed-limit
#               kill a connection that stalls instead of hanging on it. This is
#               the pair that fixes "download freezes halfway": without them a
#               dead peer is waited on for ~15 minutes.
#   --auto-file-renaming=false
#               on collision, fail loudly. The default invents dest.1, leaving
#               the real filename holding older bytes -- silent corruption.
#   --allow-overwrite=true
#               required for the retry path: the caller deletes a bad file and
#               calls again, and without this aria2c refuses rather than rewrite.
libhttp_get() {
    local url="$1" dest="$2" checksum="${3:-}" quiet="${4:-}"
    local dir base
    dir="$(dirname "$dest")"
    base="$(basename "$dest")"

    mkdir -p "$dir" || return 1

    local args=(
        -x16 -s16 -k1M
        --continue=true
        --allow-overwrite=true
        --auto-file-renaming=false
        --max-tries=5
        --retry-wait=2
        --timeout=30
        --lowest-speed-limit=32K
        --file-allocation=none
        ${checksum:+--checksum=sha-256="$checksum"}
        -d "$dir" -o "$base"
    )

    # HF gated repos need the token as a bearer header. Unset means public.
    #
    # Scoped to huggingface.co on purpose. Sending it unconditionally did two
    # bad things: it handed the token to every host this function was pointed
    # at, and github.com answers a foreign bearer token with 401 rather than
    # ignoring it -- so an unauthenticated public download failed outright.
    case "$url" in
        https://huggingface.co/* | https://*.huggingface.co/*)
            [ -n "${HF_TOKEN:-}" ] && args+=(--header "Authorization: Bearer ${HF_TOKEN}")
            ;;
    esac

    if [ "$quiet" = quiet ]; then
        args+=(--quiet=true)
    else
        args+=(--summary-interval=10 --console-log-level=warn)
    fi

    aria2c "${args[@]}" "$url"
}

# libhttp_unfinished: true when a previous transfer to $1 did not complete.
#
# $1 -- destination path
#
# Reports aria2c's own verdict: it keeps resume state in <dest>.aria2 while a
# transfer is in flight and deletes that file on success, so the control file's
# presence is the only trustworthy "not finished" signal.
#
# The destination's size is NOT such a signal, and this function exists so that
# no caller is tempted to use it. aria2c writes 16 segments concurrently, the
# last of which starts near the end of the file, so the kernel reports a sparse
# file whose apparent size is almost complete from the first seconds. Measured
# on an interrupted 4.89 GB transfer: 152 MB actually fetched, `stat` reporting
# 4.59 GB. Any size threshold accepts that file as done.
libhttp_unfinished() {
    [ -f "$1.aria2" ]
}

# libhttp_discard: remove a destination and aria2c's control file for it.
#
# $1 -- destination path
#
# Both, always. aria2c stores resume state in <dest>.aria2, and a control file
# whose data file has been deleted makes every later attempt fail outright
# rather than start over -- a partial download that cannot be retried.
libhttp_discard() {
    rm -f "$1" "$1.aria2"
}
