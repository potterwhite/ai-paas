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
# fileinfo.sh -- measure files on disk.
#
# Every function here answers a question about a file that already exists and
# returns the answer on stdout. Facts only: no expected value is passed in, no
# comparison is made, nothing is printed for a human, nothing is deleted.
#
# What does NOT live here:
#   - expectations ("should this file be 9925342208 bytes?") -- caller's job
#   - the decision to download, skip, or discard                -- caller's job
#   - progress or status messages                               -- caller's job
#
# Keeping the comparison out means the caller holds both the measured and the
# expected value at the point of decision, and can say which is which when they
# disagree. A helper that returned only pass/fail could not.
#
# Functions are prefixed libfileinfo_ so a `grep -r libfileinfo_` finds every
# caller across the repo.
#
# Source-only. Not executable.

# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

# libfileinfo_size: apparent size of $1 in bytes, or 0 when unreadable.
#
# $1 -- path
#
# "Apparent" is the number the kernel reports, which for a sparse file exceeds
# the bytes actually stored. Correct for a file a transfer finished with; do not
# compare it against an expected size while a transfer may still be in flight
# (see libhttp_unfinished for why).
#
# A missing or unstattable path yields 0 rather than an error, so callers can
# use the result in arithmetic without guarding first.
libfileinfo_size() {
    stat -c%s "$1" 2>/dev/null || echo 0
}

# libfileinfo_sha256: SHA-256 of $1 as 64 lowercase hex chars, empty on failure.
#
# $1 -- path
#
# Reads the entire file, so cost scales with size -- roughly 20 s for 10 GB on
# an NVMe disk. This is the only check that detects a file which is the right
# length but wrong content: a truncated-then-padded transfer, a silent disk
# error, or a CDN that served an error page under the right Content-Length.
#
# Empty output means the file could not be hashed at all (missing, unreadable).
# Callers must treat empty as "unknown", never as "matches nothing".
libfileinfo_sha256() {
    sha256sum "$1" 2>/dev/null | cut -d' ' -f1
}

# libfileinfo_allocated: bytes actually stored for $1 on disk, or 0 when unreadable.
#
# $1 -- path
#
# The counterpart to libfileinfo_size, and the only one of the two that means
# anything mid-transfer. aria2c runs with --file-allocation=none and writes 16
# segments concurrently, the last of which starts near the end of the file, so
# the result is sparse: apparent size reads as almost complete within seconds
# while most of the file is holes. Allocated blocks count only the bytes that
# arrived.
#
# Use this to answer "did that attempt make progress?" -- comparing apparent
# size across attempts compares two numbers that were both nearly final before
# either transfer had gotten anywhere.
#
# %b is in %B-sized units, not always 512, so both are read rather than
# assuming. A missing or unstattable path yields 0, matching libfileinfo_size,
# so callers can subtract without guarding first.
libfileinfo_allocated() {
    local blocks unit
    read -r blocks unit < <(stat -c'%b %B' "$1" 2>/dev/null) || { echo 0; return 0; }
    if [ -z "$blocks" ] || [ -z "$unit" ]; then
        echo 0
        return 0
    fi
    echo $(( blocks * unit ))
}

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

# libfileinfo_human: render a byte count as a short human-readable string.
#
# $1 -- byte count (integer)
#
# For log lines only. Rounds, so the result must never be compared or parsed
# back into a number -- pass the raw byte count wherever a decision is made.
#
# Uses awk rather than `du -h` because the input is a number the caller already
# has, and re-reading the file from disk to format a message it already measured
# would be wasteful and could disagree with the value being reported.
libfileinfo_human() {
    awk -v b="$1" 'BEGIN {
        split("B KiB MiB GiB TiB", u, " ")
        i = 1
        while (b >= 1024 && i < 5) { b /= 1024; i++ }
        printf (i == 1 ? "%d%s\n" : "%.1f%s\n"), b, u[i]
    }'
}
