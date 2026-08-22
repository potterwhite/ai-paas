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
# Model groups downloaded (total ~40 GiB on first run):
#   1. Custom nodes     — 5 ComfyUI extensions (git clone)
#   2. CogVideoX-5B     — ~24.6 GiB (transformer + VAE + T5-XXL BF16 + T5-XXL fp8)
#   3. LivePortrait     — ~504 MiB  (digital human)
#   4. SD 1.5           — ~4.0 GiB  (image generation)
#   5. SDXL Base        — ~6.8 GiB  (image generation, higher quality)
#   6. Workflow sync    — copy built-in workflows to Browse UI
#   7. (reserved — see step numbering)
#   8. MuseTalk         — ~4.0 GiB  (audio-driven lip sync: weights + whisper + vae + dwpose)
#
# Sizes are the real byte counts from the HuggingFace tree API, in the same
# binary units libfileinfo_human prints, so a label and its [done] line agree.
# They used to be hand-written guesses and several were off by 2x -- Whisper
# tiny was labelled ~72 MB and arrives as 144.1MiB, SDXL VAE ~160 MB against
# 319.1MiB -- which made a correct download look like the wrong file.
#
# Each file is verified by SHA-256 checksum after download. Files that already
# exist AND pass checksum are skipped. Corrupt/partial files are re-downloaded.
#
# Uses HF_TOKEN env var if set (for gated models).
# ==============================================================================

set -e

MODELS_BASE="/root/ComfyUI/models"
NODES_DIR="/root/ComfyUI/custom_nodes"

TOTAL_STEPS=8

# Node install failures. Downloads are tallied by libs/fetch.sh, but nodes are
# not its concern, so step 1 keeps its own count and the summary prints both.
NODE_FAIL_COUNT=0

# ── shared libraries ─────────────────────────────────────────────────────────
# Downloading is not implemented here. libs/ owns it, split three ways:
#   libs/http.sh      aria2c invocation, resume state, control files
#   libs/fileinfo.sh  size and sha256 of a file on disk
#   libs/fetch.sh     whether a file needs downloading, and the running tally
#
# All three are sourced here rather than sourcing each other, so this is the
# only place that has to know where libs/ ended up. There are two possibilities
# and both are just "next to this script":
#   /root/ComfyUI/libs   bind-mounted alongside setup.sh (normal case)
#   /tmp/libs            docker-cp'd by scripts/data_models.sh when the
#                        bind-mount did not apply and it fell back to /tmp
# The third form is running from a host checkout, where libs/ sits at the repo
# root two levels up.
SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBS_DIR=""
for _candidate in "${SETUP_DIR}/libs" "${SETUP_DIR}/../../libs"; do
    if [ -f "${_candidate}/fetch.sh" ]; then
        LIBS_DIR="$(cd "${_candidate}" && pwd)"
        break
    fi
done
if [ -z "${LIBS_DIR}" ]; then
    echo "ERROR: cannot find libs/ (looked next to ${SETUP_DIR} and two levels up)." >&2
    echo "       The comfyui service must bind-mount it:" >&2
    echo "         - ./libs:/root/ComfyUI/libs:ro" >&2
    exit 1
fi

# shellcheck source=../../libs/http.sh
source "${LIBS_DIR}/http.sh"
# shellcheck source=../../libs/fileinfo.sh
source "${LIBS_DIR}/fileinfo.sh"
# shellcheck source=../../libs/fetch.sh
source "${LIBS_DIR}/fetch.sh"

# Checks that the three libs resolved and that aria2c exists. Aborts here rather
# than failing on the first transfer, which on a 26 GB run could be minutes in.
libfetch_require || exit 1

# ── pip configuration ──────────────────────────────────────────────────────────
# Retry on transient network blips so one failed request doesn't abort the setup.
# See https://pip.pypa.io/en/stable/topics/configuration/#environment-variables
export PIP_RETRIES=5
export PIP_TIMEOUT=60

# ── helpers ──────────────────────────────────────────────────────────────────

step_header() {
    local step="$1" total="$2" title="$3"
    echo ""
    echo "════════════════════════════════════════"
    echo " [${step}/${total}] ${title}"
    echo "════════════════════════════════════════"
}

