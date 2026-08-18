#!/usr/bin/env bash
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
#   An OCI image layout, tarred into <image>.tar, then `docker load`ed.
#   OCI layout is used rather than docker-archive because blobs are
#   addressed purely by digest — no hand-written diffID ordering to get
#   wrong. The .tar is kept, so it doubles as an offline transfer file:
#   copy it to any host and `docker load -i` it there.
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

# ---------- 4. OCI layout ----------
printf '{"imageLayoutVersion":"1.0.0"}' > "$WORKDIR/oci-layout"
jq -n --arg mt "$MT" --arg d "sha256:$MAN_DIGEST" --argjson s "$MAN_SIZE" \
      --arg name "$REPO:$TAG" '{
  schemaVersion: 2,
  mediaType: "application/vnd.oci.image.index.v1+json",
  manifests: [{
    mediaType: $mt, digest: $d, size: $s,
    annotations: {
      "org.opencontainers.image.ref.name": $name,
      "io.containerd.image.name": ("docker.io/" + $name)
    }
  }]
}' > "$WORKDIR/index.json"

# ---------- 5. load ----------
ARCHIVE="$WORKDIR.tar"
echo "==> packing $ARCHIVE"
tar -C "$WORKDIR" -cf "$ARCHIVE" oci-layout index.json blobs
ls -lh "$ARCHIVE"

echo "==> docker load"
docker load -i "$ARCHIVE"

echo
echo "Done. If the loaded name is not exactly '$IMAGE', retag it:"
echo "  docker tag <loaded-name> $IMAGE"
echo
echo "Archive kept at $ARCHIVE — reusable offline on any host via 'docker load -i'."
echo "Delete $WORKDIR once loaded; the .tar alone is enough."
