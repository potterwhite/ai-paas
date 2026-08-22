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
# Step 1 — download the two ONNX weights. Runs on the HOST.
#
# Not the container: the weights live in the upstream clone, which is
# bind-mounted, so downloading here or there is the same thing — and the
# host already has aria2c.
#
# Why not upstream's scripts/download_model.py: it uses single-threaded
# requests, and objects.githubusercontent.com throttles one TCP stream to
# ~180 KB/s from here. aria2c splits the file over 16 connections and gets
# 20x that. Same URLs, same files.
#
# Idempotent: a file that already exists at the right size is skipped.
# ============================================================
set -euo pipefail

# Target defaults to the model store, resolved the same way scripts/core.sh
# resolves it — MODELS_PATH from the environment, else from .env, else the
# repo-relative models/ dir — so nothing here hard-codes a machine's layout.
# Pass a path as $1 to override.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
if [ -z "${MODELS_PATH:-}" ] && [ -f "${REPO_ROOT}/.env" ]; then
    # shellcheck disable=SC1091
    . "${REPO_ROOT}/.env"
fi
SRC="${1:-${MODELS_PATH:-${REPO_ROOT}/models}/idphoto/src}"

if [ ! -f "$SRC/deploy_api.py" ]; then
    echo "ERROR: $SRC is not a HivisionIDPhotos clone (no deploy_api.py)."
    echo "Pass the path as \$1, or clone it there first. See README.md."
    exit 1
fi

# aria2c is preferred but is not installed by default on most systems, so it
# must not be a hard requirement. curl and wget download the same bytes from the
# same URLs over a single stream — correct, just slower on a throttled host.
DOWNLOADER=""
for candidate in aria2c curl wget; do
    if command -v "$candidate" >/dev/null 2>&1; then
        DOWNLOADER="$candidate"
        break
    fi
done
if [ -z "$DOWNLOADER" ]; then
    echo "ERROR: need one of aria2c, curl or wget on PATH."
    exit 1
fi
if [ "$DOWNLOADER" = aria2c ]; then
    echo "==> downloader: aria2c (16 connections)"
else
    echo "==> downloader: $DOWNLOADER (single stream — aria2c is ~20x faster here)"
fi

fetch() {
    url="$1"; dir="$2"; name="$3"
    case "$DOWNLOADER" in
        aria2c)
            # -o takes a bare filename, so -d carries the directory.
            aria2c -x16 -s16 -k1M --continue=true --allow-overwrite=true \
                   -d "$dir" -o "$name" "$url"
            ;;
        curl|wget)
            # Download to .part and rename only on success. Without this an
            # interrupted transfer sits at the real filename, where it looks
            # like a complete model to anything that does not size-check it.
            part="${dir}/${name}.part"
            if [ "$DOWNLOADER" = curl ]; then
                curl -fL --retry 3 --retry-delay 2 -o "$part" "$url"
            else
                wget -O "$part" "$url"
            fi
            mv -f "$part" "${dir}/${name}"
            ;;
    esac
}

# name | dest dir (relative to SRC) | expected bytes | url
#
# The size check is the point of this script. A failed redirect writes an
# HTML error page to the destination — right filename, right extension,
# and it only surfaces much later as an opaque onnxruntime protobuf error.
# Sizes below are from the files verified working on this box.
WEIGHTS=(
"birefnet-v1-lite.onnx|hivision/creator/weights|224005088|https://github.com/ZhengPeng7/BiRefNet/releases/download/v1/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx"
"retinaface-resnet50.onnx|hivision/creator/retinaface/weights|109458296|https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/retinaface-resnet50.onnx"
)

fail=0

for entry in "${WEIGHTS[@]}"; do
    IFS='|' read -r name subdir want url <<<"$entry"
    dir="$SRC/$subdir"
    dest="$dir/$name"

    mkdir -p "$dir"

    if [ -f "$dest" ]; then
        have=$(stat -c '%s' "$dest")
        if [ "$have" = "$want" ]; then
            echo "==> $name already present and correct, skipping"
            continue
        fi
        # A partial file from an interrupted curl would otherwise be loaded
        # as if it were a complete model. Remove it, do not resume.
        echo "==> $name is $have bytes, want $want — removing and refetching"
        rm -f "$dest"
    fi

    echo "==> downloading $name"
    fetch "$url" "$dir" "$name"

    have=$(stat -c '%s' "$dest")
    if [ "$have" != "$want" ]; then
        echo "ERROR: $name is $have bytes, expected $want."
        echo "       Almost certainly an HTML error page. Delete it and retry."
        fail=1
    fi
done

echo
if [ "$fail" != 0 ]; then
    echo "FAILED — at least one weight is the wrong size. Do not continue."
    exit 1
fi

ls -l "$SRC/hivision/creator/weights/birefnet-v1-lite.onnx" \
      "$SRC/hivision/creator/retinaface/weights/retinaface-resnet50.onnx"
echo
echo "OK. Next: docker compose --profile idphoto up -d idphoto"
