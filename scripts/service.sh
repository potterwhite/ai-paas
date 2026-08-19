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

# Service management functions for ai-paas controller

# Source core functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/scripts/core.sh"

# Show all running ai-paas containers
show_containers() {
    log_info "ai-paas container status:"
    docker ps --filter "name=ai_" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# Create every GPU-exclusive container without starting it.
#
# The Router start/stops containers through the Docker SDK, which only works on
# containers that already exist — and they are profile-gated precisely so that
# compose does not start them (one card, one holder). `up --no-start` bridges
# that: compose creates them, the Router decides which one runs. Cheap no-op
# when they already exist.
create_gpu_containers() {
    cd "${SCRIPT_DIR}"
    # shellcheck disable=SC2046  # word splitting is how the flags are passed
    docker compose -f "${DOCKER_COMPOSE_FILE}" \
        $(gpu_profile_flags) \
        up --no-start $(gpu_exclusive_services | tr '\n' ' ')
}

# Stop ai-paas services (except external ones like harbor)
#
# `stop`, not `down`: down REMOVES containers, and idphoto's pip packages live in
# its container layer — so a down here would force a re-run of 2-install.sh on
# every platform restart. Stopping keeps the containers (and their installs).
#
# The --profile flags are NOT optional: compose skips profile-gated services
# entirely without them, so ai_comfyui / ai_idphoto would survive a "stop" and
# keep holding the GPU.
stop_services() {
    log_info "Stopping ai-paas services..."
    cd "${SCRIPT_DIR}"
    # shellcheck disable=SC2046
    docker compose -f "${DOCKER_COMPOSE_FILE}" $(gpu_profile_flags) stop
    log_info "Services stopped."
}

# Start ai-paas services
start_services() {
    # Check if vLLM model exists before starting
    local vllm_model_path="${MODELS_DIR}/qwen2.5-32b-instruct-awq"
    if [[ ! -d "${vllm_model_path}" || ! -f "${vllm_model_path}/config.json" ]]; then
        log_error "vLLM model not found or incomplete: ${vllm_model_path}"
        log_error "Please download the model first:"
        log_error "  1. Install git-lfs: sudo apt-get install git-lfs"
        log_error "  2. Run: git lfs install"
        log_error "  3. Run: git clone https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-AWQ ${vllm_model_path}"
        log_error ""
        log_error "Or use Python with huggingface_hub:"
        log_error "  pip install huggingface_hub"
        log_error "  python -c \"from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen2.5-32B-Instruct-AWQ', local_dir='${vllm_model_path}')\""
        return 1
    fi

    log_info "Starting ai-paas services..."
    cd "${SCRIPT_DIR}"
    docker compose -f "${DOCKER_COMPOSE_FILE}" up -d
    # Router-scheduled GPU containers (comfyui, idphoto) must exist before the
    # /gpu panel can start them; COMPOSE_PROFILES above only covers the vLLM.
    create_gpu_containers
    log_info "Services started."
}

# Restart ai-paas services
restart_services() {
    stop_services
    sleep 2
    start_services
}

# Stop ALL services including profile-gated ones (comfyui, idphoto, cookies, etc.)
#
# `stop`, not `down` — see stop_services() for why (idphoto's install lives in the
# container layer). GPU profiles come from config/gpu-registry.json.
stop_all_services() {
    log_info "Stopping ALL ai-paas services (including profile services)..."
    cd "${SCRIPT_DIR}"
    # shellcheck disable=SC2046  # word splitting is how the flags are passed
    docker compose -f "${DOCKER_COMPOSE_FILE}" \
        $(gpu_profile_flags) \
        --profile cookies \
        stop
    log_info "All services stopped."
}

# Start ALL services that are safe to run together, and CREATE the rest.
#
# One GPU, one holder: the card-exclusive containers (every vllm-*, comfyui,
# idphoto) must never be bulk-started — doing so is what the old
# `--profile comfyui up -d` did, booting ComfyUI next to a vLLM and putting two
# processes on one 24 GB card. They are created with --no-start instead, which
# is all the Router needs: it start/stops existing containers via the Docker SDK
# and enforces exclusivity itself. Pick one afterwards with:
#     curl -X POST :4000/gpu/mode -d '{"mode":"llm"}'      # or idphoto/comfyui
# or the /gpu panel in ai_webapp. COMPOSE_PROFILES in .env still decides which
# vLLM (if any) comes up automatically.
start_all_services() {
    log_info "Creating GPU-exclusive containers (not started — Router schedules them)..."
    create_gpu_containers

    log_info "Starting always-on ai-paas services..."
    docker compose -f "${DOCKER_COMPOSE_FILE}" --profile cookies up -d

    log_info "All services started."
    log_info "GPU is idle by default — choose a mode via the /gpu panel or:"
    log_info "  curl -X POST http://localhost:4000/gpu/mode -H 'Content-Type: application/json' \\"
    log_info "       -H \"Authorization: Bearer \${LITELLM_MASTER_KEY}\" -d '{\"mode\":\"llm\"}'"
}

# Restart ALL services including profile-gated ones (comfyui, idphoto, cookies, etc.)
restart_all_services() {
    stop_all_services
    sleep 2
    start_all_services
}