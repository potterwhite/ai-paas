#!/usr/bin/env bash
# ============================================================
# Step 3 — start the WebUI. Runs INSIDE the container:
#
#     docker exec -it ai_idphoto bash /opt/idphoto/3-run.sh
#
# Then open http://<host>:7860
#
# app.py is the Gradio WebUI. deploy_api.py is a separate, UI-less FastAPI
# server (7 POST endpoints, no pages) — that one is for the ai_webapp
# integration later, and is not what you want in a browser.
#
# app.py defaults to --host 127.0.0.1, which inside a container means
# nothing outside can reach it. 0.0.0.0 is required.
#
# GPU only. Every ai_vllm_* container must be STOPPED: birefnet-v1-lite
# wants ~16 GB VRAM and vLLM holds ~22 GB of this 24 GB card.
# ============================================================
set -euo pipefail

cd /workspace

if [ ! -f app.py ]; then
    echo "[3-run.sh] app.py not found in /workspace."
    echo "[3-run.sh] Clone the repo into \$MODELS_PATH/idphoto/src first — see README.md"
    exit 1
fi

# app.py builds its model dropdown from whatever .onnx files exist, and
# raises if the directory is empty. Better to say why here than to let it
# fail with a message about a directory the reader has not seen.
if ! ls hivision/creator/weights/*.onnx >/dev/null 2>&1; then
    echo "[3-run.sh] No weights in hivision/creator/weights/."
    echo "[3-run.sh] Run 1-download-weights.sh on the host first."
    exit 1
fi

exec python app.py --host 0.0.0.0 --port 7860
