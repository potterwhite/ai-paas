#!/usr/bin/env bash
# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# ============================================================
# Pull a container image into a single local archive using aria2c,
# then load it into Docker.
#
# WHY THIS EXISTS
#   `docker pull` opens exactly ONE connection per layer and cannot
#   split a layer across connections. On a throttled link a single
#   1.4 GB layer (e.g. cuDNN) therefore crawls, and raising
#   max-concurrent-downloads does nothing once only one big layer is
#   left. Registry blobs are plain HTTPS objects that honour Range
#   requests, so aria2c can fetch each one over 16 connections.
#
# WHAT IT PRODUCES
#   A docker-archive tar (<image>.tar), then `docker load`s it.
#   docker-archive — not OCI layout — because Docker's classic
#   graphdriver image store only accepts the former; `docker load` of an
#   OCI layout fails with "does not contain a manifest.json" unless the
#   containerd snapshotter is enabled, and switching that hides every
#   image already in the classic store. The tar is kept, so it doubles
#   as an offline transfer file: copy it anywhere and `docker load -i`.
#
# USAGE
#   scripts/pull_image_fast.sh nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
#   scripts/pull_image_fast.sh nvidia/cuda:TAG docker.1ms.run   # other mirror
#
#   CONNS=32 ...     more connections per blob (default 16)
#   ARCH=arm64 ...   pick another platform  (default amd64)
#   WORKDIR=/path .. where blobs land      (default ./oci-<repo>-<tag>)
#
# Re-running is cheap: aria2c resumes partial blobs and skips complete
# ones, so an interrupted run picks up where it stopped.
# ============================================================
set -euo pipefail

IMAGE="${1:?usage: $0 <repo:tag> [registry-host]}"
REGISTRY="${2:-docker.m.daocloud.io}"
ARCH="${ARCH:-amd64}"
CONNS="${CONNS:-16}"

for tool in aria2c jq curl docker tar; do
    command -v "$tool" >/dev/null || { echo "ERROR: $tool not installed"; exit 1; }
done

REPO="${IMAGE%%:*}"
TAG="${IMAGE##*:}"
[ "$REPO" = "$TAG" ] && TAG=latest
# Docker Hub official images live under library/ ; "nvidia/cuda" already
# carries a namespace so it is left alone.
case "$REPO" in */*) API_REPO="$REPO" ;; *) API_REPO="library/$REPO" ;; esac

WORKDIR="${WORKDIR:-./oci-$(echo "$REPO" | tr / _)-$TAG}"
BLOBS="$WORKDIR/blobs/sha256"
mkdir -p "$BLOBS"

echo "==> image=$IMAGE  registry=$REGISTRY  arch=$ARCH  workdir=$WORKDIR"

# ---------- 1. auth ----------
# Registries answer an unauthenticated /v2/ with a WWW-Authenticate
# challenge naming their token service. Parsing it keeps this script
# working across mirrors that each front a different auth endpoint.
AUTH_HDR=""
CHALLENGE=$(curl -sI "https://$REGISTRY/v2/" | tr -d '\r' | grep -i '^www-authenticate:' || true)
if [ -n "$CHALLENGE" ]; then
    REALM=$(sed -n 's/.*realm="\([^"]*\)".*/\1/p' <<<"$CHALLENGE")
    SERVICE=$(sed -n 's/.*service="\([^"]*\)".*/\1/p' <<<"$CHALLENGE")
    if [ -n "$REALM" ]; then
        echo "==> auth realm: $REALM"
        TOKEN=$(curl -s "$REALM?service=${SERVICE}&scope=repository:${API_REPO}:pull" \
                | jq -r '.token // .access_token // empty')
        [ -n "$TOKEN" ] && AUTH_HDR="Authorization: Bearer $TOKEN"
    fi
fi
[ -z "$AUTH_HDR" ] && echo "==> no token needed (anonymous)"

