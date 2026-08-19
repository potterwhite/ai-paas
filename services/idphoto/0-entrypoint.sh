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
# Step 0 — container entrypoint. Docker runs this; you never call it by hand.
# (Numbered 0 because it happens before steps 1-3, and it is the one script
#  here that is not a manual command.)
#
# It answers exactly one question: are the pip dependencies installed?
#
#   missing -> idle and print the one command to run. The container stays up
#              so you can exec into it and install.
#   present -> hand straight over to 3-run.sh.
#
# Packages live in the container's writable layer, which survives `docker
# restart` and the Router's Docker-SDK start/stop. It does NOT survive
# `--build` / `--force-recreate` / `docker rm` — but that is the deliberate
# "throw it away and start over" reset described in README.md, and the pip
# cache is a host bind mount so redoing step 2 takes seconds.
#
# Net effect: step 2 is a one-time step. Every ordinary start — restart, or a
# Router GPU-mode switch — goes straight to the WebUI.
# ============================================================
set -euo pipefail

# Probe the two heaviest third-party imports rather than a marker file: a
# marker can outlive the packages it claims are present (e.g. a half-finished
# install), and these two are exactly what 3-run.sh needs to get to a page.
if ! python3 -c 'import gradio, onnxruntime' >/dev/null 2>&1; then
    echo "============================================================"
    echo "[0-entrypoint] Python dependencies are not installed."
    echo "[0-entrypoint] Run this once:"
    echo
    echo "    docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh"
    echo
    echo "[0-entrypoint] Then:  docker restart ai_idphoto"
    echo "[0-entrypoint] Idling until then."
    echo "============================================================"
    exec sleep infinity
fi

echo "[0-entrypoint] Dependencies present — starting the WebUI via 3-run.sh"
exec bash /opt/idphoto/3-run.sh
