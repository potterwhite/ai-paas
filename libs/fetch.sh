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
# fetch.sh -- decide whether a file needs downloading, and download it.
#
# This is the policy layer. It owns exactly one rule: a file is present only if
# its SHA-256 matches what the caller expects. Anything else -- missing, partial,
# right size but wrong bytes -- is re-downloaded.
#
# Dependencies are called, never sourced. This file has zero outgoing source
# statements, same as every other file in libs/, so the whole library is a set
# of leaves and the entry script does all sourcing:
#
#     source libs/http.sh
#     source libs/fileinfo.sh
#     source libs/fetch.sh
#     libfetch_require || exit 1
#
# The reason is practical, not stylistic. These libs are read from three
# different places depending on how they were delivered -- a read-only bind
# mount at /root/ComfyUI/libs, a docker-cp fallback under /tmp, or the host
# checkout. If each lib sourced its own dependencies, that path guess would be
# duplicated in every file and would break on any new mount point. Sourced from
# the entry script, it exists once, in the script that already knows where it is.
#
# What does NOT live here:
#   - aria2c flags, resume state          -- libs/http.sh
#   - how a size or hash is obtained      -- libs/fileinfo.sh
#   - which models a service needs        -- the calling service's script
#
# Source-only. Not executable.

# ---------------------------------------------------------------------------
# Tally
# ---------------------------------------------------------------------------
# Kept here rather than in the caller because every branch that could change a
# count is in this file. When the caller incremented them, a branch added here
# was silently uncounted -- which is how the LivePortrait loop in comfyui's
# setup.sh ended up maintaining its own copy of the arithmetic.
#
# Read them after the last libfetch_* call; do not write them.
LIBFETCH_DOWNLOADED=0
LIBFETCH_SKIPPED=0
LIBFETCH_FAILED=0

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# How many times libfetch_model asks aria2c for one file before giving up.
#
# Higher than it looks, because attempts are cheap now: an attempt that made
# progress resumes rather than restarting, so the cost of a wasted round is the
# stall that ended it, not the bytes already transferred. Four rounds of a
# resuming transfer finish files that two rounds of a restarting one never
# could.
#
# Not unbounded, because each round can burn minutes against a stalled CDN and
# a prepare run has dozens of files behind this one. Partial data survives a
# give-up, so the remaining rounds are simply taken on the next run.
LIBFETCH_MAX_ATTEMPTS="${LIBFETCH_MAX_ATTEMPTS:-4}"

# How many consecutive zero-byte attempts before the partial data is treated as
# unresumable and discarded.
#
# Must be at least 2. At 1, any transient failure that lands before the first
# byte moves -- a TLS handshake error, a DNS blip -- destroys however many
# gigabytes were already on disk. The cost of the extra attempt is bounded by
# the fact that the state this detects fails instantly rather than stalling.
LIBFETCH_STALL_LIMIT="${LIBFETCH_STALL_LIMIT:-2}"

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

# libfetch_require: verify this file's dependencies were sourced. Returns 1 if not.
#
# bash resolves a function name at call time, so a missing `source` surfaces as
# "libhttp_get: command not found" at the moment of first use -- possibly hours
# into a multi-gigabyte run. This is the link-time check bash does not have: it
# fails at startup instead.
libfetch_require() {
    local fn
    for fn in libhttp_require libhttp_get libhttp_unfinished libhttp_discard \
              libfileinfo_size libfileinfo_allocated libfileinfo_sha256 \
              libfileinfo_human; do
        if ! declare -F "$fn" >/dev/null; then
            echo "ERROR: fetch.sh needs ${fn}()." >&2
            echo "       Source libs/http.sh and libs/fileinfo.sh before libs/fetch.sh." >&2
            return 1
        fi
    done
    libhttp_require || return 1
}

# ---------------------------------------------------------------------------
# Large files -- checksum required
# ---------------------------------------------------------------------------

