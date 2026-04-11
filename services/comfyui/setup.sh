#!/usr/bin/env bash
# ==============================================================================
# ComfyUI One-Shot Setup — nodes + all models
# Idempotent: safe to run multiple times, skips anything already present.
#
# Called automatically by pre-start.sh on container startup.
# Can also be run manually:
#   docker exec ai_comfyui bash /root/ComfyUI/setup.sh
#
# Models downloaded (total ~40 GB on first run):
#   CogVideoX-5B    ~21 GB  (video generation)
#   LivePortrait    ~300 MB (digital human)
#   SD 1.5          ~4 GB   (image generation, already present)
#   SDXL Base       ~7 GB   (image generation, higher quality)
#
# Uses HF_TOKEN env var if set (for gated models).
# ==============================================================================

set -e

MODELS_BASE="/root/ComfyUI/models"
NODES_DIR="/root/ComfyUI/custom_nodes"

# ── helpers ──────────────────────────────────────────────────────────────────

dl() {
    local url="$1" dest="$2" label="$3"
    mkdir -p "$(dirname "$dest")"
    if [ -f "$dest" ] && [ "$(stat -c%s "$dest" 2>/dev/null || echo 0)" -gt 1000000 ]; then
        echo "  [skip] $label ($(du -sh "$dest" 2>/dev/null | cut -f1))"
        return
    fi
    echo "  [download] $label..."
    local hf_args=()
    [ -n "${HF_TOKEN:-}" ] && hf_args=(--header "Authorization: Bearer $HF_TOKEN")
    wget -c --show-progress --progress=bar:force "${hf_args[@]}" -O "$dest" "$url" 2>&1 || true
    echo "  [done] $label ($(du -sh "$dest" 2>/dev/null | cut -f1))"
}

dl_small() {
    local url="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    [ -f "$dest" ] && return
    local hf_args=()
    [ -n "${HF_TOKEN:-}" ] && hf_args=(--header "Authorization: Bearer $HF_TOKEN")
    wget -q "${hf_args[@]}" -O "$dest" "$url" 2>/dev/null || true
}

install_node() {
    local name="$1" url="$2" req="${3:-requirements.txt}"
    if [ ! -d "$NODES_DIR/$name" ]; then
        echo "  [install] $name..."
        git clone --depth=1 "$url" "$NODES_DIR/$name"
        if [ -f "$NODES_DIR/$name/$req" ]; then
            pip install -r "$NODES_DIR/$name/$req" --quiet
        fi
        echo "  [done] $name"
    else
        echo "  [skip] $name (already installed)"
    fi
}

# ── 1. Custom nodes ───────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo " [1/5] Custom nodes"
echo "════════════════════════════════════════"
cd "$NODES_DIR"

install_node "ComfyUI-Manager" \
    "https://github.com/ltdrdata/ComfyUI-Manager.git"

install_node "ComfyUI-CogVideoXWrapper" \
    "https://github.com/kijai/ComfyUI-CogVideoXWrapper.git"

install_node "ComfyUI-VideoHelperSuite" \
    "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"

install_node "ComfyUI-AdvancedLivePortrait" \
    "https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait.git"

# ── 2. CogVideoX-5B (~21 GB) ─────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo " [2/5] CogVideoX-5B model (~21 GB)"
echo "════════════════════════════════════════"
HF="https://huggingface.co/THUDM/CogVideoX-5b/resolve/main"
CDIR="$MODELS_BASE/diffusion_models/cogvideox5b"

dl "$HF/transformer/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "$CDIR/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "CogVideoX transformer shard 1 (~10 GB)"
dl "$HF/transformer/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "$CDIR/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "CogVideoX transformer shard 2 (~1.2 GB)"
dl_small "$HF/transformer/config.json"                                    "$CDIR/config.json"
dl_small "$HF/transformer/diffusion_pytorch_model.safetensors.index.json" "$CDIR/diffusion_pytorch_model.safetensors.index.json"

dl "$HF/vae/diffusion_pytorch_model.safetensors" \
   "$MODELS_BASE/vae/cogvideox5b_vae.safetensors" \
   "CogVideoX VAE (~862 MB)"
dl_small "$HF/vae/config.json" "$MODELS_BASE/vae/cogvideox5b_vae_config.json"

T5DIR="$MODELS_BASE/text_encoders/t5xxl"
dl "$HF/text_encoder/model-00001-of-00002.safetensors" \
   "$T5DIR/model-00001-of-00002.safetensors" \
   "T5-XXL shard 1 (~5 GB)"
dl "$HF/text_encoder/model-00002-of-00002.safetensors" \
   "$T5DIR/model-00002-of-00002.safetensors" \
   "T5-XXL shard 2 (~4.5 GB)"
dl_small "$HF/text_encoder/config.json"                    "$T5DIR/config.json"
dl_small "$HF/text_encoder/model.safetensors.index.json"   "$T5DIR/model.safetensors.index.json"

for f in tokenizer_config.json spiece.model special_tokens_map.json added_tokens.json; do
    dl_small "$HF/tokenizer/$f" "$MODELS_BASE/tokenizers/t5xxl/$f"
done

# ── 3. LivePortrait (~350 MB) ─────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo " [3/5] LivePortrait models (~350 MB)"
echo "════════════════════════════════════════"
LP_DIR="$MODELS_BASE/liveportrait"
LP_HF="https://huggingface.co/KwaiVGI/LivePortrait/resolve/main/pretrained_weights"

mkdir -p "$LP_DIR"
for m in appearance_feature_extractor.pth motion_extractor.pth \
          spade_generator.pth stitching_retargeting_module.pth warping_module.pth; do
    dest="$LP_DIR/$m"
    if [ -f "$dest" ] && [ "$(stat -c%s "$dest" 2>/dev/null || echo 0)" -gt 1000 ]; then
        echo "  [skip] $m ($(du -sh "$dest" 2>/dev/null | cut -f1))"
    else
        echo "  [download] $m..."
        wget -c --show-progress --progress=bar:force -O "$dest" "$LP_HF/$m" 2>&1 || true
        echo "  [done] $m"
    fi
done

# ── 4. SD 1.5 (~4 GB, checkpoint) ────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo " [4/5] Stable Diffusion 1.5 (~4 GB)"
echo "════════════════════════════════════════"
SD15_DEST="$MODELS_BASE/checkpoints/v1-5-pruned-emaonly.safetensors"
dl "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors" \
   "$SD15_DEST" \
   "SD 1.5 checkpoint (~4 GB)"

# ── 5. SDXL Base (~7 GB, checkpoint) ─────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo " [5/5] SDXL Base 1.0 (~7 GB)"
echo "════════════════════════════════════════"
SDXL_DEST="$MODELS_BASE/checkpoints/sd_xl_base_1.0.safetensors"
dl "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors" \
   "$SDXL_DEST" \
   "SDXL Base 1.0 checkpoint (~7 GB)"

# SDXL VAE (required for correct colours in SDXL)
dl "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors" \
   "$MODELS_BASE/vae/sdxl_vae.safetensors" \
   "SDXL VAE fp16-fix (~160 MB)"

# ── done ──────────────────────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════"
echo " Setup complete"
echo "════════════════════════════════════════"
