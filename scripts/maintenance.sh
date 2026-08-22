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

# Show help for the `clean` command family
show_clean_help() {
    cat << EOF
ai-paas cleanup - destructive operations, each guarded by its own confirmation

Usage: $0 clean <target>

Targets:
    data             Stop services, then wipe all runtime data in data/
                       KEEPS : data/comfyui_workflows/ (backed up and restored)
                       KEEPS : git-tracked files under data/ (restored from git)
    model            Interactive model cleanup: list models, delete by index
                       NOTE  : the idphoto entry is not just weights — it is the
                               upstream clone + ONNX weights + pip cache
    model all        Delete ALL models, then drop the repo-root models symlink
                       ('prepare' recreates the symlink, and the idphoto tree)
    all              data + model all, in that order — nothing more
                       Each stage confirms separately; answer 'n' to skip one
    help             Show this message

Examples:
    $0 clean data              # Reset runtime state, keep every model
    $0 clean model             # Pick which models to delete
    $0 clean all               # Full factory reset (re-download models afterwards)

Note: all targets stop the affected services first — models and data are
      bind-mounted into running containers, and deleting a live mount source
      breaks every write inside it until the container is recreated.
EOF
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
    clean <target>   Cleanup operations (see '$0 clean help')
                       clean data           Stop services, wipe runtime data (keeps workflows)
                       clean model          Interactive model cleanup (selective delete)
                       clean model all      Delete ALL models
                       clean all            clean data + clean model all

  Wiki Management:
    wiki-vault       Unified wiki vault management (init + ingest + status)
                     Usage: wiki-vault status
                            wiki-vault run [--vault-path <path>] [--window HH:MM-HH:MM] [--bg|--fg]
                            wiki-vault reset [--vault-path <path>]
                       status           Show all vaults and ingest progress
                       run              Initialize (if needed) and start batch ingest
                       reset            Reset batch progress for a vault
                       --vault-path     Path to the Obsidian vault (interactive if omitted)
                       --window         Time window for processing (can specify multiple)
                       --bg / --fg      Force background or foreground mode

  System Maintenance:
    fix-permissions  Fix ownership/permissions on directories (default: data/)
    reset-router     Reset router database and Redis only
    prepare          Prepare ALL models (no arguments)
                       Stage 1: all vLLM models — qwen + gemma (~40 GB), resume-safe
                       Stage 2: idphoto — upstream clone + ONNX weights (~320 MB),
                                then optionally builds the container and installs its deps
                       Stage 3: ComfyUI preset models (~50 GB) via container setup.sh
                     New vLLM models are added to the registry in scripts/data_models.sh
                     and picked up here automatically.
    rebuild-comfyui  Full ComfyUI rebuild from scratch:
                     wipes comfyui_workdir, re-clones all custom nodes (incl. MuseTalk),
                     re-runs setup.sh. Preserves model weights and git-tracked workflows.
                     Use this after updating setup.sh or when nodes are broken.
    help             Show this help message

Examples:
    $0 status                  # Check which containers are running
    $0 logs ai_vllm            # Follow logs for vLLM container
    $0 logs all                # Show logs from all containers sequentially
    $0 check-deps              # Verify all dependencies are ready
    $0 clean all               # Full cleanup (data + all models)
    $0 prepare                 # Prepare everything: all vLLM models + ComfyUI presets
    $0 clean data              # Clean runtime data only
    $0 rebuild-comfyui         # Wipe workdir + re-clone nodes + re-run setup.sh
    $0 wiki-vault status                          # Show all vaults and progress
    $0 wiki-vault run                             # Interactive: select vault, window, bg mode
    $0 wiki-vault run --vault-path /path/to/vault # Direct: init + ingest (foreground)
    $0 wiki-vault run --vault-path /path --window 02:00-06:00 --bg  # Background with window

Auto-Completion:
    To enable bash auto-completion, source the completion script:
        source paas-controller-completion.bash
    Or add to your ~/.bashrc:
        source /path/to/ai-paas/paas-controller-completion.bash

Note: Always run from the ai-paas project root directory.
EOF
}