fetch_json() {   # $1 = url
    local -a h=(-sL
        -H 'Accept: application/vnd.docker.distribution.manifest.v2+json'
        -H 'Accept: application/vnd.docker.distribution.manifest.list.v2+json'
        -H 'Accept: application/vnd.oci.image.manifest.v1+json'
        -H 'Accept: application/vnd.oci.image.index.v1+json')
    [ -n "$AUTH_HDR" ] && h+=(-H "$AUTH_HDR")
    curl "${h[@]}" "$1"
}

# ---------- 2. manifest ----------
MAN=$(fetch_json "https://$REGISTRY/v2/$API_REPO/manifests/$TAG")
if [ -z "$MAN" ] || [ "$(jq -r 'type' <<<"$MAN" 2>/dev/null)" != "object" ]; then
    echo "ERROR: could not fetch manifest. Raw response:"; echo "$MAN" | head -5; exit 1
fi

MT=$(jq -r '.mediaType // empty' <<<"$MAN")
# A manifest LIST covers several architectures; resolve it down to the
# single-arch manifest we want before touching any blobs.
if jq -e '.manifests' >/dev/null 2>&1 <<<"$MAN"; then
    echo "==> manifest list -> selecting linux/$ARCH"
    SUB=$(jq -r --arg a "$ARCH" \
          '.manifests[] | select(.platform.architecture==$a and .platform.os=="linux") | .digest' \
          <<<"$MAN" | head -1)
    [ -n "$SUB" ] || { echo "ERROR: no linux/$ARCH in manifest list"; exit 1; }
    MAN=$(fetch_json "https://$REGISTRY/v2/$API_REPO/manifests/$SUB")
    MT=$(jq -r '.mediaType // empty' <<<"$MAN")
fi
[ -n "$MT" ] || MT="application/vnd.docker.distribution.manifest.v2+json"

# The manifest is itself a blob, addressed by its own digest — that is
# what index.json has to point at.
printf '%s' "$MAN" > "$BLOBS/tmp-manifest.json"
MAN_DIGEST=$(sha256sum "$BLOBS/tmp-manifest.json" | cut -d' ' -f1)
MAN_SIZE=$(stat -c%s "$BLOBS/tmp-manifest.json")
mv "$BLOBS/tmp-manifest.json" "$BLOBS/$MAN_DIGEST"
echo "==> manifest sha256:$MAN_DIGEST ($MAN_SIZE bytes)"

# ---------- 3. blobs via aria2c ----------
# One aria2c input stanza per blob. Complete files are skipped and
# partial ones resumed, so re-running after an interrupt costs nothing.
LIST="$WORKDIR/aria2.in"
: > "$LIST"
COUNT=0
TOTAL=0
while read -r digest size; do
    hex="${digest#sha256:}"
    if [ -f "$BLOBS/$hex" ] && [ "$(stat -c%s "$BLOBS/$hex")" = "$size" ]; then
        continue
    fi
    {   echo "https://$REGISTRY/v2/$API_REPO/blobs/$digest"
        echo "  dir=$BLOBS"
        echo "  out=$hex"
    } >> "$LIST"
    COUNT=$((COUNT+1))
    TOTAL=$((TOTAL+size))
done < <(jq -r '[.config] + .layers | .[] | "\(.digest) \(.size)"' <<<"$MAN")

if [ "$COUNT" -gt 0 ]; then
    echo "==> downloading $COUNT blob(s), $((TOTAL/1024/1024)) MB total, $CONNS connections each"
    ARIA_ARGS=(-i "$LIST" -x"$CONNS" -s"$CONNS" -k1M -j2 --continue=true
               --file-allocation=none --auto-file-renaming=false
               --summary-interval=10 --console-log-level=warn
               --max-tries=0 --retry-wait=3)
    [ -n "$AUTH_HDR" ] && ARIA_ARGS+=(--header="$AUTH_HDR")
    aria2c "${ARIA_ARGS[@]}"
