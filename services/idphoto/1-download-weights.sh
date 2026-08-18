#!/usr/bin/env bash
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

SRC="${1:-/Development/docker/docker-volumes/ai_paas/idphoto/src}"

if [ ! -f "$SRC/deploy_api.py" ]; then
    echo "ERROR: $SRC is not a HivisionIDPhotos clone (no deploy_api.py)."
    echo "Pass the path as \$1, or clone it there first. See README.md."
    exit 1
fi

command -v aria2c >/dev/null || { echo "ERROR: aria2c not installed."; exit 1; }

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
    # -o takes a bare filename, so -d carries the directory.
    aria2c -x16 -s16 -k1M --continue=true --allow-overwrite=true \
           -d "$dir" -o "$name" "$url"

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
