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

# The plain onnxruntime wheel and onnxruntime-gpu unpack into the same
# onnxruntime/ package directory, and onnxruntime_pybind11_state...so is a
# single filename — whichever installs last wins. mtcnn-runtime declares
# `Requires: onnxruntime`, so pip drags the CPU wheel in during the install
# below regardless of what requirements.txt asks for, and it usually lands
# last. So the fix cannot be a check before the install; it has to be a
# repair after it.
echo "==> installing $REQ"
pip install -r "$REQ"

# Purge BOTH, then reinstall only the GPU one. Removing just the CPU wheel
# would delete files its RECORD shares with onnxruntime-gpu and leave that
# one broken.
ORT_PIN=$(grep -E '^onnxruntime-gpu' "$REQ")
echo
echo "==> repairing onnxruntime: purging both wheels, reinstalling $ORT_PIN"
pip uninstall -y onnxruntime onnxruntime-gpu 2>/dev/null || true
pip install "$ORT_PIN"

# Belt and braces: if anything reintroduced the CPU wheel, the python check
# below would still pass on a lucky install order, so assert at pip level too.
if pip show onnxruntime >/dev/null 2>&1; then
    echo "FAIL: plain onnxruntime is installed alongside onnxruntime-gpu."
    echo "      They collide on onnxruntime_pybind11_state...so — last writer wins."
    exit 1
fi

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

# app.py:78 passes show_api= to Blocks.launch(), removed in gradio 6.
import gradio
if int(gradio.__version__.split(".")[0]) >= 5:
    print(f"FAIL: gradio {gradio.__version__} — app.py needs 4.x (show_api).")
    ok = False
else:
    print(f"gradio {gradio.__version__} OK")

# The next two only fail on the first HTTP request, long after this script
# would have said OK, so assert them here.

# gradio/routes.py:432 uses TemplateResponse(name, context), the positional
# order starlette 1.0 removed. Symptom is TypeError: unhashable type: 'dict'.
import starlette
if int(starlette.__version__.split(".")[0]) >= 1:
    print(f"FAIL: starlette {starlette.__version__} — gradio 4.x needs <1.0 "
          "(old TemplateResponse argument order).")
    ok = False
else:
    print(f"starlette {starlette.__version__} OK")

# pydantic >=2.11 emits `additionalProperties: true` for FileData.meta, and
# gradio_client 1.3.0 recurses into that bool. Assert the behaviour rather
# than the version number — this is the exact call GET / makes.
import pydantic
from gradio.data_classes import FileData
import gradio_client.utils as gc_utils
try:
    gc_utils.json_schema_to_python_type(FileData.model_json_schema())
    print(f"pydantic {pydantic.VERSION} OK (FileData schema round-trips)")
except TypeError as e:
    print(f"FAIL: pydantic {pydantic.VERSION} breaks gradio_client schema "
          f"parsing ({e}). Every page load would 500.")
    ok = False

# Touches the whole beauty plugin chain, which is where the gradio
# dependency hides. If this imports, the API path is clear.
from hivision import IDCreator  # noqa: F401
print("hivision import chain OK")

sys.exit(0 if ok else 1)
PY

echo
echo "OK. Next: docker restart ai_idphoto   (0-entrypoint.sh then starts the WebUI)"
