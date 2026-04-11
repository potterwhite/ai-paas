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

# Data & models management functions for ai-paas controller

# Source core functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/scripts/core.sh"

# Helper function: Core data directory cleanup logic
cleanup_data_directory() {
    log_info "Cleaning data directory..."
    if [[ -d "${DATA_DIR}" ]]; then
        # Backup workflows first
        if [[ -d "${DATA_DIR}/comfyui_workflows" ]]; then
            log_info "Backing up comfyui_workflows..."
            mkdir -p /tmp/paas_backup
            cp -r "${DATA_DIR}/comfyui_workflows" /tmp/paas_backup/
        fi

        # Fix permissions before cleanup
        fix_permissions "${DATA_DIR}"
        rm -rf "${DATA_DIR:?}"/*

        # Restore workflows
        if [[ -d "/tmp/paas_backup/comfyui_workflows" ]]; then
            cp -r /tmp/paas_backup/comfyui_workflows "${DATA_DIR}/"
            rm -rf /tmp/paas_backup
        fi

        # Recreate required dirs
        mkdir -p "${DATA_DIR}/comfyui_workdir"
        mkdir -p "${DATA_DIR}/router_db"
        mkdir -p "${DATA_DIR}/router_redis"
        mkdir -p "${DATA_DIR}/comfyui_workflows"
        # Fix permissions for recreated directories
        fix_permissions "${DATA_DIR}"
    fi
}

# Helper function: Core models directory cleanup logic
cleanup_models_directory() {
    local full_cleanup=${1:-false}
    
    log_info "Cleaning models directory..."
    if [[ -d "${MODELS_DIR}" ]]; then
        if [[ "$full_cleanup" == "true" ]]; then
            rm -rf "${MODELS_DIR:?}"/*
            log_info "All models deleted."
        fi
    fi
}

# Clean data directory (stopping services first)
clean_data() {
    check_dir

    log_warn "This will stop all ai-paas services and delete all runtime data in data/"
    log_warn "Data to be deleted:"
    echo "  - ${DATA_DIR}/comfyui_workdir/ (ComfyUI state)"
    echo "  - ${DATA_DIR}/router_db/ (Router SQLite database)"
    echo "  - ${DATA_DIR}/router_redis/ (Redis data)"
    echo "  - ${DATA_DIR}/comfyui_workflows/ (Custom workflows - will be preserved if not in workdir)"

    if confirm "Continue with data cleanup?"; then
        stop_services
        cleanup_data_directory  # Reuse the helper function
        log_info "Data cleanup complete. All runtime data has been reset."
        log_info "Use 'start' to restart services."
    else
        log_info "Cleanup cancelled."
    fi
}

# Clean models directory (interactive)
clean_models() {
    check_dir

    if [[ ! -d "${MODELS_DIR}" ]]; then
        log_warn "Models directory does not exist: ${MODELS_DIR}"
        return
    fi

    log_info "Current models:"
    du -sh "${MODELS_DIR}"/* 2>/dev/null || true

    if confirm "List models for interactive selection?"; then
        local models=()
        local i=1

        for model in "${MODELS_DIR}"/*/; do
            [[ -d "$model" ]] || continue
            model_name="$(basename "$model")"
            models+=("$model_name")
            echo "  [$i] $model_name ($(du -sh "$model" | cut -f1))"
            ((i++))
        done

        if [[ ${#models[@]} -eq 0 ]]; then
            log_warn "No models found."
            return
        fi

        echo ""
        read -p "Enter numbers to delete (comma-separated, or 'all' to wipe all): " selection

        if [[ "$selection" == "all" ]]; then
            if confirm "Delete ALL models? This cannot be undone!"; then
                # Fix permissions before cleaning models
                fix_permissions "${MODELS_DIR}"
                cleanup_models_directory true  # Reuse the helper function
                log_info "All models deleted."
            fi
        else
            local IFS=','
            for idx in $selection; do
                if [[ "$idx" =~ ^[0-9]+$ ]] && [[ "$idx" -ge 1 ]] && [[ "$idx" -le ${#models[@]} ]]; then
                    model_to_delete="${models[$((idx-1))]}"
                    if confirm "Delete model '$model_to_delete'?"; then
                        # Fix permissions for specific model directory before deletion
                        fix_permissions "${MODELS_DIR}/${model_to_delete}"
                        rm -rf "${MODELS_DIR}/${model_to_delete}"
                        log_info "Deleted: $model_to_delete"
                    fi
                else
                    log_warn "Invalid index: $idx"
                fi
            done
        fi
    fi
}

# Download ComfyUI preset models by executing container's setup.sh
prepare_comfyui() {
    check_dir

    local host_setup_sh="${SCRIPT_DIR}/services/comfyui/setup.sh"
    local container_setup_sh="/root/ComfyUI/setup.sh"

    # ── Step 1: Guard — vLLM GPU conflict ────────────────────────────────────
    if docker ps --format "{{.Names}}" | grep -q "^ai_vllm$"; then
        echo ""
        log_warn "vLLM (ai_vllm) is currently running and holds the GPU."
        log_warn "ComfyUI needs exclusive GPU access for model downloads."
        echo ""
        log_info "Recommended: stop vLLM first, then re-run this command."
        log_info "  Command: ./paas-controller.sh stop"
        echo ""
        if ! confirm "Proceed anyway (not recommended)?"; then
            log_info "Aborted. Run './paas-controller.sh stop' first, then retry."
            return 1
        fi
    fi

    # ── Step 2: Info + confirm ────────────────────────────────────────────────
    echo ""
    log_info "ComfyUI preset model download"
    echo "  Script : ${container_setup_sh}"
    echo "  Models : SD 1.5 (~4 GB), SDXL (~7 GB), CogVideoX-5B (~21 GB), LivePortrait (~350 MB)"
    echo "  Total  : ~40 GB — may take several hours depending on network speed"
    echo ""

    if ! confirm "Proceed with download?"; then
        log_info "Download cancelled."
        return 0
    fi

    # ── Step 3: Ensure ComfyUI container is running (with correct mounts) ────
    local container_running
    container_running=$(docker inspect -f '{{.State.Running}}' ai_comfyui 2>/dev/null || echo "false")

    # If container is running but setup.sh is inaccessible (stale mounts from a
    # previous compose config), stop and recreate it with current config.
    if [[ "$container_running" == "true" ]]; then
        if ! docker exec ai_comfyui test -f "${container_setup_sh}" 2>/dev/null; then
            log_warn "ai_comfyui is running but ${container_setup_sh} is not accessible."
            log_info "Container has stale mounts. Stopping for recreate..."
            docker stop ai_comfyui
            docker rm ai_comfyui
            container_running="false"
        fi
    fi

    if [[ "$container_running" != "true" ]]; then
        # Guard A: Migrate legacy model data if MODELS_PATH was changed
        # The legacy path is ~/ai-paas/models/comfyui. If MODELS_DIR differs from
        # the repo-relative models/ dir AND legacy path has data AND new path is
        # empty, offer to move the data automatically.
        local legacy_models="${SCRIPT_DIR}/models/comfyui"
        local new_models="${MODELS_DIR}/comfyui"
        if [[ "${MODELS_DIR}" != "${SCRIPT_DIR}/models" ]] && \
           [[ -d "$legacy_models" ]] && \
           [[ -n "$(ls -A "$legacy_models" 2>/dev/null)" ]] && \
           [[ ! -d "$new_models" || -z "$(ls -A "$new_models" 2>/dev/null)" ]]; then
            echo ""
            log_warn "MODELS_PATH is set to: ${MODELS_DIR}"
            log_warn "But existing ComfyUI models found at legacy path: ${legacy_models}"
            log_warn "  Size: $(du -sh "$legacy_models" 2>/dev/null | cut -f1)"
            echo ""
            log_info "These models need to be at: ${new_models}"
            log_info "Options:"
            echo "  [1] Move now   — mv ${legacy_models} ${new_models}  (fast, frees old space)"
            echo "  [2] Copy now   — cp -r ${legacy_models} ${new_models}  (slow, keeps backup)"
            echo "  [3] Skip       — proceed without migrating (downloads may repeat)"
            echo ""
            local choice
            read -rp "Choose [1/2/3]: " choice
            case "$choice" in
                1)
                    log_info "Moving ${legacy_models} → ${new_models} ..."
                    mkdir -p "$(dirname "$new_models")"
                    mv "$legacy_models" "$new_models"
                    log_info "Move complete."
                    ;;
                2)
                    log_info "Copying ${legacy_models} → ${new_models} (this may take a while)..."
                    mkdir -p "$new_models"
                    cp -r "$legacy_models"/. "$new_models"/
                    log_info "Copy complete."
                    ;;
                *)
                    log_warn "Skipping migration. Container will use: ${new_models}"
                    ;;
            esac
        fi

        echo ""
        log_info "Starting ai_comfyui container (profile: comfyui)..."

        # If a stopped container with this name already exists (e.g. from a
        # different compose project file), remove it first so up can create fresh.
        # This also releases any root-owned placeholder files in bind-mount dirs.
        if docker ps -a --format "{{.Names}}" | grep -q "^ai_comfyui$"; then
            local old_state
            old_state=$(docker inspect -f '{{.State.Status}}' ai_comfyui 2>/dev/null || echo "unknown")
            if [[ "$old_state" != "running" ]]; then
                log_info "Removing stopped ai_comfyui container (leftover from previous run)..."
                docker rm ai_comfyui
            fi
        fi

        # Guard B: clean stale Docker-created placeholder files/dirs in comfyui_workdir.
        # These are created when a bind-mount target doesn't exist at container creation
        # time. Must be done AFTER docker rm to avoid permission errors on root-owned files.
        local workdir="${DATA_DIR}/comfyui_workdir"
        if [[ -d "$workdir" ]]; then
            local placeholders=("setup.sh" "extra_model_paths.yaml" "models" "workflows")
            local cleaned=false
            for p in "${placeholders[@]}"; do
                local fp="${workdir}/${p}"
                # A file that is 0 bytes, or an empty directory = placeholder
                if [[ -f "$fp" && ! -s "$fp" ]] || \
                   { [[ -d "$fp" ]] && [[ -z "$(ls -A "$fp" 2>/dev/null)" ]]; }; then
                    rm -rf "$fp" 2>/dev/null || true
                    [[ ! -e "$fp" ]] && cleaned=true
                fi
            done
            if [[ "$cleaned" == "true" ]]; then
                log_info "Removed stale Docker bind-mount placeholders from comfyui_workdir."
            fi
        fi

        cd "${SCRIPT_DIR}"
        docker compose -f "${DOCKER_COMPOSE_FILE}" --profile comfyui up -d comfyui
        echo ""
        log_info "Waiting for container to become ready..."
        sleep 5
    fi

    # ── Step 4: Resolve the actual path to run setup.sh from ─────────────────
    # The bind-mount target path (/root/ComfyUI/setup.sh) may be read-only or
    # "device busy" if the mount point itself is occupied. Use a temp path as
    # fallback so chmod/exec never touch the mount point directly.
    local run_path="${container_setup_sh}"

    echo ""
    log_info "Verifying setup.sh inside container..."

    if ! docker exec ai_comfyui test -f "${container_setup_sh}" 2>/dev/null; then
        log_warn "setup.sh not found at ${container_setup_sh} (bind-mount may not have applied)"
        echo ""

        if [[ -f "${host_setup_sh}" ]]; then
            # Copy to /tmp to avoid touching the busy bind-mount path
            local tmp_path="/tmp/paas_setup.sh"
            log_info "Fallback: copying setup.sh into container at ${tmp_path} ..."
            log_info "  Source: ${host_setup_sh}"
            docker cp "${host_setup_sh}" "ai_comfyui:${tmp_path}"
            docker exec ai_comfyui chmod +x "${tmp_path}"
            run_path="${tmp_path}"
            log_info "Copy complete. Will run from ${tmp_path}."
        else
            echo ""
            log_error "Cannot proceed: setup.sh not found on host either."
            log_error "  Expected: ${host_setup_sh}"
            echo ""
            log_info "To diagnose, run:"
            log_info "  docker exec -it ai_comfyui ls /root/ComfyUI/"
            log_info "  ls ${SCRIPT_DIR}/services/comfyui/"
            return 1
        fi
    else
        log_info "setup.sh found inside container. Proceeding."
    fi

    # ── Step 5: Run setup.sh ─────────────────────────────────────────────────
    echo ""
    log_info "Running setup.sh inside ai_comfyui (path: ${run_path})..."
    echo "────────────────────────────────────────────────────────"
    docker exec -it ai_comfyui bash "${run_path}"
    local exit_code=$?
    echo "────────────────────────────────────────────────────────"
    echo ""

    if [[ $exit_code -eq 0 ]]; then
        log_info "All preset models downloaded successfully."
        log_info "Next steps:"
        echo "  - To use ComfyUI UI : open http://localhost:8188"
        echo "  - To switch back to vLLM: ./paas-controller.sh stop && ./paas-controller.sh start"
    else
        log_error "setup.sh exited with code ${exit_code}."
        echo ""
        log_info "To check what went wrong:"
        log_info "  ./paas-controller.sh logs ai_comfyui"
        log_info "To retry setup manually:"
        log_info "  docker exec -it ai_comfyui bash ${container_setup_sh}"
    fi
}

# Show vLLM model info: currently loaded model and all available models in MODELS_DIR
prepare_vllm() {
    check_dir

    # Detect current model from docker-compose.yml
    local compose_file="${DOCKER_COMPOSE_FILE}"
    local current_model=""
    if [[ -f "$compose_file" ]]; then
        # Extract the value after '- --model' line (next non-empty line)
        current_model=$(awk '/- --model/{found=1; next} found && /^[[:space:]]*-/{gsub(/^[[:space:]]*-[[:space:]]*/,""); print; exit}' "$compose_file")
    fi

    log_info "vLLM model directory: ${MODELS_DIR}"
    echo ""

    if [[ -n "$current_model" ]]; then
        log_info "Currently configured model (docker-compose.yml):"
        echo "  ${current_model}"
    else
        log_warn "Could not detect current model from docker-compose.yml."
    fi
    echo ""

    # List all model directories (exclude comfyui subdir)
    log_info "Available models in ${MODELS_DIR}:"
    local found=false
    local i=1
    for d in "${MODELS_DIR}"/*/; do
        [[ -d "$d" ]] || continue
        local name
        name="$(basename "$d")"
        [[ "$name" == "comfyui" ]] && continue
        local size
        size=$(du -sh "$d" 2>/dev/null | cut -f1)
        if [[ "$d" == "${current_model}/" ]] || [[ "${MODELS_DIR}/${name}" == "$current_model" ]]; then
            echo "  [$i] ${name}  (${size})  ← current"
        else
            echo "  [$i] ${name}  (${size})"
        fi
        found=true
        ((i++))
    done

    if [[ "$found" == "false" ]]; then
        log_warn "No model directories found in ${MODELS_DIR} (excluding comfyui/)."
        echo ""
        log_info "To download a vLLM model, see: docs/zh/1-for-ai/vllm-model-download.md"
        return 0
    fi

    echo ""
    log_info "To switch models:"
    echo "  1. Edit docker-compose.yml — change the '- /models/<name>' line under vllm command"
    echo "  2. Run: docker compose up -d --force-recreate vllm"
    echo ""
    log_info "For download instructions: docs/zh/1-for-ai/vllm-model-download.md"
}

# Dispatcher: prepare [comfyui|vllm]
prepare() {
    local subcommand="${1:-}"

    case "$subcommand" in
        comfyui|"")
            prepare_comfyui
            ;;
        vllm)
            prepare_vllm
            ;;
        *)
            log_error "Unknown prepare subcommand: $subcommand"
            echo "Usage: prepare [comfyui|vllm]"
            echo "  comfyui  Download ComfyUI preset models via container setup.sh (default)"
            echo "  vllm     Show current vLLM model and available models; switch instructions"
            return 1
            ;;
    esac
}

# Full cleanup: stop services, clean data, and clean models
cleanall() {
    check_dir

    log_warn "FULL CLEANUP: This will stop all services and delete:"
    echo "  - All runtime data in data/"
    echo "  - ALL models in models/ (including production models!)"
    echo ""
    log_warn "This action CANNOT be undone. You will need to re-download all models."
    echo ""

    if ! confirm "Are you absolutely sure you want to proceed?"; then
        log_info "Cleanall cancelled."
        return 0
    fi

    # Step 1: Stop services
    stop_services

    # Step 2: Fix permissions and clean data directory (reuse helper)
    fix_permissions "${DATA_DIR}"
    cleanup_data_directory

    # Step 3: Fix permissions and clean ALL models (reuse helper with full cleanup flag)
    fix_permissions "${MODELS_DIR}"
    cleanup_models_directory true

    log_info "Full cleanup complete."
    log_warn "Please re-download required models before starting services again."
}