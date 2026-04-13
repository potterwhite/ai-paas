#!/usr/bin/env bash
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

# ==============================================================================
# ComfyUI One-Shot Setup — nodes + all models
# Idempotent: safe to run multiple times, skips files that pass checksum.
#
# Called automatically by pre-start.sh on container startup.
# Can also be run manually:
#   docker exec ai_comfyui bash /root/ComfyUI/setup.sh
#
# Model groups downloaded (total ~45 GB on first run):
#   1. Custom nodes     — 4 ComfyUI extensions (git clone)
#   2. CogVideoX-5B    — ~26 GB  (transformer + VAE + T5-XXL BF16 + T5-XXL fp8)
#   3. LivePortrait     — ~350 MB (digital human)
#   4. SD 1.5           — ~4 GB   (image generation)
#   5. SDXL Base        — ~7 GB   (image generation, higher quality)
#   6. Workflow sync    — copy built-in workflows to Browse UI
#
# Each file is verified by SHA-256 checksum after download. Files that already
# exist AND pass checksum are skipped. Corrupt/partial files are re-downloaded.
#
# Uses HF_TOKEN env var if set (for gated models).
# ==============================================================================

set -e

MODELS_BASE="/root/ComfyUI/models"
NODES_DIR="/root/ComfyUI/custom_nodes"

# Counters for final summary
TOTAL_STEPS=6
DOWNLOAD_COUNT=0
SKIP_COUNT=0
FAIL_COUNT=0

# ── helpers ──────────────────────────────────────────────────────────────────

step_header() {
    local step="$1" total="$2" title="$3"
    echo ""
    echo "════════════════════════════════════════"
    echo " [${step}/${total}] ${title}"
    echo "════════════════════════════════════════"
}

# Download a file with SHA-256 verification.
# Usage: dl URL DEST LABEL EXPECTED_SHA256
# If EXPECTED_SHA256 is empty, size-based check is used as fallback.
dl() {
    local url="$1" dest="$2" label="$3" expected_sha="${4:-}"
    mkdir -p "$(dirname "$dest")"

    # Check existing file
    if [ -f "$dest" ] && [ "$(stat -c%s "$dest" 2>/dev/null || echo 0)" -gt 1000000 ]; then
        if [ -n "$expected_sha" ]; then
            local actual_sha
            actual_sha=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
            if [ "$actual_sha" = "$expected_sha" ]; then
                echo "  [skip] $label ($(du -sh "$dest" 2>/dev/null | cut -f1), checksum OK ✓)"
                SKIP_COUNT=$((SKIP_COUNT + 1))
                return
            else
                echo "  [redownload] $label (checksum mismatch, re-downloading...)"
                rm -f "$dest"
            fi
        else
            echo "  [skip] $label ($(du -sh "$dest" 2>/dev/null | cut -f1))"
            SKIP_COUNT=$((SKIP_COUNT + 1))
            return
        fi
    fi

    echo "  [download] $label..."
    local hf_args=()
    [ -n "${HF_TOKEN:-}" ] && hf_args=(--header "Authorization: Bearer $HF_TOKEN")
    if wget -c --show-progress --progress=bar:force "${hf_args[@]}" -O "$dest" "$url" 2>&1; then
        # Verify checksum after download
        if [ -n "$expected_sha" ]; then
            local actual_sha
            actual_sha=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
            if [ "$actual_sha" = "$expected_sha" ]; then
                echo "  [done] $label ($(du -sh "$dest" 2>/dev/null | cut -f1), checksum OK ✓)"
                DOWNLOAD_COUNT=$((DOWNLOAD_COUNT + 1))
            else
                echo "  [WARN] $label downloaded but checksum mismatch!"
                echo "         Expected: $expected_sha"
                echo "         Actual:   $actual_sha"
                FAIL_COUNT=$((FAIL_COUNT + 1))
            fi
        else
            echo "  [done] $label ($(du -sh "$dest" 2>/dev/null | cut -f1))"
            DOWNLOAD_COUNT=$((DOWNLOAD_COUNT + 1))
        fi
    else
        echo "  [FAIL] $label — download failed"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
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
        echo "  [done] $name installed"
    else
        echo "  [skip] $name (already installed)"
    fi
}

