#!/usr/bin/env bash
# ============================================================
# Start the HivisionIDPhotos API inside the sandbox container.
#
# Bind-mounted from services/idphoto/run.sh, so you can read and edit
# it on the host at any time — it is not baked into the image.
#
# The inference device comes from IDPHOTO_DEVICE (set in .env, passed
# in by docker-compose). HivisionIDPhotos has no --device flag: it
# calls onnxruntime.get_device() and then falls back to CPU if the CUDA
# provider fails to initialise. So we drive it via CUDA_VISIBLE_DEVICES.
#
#   cpu (default) — CUDA hidden -> CPUExecutionProvider.
#                   Image quality is IDENTICAL to gpu; only slower.
#   gpu           — requires every ai_vllm_* container to be STOPPED:
#                   birefnet-v1-lite wants ~16 GB VRAM and vLLM holds ~22 GB
#                   of this 24 GB card, so they cannot coexist.
# ============================================================
set -euo pipefail

cd /workspace

if [ ! -f deploy_api.py ]; then
    echo "[run.sh] deploy_api.py not found in /workspace."
    echo "[run.sh] Clone the repo into data/idphoto/src first — see services/idphoto/README.md"
    exit 1
fi

case "${IDPHOTO_DEVICE:-cpu}" in
    gpu)
        export CUDA_VISIBLE_DEVICES=0
        echo "[run.sh] device=gpu — make sure ai_vllm_* are stopped (birefnet needs ~16 GB VRAM)"
        ;;
    *)
        export CUDA_VISIBLE_DEVICES=""
        echo "[run.sh] device=cpu — the CUDA init warning printed below is EXPECTED and harmless"
        ;;
esac

# deploy_api.py binds 0.0.0.0:8080. Not published to the host: ai_webapp
# reaches it over the internal network as http://ai_idphoto:8080.
exec python deploy_api.py
