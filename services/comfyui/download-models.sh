#!/usr/bin/env bash
# ==============================================================================
# CogVideoX-5B Model Downloader — Phase 3 Step 3.3
# Downloads all required model files from HuggingFace (THUDM/CogVideoX-5b).
#
# Run this on the HOST (not inside container):
#   cd /home/james/ai-paas
#   bash services/comfyui/download-models.sh
#
# Or run INSIDE the container (writes directly to model paths):
#   docker exec ai_comfyui bash -c "$(cat services/comfyui/download-models.sh)"
#
# Models downloaded (total ~21 GB):
#   diffusion_models/cogvideox5b/  — Transformer weights (2 shards, ~11 GB)
#   vae/cogvideox5b_vae.safetensors — VAE encoder/decoder (~862 MB)
#   text_encoders/t5xxl/           — T5-XXL text encoder (2 shards, ~9.5 GB)
#   tokenizers/t5xxl/              — T5 tokenizer files
#
# Inside container paths map to host $MODELS_PATH/comfyui/ (set in .env)
# ==============================================================================

set -e

# Detect if running inside container or on host
if [ -d "/root/ComfyUI/models" ]; then
    MODELS_BASE="/root/ComfyUI/models"
    echo "Running INSIDE container — writing to $MODELS_BASE"
else
    # Resolve MODELS_BASE from MODELS_PATH env var, or fall back to repo-relative path
    SCRIPT_HOST_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
    if [[ -f "${SCRIPT_HOST_DIR}/.env" ]]; then
        # shellcheck disable=SC1091
        source "${SCRIPT_HOST_DIR}/.env"
    fi
    MODELS_BASE="${MODELS_PATH:-${SCRIPT_HOST_DIR}/models}/comfyui"
    echo "Running on HOST — writing to $MODELS_BASE"
fi

HF_BASE="https://huggingface.co/THUDM/CogVideoX-5b/resolve/main"

dl() {
    local url="$1"
    local dest="$2"
    local label="$3"
    mkdir -p "$(dirname "$dest")"
    if [ -f "$dest" ] && [ "$(stat -c%s "$dest")" -gt 1000000 ]; then
        echo "  [skip] $label (already exists: $(du -sh "$dest" | cut -f1))"
        return
    fi
    echo "  [download] $label..."
    wget -q -c --show-progress -O "$dest" "$url" 2>&1 | tail -1 || true
    echo "  [done] $label: $(du -sh "$dest" | cut -f1)"
}

dl_small() {
    local url="$1"
    local dest="$2"
    mkdir -p "$(dirname "$dest")"
    [ -f "$dest" ] || wget -q -O "$dest" "$url" 2>/dev/null
}

echo ""
echo "=== Downloading CogVideoX-5B model files (~21 GB total) ==="
echo ""

echo "[1/4] Transformer weights (~11.1 GB)..."
dl "$HF_BASE/transformer/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "$MODELS_BASE/diffusion_models/cogvideox5b/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "transformer shard 1 (9.93 GB)"
dl "$HF_BASE/transformer/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "$MODELS_BASE/diffusion_models/cogvideox5b/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "transformer shard 2 (1.22 GB)"
dl_small "$HF_BASE/transformer/config.json" \
         "$MODELS_BASE/diffusion_models/cogvideox5b/config.json"
dl_small "$HF_BASE/transformer/diffusion_pytorch_model.safetensors.index.json" \
         "$MODELS_BASE/diffusion_models/cogvideox5b/diffusion_pytorch_model.safetensors.index.json"

echo ""
echo "[2/4] VAE (~862 MB)..."
dl "$HF_BASE/vae/diffusion_pytorch_model.safetensors" \
   "$MODELS_BASE/vae/cogvideox5b_vae.safetensors" \
   "VAE (862 MB)"
dl_small "$HF_BASE/vae/config.json" \
         "$MODELS_BASE/vae/cogvideox5b_vae_config.json"

echo ""
echo "[3/4] T5-XXL text encoder (~9.5 GB)..."
dl "$HF_BASE/text_encoder/model-00001-of-00002.safetensors" \
   "$MODELS_BASE/text_encoders/t5xxl/model-00001-of-00002.safetensors" \
   "T5 shard 1 (4.99 GB)"
dl "$HF_BASE/text_encoder/model-00002-of-00002.safetensors" \
   "$MODELS_BASE/text_encoders/t5xxl/model-00002-of-00002.safetensors" \
   "T5 shard 2 (4.53 GB)"
dl_small "$HF_BASE/text_encoder/config.json" \
         "$MODELS_BASE/text_encoders/t5xxl/config.json"
dl_small "$HF_BASE/text_encoder/model.safetensors.index.json" \
         "$MODELS_BASE/text_encoders/t5xxl/model.safetensors.index.json"

echo ""
echo "[4/4] Tokenizer files..."
for f in tokenizer_config.json spiece.model special_tokens_map.json added_tokens.json; do
    dl_small "$HF_BASE/tokenizer/$f" "$MODELS_BASE/tokenizers/t5xxl/$f"
done
echo "  [done] tokenizer"

echo ""
echo "=== Download complete. Summary: ==="
du -sh "$MODELS_BASE/diffusion_models/cogvideox5b/" \
       "$MODELS_BASE/vae/cogvideox5b_vae.safetensors" \
       "$MODELS_BASE/text_encoders/t5xxl/" 2>/dev/null
echo ""
echo "Next steps:"
echo "  1. Restart ai_comfyui: docker compose restart comfyui"
echo "  2. Open http://192.168.0.19:8188"
echo "  3. Load workflow: services/comfyui/workflows/cogvideox5b_basic.json"
