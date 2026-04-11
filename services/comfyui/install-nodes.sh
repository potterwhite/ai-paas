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
# ComfyUI Custom Node Installer — Phase 3 Step 3.3
# Run via: docker exec ai_comfyui bash -c "$(cat services/comfyui/install-nodes.sh)"
# Or copy to workdir: sudo cp services/comfyui/install-nodes.sh data/comfyui_workdir/
#   then: docker exec ai_comfyui bash /root/ComfyUI/install-nodes.sh
#
# Nodes installed:
#   1. ComfyUI-Manager         — node management UI (install/update other nodes)
#   2. ComfyUI-CogVideoXWrapper — CogVideoX video generation nodes (kijai)
#   3. ComfyUI-VideoHelperSuite — video preview/save/load nodes
#
# After running: restart ai_comfyui to reload new nodes.
# ==============================================================================

set -e

NODES_DIR="/root/ComfyUI/custom_nodes"
cd "$NODES_DIR"

echo "=== Installing ComfyUI custom nodes ==="

# 1. ComfyUI Manager (must be first — enables GUI-based node management)
if [ ! -d "ComfyUI-Manager" ]; then
    echo "[1/3] Installing ComfyUI-Manager..."
    git clone --depth=1 https://github.com/ltdrdata/ComfyUI-Manager.git
    cd ComfyUI-Manager
    pip install -r requirements.txt --quiet
    cd ..
    echo "[1/3] Done: ComfyUI-Manager"
else
    echo "[1/3] Skipped: ComfyUI-Manager (already installed)"
fi

# 2. ComfyUI-CogVideoXWrapper — CogVideoX-5B video generation
if [ ! -d "ComfyUI-CogVideoXWrapper" ]; then
    echo "[2/3] Installing ComfyUI-CogVideoXWrapper..."
    git clone --depth=1 https://github.com/kijai/ComfyUI-CogVideoXWrapper.git
    cd ComfyUI-CogVideoXWrapper
    pip install -r requirements.txt --quiet
    cd ..
    echo "[2/3] Done: ComfyUI-CogVideoXWrapper"
else
    echo "[2/3] Skipped: ComfyUI-CogVideoXWrapper (already installed)"
fi

# 3. ComfyUI-VideoHelperSuite — video preview/save/load
if [ ! -d "ComfyUI-VideoHelperSuite" ]; then
    echo "[3/3] Installing ComfyUI-VideoHelperSuite..."
    git clone --depth=1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
    cd ComfyUI-VideoHelperSuite
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt --quiet
    fi
    cd ..
    echo "[3/3] Done: ComfyUI-VideoHelperSuite"
else
    echo "[3/3] Skipped: ComfyUI-VideoHelperSuite (already installed)"
fi

# =====================================================================
# INSTALL COMPLETE - ComfyUI-AdvancedLivePortrait
# =====================================================================
# This node was installed above. When running this script in the future,
# skip installation if the folder already exists.
# =====================================================================
# To install ComfyUI-AdvancedLivePortrait manually:
#   cd /root/ComfyUI/custom_nodes
#   git clone --depth=1 https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait.git
#   cd ComfyUI-AdvancedLivePortrait
#   pip install -r requirements.txt --quiet
#   Restart ai_comfyui container after installing
# =====================================================================

echo ""
echo "=== All nodes installed. Restart ai_comfyui to load them. ==="
echo "    Next step: run download-models.sh or check download progress"
