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

# Stop ai-paas services (except external ones like harbor)
stop_services() {
    log_info "Stopping ai-paas services..."
    cd "${SCRIPT_DIR}"
    docker compose -f "${DOCKER_COMPOSE_FILE}" down
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
    log_info "Services started."
}

# Restart ai-paas services
restart_services() {
    stop_services
    sleep 2
    start_services
}

# Stop ALL services including profile-gated ones (comfyui, cookies, etc.)
stop_all_services() {
    log_info "Stopping ALL ai-paas services (including profile services)..."
    cd "${SCRIPT_DIR}"
    docker compose -f "${DOCKER_COMPOSE_FILE}" \
        --profile comfyui \
        --profile cookies \
        down
    log_info "All services stopped."
}

# Start ALL services including profile-gated ones (comfyui, cookies, etc.)
start_all_services() {
    log_info "Starting ALL ai-paas services (including profile services)..."
    cd "${SCRIPT_DIR}"
    docker compose -f "${DOCKER_COMPOSE_FILE}" \
        --profile comfyui \
        --profile cookies \
        up -d
    log_info "All services started."
}

# Restart ALL services including profile-gated ones (comfyui, cookies, etc.)
restart_all_services() {
    stop_all_services
    sleep 2
    start_all_services
}