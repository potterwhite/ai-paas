#!/usr/bin/env bash
# ============================================================
# Step 2 — install dependencies. Runs INSIDE the container:
#
#     docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh
#
# This is the "blow it away and start over" button. Delete the container,
# recreate it, run this once. Everything pip installs lives in the
# container layer and dies with it; the clone, the weights and the pip
# cache are bind-mounted from the host and survive.
#
# Idempotent, and fast on a second run because the pip cache is warm.
# ============================================================
set -euo pipefail

REQ=/opt/idphoto/requirements.txt

[ -f "$REQ" ] || { echo "ERROR: $REQ not found — is services/idphoto mounted at /opt/idphoto?"; exit 1; }
[ -f /workspace/deploy_api.py ] || { echo "ERROR: /workspace is not the clone. See README.md."; exit 1; }

# The plain onnxruntime wheel and onnxruntime-gpu install into the same
# `onnxruntime` package directory. If the CPU one is already there — from
# a previous `pip install -r requirements.txt` against the upstream file —
# pip will not replace it, and get_device() keeps reporting CPU.
if pip show onnxruntime >/dev/null 2>&1; then
    echo "==> removing CPU-only onnxruntime (it shadows onnxruntime-gpu)"
    pip uninstall -y onnxruntime
fi

echo "==> installing $REQ"
pip install -r "$REQ"

# ---------- verify ----------
# Both defects this file works around are silent, so asserting is the
# only way to know the install is actually good.
echo
echo "==> verifying"

# hivision is not installed as a package — it is imported from the clone,
# so the check has to run with /workspace as the working directory.
cd /workspace

python - <<'PY'
import sys
import onnxruntime as ort

dev = ort.get_device()
providers = ort.get_available_providers()
print(f"onnxruntime {ort.__version__}  device={dev}")
print(f"providers: {providers}")

ok = True
if dev != "GPU":
    print("FAIL: get_device() is not GPU — inference would silently run on CPU.")
    ok = False
if "CUDAExecutionProvider" not in providers:
    print("FAIL: CUDAExecutionProvider missing.")
    ok = False

from PIL import Image  # noqa: F401  — upstream forgets to declare this
print("Pillow OK")

# Touches the whole beauty plugin chain, which is where the gradio
# dependency hides. If this imports, the API path is clear.
from hivision import IDCreator  # noqa: F401
print("hivision import chain OK")

sys.exit(0 if ok else 1)
PY

echo
echo "OK. Next: docker exec -it ai_idphoto bash /opt/idphoto/3-run.sh"
