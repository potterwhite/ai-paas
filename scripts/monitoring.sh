#!/bin/bash
# Logs & monitoring functions for ai-paas controller

# Source core functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/scripts/core.sh"

# Show logs for one or all containers
show_logs() {
    check_dir

    local containers=()
    if [[ "$1" == "all" || -z "$1" ]]; then
        # Get all ai-paas containers (running or stopped)
        while IFS= read -r name; do
            containers+=("$name")
        done < <(docker ps -a --filter "name=ai_" --format "{{.Names}}" | sort)
    else
        containers=("$1")
    fi

    if [[ ${#containers[@]} -eq 0 ]]; then
        log_warn "No ai-paas containers found."
        return
    fi

    # If only one container, just attach to its logs
    if [[ ${#containers[@]} -eq 1 ]]; then
        local container="${containers[0]}"
        if ! docker ps --filter "name=^${container}$" --format "{{.Names}}" | grep -q .; then
            log_warn "Container $container is not running. Showing last logs (--tail 100)."
            docker logs --tail 100 "$container" || log_error "Failed to get logs for $container"
        else
            log_info "Following logs for $container (Ctrl+C to stop)"
            docker logs -f --tail 50 "$container" || log_error "Failed to get logs for $container"
        fi
        return
    fi

    # Multiple containers: show a menu to select one, or show all in sequence
    echo ""
    log_info "Available containers:"
    local i=1
    for c in "${containers[@]}"; do
        echo "  [$i] $c"
        ((i++))
    done
    echo "  [a] All containers (show all logs sequentially)"
    echo ""
    read -p "Select container number or 'a' for all: " selection

    if [[ "$selection" == "a" || "$selection" == "A" ]]; then
        # Show all containers' logs, each with a header
        for c in "${containers[@]}"; do
            echo ""
            echo "═══════════════════════════════════════════════════════════════"
            echo "  Container: $c"
            echo "═══════════════════════════════════════════════════════════════"
            docker logs --tail 50 "$c" 2>&1 || echo "  (no logs or container not running)"
            echo ""

            read -p "Press Enter to continue to next container, or Ctrl+C to exit..."
        done
    elif [[ "$selection" =~ ^[0-9]+$ ]] && [[ "$selection" -ge 1 ]] && [[ "$selection" -le ${#containers[@]} ]]; then
        local selected="${containers[$((selection-1))]}"
        echo ""
        log_info "Following logs for $selected (Ctrl+C to stop)"
        docker logs -f --tail 50 "$selected" || log_error "Failed to get logs for $selected"
    else
        log_error "Invalid selection."
    fi
}

# Show disk usage
show_disk_usage() {
    echo "=== Disk Usage ==="
    echo "Project root:"
    du -sh "${SCRIPT_DIR}" 2>/dev/null || echo "  N/A"

    if [[ -d "${DATA_DIR}" ]]; then
        echo ""
        echo "Data directory:"
        du -sh "${DATA_DIR}"/* 2>/dev/null || echo "  Empty"
    fi

    if [[ -d "${MODELS_DIR}" ]]; then
        echo ""
        echo "Models directory:"
        du -sh "${MODELS_DIR}" 2>/dev/null || echo "  N/A"
        du -sh "${MODELS_DIR}"/* 2>/dev/null || echo "  Empty"
    fi
}

# Generic dependency check for all services
check_deps() {
    check_dir

    local has_issues=0
    local env_file="${SCRIPT_DIR}/.env"

    log_info "Checking system dependencies..."
    echo ""

    # 1. Check .env configuration
    echo "📋 Environment Configuration:"
    if [[ ! -f "${env_file}" ]]; then
        log_error "  .env file NOT FOUND"
        echo "    → Create it: cp .env.example .env && edit it"
        has_issues=1
    else
        log_info "  ✓ .env exists"
        # Check if MODELS_PATH is set and not commented/empty
        local models_path_line
        models_path_line=$(grep -E '^\s*MODELS_PATH=' "${env_file}" | head -1 || echo "")
        if [[ -z "$models_path_line" ]] || [[ "$models_path_line" =~ ^\s*# ]] || [[ "$models_path_line" =~ MODELS_PATH=$ ]] && [[ "$models_path_line" != *"/"* ]]; then
            log_warn "  ⚠ MODELS_PATH not properly set"
            echo "    → Set MODELS_PATH in .env (absolute host path)"
            has_issues=1
        else
            log_info "  ✓ MODELS_PATH configured"
        fi
        # Check default password
        if grep -q '^UI_PASSWORD=your-password\|^UI_PASSWORD=123' "${env_file}"; then
            log_warn "  ⚠ Using default UI_PASSWORD"
            echo "    → Recommend changing it"
        fi
    fi

    # 2. Check models directory
    echo ""
    echo "📦 Models Directory:"
    if [[ ! -d "${MODELS_DIR}" ]]; then
        log_warn "  ⚠ Models directory not found: ${MODELS_DIR}"
        echo "    → Will be created when needed"
    else
        log_info "  ✓ Models directory exists"
        local total_size
        total_size=$(du -sh "${MODELS_DIR}" 2>/dev/null | cut -f1 || echo "0")
        echo "    Total size: $total_size"

        # Check for vLLM required model
        local vllm_model="${MODELS_DIR}/qwen2.5-32b-instruct-awq"
        if [[ -d "$vllm_model" ]]; then
            if [[ -f "$vllm_model/config.json" ]]; then
                log_info "  ✓ vLLM model found: qwen2.5-32b-instruct-awq"
            else
                log_error "  ✗ vLLM model incomplete (missing config.json)"
                echo "    → Re-download the model"
                has_issues=1
            fi
        else
            log_error "  ✗ vLLM model NOT FOUND: qwen2.5-32b-instruct-awq"
            echo "    → Download from HuggingFace or adjust docker-compose --model argument"
            has_issues=1
        fi
    fi

    # 3. Check data directory
    echo ""
    echo "🗄️  Data Directory:"
    if [[ ! -d "${DATA_DIR}" ]]; then
        log_warn "  ⚠ Data directory not found: ${DATA_DIR}"
        echo "    → Will be created on first start"
    else
        log_info "  ✓ Data directory exists"
        local required_dirs=("router_db" "router_redis" "comfyui_workdir")
        for dir in "${required_dirs[@]}"; do
            if [[ -d "${DATA_DIR}/${dir}" ]]; then
                log_info "    ✓ ${dir}/ exists"
            else
                log_warn "    ⚠ ${dir}/ missing (will be created)"
            fi
        done
    fi

    # 4. Check Docker & docker-compose
    echo ""
    echo "🐳 Docker Environment:"
    if command -v docker &>/dev/null; then
        log_info "  ✓ docker CLI found"
        if docker ps &>/dev/null; then
            log_info "  ✓ Docker daemon accessible"
        else
            log_error "  ✗ Cannot connect to Docker daemon"
            echo "    → Start Docker service: systemctl start docker"
            has_issues=1
        fi
    else
        log_error "  ✗ docker CLI not found"
        echo "    → Install Docker: https://docs.docker.com/engine/install/"
        has_issues=1
    fi

    if command -v docker-compose &>/dev/null || docker compose version &>/dev/null; then
        log_info "  ✓ docker-compose available"
    else
        log_error "  ✗ docker-compose not found"
        has_issues=1
    fi

    # 5. Check NVIDIA GPU & drivers
    echo ""
    echo "🎮 GPU Environment:"
    if command -v nvidia-smi &>/dev/null; then
        log_info "  ✓ nvidia-smi available"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || log_warn "  ⚠ Could not query GPU info"
    else
        log_warn "  ⚠ nvidia-smi not found (NVIDIA drivers may not be installed)"
        echo "    → Install NVIDIA drivers for GPU support"
    fi

    # Summary
    echo ""
    if [[ $has_issues -eq 0 ]]; then
        log_info "All checks passed! ✓"
        echo "You should be able to start services with: $0 start"
    else
        log_error "Some dependencies are missing or misconfigured."
        echo "Please fix the issues above before starting services."
        return 1
    fi
}