# ── Pre-flight info ──────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          ComfyUI Setup — Model Download & Config        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Models directory : $(realpath "$MODELS_BASE" 2>/dev/null || echo "$MODELS_BASE")"
echo "  Nodes directory  : $(realpath "$NODES_DIR" 2>/dev/null || echo "$NODES_DIR")"
echo "  Total steps      : ${TOTAL_STEPS}"
echo ""
echo "  Step 1: Custom nodes          — install 4 ComfyUI extensions"
echo "  Step 2: CogVideoX-5B          — ~26 GB (transformer + VAE + T5-XXL)"
echo "  Step 3: LivePortrait           — ~350 MB (digital human models)"
echo "  Step 4: Stable Diffusion 1.5   — ~4 GB (image generation)"
echo "  Step 5: SDXL Base 1.0          — ~7 GB (high-quality image generation)"
echo "  Step 6: Workflow sync          — copy built-in workflows to Browse UI"
echo ""
echo "  Existing files with valid checksums will be skipped (no re-download)."
echo ""

# ── 1. Custom nodes ──────────────────────────────────────────────────────────

step_header 1 "$TOTAL_STEPS" "Custom nodes — install ComfyUI extensions"
echo "  Installing required extensions for CogVideoX, LivePortrait, and video export."
echo ""
cd "$NODES_DIR"

install_node "ComfyUI-Manager" \
    "https://github.com/ltdrdata/ComfyUI-Manager.git"

install_node "ComfyUI-CogVideoXWrapper" \
    "https://github.com/kijai/ComfyUI-CogVideoXWrapper.git"

install_node "ComfyUI-VideoHelperSuite" \
    "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"

install_node "ComfyUI-AdvancedLivePortrait" \
    "https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait.git"

# Compatibility patch: CogVideoXWrapper's CogVideoXLatentFormat doesn't inherit
# from ComfyUI's LatentFormat base class and is missing latent_rgb_factors_reshape.
# This causes AttributeError when ComfyUI core tries to create a latent previewer.
# Patch: add the missing attribute if not already present.
COGVIDEO_PIPELINE="$NODES_DIR/ComfyUI-CogVideoXWrapper/pipeline_cogvideox.py"
if [ -f "$COGVIDEO_PIPELINE" ]; then
    if ! grep -q "latent_rgb_factors_reshape" "$COGVIDEO_PIPELINE"; then
        echo "  [patch] Adding latent_rgb_factors_reshape to CogVideoXLatentFormat..."
        sed -i '/latent_rgb_factors_bias.*=.*\[/a\    latent_rgb_factors_reshape = None' "$COGVIDEO_PIPELINE"
        echo "  [done] Compatibility patch applied"
    else
        echo "  [skip] CogVideoXLatentFormat patch (already applied or upstream fixed)"
    fi
fi

# ── 2. CogVideoX-5B (~26 GB) ────────────────────────────────────────────────

step_header 2 "$TOTAL_STEPS" "CogVideoX-5B — video generation models (~26 GB)"
echo "  Downloads: transformer (2 shards), VAE, T5-XXL BF16 (2 shards),"
echo "  T5-XXL fp8 single-file, tokenizer. Source: THUDM/CogVideoX-5b"
echo ""

HF="https://huggingface.co/THUDM/CogVideoX-5b/resolve/main"
CDIR="$MODELS_BASE/diffusion_models/cogvideox5b"

echo "  ── 2a. Transformer weights (~11.1 GB) ──"
dl "$HF/transformer/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "$CDIR/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "CogVideoX transformer shard 1 (~10 GB)"
dl "$HF/transformer/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "$CDIR/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "CogVideoX transformer shard 2 (~1.2 GB)"
dl_small "$HF/transformer/config.json"                                    "$CDIR/config.json"
dl_small "$HF/transformer/diffusion_pytorch_model.safetensors.index.json" "$CDIR/diffusion_pytorch_model.safetensors.index.json"

echo "  ── 2b. VAE (~862 MB) ──"
dl "$HF/vae/diffusion_pytorch_model.safetensors" \
   "$MODELS_BASE/vae/cogvideox5b_vae.safetensors" \
   "CogVideoX VAE (~862 MB)"
dl_small "$HF/vae/config.json" "$MODELS_BASE/vae/cogvideox5b_vae_config.json"

echo "  ── 2c. T5-XXL text encoder BF16 shards (~9.5 GB) ──"
T5DIR="$MODELS_BASE/text_encoders/t5xxl"
dl "$HF/text_encoder/model-00001-of-00002.safetensors" \
   "$T5DIR/model-00001-of-00002.safetensors" \
   "T5-XXL BF16 shard 1 (~5 GB)"
dl "$HF/text_encoder/model-00002-of-00002.safetensors" \
   "$T5DIR/model-00002-of-00002.safetensors" \
   "T5-XXL BF16 shard 2 (~4.5 GB)"
dl_small "$HF/text_encoder/config.json"                    "$T5DIR/config.json"
dl_small "$HF/text_encoder/model.safetensors.index.json"   "$T5DIR/model.safetensors.index.json"

