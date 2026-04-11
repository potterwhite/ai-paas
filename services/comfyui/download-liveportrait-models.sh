#!/usr/bin/env bash
# ==============================================================================
# LivePortrait Model Downloader — Phase 3 Step 3.4
# Downloads pretrained models for ComfyUI-AdvancedLivePortrait from HuggingFace.
#
# Run this INSIDE the container after installing the node:
#   docker exec ai_comfyui bash -c "$(cat services/comfyui/download-liveportrait-models.sh)"
#
# Or on host (models go to custom_nodes/models):
#   cd /home/james/ai-paas
#   bash services/comfyui/download-liveportrait-models.sh
#
# Models: LivePortrait pretrained weights from KwaiVGI (~300 MB total)
#   - appearance_feature.pth
#   - motion_extractor.pth
#   - spade_generator.pth
#   - stitching_retargeting_module.pth
#   - warping_module.pth
#   - landmark_model.pth / face-analysis models
#
# The ComfyUI-AdvancedLivePortrait node can also auto-download on first use.
# This script pre-caches them to avoid delays during generation.
# ==============================================================================

set -e

# Detect running environment
LIVEPORTRAIT_DIR=""
if [ -d "/root/ComfyUI" ]; then
    LIVEPORTRAIT_DIR="/root/ComfyUI/custom_nodes/ComfyUI-AdvancedLivePortrait/models/liveportrait"
    echo "Running INSIDE container — writing to $LIVEPORTRAIT_DIR"
elif [ -d "services/comfyui" ]; then
    LIVEPORTRAIT_DIR="data/comfyui_workdir/custom_nodes/ComfyUI-AdvancedLivePortrait/models/liveportrait"
    echo "Running on HOST — writing to $LIVEPORTRAIT_DIR"
else
    echo "ERROR: Cannot detect environment."
    echo "Ensure ComfyUI-AdvancedLivePortrait node is already installed."
    exit 1
fi

mkdir -p "$LIVEPORTRAIT_DIR"

HF="https://huggingface.co/KwaiVGI/LivePortrait/resolve/main"

# LivePortrait pretrained models (all .pth files in pretrained_weights/)
MODELS="appearance_feature.pth motion_extractor.pth spade_generator.pth stitching_retargeting_module.pth warping_module.pth"

echo ""
echo "=== Downloading LivePortrait models (~300 MB total) ==="
echo ""

for model in $MODELS; do
    dest="$LIVEPORTRAIT_DIR/$model"
    if [ -f "$dest" ] && [ "$(stat -c%s "$dest" 2>/dev/null || echo 0)" -gt 1000 ]; then
        echo "  [skip] $model ($(du -sh "$dest" | cut -f1))"
        continue
    fi
    echo "  [download] $model..."
    wget -q -c --show-progress -O "$dest" "$HF/pretrained_weights/$model" 2>&1 | tail -1 || echo "  [WARN] $model download failed"
    echo "  [done] $model: $(du -sh "$dest" | cut -f1)"
done

echo ""
echo "=== Download complete ==="
echo ""
echo "Next steps:"
echo "  1. Restart ai_comfyui: docker compose restart ai_comfyui"
echo "  2. Open http://192.168.0.19:8188"
echo "  3. Drag workflow: services/comfyui/workflows/liveportrait_basic.json"
echo "  4. Upload a portrait photo and a driving video, then Queue Prompt"
