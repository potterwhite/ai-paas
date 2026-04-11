#!/usr/bin/env bash
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