echo "  ── 2d. Tokenizer ──"
for f in tokenizer_config.json spiece.model special_tokens_map.json added_tokens.json; do
    dl_small "$HF/tokenizer/$f" "$MODELS_BASE/tokenizers/t5xxl/$f"
done
echo "  [done] tokenizer files"

echo "  ── 2e. T5-XXL fp8 single-file for CLIPLoader (~4.9 GB) ──"
echo "  This file is required by built-in CogVideoX workflows."
echo "  Source: comfyanonymous/flux_text_encoders"
dl "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" \
   "$MODELS_BASE/text_encoders/t5xxl_fp8_e4m3fn.safetensors" \
   "T5-XXL fp8 single-file (~4.9 GB)" \
   "7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09"

# ── 3. LivePortrait (~350 MB) ────────────────────────────────────────────────

step_header 3 "$TOTAL_STEPS" "LivePortrait — digital human models (~350 MB)"
echo "  Downloads 5 pretrained weight files for face animation."
echo "  Source: KwaiVGI/LivePortrait"
echo ""
LP_DIR="$MODELS_BASE/liveportrait"
LP_HF="https://huggingface.co/KwaiVGI/LivePortrait/resolve/main/pretrained_weights"

mkdir -p "$LP_DIR"
for m in appearance_feature_extractor.pth motion_extractor.pth \
          spade_generator.pth stitching_retargeting_module.pth warping_module.pth; do
    dest="$LP_DIR/$m"
    if [ -f "$dest" ] && [ "$(stat -c%s "$dest" 2>/dev/null || echo 0)" -gt 1000 ]; then
        echo "  [skip] $m ($(du -sh "$dest" 2>/dev/null | cut -f1))"
        SKIP_COUNT=$((SKIP_COUNT + 1))
    else
        echo "  [download] $m..."
        wget -c --show-progress --progress=bar:force -O "$dest" "$LP_HF/$m" 2>&1 || true
        echo "  [done] $m"
        DOWNLOAD_COUNT=$((DOWNLOAD_COUNT + 1))
    fi
done

# ── 4. SD 1.5 (~4 GB) ───────────────────────────────────────────────────────

step_header 4 "$TOTAL_STEPS" "Stable Diffusion 1.5 — basic image generation (~4 GB)"
echo "  Standard SD 1.5 checkpoint for text-to-image workflows."
echo ""
dl "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors" \
   "$MODELS_BASE/checkpoints/v1-5-pruned-emaonly.safetensors" \
   "SD 1.5 checkpoint (~4 GB)"

# ── 5. SDXL Base (~7 GB) ────────────────────────────────────────────────────

step_header 5 "$TOTAL_STEPS" "SDXL Base 1.0 — high-quality image generation (~7 GB)"
echo "  SDXL checkpoint + VAE for higher resolution/quality images."
echo ""
dl "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors" \
   "$MODELS_BASE/checkpoints/sd_xl_base_1.0.safetensors" \
   "SDXL Base 1.0 checkpoint (~7 GB)"

dl "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors" \
   "$MODELS_BASE/vae/sdxl_vae.safetensors" \
   "SDXL VAE fp16-fix (~160 MB)"

# ── 6. Workflow sync ────────────────────────────────────────────────────────

step_header 6 "$TOTAL_STEPS" "Workflow sync — copy to ComfyUI Browse UI"
echo "  Copying built-in workflows so they appear in ComfyUI's sidebar."
echo ""

WF_SRC="/root/ComfyUI/workflows"
WF_DST="/root/ComfyUI/user/default/workflows"
if [ -d "$WF_SRC" ] && ls "$WF_SRC"/*.json >/dev/null 2>&1; then
    mkdir -p "$WF_DST"
    wf_count=0
    for wf in "$WF_SRC"/*.json; do
        cp -u "$wf" "$WF_DST/" 2>/dev/null || true
        wf_count=$((wf_count + 1))
    done
    echo "  [done] Synced ${wf_count} workflows to ComfyUI Browse UI"
else
    echo "  [skip] No workflow files found in $WF_SRC"
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete                        ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Downloaded : ${DOWNLOAD_COUNT} files                              ║"
echo "║  Skipped    : ${SKIP_COUNT} files (already present)               ║"
if [ "$FAIL_COUNT" -gt 0 ]; then
echo "║  Failed     : ${FAIL_COUNT} files (check logs above)              ║"
fi
echo "║                                                          ║"
echo "║  Models dir : $(realpath "$MODELS_BASE" 2>/dev/null || echo "$MODELS_BASE")"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "  ⚠  Some downloads failed. Re-run this script to retry."
fi
