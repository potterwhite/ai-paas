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

# ── shared download libraries ────────────────────────────────────────────────
# The same three libs services/comfyui/setup.sh uses, for the same reason: this
# host reaches huggingface.co through a transparent proxy that stalls single
# streams, and aria2c's 16 connections plus per-file resume are what make a
# 20 GB transfer finishable here.
#
#   libs/http.sh      aria2c invocation, resume state, control files
#   libs/fileinfo.sh  size and sha256 of a file on disk
#   libs/fetch.sh     whether a file needs downloading, and the running tally
#
# Sourced here, never sourcing each other — libs/ is a set of leaves and the
# entry script does all the sourcing. See the header of libs/fetch.sh.
#
# libfetch_require is NOT called at source time, unlike in setup.sh. This file is
# sourced by paas-controller.sh for EVERY command, so a missing aria2c would take
# down `status` and `logs` as well. It is checked in _download_all_vllm_models
# instead, which is the only thing here that transfers bytes.
# shellcheck source=../libs/http.sh
source "${SCRIPT_DIR}/libs/http.sh"
# shellcheck source=../libs/fileinfo.sh
source "${SCRIPT_DIR}/libs/fileinfo.sh"
# shellcheck source=../libs/fetch.sh
source "${SCRIPT_DIR}/libs/fetch.sh"

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

        # `rm -rf data/*` also destroys the version-controlled files that
        # .gitignore explicitly whitelists (e.g. comfyui_extra_model_paths.yaml,
        # which docker-compose bind-mounts as a FILE — if it is missing, Docker
        # substitutes a directory and ComfyUI loses every model path).
        # Restoring from git covers any file added to the whitelist later,
        # instead of hard-coding names here.
        if git -C "${SCRIPT_DIR}" rev-parse --git-dir >/dev/null 2>&1; then
            local restored
            restored=$(git -C "${SCRIPT_DIR}" ls-files -d -- data/ 2>/dev/null | wc -l)
            if [[ "${restored}" -gt 0 ]]; then
                log_info "Restoring ${restored} git-tracked file(s) under data/..."
                git -C "${SCRIPT_DIR}" checkout -- data/ 2>/dev/null || \
                    log_warn "Could not restore tracked files — run: git restore data/"
            fi
        fi

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

# Helper function: destroy every model, then drop the repo-root models symlink.
# `prepare` recreates the link via ensure_models_link, so dropping it here stops
# a wiped tree from looking populated. Shared by `clean model` (selection 'all')
# and `clean all`; callers MUST stop services first — see stop_before_delete().
purge_all_models() {
    fix_permissions "${MODELS_DIR}"
    cleanup_models_directory true
    remove_models_link
}

# Helper function: running containers hold data/ and models/ paths as bind mounts
# (/models for vLLM and Xinference, ${MODELS_DIR}/comfyui for ComfyUI). Deleting a
# mount source while its container is up leaves the mount pointing at the unlinked
# inode: the dir still stats as a writable directory but every write inside it
# fails with ENOENT until the container is recreated. So every destructive path
# goes through here first. Cheap to repeat — `clean all` runs it twice.
stop_before_delete() {
    stop_services
}

# `clean data` — wipe runtime data (owns its own warning + confirmation)
clean_data() {
    check_dir

    log_warn "This will stop all ai-paas services and delete all runtime data in data/"
    log_warn "Data to be deleted:"
    echo "  - ${DATA_DIR}/comfyui_workdir/ (ComfyUI state)"
    echo "  - ${DATA_DIR}/router_db/ (Router SQLite database)"
    echo "  - ${DATA_DIR}/router_redis/ (Redis data)"
    echo "  - ${DATA_DIR}/comfyui_workflows/ (Custom workflows - will be preserved if not in workdir)"

    if ! confirm "Continue with data cleanup?"; then
        log_info "Data cleanup cancelled."
        return 0
    fi

    stop_before_delete
    cleanup_data_directory  # Reuse the helper function
    log_info "Data cleanup complete. All runtime data has been reset."
    log_info "Use 'start' to restart services."
}

