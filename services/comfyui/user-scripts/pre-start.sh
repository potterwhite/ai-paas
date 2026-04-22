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
# ComfyUI pre-start hook — auto-install nodes + download models
# Called by yanwk/comfyui-boot entrypoint BEFORE ComfyUI starts.
#
# This file is mounted read-only into /root/user-scripts/pre-start.sh via
# docker-compose.yml. On first boot (or after a git clone + docker compose up),
# it ensures all custom nodes and model weights are in place.
#
# Idempotent: skips anything already downloaded or installed.
# ==============================================================================

set -e

SETUP_SCRIPT="/root/ComfyUI/setup.sh"

# setup.sh is bind-mounted from services/comfyui/setup.sh
if [ ! -f "$SETUP_SCRIPT" ]; then
    echo "[pre-start] ERROR: setup.sh not found at $SETUP_SCRIPT" >&2
    echo "[pre-start] Check docker-compose.yml volume mounts for ai_comfyui." >&2
    exit 1
fi

echo "[pre-start] Running ComfyUI auto-setup (nodes + models)..."
bash "$SETUP_SCRIPT"
echo "[pre-start] Setup complete — handing off to ComfyUI."
echo "[pre-start] Syncing built-in workflows to Browse UI..."
WF_SRC="/root/ComfyUI/workflows"
WF_DST="/root/ComfyUI/user/default/workflows"
if [ -d "$WF_SRC" ] && ls "$WF_SRC"/*.json >/dev/null 2>&1; then
    mkdir -p "$WF_DST"
    for wf in "$WF_SRC"/*.json; do
        cp -f "$wf" "$WF_DST/" 2>/dev/null || true
    done
    echo "[pre-start] Workflows synced."
fi

echo "[pre-start] Syncing workflow default images to ComfyUI input dir..."
INPUT_DIR="/root/ComfyUI/input"
mkdir -p "$INPUT_DIR"
for img in "$WF_SRC"/*.png "$WF_SRC"/*.jpg "$WF_SRC"/*.jpeg "$WF_SRC"/*.webp; do
    [ -f "$img" ] && cp -f "$img" "$INPUT_DIR/" 2>/dev/null || true
done
echo "[pre-start] Default images synced."
