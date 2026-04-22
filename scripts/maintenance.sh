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

# Maintenance functions for ai-paas controller

# Source core functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/scripts/core.sh"

# Repair directory permissions - can fix specific directories or default to data/
fix_permissions() {
    check_dir

    # If a directory is specified as first argument, use it; otherwise use DATA_DIR
    local target_dir="${1:-${DATA_DIR}}"
    
    if [[ -n "$target_dir" ]]; then
        log_info "Fixing permissions for directory: $target_dir"
        
        if [[ -d "$target_dir" ]]; then
            # Use 2>/dev/null || true to suppress permission errors and continue
            sudo chown -R "$(id -u):$(id -g)" "$target_dir" 2>/dev/null || true
            sudo find "$target_dir" -type d -exec chmod 755 {} \; 2>/dev/null || true
            sudo find "$target_dir" -type f -exec chmod 644 {} \; 2>/dev/null || true
            log_info "Permissions fixed for: $target_dir"
        else
            log_warn "Directory not found: $target_dir"
            return 1
        fi
    else
        log_warn "No directory specified for permission fixing"
        return 1
    fi
}

# Reset router database only
reset_router() {
    check_dir

    log_warn "This will delete the router SQLite database and Redis data."
    log_warn "All routing history and task queues will be lost."

    if confirm "Reset router database?"; then
        # Stop services first
        stop_services

        # Remove router data
        rm -rf "${DATA_DIR}/router_db/"*
        rm -rf "${DATA_DIR}/router_redis/"*

        log_info "Router database reset complete."
        log_info "Use 'start' to restart services with fresh router state."
    else
        log_info "Reset cancelled."
    fi
}

# Show help
show_help() {
    cat << EOF
ai-paas Controller - Management script for the ai-paas platform

Usage: $0 <command> [options]

Commands:

  Service Management:
    status           Show running containers and their health
    start            Start default services (no-profile: webapp/router/whisper etc)
    start-all        Start ALL services including comfyui, cookies profiles
    stop             Stop default services
    stop-all         Stop ALL services including comfyui, cookies profiles
    restart          Stop and start default services (no-profile services only)
    restart-all      Stop and start ALL services including comfyui, cookies profiles

  Logs & Monitoring:
    logs [container] Show logs for a container or all containers
                      Options: container name (ai_vllm, ai_webapp, etc.) or 'all'
    disk-usage       Show disk usage for project, data, and models
    check-deps       Check all dependencies (models, config, Docker, GPU)

  Data & Models:
    clean-data       Stop services and clean all runtime data (preserves workflows)
    clean-models     Interactive model cleanup (selective delete)
    cleanall         Full cleanup: stops services, cleans data AND all models

   System Maintenance:
     fix-permissions  Fix ownership/permissions on directories (default: data/)
     reset-router     Reset router database and Redis only
     prepare          Download/manage models for ComfyUI or vLLM
                      Usage: prepare [comfyui|vllm]
                        comfyui  Download ComfyUI preset models (~40 GB) via container setup.sh
                        vllm     Show configured model, list available models, switch instructions
     help             Show this help message

Examples:
    $0 status                  # Check which containers are running
    $0 logs ai_vllm            # Follow logs for vLLM container
    $0 logs all                # Show logs from all containers sequentially
    $0 check-deps              # Verify all dependencies are ready
    $0 cleanall                # Full cleanup (data + models)
    $0 prepare comfyui         # Download ComfyUI preset models (~40 GB)
    $0 prepare vllm            # Show vLLM model info and switch instructions
    $0 clean-data              # Clean runtime data only

Auto-Completion:
    To enable bash auto-completion, source the completion script:
        source paas-controller-completion.bash
    Or add to your ~/.bashrc:
        source /path/to/ai-paas/paas-controller-completion.bash

Note: Always run from the ai-paas project root directory.
EOF
}