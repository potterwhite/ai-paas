#!/bin/bash
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

# Core functions and variables for ai-paas controller

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Directory definitions
DATA_DIR="${SCRIPT_DIR}/data"

# Load MODELS_PATH from .env if available, otherwise use default
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/.env"
fi
MODELS_DIR="${MODELS_PATH:-${SCRIPT_DIR}/models}"

# Find docker-compose.yml file
DOCKER_COMPOSE_FILE=""
if [[ -f "${SCRIPT_DIR}/docker-compose.yml" ]]; then
    DOCKER_COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
elif [[ -f "${SCRIPT_DIR}/configs/docker-compose.yml" ]]; then
    DOCKER_COMPOSE_FILE="${SCRIPT_DIR}/configs/docker-compose.yml"
else
    echo "ERROR: docker-compose.yml not found in ${SCRIPT_DIR} or ${SCRIPT_DIR}/configs/"
    exit 1
fi

# Helper functions for output
log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

# Confirmation prompt
confirm() {
    local prompt="$1"
    read -p "$prompt [y/N]: " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# Check if running in correct directory and docker-compose file exists
check_dir() {
    if [[ -z "${DOCKER_COMPOSE_FILE}" ]] || [[ ! -f "${DOCKER_COMPOSE_FILE}" ]]; then
        log_error "Cannot find docker-compose.yml. Please run from ai-paas project root."
        exit 1
    fi
}

# ── GPU registry ─────────────────────────────────────────────────────────────
# config/gpu-registry.json is the single source of truth for GPU container
# names, their compose profiles and which of them are card-exclusive. Router
# and ai_webapp read the same file — see its "_doc" block.
GPU_REGISTRY_FILE="${SCRIPT_DIR}/config/gpu-registry.json"

# Run a jq filter over the registry. Fails loudly rather than falling back to a
# guess: a missing container name here would make `stop-all` quietly leave a
# GPU container running, which is the failure this registry exists to prevent.
gpu_registry() {
    if [[ ! -f "${GPU_REGISTRY_FILE}" ]]; then
        log_error "GPU registry not found: ${GPU_REGISTRY_FILE}"
        exit 1
    fi
    if ! command -v jq >/dev/null 2>&1; then
        log_error "jq is required to read ${GPU_REGISTRY_FILE} (apt-get install jq)"
        exit 1
    fi
    jq -r "$1" "${GPU_REGISTRY_FILE}"
}

# jq prelude: registry entries only, skipping "_"-prefixed documentation keys.
_GPU_ENTRIES='.containers | to_entries[] | select(.key | startswith("_") | not) | .value'

# Compose profile names of every profile-gated GPU container, as `--profile x`
# flags. Needed for `down`: compose ignores profile-gated services otherwise.
gpu_profile_flags() {
    local p
    for p in $(gpu_registry "${_GPU_ENTRIES} | select(.profile != null) | .profile"); do
        printf -- '--profile %s ' "$p"
    done
}

# Compose service keys of the card-exclusive containers. Exactly one of these
# may hold the GPU at a time, so they get created but never bulk-started.
gpu_exclusive_services() {
    gpu_registry "${_GPU_ENTRIES} | select(.exclusive) | .compose_service"
}