# ── custom nodes: two transports, git first ──────────────────────────────────
#
# git is preferred but unreliable against github.com from this host, so it gets
# a bounded number of tries before the aria2c tarball takes over. These are
# policy knobs, kept together so they are easy to retune.
GIT_ATTEMPTS=3
GIT_TIMEOUT=180        # hard ceiling per attempt, catches a hang after transfer
GIT_MIN_SPEED=32768    # abort an attempt that falls below 32 KB/s ...
GIT_MIN_SPEED_TIME=20  # ... for this long (same limit libhttp gives aria2c)

# Transport 1 -- git clone.
# Keeps .git, which is what lets ComfyUI-Manager report a node's version and
# update it in place. The downside is a single HTTP connection: measured
# 252 KiB/s against github.com from this host, and one 15 MB repo sat at 2.1 MB
# for 13 minutes without advancing. Which repo stalls is luck, not size --
# ComfyUI-Manager (15 MB) clones fine while AdvancedLivePortrait (15 MB) never
# has. So each attempt is bounded twice: by throughput and by wall clock.
#
# GIT_TERMINAL_PROMPT=0 makes git fail instead of asking for credentials. A URL
# that 404s looks like a private repo to git, so it prompts for a username --
# and setup.sh runs under `docker exec -it`, so that prompt finds a real TTY and
# waits forever instead of reporting the bad URL.
node_clone_git() {
    local url="$1" dir="$2" attempt

    echo "  [git] transport = git clone --depth=1"
    echo "        why   : keeps .git, so ComfyUI-Manager can show the version and update this node"
    echo "        watch : one connection only, stalls at random here — each attempt is time- and speed-bounded"

    for attempt in $(seq 1 "$GIT_ATTEMPTS"); do
        echo "  [git] attempt ${attempt}/${GIT_ATTEMPTS} — cloning ${url}"
        if GIT_TERMINAL_PROMPT=0 timeout "$GIT_TIMEOUT" \
            git -c "http.lowSpeedLimit=${GIT_MIN_SPEED}" \
                -c "http.lowSpeedTime=${GIT_MIN_SPEED_TIME}" \
                clone --depth=1 "$url" "$dir"; then
            return 0
        fi
        # Leave nothing behind that a later run would read as installed.
        rm -rf "$dir"
        echo "  [git] attempt ${attempt}/${GIT_ATTEMPTS} failed (stalled, timed out, or refused) — partial clone discarded"
    done

    echo "  [git] giving up after ${GIT_ATTEMPTS} attempts"
    return 1
}

# Transport 2 -- tarball over aria2c.
# api.github.com/repos/OWNER/REPO/tarball redirects to codeload with the default
# branch already resolved, so there is no main-vs-master guessing. aria2c pulls
# it over 16 connections (measured 3.5 MiB/s, 14x git's rate here) and there is
# no index-pack stage to die in. The cost is no .git: the node still loads,
# because ComfyUI only imports the package and looks for __init__.py, but
# ComfyUI-Manager cannot version or update it.
node_fetch_tarball() {
    local url="$1" dir="$2"
    local tarball="/tmp/node-$(basename "$dir").tar.gz"

    # Same repo, different endpoint: strip the clone URL down to OWNER/REPO.
    local slug="${url#https://github.com/}"
    slug="${slug%.git}"

    echo "  [aria2c] transport = tarball via aria2c -x16"
    echo "           why   : 16 connections and no index-pack stage — measured 14x faster than git here"
    echo "           watch : no .git, so ComfyUI-Manager shows this node as unknown version;"
    echo "                   to update it, delete the directory and re-run this script"

    rm -f "$tarball" "${tarball}.aria2"

    # Retried for the same reason libfetch_model is: this network is flaky enough
    # that a single aria2c run gets cut off by its own low-speed guard. Measured
    # here -- one run stopped at 2.0 MB of 15 MB, the next three completed.
    # --continue=true means a retry resumes from the .aria2 control file rather
    # than starting over.
    local attempt
    for attempt in 1 2 3; do
        echo "  [aria2c] attempt ${attempt}/3 — downloading tarball for ${slug}"
        libhttp_get "https://api.github.com/repos/${slug}/tarball" "$tarball" quiet && break
        if [ "$attempt" = 3 ]; then
            echo "  [aria2c] transfer failed 3 times"
            libhttp_discard "$tarball"
            return 1
        fi
        echo "  [aria2c] attempt ${attempt}/3 stalled — resuming"
    done

    # --strip-components=1 drops the OWNER-REPO-SHA/ prefix GitHub adds. There is
    # no published checksum for a tarball built on the fly, so gzip's own CRC is
    # the integrity check: a truncated transfer fails here rather than unpacking
    # a half-node that ComfyUI would then try to import.
    mkdir -p "$dir"
    if ! tar -xzf "$tarball" -C "$dir" --strip-components=1; then
        echo "  [aria2c] archive is corrupt or truncated — discarded"
        rm -rf "$dir"
        libhttp_discard "$tarball"
        return 1
    fi
    libhttp_discard "$tarball"
    echo "  [aria2c] extracted into ${dir}"
}