else
    echo "==> all blobs already present"
fi

# Verify before assembling: a truncated blob otherwise surfaces much
# later as an opaque `docker load` failure.
echo "==> verifying blob sizes"
while read -r digest size; do
    hex="${digest#sha256:}"
    actual=$(stat -c%s "$BLOBS/$hex" 2>/dev/null || echo 0)
    if [ "$actual" != "$size" ]; then
        echo "ERROR: $hex is $actual bytes, expected $size — just re-run this script"
        exit 1
    fi
done < <(jq -r '[.config] + .layers | .[] | "\(.digest) \(.size)"' <<<"$MAN")
echo "    all blobs OK"

# ---------- 4. assemble a docker-archive ----------
# Layout docker's tarexport loader expects:
#   manifest.json          [{Config, RepoTags, Layers}]
#   <config-hex>.json      the image config blob
#   blobs/sha256/<hex>     the layer blobs, referenced by Layers
# RepoTags carries the final name, so no retag step is needed.
rm -f "$BLOBS"/*.aria2
CONFIG_HEX=$(jq -r '.config.digest | sub("^sha256:";"")' <<<"$MAN")
cp -f "$BLOBS/$CONFIG_HEX" "$WORKDIR/$CONFIG_HEX.json"

write_manifest() {   # $1 = jq array of layer paths inside the tar
    jq -n --arg cfg "$CONFIG_HEX.json" --arg tag "$REPO:$TAG" --argjson layers "$1" \
        '[{Config: $cfg, RepoTags: [$tag], Layers: $layers}]' > "$WORKDIR/manifest.json"
}

LAYERS=$(jq -c '[.layers[] | "blobs/sha256/" + (.digest | sub("^sha256:";""))]' <<<"$MAN")
write_manifest "$LAYERS"

ARCHIVE="$WORKDIR.tar"
pack_and_load() {    # $1... = paths inside WORKDIR to include
    rm -f "$ARCHIVE"
    echo "==> packing $ARCHIVE"
    tar -C "$WORKDIR" -cf "$ARCHIVE" "$@"
    ls -lh "$ARCHIVE"
    echo "==> docker load"
    docker load -i "$ARCHIVE"
}

# ---------- 5. load ----------
# Layer blobs are gzipped (mediaType ...tar.gzip). Docker's loader pipes
# each one through DecompressStream, so gzip normally loads as-is. If
# this daemon refuses, fall back to decompressing them ourselves.
if pack_and_load manifest.json "$CONFIG_HEX.json" blobs; then
    :
else
    echo
    echo "==> compressed layers rejected — decompressing and retrying"
    echo "    (needs roughly 2.5x the archive size in free disk)"
    mkdir -p "$WORKDIR/plain"
    while read -r digest; do
        hex="${digest#sha256:}"
        out="$WORKDIR/plain/$hex.tar"
        [ -s "$out" ] && continue
        # gzip magic is 1f 8b; anything else is already a plain tar.
        if [ "$(head -c2 "$BLOBS/$hex" | od -An -tx1 | tr -d ' ')" = "1f8b" ]; then
            echo "    gunzip $hex"
            gunzip -c "$BLOBS/$hex" > "$out"
        else
            cp -f "$BLOBS/$hex" "$out"
        fi
    done < <(jq -r '.layers[].digest' <<<"$MAN")

    write_manifest "$(jq -c '[.layers[] | "plain/" + (.digest | sub("^sha256:";"")) + ".tar"]' <<<"$MAN")"
    pack_and_load manifest.json "$CONFIG_HEX.json" plain
fi

echo
echo "Loaded as $REPO:$TAG — verify with: docker images | grep '${REPO##*/}'"
echo "Archive kept at $ARCHIVE — reusable offline on any host via 'docker load -i'."
echo "Delete $WORKDIR once loaded; the .tar alone is enough."