# libfetch_model: ensure DEST holds exactly the bytes SHA256 describes.
#
# $1 -- source URL
# $2 -- destination path (parent directories are created)
# $3 -- label for progress output
# $4 -- expected SHA-256, 64 hex chars, REQUIRED
#
# Returns 0 when DEST ends up correct (whether skipped or downloaded), 1 otherwise.
#
# The checksum is not optional and an empty $4 is a hard error. The alternative
# -- accept any file over some size threshold -- is what this replaces, and it
# fails in the worst possible way: a transfer cut at 60% is accepted forever,
# then surfaces months later as an unreadable safetensors with no hint that the
# download was to blame.
#
# Cost is honest: every run reads every file to hash it, roughly 1-2 min for
# ComfyUI's 26 GB. Bought deliberately, because size and mtime cannot tell a
# complete file from a truncated one, and a wrong model file is far more
# expensive to diagnose than the read is to perform. Paid visibly too -- each
# read is announced by a [check] line before it starts, so the wait is legible
# as work rather than as a hang.
libfetch_model() {
    local url="$1" dest="$2" label="$3" expected="$4"
    # Declared here rather than at first use: `local` is a runtime statement, so
    # a declaration inside the existing-file branch below would not run when that
    # branch is skipped, and the post-download assignments would then silently
    # write globals.
    local size actual

    if [ -z "$expected" ]; then
        echo "  [FAIL] ${label} — no SHA-256 given (required)" >&2
        LIBFETCH_FAILED=$((LIBFETCH_FAILED + 1))
        return 1
    fi

    mkdir -p "$(dirname "$dest")"

    # An existing file is trusted only after both checks agree: aria2c is not
    # mid-transfer, and the bytes hash correctly. Either failure discards it --
    # resuming onto a file whose control state was lost cannot be made safe.
    if [ -f "$dest" ] && ! libhttp_unfinished "$dest"; then
        size="$(libfileinfo_size "$dest")"

        # Announced before the read, not after. Hashing ComfyUI's 26 GB takes
        # 1-2 min during which sha256sum prints nothing, so a silent run is
        # indistinguishable from a hung one -- and the reflex that costs is
        # Ctrl-C, which is how a complete file becomes a partial one. Naming the
        # size lets the reader judge the wait instead of guessing at it.
        echo "  [check] ${label} — hashing $(libfileinfo_human "$size"), hold on..."
        actual="$(libfileinfo_sha256 "$dest")"

        if [ "$actual" = "$expected" ]; then
            # Says "matched", not just "skip": the old message could equally have
            # meant the checksum was never consulted, which is the one thing a
            # reader most needs to rule out here.
            echo "  [skip] ${label} — checksum matched ($(libfileinfo_human "$size"))"
            LIBFETCH_SKIPPED=$((LIBFETCH_SKIPPED + 1))
            return 0
        fi

        # Both hashes printed, same as the post-download mismatch below. Without
        # the actual value a reader cannot tell a truncated transfer from a file
        # this list has the wrong expected hash for, and those need opposite
        # fixes -- re-download versus correct the caller.
        echo "  [stale] ${label} — checksum MISMATCH, discarding"
        echo "          expected ${expected}"
        echo "          actual   ${actual:-<unreadable>}"
        libhttp_discard "$dest"
    fi

    echo "  [download] ${label}"
    # Resume-first. Each attempt is measured, and partial data is discarded only
    # when the attempt that produced it got nowhere.
    #
    # The unconditional discard this replaces made large files on a throttled
    # link unfinishable. HF's CDN drops to 0 B/s for minutes at a time and
    # --lowest-speed-limit kills connections one by one until aria2c exits, which
    # is a network verdict, not damaged local state -- aria2c says so itself
    # ("aria2 will resume download if the transfer is restarted"). Throwing the
    # bytes away turned that into a restart from zero: a 9.2 GB shard reached
    # 5.6 GB, was discarded, reached 846 MB, was discarded, and failed. 6.4 GB
    # transferred, nothing kept, and no number of re-runs would ever converge.
    #
    # Discard is still right for the case the old comment describes -- a control
    # file left by kill -9, which aria2c refuses to start against at all ("Failed
    # to read from the segment file") and which no retry clears.
    #
    # But "this attempt moved no bytes" does not identify that case on its own.
    # A TLS handshake that fails before the first byte moves looks identical and
    # is merely transient -- observed on the very first test run of this code,
    # where attempt 1 died on "SSL/TLS handshake failure" having transferred 0 B
    # and the discard threw away 8 MB that would have resumed fine. So one stall
    # is ambiguous and gets another resuming attempt; only consecutive stalls
    # are taken as a verdict on the local state. A genuinely unreadable control
    # file fails instantly, so the extra attempt it costs is a second or two,
    # while the data an over-eager discard destroys is measured in gigabytes.
    local attempt before after stalled=0
    for attempt in $(seq 1 "$LIBFETCH_MAX_ATTEMPTS"); do
        before="$(libfileinfo_allocated "$dest")"
        libhttp_get "$url" "$dest" "$expected" && break
        after="$(libfileinfo_allocated "$dest")"

        if [ "$after" -gt "$before" ]; then
            stalled=0
        else
            stalled=$((stalled + 1))
        fi

        if [ "$attempt" -ge "$LIBFETCH_MAX_ATTEMPTS" ]; then
            echo "  [FAIL] ${label} — transfer failed ${LIBFETCH_MAX_ATTEMPTS} times"
            # Partial data is kept on the way out, which is the other half of
            # making a large file finishable: the next run resumes from here
            # instead of from zero. Safe because the control file makes
            # libhttp_unfinished true, so the entry check above skips the hash
            # branch and comes straight back to aria2c --continue.
            if libhttp_unfinished "$dest" && [ "$after" -gt 0 ]; then
                echo "         kept $(libfileinfo_human "$after") of partial data — re-run to resume from there"
            fi
            LIBFETCH_FAILED=$((LIBFETCH_FAILED + 1))
            return 1
        fi

        if libhttp_unfinished "$dest" && [ "$after" -gt 0 ] \
           && [ "$stalled" -lt "$LIBFETCH_STALL_LIMIT" ]; then
            echo "  [retry] ${label} — resuming from $(libfileinfo_human "$after") (attempt $((attempt + 1)) of ${LIBFETCH_MAX_ATTEMPTS})"
        else
            libhttp_discard "$dest"
            echo "  [retry] ${label} — ${stalled} attempts moved no bytes, discarded partial data, starting over (attempt $((attempt + 1)) of ${LIBFETCH_MAX_ATTEMPTS})"
        fi
    done

    size="$(libfileinfo_size "$dest")"
    echo "  [done] ${label} — checksum matched ($(libfileinfo_human "$size"))"
    LIBFETCH_DOWNLOADED=$((LIBFETCH_DOWNLOADED + 1))
    return 0
}

# ---------------------------------------------------------------------------
# Small config files -- best effort
# ---------------------------------------------------------------------------

# libfetch_config: fetch a small text file, quietly, without a checksum.
#
# $1 -- source URL
# $2 -- destination path
#
# Always returns 0 and never touches the tally.
#
# For the JSON that accompanies a model -- config.json, tokenizer files, weight
# index maps. A checksum is skipped here for a reason that does not apply to
# weights: these are kilobytes, the loader parses them immediately and fails
# loudly on damage, and re-fetching costs a second. Weights are the opposite on
# all three counts, which is why libfetch_model refuses to run without one.
#
# An existing file is left alone. These change only when the upstream repo is
# restructured, and re-fetching on every run would add dozens of requests to
# HuggingFace for content already on disk.
libfetch_config() {
    local url="$1" dest="$2"
    [ -f "$dest" ] && return 0
    mkdir -p "$(dirname "$dest")"
    libhttp_get "$url" "$dest" quiet || rm -f "$dest" "$dest.aria2"
    return 0
}