# Install a ComfyUI custom node.
# Usage: install_node NAME GIT_URL [REQUIREMENTS_FILE]
#
# Tries git, falls back to the aria2c tarball, then installs requirements. Pass
# "" as the third argument to skip dependency installation (note ${3-...}, not
# ${3:-...}, so an explicitly empty value survives).
#
# "Installed" means __init__.py is present, because that is what ComfyUI needs:
# it imports each custom_nodes subdirectory as a Python package. Checking for the
# directory instead -- what this used to do -- counts an interrupted clone as
# installed, since git creates the directory and .git before checking out any
# files. ComfyUI-AdvancedLivePortrait had been in exactly that state: a directory
# holding nothing but .git, with no HEAD, reported as "[skip] (already
# installed)" on every run while the node was unusable.
install_node() {
    local name="$1" url="$2" req="${3-requirements.txt}"
    local dir="$NODES_DIR/$name"
    local transport

    if [ -f "$dir/__init__.py" ]; then
        echo "  [skip] $name (already installed)"
        return 0
    fi

    # Anything present without __init__.py is a failed install, and git clone
    # refuses a non-empty target, so clear it out first.
    if [ -e "$dir" ]; then
        echo "  [repair] $name — incomplete install, starting over"
        rm -rf "$dir"
    else
        echo "  [install] $name"
    fi

    if node_clone_git "$url" "$dir"; then
        transport="git"
    elif node_fetch_tarball "$url" "$dir"; then
        transport="aria2c tarball"
    else
        rm -rf "$dir"
        echo "  [FAIL] $name — both git and aria2c failed"
        NODE_FAIL_COUNT=$((NODE_FAIL_COUNT + 1))
        return 1
    fi

    if [ ! -f "$dir/__init__.py" ]; then
        echo "  [FAIL] $name — fetched via ${transport} but has no __init__.py; ComfyUI cannot load it"
        NODE_FAIL_COUNT=$((NODE_FAIL_COUNT + 1))
        return 1
    fi

    if [ -n "$req" ] && [ -f "$dir/$req" ]; then
        pip install -r "$dir/$req" --quiet
    fi
    echo "  [done] $name installed (transport: ${transport})"
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
echo "  Step 1: Custom nodes          — install 5 ComfyUI extensions"
echo "  Step 2: CogVideoX-5B           — ~24.6 GiB (transformer + VAE + T5-XXL)"
echo "  Step 3: LivePortrait           — ~504 MiB (5 weights + face detector)"
echo "  Step 4: Stable Diffusion 1.5   — ~4.0 GiB (image generation)"
echo "  Step 5: SDXL Base 1.0          — ~6.8 GiB (high-quality image generation)"
echo "  Step 6: Workflow sync          — copy built-in workflows to Browse UI"
echo "  Step 7: (skipped — reserved numbering)"
echo "  Step 8: MuseTalk               — ~4.0 GiB (audio lip sync: weights + whisper + vae + dwpose)"
echo ""
echo "  Existing files with valid checksums will be skipped (no re-download)."
echo ""

# ── 1. Custom nodes ──────────────────────────────────────────────────────────

step_header 1 "$TOTAL_STEPS" "Custom nodes — install ComfyUI extensions"
echo "  Installing required extensions for CogVideoX, LivePortrait, and video export."
echo ""
cd "$NODES_DIR"

install_node "ComfyUI-Manager" \
    "https://github.com/ltdrdata/ComfyUI-Manager.git" || true

install_node "ComfyUI-CogVideoXWrapper" \
    "https://github.com/kijai/ComfyUI-CogVideoXWrapper.git" || true

install_node "ComfyUI-VideoHelperSuite" \
    "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git" || true

install_node "ComfyUI-AdvancedLivePortrait" \
    "https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait.git" || true

# Third argument is empty on purpose: MuseTalk's dependencies are installed by
# the block below, which pins versions and works around packages that cannot be
# built in an isolated environment. Letting install_node run its requirements.txt
# would undo that.
install_node "ComfyUI-MuseTalk" \
    "https://github.com/chaojie/ComfyUI-MuseTalk.git" "" || true

# MuseTalk Python dependencies — checked on EVERY startup because Python packages
# live in /usr/local (not in the persistent volume) and are lost on container rebuild.
echo "  [deps] Checking MuseTalk Python dependencies..."

# -- chumpy: setup.py does `import pip` which fails in Python 3.13+ isolated build env
if ! python3.13 -c "import chumpy" 2>/dev/null; then
    echo "  [install] chumpy (--no-build-isolation workaround for Python 3.13)..."
    pip install chumpy --no-build-isolation --quiet
    echo "  [done] chumpy"
fi

# -- mmcv 2.2.0: setup.py uses locals()['__version__'] pattern broken in Python 3.13
#    Build with MMCV_WITH_OPS=0 (no CUDA ops needed for MuseTalk's mmpose usage)
if ! python3.13 -c "import mmcv" 2>/dev/null; then
    echo "  [install] mmcv 2.2.0 (patching setup.py locals() bug for Python 3.13)..."
    MMCV_TMP=$(mktemp -d)
    curl -sL "https://files.pythonhosted.org/packages/e9/a2/57a733e7e84985a8a0e3101dfb8170fc9db92435c16afad253069ae3f9df/mmcv-2.2.0.tar.gz" \
        | tar -xz -C "$MMCV_TMP"
    python3.13 -c "
path = '${MMCV_TMP}/mmcv-2.2.0/setup.py'
old = '''def get_version():
    version_file = 'mmcv/version.py'
    with open(version_file, encoding='utf-8') as f:
        exec(compile(f.read(), version_file, 'exec'))
    return locals()['__version__']'''
new = '''def get_version():
    version_file = 'mmcv/version.py'
    with open(version_file, encoding='utf-8') as f:
        code = f.read()
    g = {}
    exec(compile(code, version_file, 'exec'), g)
    return g['__version__']'''
with open(path, 'r') as f:
    content = f.read()
content = content.replace(old, new)
content = content.replace('except DistributionNotFound:', 'except (DistributionNotFound, Exception):')
with open(path, 'w') as f:
    f.write(content)
"
    cd "${MMCV_TMP}/mmcv-2.2.0" && MMCV_WITH_OPS=0 python3.13 -m pip install . --no-build-isolation --quiet
    cd "$NODES_DIR"
    rm -rf "$MMCV_TMP"
    echo "  [done] mmcv"
fi

# -- xtcocotools 1.14.3: same locals() bug in setup.py
if ! python3.13 -c "import xtcocotools" 2>/dev/null; then
    echo "  [install] xtcocotools 1.14.3 (patching setup.py locals() bug for Python 3.13)..."
    XTCOCO_TMP=$(mktemp -d)
    curl -sL "https://files.pythonhosted.org/packages/6c/79/ff409182e7c6b49299cbd7ee9ac8a14bb7174827b8c0616248fd897cf5c0/xtcocotools-1.14.3.tar.gz" \
        | tar -xz -C "$XTCOCO_TMP"
    python3.13 -c "
path = '${XTCOCO_TMP}/xtcocotools-1.14.3/setup.py'
old = '''def get_version():
    with open(version_file, 'r') as f:
        exec(compile(f.read(), version_file, 'exec'))
    import sys
    # return short version for sdist
    if 'sdist' in sys.argv or 'bdist_wheel' in sys.argv:
        return locals()['short_version']
    else:
        return locals()['__version__']'''
new = '''def get_version():
    with open(version_file, 'r') as f:
        code = f.read()
    g = {}
    exec(compile(code, version_file, 'exec'), g)
    import sys
    if 'sdist' in sys.argv or 'bdist_wheel' in sys.argv:
        return g.get('short_version', g['__version__'])
    else:
        return g['__version__']'''
with open(path, 'r') as f:
    content = f.read()
with open(path, 'w') as f:
    f.write(content.replace(old, new))
"
    cd "${XTCOCO_TMP}/xtcocotools-1.14.3" && python3.13 -m pip install . --no-build-isolation --quiet
    cd "$NODES_DIR"
    rm -rf "$XTCOCO_TMP"
    echo "  [done] xtcocotools"
fi

# -- mmpose --no-deps (avoids re-triggering broken xtcocotools/mmcv from its dep resolver)
if ! python3.13 -c "import mmpose" 2>/dev/null; then
    echo "  [install] mmpose + helpers..."
    pip install mmpose --no-deps --quiet
    pip install json-tricks munkres --quiet
    echo "  [done] mmpose"
fi

# -- mmdet: required by mmpose at import time (rtmo_head.py)
#    mmdet 3.1.0 has a hardcoded mmcv_maximum_version='2.1.0' check that rejects mmcv 2.2.0.
#    We install --no-deps and patch the version gate to allow mmcv<2.3.0.
if ! python3.13 -c "import mmdet" 2>/dev/null; then
    echo "  [install] mmdet 3.1.0..."
    pip install "mmdet==3.1.0" --no-deps --quiet
fi
# NOTE: locate __init__.py via find_spec, NOT `import mmdet` — importing it here
#       trips the very version assertion we are about to patch, and under `set -e`
#       a failing command substitution aborts the whole script.
MMDET_INIT=$(python3.13 -c "import importlib.util as u; s = u.find_spec('mmdet'); print(s.origin if s else '')" 2>/dev/null || true)
if [ -n "$MMDET_INIT" ] && grep -q "mmcv_maximum_version = '2.1.0'" "$MMDET_INIT" 2>/dev/null; then
    echo "  [patch] mmdet: widening mmcv_maximum_version to 2.3.0..."
    sed -i "s/mmcv_maximum_version = '2.1.0'/mmcv_maximum_version = '2.3.0'/" "$MMDET_INIT"
    echo "  [done] mmdet patched"
fi

# -- Remaining safe MuseTalk runtime deps
for pkg in accelerate soundfile ffmpeg-python pydub more-itertools face-alignment; do
    mod=$(echo "$pkg" | tr '-' '_' | sed 's/ffmpeg_python/ffmpeg/;s/face_alignment/face_alignment/')
    if ! python3.13 -c "import $mod" 2>/dev/null; then
        echo "  [install] $pkg..."
        pip install "$pkg" --quiet
    fi
done
echo "  [done] MuseTalk deps OK"

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

# ── 2. CogVideoX-5B (~24.6 GiB) ─────────────────────────────────────────────

step_header 2 "$TOTAL_STEPS" "CogVideoX-5B — video generation models (~24.6 GiB)"
echo "  Downloads: transformer (2 shards), VAE, T5-XXL BF16 (2 shards),"
echo "  T5-XXL fp8 single-file, tokenizer. Source: THUDM/CogVideoX-5b"
echo ""

HF="https://huggingface.co/THUDM/CogVideoX-5b/resolve/main"
CDIR="$MODELS_BASE/diffusion_models/cogvideox5b"

# Checksums below come from the HuggingFace tree API, which reports lfs.oid for
# every LFS file and for these repos that oid is the sha256 of the content:
#   curl -s https://huggingface.co/api/models/<repo>/tree/main/<dir>
# THUDM/CogVideoX-5b now redirects to zai-org/CogVideoX-5b after a rename, so
# the API was queried under the new name; same objects, same digests.
#
# `|| true` on each call keeps `set -e` from aborting the run at the first bad
# file, so the remaining models still download and the summary still prints. The
# failure is not swallowed: libfetch_model has already printed [FAIL] and
# incremented LIBFETCH_FAILED by the time control returns here.

echo "  ── 2a. Transformer weights (~10.4 GiB) ──"
libfetch_model "$HF/transformer/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "$CDIR/diffusion_pytorch_model-00001-of-00002.safetensors" \
   "CogVideoX transformer shard 1 (~9.2 GiB)" \
   "b7101be7e75631130cdf4a63ad798452bdce29716aaa47829e882dd384c398bf" || true
libfetch_model "$HF/transformer/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "$CDIR/diffusion_pytorch_model-00002-of-00002.safetensors" \
   "CogVideoX transformer shard 2 (~1.1 GiB)" \
   "ebe6c0e34a52c89f8ea8032a3a8a278a9ff1880dc70e1e6f3b840bcfd0396647" || true
libfetch_config "$HF/transformer/config.json"                                    "$CDIR/config.json"
libfetch_config "$HF/transformer/diffusion_pytorch_model.safetensors.index.json" "$CDIR/diffusion_pytorch_model.safetensors.index.json"

echo "  ── 2b. VAE (~822 MiB) ──"
libfetch_model "$HF/vae/diffusion_pytorch_model.safetensors" \
   "$MODELS_BASE/vae/cogvideox5b_vae.safetensors" \
   "CogVideoX VAE (~822 MiB)" \
   "a410e48d988c8224cef392b68db0654485cfd41f345f4a3a81d3e6b765bb995e" || true
libfetch_config "$HF/vae/config.json" "$MODELS_BASE/vae/cogvideox5b_vae_config.json"

echo "  ── 2c. T5-XXL text encoder BF16 shards (~8.9 GiB) ──"
T5DIR="$MODELS_BASE/text_encoders/t5xxl"
libfetch_model "$HF/text_encoder/model-00001-of-00002.safetensors" \
   "$T5DIR/model-00001-of-00002.safetensors" \
   "T5-XXL BF16 shard 1 (~4.7 GiB)" \
   "9162b8ae9152e7a8e3bbebc535c8692783f50aec8cd3bb8ef6a751c432dd6392" || true
libfetch_model "$HF/text_encoder/model-00002-of-00002.safetensors" \
   "$T5DIR/model-00002-of-00002.safetensors" \
   "T5-XXL BF16 shard 2 (~4.2 GiB)" \
   "d3edef29693d52402b1cc7c362f031e052f2e9482ed0c765c6351950434349b0" || true
libfetch_config "$HF/text_encoder/config.json"                    "$T5DIR/config.json"
libfetch_config "$HF/text_encoder/model.safetensors.index.json"   "$T5DIR/model.safetensors.index.json"

echo "  ── 2d. Tokenizer ──"
for f in tokenizer_config.json spiece.model special_tokens_map.json added_tokens.json; do
    libfetch_config "$HF/tokenizer/$f" "$MODELS_BASE/tokenizers/t5xxl/$f"
done
echo "  [done] tokenizer files"

echo "  ── 2e. T5-XXL fp8 single-file for CLIPLoader (~4.6 GiB) ──"
echo "  This file is required by built-in CogVideoX workflows."
echo "  Source: comfyanonymous/flux_text_encoders"
libfetch_model "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" \
   "$MODELS_BASE/text_encoders/t5xxl_fp8_e4m3fn.safetensors" \
   "T5-XXL fp8 single-file (~4.6 GiB)" \
   "7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09" || true

# ── 3. LivePortrait (~504 MiB) ───────────────────────────────────────────────

step_header 3 "$TOTAL_STEPS" "LivePortrait — digital human models (~504 MiB)"
echo "  Downloads 5 pretrained weight files for face animation."
echo "  Source: KlingTeam/LivePortrait (formerly KwaiVGI)"
echo ""

# Layout is not ours to choose -- ComfyUI-AdvancedLivePortrait/nodes.py builds the
# paths itself, and it wants two subdirectories:
#   os.path.join(get_model_dir("liveportrait"), "base_models",        <name>.pth)
#   os.path.join(get_model_dir("liveportrait"), "retargeting_models", <name>.pth)
# which is also how the weights are laid out on HuggingFace.
#
# Pre-fetching matters here beyond convenience. When a .pth is missing the node
# downloads a substitute itself, with `requests` in 1 KB blocks over a single
# connection -- the exact pattern that stalls on this network. Same for
# ultralytics/face_yolov8n.pt, which it fetches on first face detection.
#
# The repo was renamed KwaiVGI -> KlingTeam and the weights were never under
# `pretrained_weights`, which is what this used to request: every file 404'd and
# the failure was invisible, because the old wget call ended in `|| true` and the
# next line printed "[done]" unconditionally. Five zero-length files on disk were
# reported as five successful downloads.
LP_DIR="$MODELS_BASE/liveportrait"
LP_HF="https://huggingface.co/KlingTeam/LivePortrait/resolve/main/liveportrait"

libfetch_model "$LP_HF/base_models/appearance_feature_extractor.pth" \
   "$LP_DIR/base_models/appearance_feature_extractor.pth" \
   "LivePortrait appearance_feature_extractor" \
   "5279bb8654293dbdf327030b397f107237dd9212fb11dd75b83dfb635211ceb5" || true

libfetch_model "$LP_HF/base_models/motion_extractor.pth" \
   "$LP_DIR/base_models/motion_extractor.pth" \
   "LivePortrait motion_extractor" \
   "251e6a94ad667a1d0c69526d292677165110ef7f0cf0f6d199f0e414e8aa0ca5" || true

libfetch_model "$LP_HF/base_models/spade_generator.pth" \
   "$LP_DIR/base_models/spade_generator.pth" \
   "LivePortrait spade_generator" \
   "4780afc7909a9f84e24c01d73b31a555ef651521a1fe3b2429bd04534d992aee" || true

libfetch_model "$LP_HF/base_models/warping_module.pth" \
   "$LP_DIR/base_models/warping_module.pth" \
   "LivePortrait warping_module" \
   "2f61a6f265fe344f14132364859a78bdbbc2068577170693da57fb96d636e282" || true

libfetch_model "$LP_HF/retargeting_models/stitching_retargeting_module.pth" \
   "$LP_DIR/retargeting_models/stitching_retargeting_module.pth" \
   "LivePortrait stitching_retargeting_module" \
   "3652d5a3f95099141a56986aaddec92fadf0a73c87a20fac9a2c07c32b28b611" || true

# Face detector the node pulls on first use, fetched here so it does not.
libfetch_model "https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8n.pt" \
   "$MODELS_BASE/ultralytics/face_yolov8n.pt" \
   "LivePortrait face detector face_yolov8n (~6 MiB)" \
   "70b640f8f60b1cf0dcc72f30caf3da9495eb2fb6509da48c53374ad6806e6a9c" || true

# ── 4. SD 1.5 (~4.0 GiB) ────────────────────────────────────────────────────

step_header 4 "$TOTAL_STEPS" "Stable Diffusion 1.5 — basic image generation (~4.0 GiB)"
echo "  Standard SD 1.5 checkpoint for text-to-image workflows."
echo ""
libfetch_model "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors" \
   "$MODELS_BASE/checkpoints/v1-5-pruned-emaonly.safetensors" \
   "SD 1.5 checkpoint (~4.0 GiB)" \
   "6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa" || true

# ── 5. SDXL Base (~6.8 GiB) ─────────────────────────────────────────────────

step_header 5 "$TOTAL_STEPS" "SDXL Base 1.0 — high-quality image generation (~6.8 GiB)"
echo "  SDXL checkpoint + VAE for higher resolution/quality images."
echo ""
libfetch_model "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors" \
   "$MODELS_BASE/checkpoints/sd_xl_base_1.0.safetensors" \
   "SDXL Base 1.0 checkpoint (~6.5 GiB)" \
   "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b" || true

libfetch_model "https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors" \
   "$MODELS_BASE/vae/sdxl_vae.safetensors" \
   "SDXL VAE fp16-fix (~319 MiB)" \
   "235745af8d86bf4a4c1b5b4f529868b37019a10f7c0b2e79ad0abca3a22bc6e1" || true

# ── 6. Workflow sync ────────────────────────────────────────────────────────

step_header 6 "$TOTAL_STEPS" "Workflow sync — copy to ComfyUI Browse UI"
echo "  Copying built-in workflows so they appear in ComfyUI's sidebar."
echo "  NOTE: Always overwrites to ensure latest changes are visible."
echo ""

WF_SRC="/root/ComfyUI/workflows"
WF_DST="/root/ComfyUI/user/default/workflows"
if [ -d "$WF_SRC" ] && ls "$WF_SRC"/*.json >/dev/null 2>&1; then
    mkdir -p "$WF_DST"
    wf_count=0
    for wf in "$WF_SRC"/*.json; do
        cp -f "$wf" "$WF_DST/" 2>/dev/null || true
        wf_count=$((wf_count + 1))
    done
    echo "  [done] Synced ${wf_count} workflows to ComfyUI Browse UI"
else
    echo "  [skip] No workflow files found in $WF_SRC"
fi

# ── 7. (reserved) ───────────────────────────────────────────────────────────

step_header 7 "$TOTAL_STEPS" "Reserved — placeholder step"
echo "  (no action)"

# ── 8. MuseTalk (~4.0 GiB) ───────────────────────────────────────────────────

step_header 8 "$TOTAL_STEPS" "MuseTalk — audio-driven lip sync models (~4.0 GiB)"
echo "  Downloads: MuseTalk weights, Whisper tiny, SD-VAE-FT-MSE, DWPose."
echo "  All placed under: models/diffusers/TMElyralab/MuseTalk/"
echo ""

MT_DIR="$MODELS_BASE/diffusers/TMElyralab/MuseTalk"
MT_HF="https://huggingface.co/TMElyralab/MuseTalk/resolve/main"

echo "  ── 8a. MuseTalk UNet weights (~3.2 GiB) ──"
libfetch_config "$MT_HF/musetalk/musetalk.json" "$MT_DIR/musetalk/musetalk.json"
libfetch_model "$MT_HF/musetalk/pytorch_model.bin" \
   "$MT_DIR/musetalk/pytorch_model.bin" \
   "MuseTalk UNet weights (~3.2 GiB)" \
   "0ee7d5ea03ea75d8dca50ea7a76df791e90633687a135c4a69393abfc0475ffe" || true

echo "  ── 8b. Whisper tiny (~144 MiB) ──"
libfetch_model "https://huggingface.co/openai/whisper-tiny/resolve/main/pytorch_model.bin" \
   "$MT_DIR/whisper/tiny.pt" \
   "Whisper tiny (~144 MiB)" \
   "9607f98a2b22d9e229ae43c52ecea79dcede9e0c5cfae67e8da6eda86d8aac1d" || true

echo "  ── 8c. SD-VAE-FT-MSE (~319 MiB) ──"
libfetch_config "https://huggingface.co/stabilityai/sd-vae-ft-mse/resolve/main/config.json" \
   "$MT_DIR/sd-vae-ft-mse/config.json"
libfetch_model "https://huggingface.co/stabilityai/sd-vae-ft-mse/resolve/main/diffusion_pytorch_model.bin" \
   "$MT_DIR/sd-vae-ft-mse/diffusion_pytorch_model.bin" \
   "SD-VAE-FT-MSE weights (~319 MiB)" \
   "1b4889b6b1d4ce7ae320a02dedaeff1780ad77d415ea0d744b476155c6377ddc" || true

echo "  ── 8d. DWPose (~388 MiB) ──"
libfetch_model "https://huggingface.co/yzd-v/DWPose/resolve/main/dw-ll_ucoco_384.pth" \
   "$MT_DIR/dwpose/dw-ll_ucoco_384.pth" \
   "DWPose dw-ll_ucoco_384 (~388 MiB)" \
   "0d9408b13cd863c4e95a149dd31232f88f2a12aa6cf8964ed74d7d97748c7a07" || true

# ── Summary ──────────────────────────────────────────────────────────────────

TOTAL_FAILED=$((LIBFETCH_FAILED + NODE_FAIL_COUNT))

if [ "$TOTAL_FAILED" -gt 0 ]; then
    BANNER_TITLE="║                 Setup INCOMPLETE                         ║"
else
    BANNER_TITLE="║                    Setup Complete                        ║"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "$BANNER_TITLE"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Downloaded : ${LIBFETCH_DOWNLOADED} files                              ║"
echo "║  Skipped    : ${LIBFETCH_SKIPPED} files (already present)               ║"
if [ "$LIBFETCH_FAILED" -gt 0 ]; then
echo "║  Failed     : ${LIBFETCH_FAILED} files (check logs above)              ║"
fi
if [ "$NODE_FAIL_COUNT" -gt 0 ]; then
echo "║  Nodes failed: ${NODE_FAIL_COUNT} (check logs above)                   ║"
fi
echo "║                                                          ║"
echo "║  Models dir : $(realpath "$MODELS_BASE" 2>/dev/null || echo "$MODELS_BASE")"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Exit non-zero on any failure, so the caller does not report success.
# Every libfetch_model call above ends in `|| true` -- that is deliberate, one
# bad URL must not abort the remaining downloads -- which means the script's
# own exit status has to be set here from the counters.
if [ "$TOTAL_FAILED" -gt 0 ]; then
    echo "  ⚠  ${TOTAL_FAILED} item(s) failed. Re-run this script to retry;"
    echo "     partial downloads resume from where they stopped."
    exit 1
fi

exit 0