# `clean model [all]` — delete models (owns its own warnings + confirmations)
#   mode 'interactive' (default): list models, pick indices or type 'all'
#   mode 'all'                  : skip the menu, wipe everything after one confirm
clean_models() {
    check_dir
    local mode="${1:-interactive}"

    if [[ ! -d "${MODELS_DIR}" ]]; then
        log_warn "Models directory does not exist: ${MODELS_DIR}"
        return 0
    fi

    if [[ "$mode" == "all" ]]; then
        log_warn "This will delete ALL models in ${MODELS_DIR}"
        log_warn "  Including ${MODELS_DIR}/idphoto — the HivisionIDPhotos clone, its ONNX"
        log_warn "  weights and its pip cache. 'prepare' rebuilds all three."
    else
        log_info "Current models:"
        du -sh "${MODELS_DIR}"/* 2>/dev/null || true
        if ! confirm "List models for interactive selection?"; then
            log_info "Model cleanup cancelled."
            return 0
        fi
    fi

    # Enumerate top-level model dirs (numbered only when a menu is shown).
    # Not every entry is a set of weights — annotate the ones where deleting has
    # a consequence beyond "download it again".
    local models=() model model_name note
    for model in "${MODELS_DIR}"/*/; do
        [[ -d "$model" ]] || continue
        model_name="$(basename "$model")"
        models+=("$model_name")
        note=""
        case "$model_name" in
            idphoto) note="   ← app clone + ONNX weights + pip cache" ;;
            comfyui) note="   ← ComfyUI checkpoints and custom-node weights" ;;
        esac
        [[ "$mode" == "all" ]] || \
            echo "  [${#models[@]}] $model_name ($(du -sh "$model" | cut -f1))${note}"
    done

    if [[ ${#models[@]} -eq 0 ]]; then
        log_warn "No models found."
        return 0
    fi

    local selection="all"
    if [[ "$mode" != "all" ]]; then
        echo ""
        read -r -p "Enter numbers to delete (comma-separated, or 'all' to wipe all): " selection
        if [[ -z "$selection" ]]; then
            log_info "Nothing selected. Model cleanup cancelled."
            return 0
        fi
    fi

    if [[ "$selection" == "all" ]]; then
        if ! confirm "Delete ALL ${#models[@]} model(s)? This cannot be undone!"; then
            log_info "Model cleanup cancelled."
            return 0
        fi
        stop_before_delete
        purge_all_models
        log_warn "Re-download required models with 'prepare' before starting services."
        return 0
    fi

    # Selective delete by index — each model confirmed individually
    stop_before_delete
    local IFS=',' idx model_to_delete
    for idx in $selection; do
        if [[ "$idx" =~ ^[0-9]+$ ]] && [[ "$idx" -ge 1 ]] && [[ "$idx" -le ${#models[@]} ]]; then
            model_to_delete="${models[$((idx-1))]}"
            if [[ "$model_to_delete" == "idphoto" ]]; then
                log_warn "'idphoto' is not only weights — it is the upstream clone, the two"
                log_warn "ONNX weights and the container's pip cache. Deleting it means"
                log_warn "re-running 'prepare' before ai_idphoto can serve anything again."
            fi
            if confirm "Delete model '$model_to_delete'?"; then
                # Fix permissions for specific model directory before deletion
                fix_permissions "${MODELS_DIR}/${model_to_delete}"
                rm -rf "${MODELS_DIR:?}/${model_to_delete}"
                log_info "Deleted: $model_to_delete"
            fi
        else
            log_warn "Invalid index: $idx"
        fi
    done
}

# Download ComfyUI preset models by executing container's setup.sh
prepare_comfyui() {
    check_dir

    # Also reached via `prepare` and `rebuild-comfyui`; keep the models link
    # guaranteed here rather than assuming the caller did it.
    ensure_models_link || return 1

    local host_setup_sh="${SCRIPT_DIR}/services/comfyui/setup.sh"
    local container_setup_sh="/root/ComfyUI/setup.sh"
    # setup.sh does not implement downloading; it sources libs/ for that. Both
    # mounts have to be present or it exits before touching a single model.
    local host_libs_dir="${SCRIPT_DIR}/libs"
    local container_libs_dir="/root/ComfyUI/libs"

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
    echo "  Host models dir : $(realpath "${MODELS_DIR}/comfyui" 2>/dev/null || echo "${MODELS_DIR}/comfyui")"
    echo ""
    echo "  Model groups to download:"
    echo "    1. Custom nodes          — 5 ComfyUI extensions (incl. MuseTalk)"
    echo "    2. CogVideoX-5B          — ~26 GB (transformer + VAE + T5-XXL)"
    echo "    3. LivePortrait           — ~350 MB (digital human)"
    echo "    4. Stable Diffusion 1.5   — ~4 GB"
    echo "    5. SDXL Base 1.0          — ~7 GB"
    echo "    6. Workflow sync          — copy to Browse UI"
    echo "    7. (reserved)"
    echo "    8. MuseTalk               — ~4.2 GB (UNet + Whisper + SD-VAE + DWPose)"
    echo ""
    echo "  Total  : ~50 GB — existing files with valid checksums are skipped"
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
    # libs/ is probed the same way and for the same reason: it was added to the
    # compose file after this container may have been created, so a container
    # started from the older config has setup.sh but no libs/ and would abort.
    if [[ "$container_running" == "true" ]]; then
        if ! docker exec ai_comfyui test -f "${container_setup_sh}" 2>/dev/null \
           || ! docker exec ai_comfyui test -f "${container_libs_dir}/fetch.sh" 2>/dev/null; then
            log_warn "ai_comfyui is running but ${container_setup_sh} or ${container_libs_dir}/ is not accessible."
            log_info "Container has stale mounts. Stopping for recreate..."
            docker stop ai_comfyui
            docker rm ai_comfyui
            container_running="false"
        fi
    fi

    # A running container can also hold a stale *models* mount: if
    # ${MODELS_DIR}/comfyui was deleted on the host while the container was up
    # (`clean model` / `clean all` do `rm -rf ${MODELS_DIR}/*`), the mount still points
    # at the unlinked inode and every mkdir inside it fails with ENOENT. The dir
    # still looks writable to `test -w`, so probe with a real mkdir.
    if [[ "$container_running" == "true" ]]; then
        if ! docker exec ai_comfyui sh -c \
            'mkdir -p /root/ComfyUI/models/.probe && rmdir /root/ComfyUI/models/.probe' 2>/dev/null; then
            log_warn "ai_comfyui is running but its models mount is stale."
            log_warn "  Host dir ${MODELS_DIR}/comfyui was deleted while the container was up."
            log_info "Recreating container to re-resolve the mount..."
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

        # Ensure the models bind-mount source exists before the container starts.
        # Docker would otherwise auto-create it root-owned; creating it here also
        # restores it after a `clean model` / `clean all` wipe.
        mkdir -p "${MODELS_DIR}/comfyui"

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
    log_info "Verifying setup.sh and libs/ inside container..."

    # Either mount missing sends both through the fallback. setup.sh finds libs/
    # next to itself, so the two must always land in the same directory -- copying
    # only the one that is missing would leave them split across /root/ComfyUI and
    # /tmp, where the lookup fails.
    if ! docker exec ai_comfyui test -f "${container_setup_sh}" 2>/dev/null \
       || ! docker exec ai_comfyui test -f "${container_libs_dir}/fetch.sh" 2>/dev/null; then
        log_warn "setup.sh or libs/ not accessible in container (bind-mount may not have applied)"
        echo ""

        if [[ -f "${host_setup_sh}" && -f "${host_libs_dir}/fetch.sh" ]]; then
            # Copy to /tmp to avoid touching the busy bind-mount path. setup.sh
            # resolves libs/ relative to its own location, so /tmp/paas_setup.sh
            # pairs with /tmp/libs.
            local tmp_path="/tmp/paas_setup.sh"
            log_info "Fallback: copying setup.sh and libs/ into container ..."
            log_info "  ${host_setup_sh} -> ${tmp_path}"
            log_info "  ${host_libs_dir}/ -> /tmp/libs/"
            docker cp "${host_setup_sh}" "ai_comfyui:${tmp_path}"
            docker exec ai_comfyui rm -rf /tmp/libs
            docker cp "${host_libs_dir}" "ai_comfyui:/tmp/libs"
            docker exec ai_comfyui chmod +x "${tmp_path}"
            run_path="${tmp_path}"
            log_info "Copy complete. Will run from ${tmp_path}."
        else
            echo ""
            log_error "Cannot proceed: setup.sh or libs/ not found on host either."
            log_error "  Expected: ${host_setup_sh}"
            log_error "  Expected: ${host_libs_dir}/fetch.sh"
            echo ""
            log_info "To diagnose, run:"
            log_info "  docker exec -it ai_comfyui ls /root/ComfyUI/"
            log_info "  ls ${SCRIPT_DIR}/services/comfyui/ ${SCRIPT_DIR}/libs/"
            return 1
        fi
    else
        log_info "setup.sh and libs/ found inside container. Proceeding."
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
        log_info "The failures are listed above -- setup.sh printed them straight to"
        log_info "this terminal, so 'logs ai_comfyui' will not show them."
        log_info "To retry (partial downloads resume from where they stopped):"
        log_info "  ./paas-controller.sh prepare"
        log_info "  docker exec -it ai_comfyui bash ${container_setup_sh}   # setup.sh only"
    fi

    # Propagate the failure: without this the function returns 0 and `prepare`
    # reports "prepare complete." right after printing setup.sh's error.
    return $exit_code
}

# ── idphoto (HivisionIDPhotos) ───────────────────────────────────────────────
# The image is deliberately an empty shell: the app code, the ONNX weights and
# the pip cache all live on the HOST under ${MODELS_DIR}/idphoto, so a broken
# container can be deleted and recreated without re-downloading anything.
#
# The consequence is that the host side must exist BEFORE the container is
# created. If it does not, Docker auto-creates the bind-mount sources as empty
# root-owned directories and 0-entrypoint.sh idles forever waiting for a clone
# that will never appear. That is what this function removes the need to do by
# hand. Full background: services/idphoto/README.md
IDPHOTO_REPO_URL="https://github.com/Zeyi-Lin/HivisionIDPhotos.git"

prepare_idphoto() {
    check_dir
    ensure_models_link || return 1

    local root="${MODELS_DIR}/idphoto"
    local src="${root}/src"
    local pip_cache="${root}/pip-cache"
    local weights_sh="${SCRIPT_DIR}/services/idphoto/1-download-weights.sh"

    log_info "idphoto (HivisionIDPhotos) host-side setup"
    echo "  Clone     : ${src}"
    echo "  pip cache : ${pip_cache}"
    echo "  Weights   : ~320 MB (birefnet-v1-lite 214 MB + retinaface-resnet50 105 MB)"
    echo ""

    # aria2c is only a fast path — 1-download-weights.sh falls back to curl or
    # wget on its own, so there is nothing to gate on here.
    if [[ ! -f "$weights_sh" ]]; then
        log_error "Missing ${weights_sh}"
        return 1
    fi

    mkdir -p "$src" "$pip_cache"

    # ── Step 1: upstream clone ───────────────────────────────────────────────
    # deploy_api.py is the marker both 1-download-weights.sh and 2-install.sh
    # test for; use the same one here so all three agree on "this is the clone".
    if [[ -f "${src}/deploy_api.py" ]]; then
        log_info "Clone already present — left untouched (it is upstream; our fixes live in services/idphoto/)."
    elif [[ -n "$(ls -A "$src" 2>/dev/null)" ]]; then
        log_error "${src} is not empty but is not a HivisionIDPhotos clone (no deploy_api.py)."
        log_error "  Move it aside and re-run — prepare never deletes this directory."
        return 1
    else
        # --depth 1: this clone is never checked out at another revision, and the
        # history is several times the size of the tree.
        log_info "Cloning ${IDPHOTO_REPO_URL} ..."
        if ! git clone --depth 1 "${IDPHOTO_REPO_URL}" "$src"; then
            log_error "Clone failed. Check network, then re-run prepare."
            # A half-written clone would trip the "not empty, not a clone" branch
            # above on the next run and need manual cleanup. Undo it here.
            rm -rf "${src:?}"
            mkdir -p "$src"
            return 1
        fi
    fi

    # ── Step 2: pip cache ownership ──────────────────────────────────────────
    # pip in the container runs as root and checks the cache directory's OWNER,
    # not its permission bits. A cache owned by the host user is silently
    # disabled — which costs a 300 MB+ re-download every time the container is
    # recreated. Note `fix-permissions` / `clean` chown models/ back to the host
    # user, so this has to be re-asserted here rather than done once.
    local cache_owner
    cache_owner=$(stat -c '%u' "$pip_cache" 2>/dev/null || echo "")
    if [[ "$cache_owner" != "0" ]]; then
        log_info "Handing pip-cache to root (pip ignores a cache it does not own)..."
        # Try the non-interactive path first, so the reason for the password
        # prompt is on screen before the prompt itself appears.
        if ! sudo -n chown -R 0:0 "$pip_cache" 2>/dev/null; then
            log_info "  sudo password required for: chown -R 0:0 ${pip_cache}"
            sudo chown -R 0:0 "$pip_cache" || \
                log_warn "chown failed — container pip cache stays disabled (only makes reinstalls slower)."
        fi
    fi

    # ── Step 3: weights ──────────────────────────────────────────────────────
    echo ""
    log_info "Downloading ONNX weights (idempotent — correct-size files are skipped)..."
    bash "$weights_sh" "$src" || return 1

    # ── Step 4: container + pip deps (one-time, lives in the container layer) ─
    # Everything above survives anything. This step does not: pip installs into
    # the container's writable layer, so `docker rm` / `--build` / `down` means
    # doing it again. It is cheap to redo (warm pip cache) and idempotent.
    echo ""
    local was_running="false" deps_ok="false" state
    state=$(docker inspect -f '{{.State.Status}}' ai_idphoto 2>/dev/null || echo absent)
    [[ "$state" == "running" ]] && was_running="true"

    # idphoto's normal state is STOPPED (Router-scheduled, `restart: "no"`), so
    # "not running" says nothing about whether the deps are installed. Probing
    # only a running container therefore reported deps-missing every time and
    # re-ran step 2 against a container that was already complete — and step 2
    # on an already-complete container is the one case that breaks it (see the
    # PID 1 guard at the top of 2-install.sh). Start it to ask, instead.
    #
    # Starting is safe: 0-entrypoint.sh either idles (deps missing) or execs
    # app.py, which allocates no VRAM until the first request. was_running is
    # already false for a container we start here, so the "put it back the way
    # we found it" step stops it again.
    if [[ "$state" != "running" && "$state" != "absent" ]]; then
        log_info "ai_idphoto exists but is stopped — starting it just long enough to check its deps."
        if docker start ai_idphoto >/dev/null 2>&1; then
            state="running"
        else
            log_warn "Could not start ai_idphoto — treating its deps as missing."
        fi
    fi

    if [[ "$state" == "running" ]]; then
        docker exec ai_idphoto python3 -c 'import gradio, onnxruntime' >/dev/null 2>&1 && deps_ok="true"

        # A container that was UP while `clean model` / `clean all` deleted
        # ${MODELS_DIR}/idphoto keeps its mount on the unlinked inode: /workspace
        # still stats as a directory, but the clone restored above is invisible
        # inside it, and the WebUI dies on "app.py not found". Only a recreate
        # re-resolves a bind mount, so probe for the clone rather than the dir.
        # (A container we just started needs no repair — mounts re-resolve then.)
        if ! docker exec ai_idphoto test -f /workspace/deploy_api.py 2>/dev/null; then
            log_warn "ai_idphoto is running on a stale /workspace mount — the host tree was"
            log_warn "  deleted underneath it. Recreating the container to re-resolve it."
            docker rm -f ai_idphoto >/dev/null
            # The pip packages lived in the layer that was just removed.
            was_running="false"
            deps_ok="false"
        fi
    fi

    if [[ "$deps_ok" == "true" ]]; then
        log_info "ai_idphoto has its deps installed and the clone visible — nothing left to do."
        if [[ "$was_running" != "true" ]]; then
            docker stop ai_idphoto >/dev/null
            log_info "  Left STOPPED, as found. The Router starts it on a GPU-mode switch."
        fi
        return 0
    fi

    log_info "One-time step left: create the container and pip-install inside it."
    log_warn "It is left STOPPED afterwards — this GPU is exclusive and Router-scheduled."
    echo ""
    if ! confirm "Do that now (a few minutes, needs network)?"; then
        log_info "Skipped. To finish later:"
        echo "  docker compose --profile idphoto up -d --build idphoto"
        echo "  docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh"
        return 0
    fi

    cd "${SCRIPT_DIR}"
    if ! docker compose -f "${DOCKER_COMPOSE_FILE}" --profile idphoto up -d --build idphoto; then
        log_error "Could not create ai_idphoto."
        return 1
    fi

    # We only get here with deps_ok=false, and 0-entrypoint.sh gates on the same
    # `import gradio, onnxruntime` we just failed — so it is idling on `sleep
    # infinity`, which is both exec-able immediately (no readiness wait) and the
    # only state 2-install.sh will pip into. Do not "optimise" the probe above
    # into something that can disagree with the entrypoint: when it said
    # deps-missing about a container that was in fact complete, this exec pipped
    # into a live WebUI and SIGBUSed it (container exit 135, install truncated).
    if ! docker exec ai_idphoto bash /opt/idphoto/2-install.sh; then
        log_error "2-install.sh failed. Fix the cause, then re-run:"
        log_error "  docker exec -it ai_idphoto bash /opt/idphoto/2-install.sh"
        return 1
    fi

    # Only put it back the way we found it. If it was already running, leaving it
    # running is the caller's state, not ours to change.
    if [[ "$was_running" != "true" ]]; then
        docker stop ai_idphoto >/dev/null
    fi

    echo ""
    log_info "idphoto ready. Hand it the GPU when you want it (this stops vLLM/ComfyUI):"
    echo "  - UI  : the /gpu panel in ai_webapp — switch mode to 'idphoto'"
    echo "  - API : POST /v1/gpu/mode  {\"mode\":\"idphoto\"}  on the router"
    echo "  Then open /idphoto in ai_webapp (7860 is not published on the host)."
}

# ══════════════════════════════════════════════════════════════════════════════
# vLLM models
#
# Downloaded with aria2c through libs/, exactly as services/comfyui/setup.sh
# does. This replaced a git clone + `git lfs pull` that could not finish here.
#
# Why git-lfs was dropped, from an observed run: qwen's 5 shards downloaded one
# at a time over a single connection, shard 4 died on "read tcp
# 192.168.0.19:55416->198.18.1.217:443: i/o timeout", and because `git lfs pull`
# returns non-zero when ANY object fails, the whole model was reported failed
# with 4 of 5 shards already on disk. git-lfs has no equivalent of aria2c's 16
# connections, no per-file retry, and no low-speed guard — the failure repeats
# for as long as the link stays flaky.
#
# What the aria2c path gives instead:
#   - 16 connections per file, so one stalled connection is not the transfer
#   - --lowest-speed-limit=32K --timeout=30 kills a dead connection in seconds
#     rather than waiting out a TCP timeout
#   - per-file retry with resume (libs/fetch.sh, LIBFETCH_MAX_ATTEMPTS rounds)
#   - one failing shard does not abandon the other four
#   - SHA-256 verification per file, so a transfer cut at 60% is never accepted
#   - a single copy on disk. git-lfs stored every object twice (.git/lfs/objects
#     plus the worktree), so an 18 GiB model cost 36 GiB and needed a prune step.
#
# It does NOT fix a dead proxy. 198.18.1.217 is in the 198.18.0.0/15 benchmark
# range, i.e. a transparent proxy / TUN interface — aria2c rides out jitter far
# better but cannot invent a route. If transfers still fail, the proxy is the
# thing to look at, not this code.
# ══════════════════════════════════════════════════════════════════════════════

# vLLM model registry: name → (huggingface_repo_id, local_dir_name, size_hint)
# local_dir_name MUST match the --model path used by the matching docker-compose
# service (vllm-<name>), otherwise the container starts against an empty path.
#
# size_hint is the summed byte count of the files the manifest below actually
# fetches, formatted the way libfileinfo_human formats it, so the hint and the
# per-file [done] lines are in the same units and add up.
declare -A VLLM_MODEL_REGISTRY=(
    [qwen]="Qwen/Qwen2.5-32B-Instruct-AWQ|qwen2.5-32b-instruct-awq|18.0GiB"
    [gemma]="cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit|gemma-4-26B-A4B-awq|16.0GiB"
)

# Deterministic download order (associative array key order is unspecified).
# Production default first, so a fresh box gets a usable model soonest.
VLLM_MODEL_ORDER=(qwen gemma)

# ── manifests ────────────────────────────────────────────────────────────────
#
# Every checksum below is the sha256 of the file's content, taken from the
# HuggingFace tree API, which reports it as lfs.oid for LFS-tracked files:
#
#   curl -s 'https://huggingface.co/api/models/<repo>/tree/main?recursive=true' \
#     | jq -r '.[] | select(.lfs) | "\(.lfs.oid)  \(.path)"'
#
# Written out literally rather than fetched at run time, same as setup.sh. A
# manifest built from a live API call verifies each download against whatever
# the repo holds today, which is not verification at all — it would follow an
# upstream force-push without a word. These digests pin the bytes, so a repo
# that changes underneath us fails loudly and a human decides what to do.
#
# The small JSON that accompanies the weights goes through libfetch_config,
# which does NOT checksum. Deliberate, and the reason is visible in the API
# output: for a non-LFS file the `oid` field is a git blob sha1, not a sha256 of
# the content, so there is no digest to check against. Acceptable here for the
# reason libfetch_config documents — these are kilobytes, vLLM parses them at
# load and fails loudly on damage, and re-fetching costs a second.
#
# `|| true` on every libfetch_model call keeps one bad shard from abandoning the
# rest. The failure is not swallowed: libfetch_model has already printed [FAIL]
# and incremented LIBFETCH_FAILED, which is what the summary reports on.

_download_qwen() {
    local dir="$1"
    local HF="https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-AWQ/resolve/main"

    echo "  ── weights: 5 shards, 18.0GiB ──"
    libfetch_model "$HF/model-00001-of-00005.safetensors" \
        "$dir/model-00001-of-00005.safetensors" \
        "qwen shard 1/5 (3.7GiB)" \
        "548f5c7078e297088c74bec4443bfe9e3b4183ee7457f328107c37a5eb861ea1" || true
    libfetch_model "$HF/model-00002-of-00005.safetensors" \
        "$dir/model-00002-of-00005.safetensors" \
        "qwen shard 2/5 (3.7GiB)" \
        "735d1b5aa8ef01420f2079b355d84cfa7a4b37571d44715276b3b903c06d65d8" || true
    libfetch_model "$HF/model-00003-of-00005.safetensors" \
        "$dir/model-00003-of-00005.safetensors" \
        "qwen shard 3/5 (3.7GiB)" \
        "f158db037c405677ea6ca21a5cb67a800ddc256217c722c0dee0eb31f3f75fb8" || true
    # The shard that killed the git-lfs run; its oid is the digest git-lfs named
    # in the i/o timeout, which is also how oid == sha256 was confirmed here.
    libfetch_model "$HF/model-00004-of-00005.safetensors" \
        "$dir/model-00004-of-00005.safetensors" \
        "qwen shard 4/5 (3.7GiB)" \
        "ece82d2cd5ecc9691572aae55cf2d66fa52edd2c199d5a6dccb8182145bae59c" || true
    libfetch_model "$HF/model-00005-of-00005.safetensors" \
        "$dir/model-00005-of-00005.safetensors" \
        "qwen shard 5/5 (3.2GiB)" \
        "1af3bf12ce80cf2f85bacb57a7d2fd584712a945f481cf394f0c7b17983269e5" || true

    echo "  ── config + tokenizer ──"
    libfetch_config "$HF/config.json"                    "$dir/config.json"
    libfetch_config "$HF/generation_config.json"         "$dir/generation_config.json"
    libfetch_config "$HF/model.safetensors.index.json"   "$dir/model.safetensors.index.json"
    libfetch_config "$HF/tokenizer.json"                 "$dir/tokenizer.json"
    libfetch_config "$HF/tokenizer_config.json"          "$dir/tokenizer_config.json"
    libfetch_config "$HF/vocab.json"                     "$dir/vocab.json"
    libfetch_config "$HF/merges.txt"                     "$dir/merges.txt"
    libfetch_config "$HF/LICENSE"                        "$dir/LICENSE"
    echo "  [done] qwen config + tokenizer files"
}

_download_gemma() {
    local dir="$1"
    local HF="https://huggingface.co/cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit/resolve/main"

    echo "  ── weights: 4 shards, 16.0GiB ──"
    libfetch_model "$HF/model-00001-of-00004.safetensors" \
        "$dir/model-00001-of-00004.safetensors" \
        "gemma shard 1/4 (5.0GiB)" \
        "8dbd104bfcf879d5fda77c5ac6fb4e939e3e8b375c8efa11192ebf63984d5892" || true
    libfetch_model "$HF/model-00002-of-00004.safetensors" \
        "$dir/model-00002-of-00004.safetensors" \
        "gemma shard 2/4 (5.0GiB)" \
        "b257e55596c1af537216f522971ab8312137dd0db04dfc66dffeb701bf75bf2f" || true
    libfetch_model "$HF/model-00003-of-00004.safetensors" \
        "$dir/model-00003-of-00004.safetensors" \
        "gemma shard 3/4 (5.0GiB)" \
        "d77dc1b6df95c3e8b6214444a7fae5bcbb5f3f5e5e50416f040c74ee1b08df97" || true
    libfetch_model "$HF/model-00004-of-00004.safetensors" \
        "$dir/model-00004-of-00004.safetensors" \
        "gemma shard 4/4 (1.0GiB)" \
        "9a396bbb0ca00d8b298914863df7da0d5d94751cf9a970c8f4f53384328afc47" || true

    # LFS-tracked in this repo, unlike qwen's, so it has a real sha256 and goes
    # through libfetch_model rather than libfetch_config.
    libfetch_model "$HF/tokenizer.json" \
        "$dir/tokenizer.json" \
        "gemma tokenizer.json (30.7MiB)" \
        "cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f" || true

    echo "  ── config + tokenizer ──"
    libfetch_config "$HF/config.json"                    "$dir/config.json"
    libfetch_config "$HF/generation_config.json"         "$dir/generation_config.json"
    libfetch_config "$HF/model.safetensors.index.json"   "$dir/model.safetensors.index.json"
    libfetch_config "$HF/tokenizer_config.json"          "$dir/tokenizer_config.json"
    libfetch_config "$HF/processor_config.json"          "$dir/processor_config.json"
    # Gemma's chat template lives in its own file rather than inside
    # tokenizer_config.json; without it vLLM serves the model with no template
    # and every /v1/chat/completions request 400s.
    libfetch_config "$HF/chat_template.jinja"            "$dir/chat_template.jinja"
    echo "  [done] gemma config + tokenizer files"
}

# Report a leftover .git from the git-lfs era, without touching it.
#
# Not deleted automatically. The worktree files are what vLLM reads and what the
# checksums above just verified, but .git/lfs/objects holds a second copy of
# every shard and a wrong `rm` here costs the whole model — so this prints the
# command and lets a human run it.
_warn_stale_git_dir() {
    local dir="$1" name="$2"
    [[ -d "${dir}/.git" ]] || return 0

    local sz
    sz=$(du -sh "${dir}/.git" 2>/dev/null | cut -f1)
    echo ""
    log_warn "${name}: leftover .git from the old git-lfs downloader (${sz})."
    log_warn "  Nothing reads it any more — vLLM loads the plain files next to it."
    log_warn "  Reclaim the space when you are ready:"
    log_warn "    rm -rf '${dir}/.git'"
}

# Download one vLLM model into MODELS_DIR.
#
# Returns 0 unless the model name is unknown. Per-file failures are counted by
# libs/fetch.sh in LIBFETCH_FAILED and reported by the caller — this function
# deliberately does not stop at the first bad shard.
_download_vllm_model() {
    local model_name="$1"
    local entry="${VLLM_MODEL_REGISTRY[$model_name]}"
    local repo_id="${entry%%|*}"
    local rest="${entry#*|}"
    local local_dir="${rest%%|*}"
    local size_hint="${rest##*|}"
    local target_path="${MODELS_DIR}/${local_dir}"
    local t0=$SECONDS

    log_info "Downloading ${model_name} (${size_hint})..."
    log_info "  Repo:  https://huggingface.co/${repo_id}"
    log_info "  Local: ${target_path}"
    echo ""
    log_info "Files already present are hashed and skipped; the rest transfer over"
    log_info "16 connections. Ctrl-C is safe — partial data resumes on the next run."
    echo ""

    mkdir -p "$target_path" || {
        log_error "Cannot create ${target_path}"
        return 1
    }

    # Exported for libhttp_get, which attaches it as a bearer header for
    # huggingface.co only. Unset simply means the public endpoint.
    if [[ -n "${HF_TOKEN:-}" ]]; then
        export HF_TOKEN
    fi

    local before_failed=${LIBFETCH_FAILED}
    case "$model_name" in
        qwen)  _download_qwen  "$target_path" ;;
        gemma) _download_gemma "$target_path" ;;
        *)
            log_error "No manifest for '${model_name}'. Add a _download_${model_name}()."
            return 1
            ;;
    esac
    local model_failed=$((LIBFETCH_FAILED - before_failed))

    local elapsed=$((SECONDS - t0))
    echo ""
    if [[ $model_failed -gt 0 ]]; then
        log_error "${model_name}: ${model_failed} file(s) failed."
        log_error "  Re-run './paas-controller.sh prepare' — finished files skip, partial files resume."
    else
        log_info "${model_name} complete: ${target_path}"
        echo "  To use: docker compose --profile llm-${model_name} up -d"
    fi
    log_info "  On disk: $(du -sh "$target_path" 2>/dev/null | cut -f1)   Elapsed: $((elapsed / 60))m$((elapsed % 60))s"
    _warn_stale_git_dir "$target_path" "$model_name"
}

# Download every model in VLLM_MODEL_ORDER.
#
# Safe to re-run: each file is skipped when its sha256 already matches, so a
# second run on a finished model transfers nothing and only pays the hash read.
_download_all_vllm_models() {
    # Checked here rather than at source time. This file is sourced by
    # paas-controller.sh for every command, and aborting at source would take
    # down `status` and `logs` too — but this is the only function that moves
    # bytes, and it must not discover the missing binary 18 GiB in.
    libfetch_require || return 1

    local total=${#VLLM_MODEL_ORDER[@]}
    local i=0
    local t0=$SECONDS
    local start_failed=${LIBFETCH_FAILED}
    local start_done=${LIBFETCH_DOWNLOADED}
    local start_skipped=${LIBFETCH_SKIPPED}

    log_info "Preparing all ${total} vLLM models into ${MODELS_DIR}"
    local avail
    avail=$(df -h "${MODELS_DIR}" 2>/dev/null | awk 'NR==2{print $4}')
    [[ -n "$avail" ]] && log_info "Free space on target volume: ${avail} (need ~34GiB for all)"
    echo ""
    log_warn "Up to 34 GiB of transfers. aria2c uses 16 connections per file and"
    log_warn "resumes, so Ctrl-C costs only the current segment."
    if [[ -z "${HF_TOKEN:-}" ]]; then
        log_warn "HF_TOKEN not set in .env — fine for these public repos, required for gated ones."
    fi
    echo ""

    local name
    for name in "${VLLM_MODEL_ORDER[@]}"; do
        ((i++))
        echo "════════════════════════════════════════════════════════"
        log_info "[${i}/${total}] ${name}"
        echo "════════════════════════════════════════════════════════"
        _download_vllm_model "$name" || true
        echo ""
    done

    local elapsed=$((SECONDS - t0))
    local n_done=$((LIBFETCH_DOWNLOADED - start_done))
    local n_skip=$((LIBFETCH_SKIPPED - start_skipped))
    local n_fail=$((LIBFETCH_FAILED - start_failed))

    log_info "vLLM stage took $((elapsed / 3600))h$(( (elapsed % 3600) / 60 ))m."
    log_info "  downloaded ${n_done}   skipped ${n_skip}   failed ${n_fail}"

    # The tally is the verdict, not a per-model exit status: every libfetch_model
    # call above ends in `|| true`, so nothing else here knows a shard was lost.
    if [[ $n_fail -gt 0 ]]; then
        log_error "${n_fail} weight file(s) did not complete."
        log_error "Re-run './paas-controller.sh prepare' to resume — finished files skip."
        return 1
    fi

    log_info "All ${total} models ready."
    log_info "Start one (only one vLLM at a time — VRAM is exclusive):"
    for name in "${VLLM_MODEL_ORDER[@]}"; do
        echo "  docker compose --profile llm-${name} up -d vllm-${name}"
    done
}

# Show vLLM model info (installed + available). Downloading is handled by
# _download_all_vllm_models / _download_vllm_model.
prepare_vllm_info() {
    check_dir
    # Info mode: show current + available + download options
    local compose_file="${DOCKER_COMPOSE_FILE}"
    local current_model=""
    if [[ -f "$compose_file" ]]; then
        # Strip the trailing YAML comment, else it is printed as part of the path.
        current_model=$(awk '/- --model/{found=1; next} found && /^[[:space:]]*-/{gsub(/^[[:space:]]*-[[:space:]]*/,""); sub(/[[:space:]]*#.*$/,""); print; exit}' "$compose_file")
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

    # List installed model directories (exclude comfyui subdir)
    log_info "Installed models:"
    local found=false
    local i=1
    for d in "${MODELS_DIR}"/*/; do
        [[ -d "$d" ]] || continue
        local name
        name="$(basename "$d")"
        # Not vLLM models: these two are per-service trees under the same root.
        [[ "$name" == "comfyui" || "$name" == "idphoto" ]] && continue
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
        log_warn "No model directories found in ${MODELS_DIR} (excluding comfyui/ and idphoto/)."
    fi

    # Registry state, by shard count and apparent size.
    #
    # Size, not sha256, and the difference is stated in the output rather than
    # left for the reader to assume. `prepare` hashes every byte because it is
    # about to trust the file; `info` is a status line someone runs to look
    # around, and hashing 34 GiB to print it would take minutes. A file of the
    # right length whose contents are wrong therefore reads as [complete] here
    # and is still caught by the next prepare.
    echo ""
    log_info "Registry (sizes checked, not checksums — run prepare to verify):"
    local key
    for key in "${VLLM_MODEL_ORDER[@]}"; do
        local entry="${VLLM_MODEL_REGISTRY[$key]}"
        local repo_id="${entry%%|*}"
        local rest="${entry#*|}"
        local local_dir="${rest%%|*}"
        local size_hint="${rest##*|}"
        local dir="${MODELS_DIR}/${local_dir}"
        local state=""

        if [[ ! -d "$dir" ]]; then
            state="  [not downloaded]"
        else
            local want have
            want=$(_vllm_expected_shards "$key")
            have=$(_vllm_present_shards "$key" "$dir")
            if [[ "$have" -eq "$want" ]]; then
                state="  [complete — ${have}/${want} shards]"
            else
                state="  [partial — ${have}/${want} shards at full size]"
            fi
            [[ -d "${dir}/.git" ]] && state+=" [stale .git: $(du -sh "${dir}/.git" 2>/dev/null | cut -f1)]"
        fi
        echo "  ${key}  ${repo_id}  (${size_hint})${state}"
    done
    echo ""
    log_info "To switch models:"
    echo "  docker compose --profile llm-<name> up -d"
}

# Shard inventory for the info display.
#
# Kept beside the manifests they mirror, and deliberately dumb: a shard counts
# as present when its byte count matches exactly. The expected sizes come from
# the same HuggingFace tree API call as the checksums above.
_vllm_expected_shards() {
    case "$1" in
        qwen)  echo 5 ;;
        gemma) echo 5 ;;   # 4 weight shards + the LFS tokenizer.json
        *)     echo 0 ;;
    esac
}

_vllm_present_shards() {
    local key="$1" dir="$2" sizes=() n=0 spec path want got
    case "$key" in
        qwen) sizes=(
            "model-00001-of-00005.safetensors|3943575336"
            "model-00002-of-00005.safetensors|3980134208"
            "model-00003-of-00005.safetensors|3947411392"
            "model-00004-of-00005.safetensors|3980134240"
            "model-00005-of-00005.safetensors|3477738728"
        ) ;;
        gemma) sizes=(
            "model-00001-of-00004.safetensors|5369790400"
            "model-00002-of-00004.safetensors|5370207662"
            "model-00003-of-00004.safetensors|5362493774"
            "model-00004-of-00004.safetensors|1088853264"
            "tokenizer.json|32169626"
        ) ;;
        *) echo 0; return ;;
    esac

    for spec in "${sizes[@]}"; do
        path="${dir}/${spec%%|*}"
        want="${spec##*|}"
        # A .aria2 control file means aria2c is mid-transfer, and the apparent
        # size of a sparse file it is writing is close to final from the first
        # seconds — so the length alone would report an unfinished shard as done.
        libhttp_unfinished "$path" && continue
        got=$(libfileinfo_size "$path")
        [[ "$got" == "$want" ]] && ((n++))
    done
    echo "$n"
}

# prepare — no arguments. Prepares EVERYTHING:
#   Stage 1: every vLLM model in VLLM_MODEL_ORDER (aria2c + sha256, resume-safe)
#   Stage 2: idphoto host tree — clone + ONNX weights (small, so it runs before
#            the multi-hour ComfyUI stage)
#   Stage 3: ComfyUI preset models via the container's setup.sh
# Adding a new vLLM model = a line in VLLM_MODEL_REGISTRY, a line in
# VLLM_MODEL_ORDER, a _download_<name>() manifest, and its shard sizes in
# _vllm_expected_shards / _vllm_present_shards; `prepare` picks it up from there.
prepare() {
    if [[ $# -gt 0 ]]; then
        log_warn "prepare takes no arguments (ignoring: $*)"
        log_warn "It always prepares everything: all vLLM models + idphoto + ComfyUI presets."
        echo ""
    fi

    # Expose MODELS_PATH inside the repo before anything reads/writes models.
    ensure_models_link || return 1
    check_dir

    local rc=0

    prepare_vllm_info
    echo ""

    log_info "══ Stage 1/3: vLLM models ══"
    echo ""
    _download_all_vllm_models || rc=1

    echo ""
    log_info "══ Stage 2/3: idphoto (clone + ONNX weights) ══"
    echo ""
    prepare_idphoto || rc=1

    echo ""
    log_info "══ Stage 3/3: ComfyUI preset models ══"
    prepare_comfyui || rc=1

    echo ""
    if [[ $rc -ne 0 ]]; then
        log_error "prepare finished with errors — re-run './paas-controller.sh prepare' to resume."
    else
        log_info "prepare complete."
    fi
    return $rc
}

# `clean all` — strictly `clean data` + `clean model all`, nothing else.
# All safety lives in those two functions (warnings, confirmations, service stop,
# permission fixes), so the composite and the individual entry points can never
# drift apart. Each stage confirms separately; declining one skips only that stage.
clean_all() {
    check_dir

    log_warn "FULL CLEANUP = 'clean data' + 'clean model all'"
    echo "  - All runtime data in data/"
    echo "  - ALL models in ${MODELS_DIR} (including production models!)"
    echo "  - ${MODELS_DIR}/idphoto/ — HivisionIDPhotos clone + ONNX weights + pip cache"
    echo ""
    log_warn "Each stage asks for its own confirmation — answer 'n' to skip a stage."
    echo ""

    clean_data
    echo ""
    clean_models all
}

# `clean` command dispatcher — third-level targets: data | model | all
clean() {
    case "${1:-help}" in
        data)
            clean_data
            ;;
        model|models)
            case "${2:-interactive}" in
                interactive)
                    clean_models interactive
                    ;;
                all)
                    clean_models all
                    ;;
                *)
                    log_error "Unknown option for 'clean model': $2"
                    echo ""
                    show_clean_help
                    return 1
                    ;;
            esac
            ;;
        all)
            clean_all
            ;;
        help|--help|-h)
            show_clean_help
            ;;
        *)
            log_error "Unknown clean target: $1"
            echo ""
            show_clean_help
            return 1
            ;;
    esac
}

# Rebuild ComfyUI from scratch: wipe workdir → restart container → run setup.sh
# Preserves: models (skipped if checksums pass), git-tracked workflows & yaml
# Destroys:  comfyui_workdir (custom nodes, ComfyUI state), generated media
rebuild_comfyui() {
    check_dir

    echo ""
    log_warn "REBUILD ComfyUI — this will:"
    echo "  WIPE  : data/comfyui_workdir/  (custom nodes, ComfyUI internal state)"
    echo "  KEEP  : models/comfyui/        (model weights — skipped if checksums pass)"
    echo "  KEEP  : data/comfyui_workflows/ (git-tracked workflow JSONs and media)"
    echo "  KEEP  : data/comfyui_extra_model_paths.yaml"
    echo ""
    echo "  After wipe, setup.sh runs inside the container to:"
    echo "    - Re-clone all 5 custom nodes (ComfyUI-MuseTalk etc.)"
    echo "    - Download any missing models (~50 GB total, skips existing)"
    echo ""

    if ! confirm "Proceed with ComfyUI rebuild?"; then
        log_info "Rebuild cancelled."
        return 0
    fi

    # Step 1: Stop ComfyUI container
    log_info "Stopping ComfyUI container..."
    cd "${SCRIPT_DIR}"
    docker compose -f "${DOCKER_COMPOSE_FILE}" --profile comfyui stop comfyui 2>/dev/null || true
    if docker ps -a --format "{{.Names}}" | grep -q "^ai_comfyui$"; then
        docker rm ai_comfyui 2>/dev/null || true
    fi

    # Step 2: Wipe comfyui_workdir (custom nodes + ComfyUI state)
    local workdir="${DATA_DIR}/comfyui_workdir"
    if [[ -d "$workdir" ]]; then
        log_info "Wiping comfyui_workdir (fixing permissions first)..."
        fix_permissions "$workdir"
        rm -rf "${workdir:?}"
        log_info "comfyui_workdir wiped."
    fi
    mkdir -p "$workdir"

    # Step 3: Re-run prepare_comfyui (starts container + runs setup.sh)
    echo ""
    log_info "Launching container and running setup.sh..."
    prepare_comfyui
}