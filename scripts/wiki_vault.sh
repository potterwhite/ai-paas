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

# Unified wiki vault management: init + ingest + status
# Replaces init-wiki and wiki-batch

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/scripts/core.sh"

WIKI_SCHEMA_SOURCE="${SCRIPT_DIR}/docs/zh/3-highlights/wiki-schema"
BATCH_SCRIPT="${SCRIPT_DIR}/scripts/wiki_batch.py"
LOG_DIR="${SCRIPT_DIR}/data"
ENV_FILE="${SCRIPT_DIR}/.env"

# ── Helpers ──────────────────────────────────────────────────────────────────

# Read .env value (simple key=value, no quotes handling needed for paths)
_read_env() {
    local key="$1"
    local default="$2"
    if [[ -f "$ENV_FILE" ]]; then
        local val
        val=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-)
        if [[ -n "$val" ]]; then
            echo "$val"
            return
        fi
    fi
    echo "$default"
}

# Get list of known vault paths from .env
_get_vaults() {
    local vaults_str
    vaults_str=$(_read_env "WIKI_VAULTS" "")
    if [[ -n "$vaults_str" ]]; then
        echo "$vaults_str" | tr ',' '\n'
    else
        # Fallback: check VAULT_PATH
        local vp
        vp=$(_read_env "VAULT_PATH" "")
        if [[ -n "$vp" ]]; then
            echo "$vp"
        fi
    fi
}

# Add a vault path to WIKI_VAULTS in .env
_register_vault() {
    local new_path="$1"
    local current
    current=$(_read_env "WIKI_VAULTS" "")

    if [[ -z "$current" ]]; then
        # First vault — also check if VAULT_PATH is set
        local vp
        vp=$(_read_env "VAULT_PATH" "")
        if [[ -n "$vp" && "$vp" != "$new_path" ]]; then
            current="$vp"
        fi
    fi

    # Check if already registered
    if echo "$current" | tr ',' '\n' | grep -qxF "$new_path"; then
        return
    fi

    local new_val
    if [[ -z "$current" ]]; then
        new_val="$new_path"
    else
        new_val="${current},${new_path}"
    fi

    if [[ -f "$ENV_FILE" ]]; then
        if grep -q "^WIKI_VAULTS=" "$ENV_FILE"; then
            sed -i "s|^WIKI_VAULTS=.*|WIKI_VAULTS=${new_val}|" "$ENV_FILE"
        else
            echo "WIKI_VAULTS=${new_val}" >> "$ENV_FILE"
        fi
    fi
}

# Check if wiki is initialized in a vault
_is_wiki_initialized() {
    local vault_path="$1"
    [[ -d "${vault_path}/_wiki" && -d "${vault_path}/_schema" ]]
}

# Initialize wiki structure in a vault (merged from init_wiki)
_init_wiki() {
    local vault_path="$1"
    local wiki_path="_wiki"
    local schema_path="_schema"
    local wiki_dir="${vault_path}/${wiki_path}"
    local schema_dir="${vault_path}/${schema_path}"

    log_info "Initializing wiki in: ${vault_path}"

    mkdir -p "${wiki_dir}"/{entity,concept,source,synthesis,question}
    mkdir -p "${schema_dir}/templates"

    # index.md
    cat > "${wiki_dir}/index.md" << 'INDEXEOF'
---
type: meta
title: "Wiki 知识库索引"
updated: __DATE__
tags: [wiki, ai-generated, meta]
status: evergreen
loa_min: 1
---

# Wiki 知识库索引

> 最后更新: __DATE__
> 总页面数: 0

## 项目

（待填充：运行 ingest 后自动生成）

## 技术概念

（待填充：运行 ingest 后自动生成）

## 源文档

（待填充：运行 ingest 后自动生成）

## 综合分析

（待填充：运行 ingest 后自动生成）

## 问答

（待填充：运行 ingest 后自动生成）
INDEXEOF
    sed -i "s/__DATE__/$(date +%Y-%m-%d)/g" "${wiki_dir}/index.md"

    # hot.md
    cat > "${wiki_dir}/hot.md" << 'HOTEOF'
---
type: meta
title: "Hot Cache"
updated: __DATE__
tags: [wiki, ai-generated, meta]
status: evergreen
loa_min: 1
---

# Hot Cache — 最近活跃内容

> 滚动窗口: 最近 7 天

## 本周重点

（待填充）

## 最近更新的项目

（待填充）

## 最近入库的文档

（待填充）

## 待处理

（待填充）
HOTEOF
    sed -i "s/__DATE__/$(date +%Y-%m-%d)/g" "${wiki_dir}/hot.md"

    # log.md
    cat > "${wiki_dir}/log.md" << LOGEOF
# Wiki 操作日志

> 追加写入，不修改已有记录

## [$(date +%Y-%m-%d\ %H:%M)] init | Wiki 初始化
- 操作: 初始化 wiki 目录结构
- Wiki 路径: ${wiki_path}/
- Schema 路径: ${schema_path}/
LOGEOF

    # Copy schema files
    if [[ -d "$WIKI_SCHEMA_SOURCE" ]]; then
        for schema_file in ingest.md query.md lint.md; do
            if [[ -f "${WIKI_SCHEMA_SOURCE}/${schema_file}" ]]; then
                sed "s|_wiki/|${wiki_path}/|g; s|_schema/|${schema_path}/|g" \
                    "${WIKI_SCHEMA_SOURCE}/${schema_file}" > "${schema_dir}/${schema_file}"
            fi
        done
        if [[ -d "${WIKI_SCHEMA_SOURCE}/templates" ]]; then
            for template_file in "${WIKI_SCHEMA_SOURCE}/templates/"*.md; do
                if [[ -f "$template_file" ]]; then
                    sed "s|_wiki/|${wiki_path}/|g; s|_schema/|${schema_path}/|g" \
                        "$template_file" > "${schema_dir}/templates/$(basename "$template_file")"
                fi
            done
        fi
        log_info "Schema files copied."
    else
        log_warn "Schema source not found at ${WIKI_SCHEMA_SOURCE}"
    fi

    log_info "Wiki initialized: ${wiki_dir}"
}

# ── Status ───────────────────────────────────────────────────────────────────

wiki_vault_status() {
    local vaults
    vaults=$(_get_vaults)

    if [[ -z "$vaults" ]]; then
        log_error "No vaults configured. Set VAULT_PATH or WIKI_VAULTS in .env"
        return 1
    fi

    local idx=1
    echo ""
    echo "Wiki Vaults"
    echo "=========================================="

    while IFS= read -r vp; do
        [[ -z "$vp" ]] && continue
        local status_icon state_file total processed pct

        if _is_wiki_initialized "$vp"; then
            state_file="${vp}/_wiki/batch_state.json"
            if [[ -f "$state_file" ]]; then
                total=$(python3 -c "import json; d=json.load(open('$state_file')); print(d.get('total',0))" 2>/dev/null || echo 0)
                processed=$(python3 -c "import json; d=json.load(open('$state_file')); print(d.get('processed',0))" 2>/dev/null || echo 0)
                if [[ "$total" -gt 0 ]]; then
                    pct=$((processed * 100 / total))
                else
                    pct=0
                fi
                status_icon="[${pct}%]"
            else
                total="?"
                processed="0"
                status_icon="[ready]"
            fi
        else
            total="-"
            processed="-"
            status_icon="[not init]"
        fi

        echo "  ${idx}) ${status_icon} ${vp}"
        echo "       Pages: ${processed}/${total}"
        idx=$((idx + 1))
    done <<< "$vaults"

    echo ""
}

# ── Run ──────────────────────────────────────────────────────────────────────

wiki_vault_run() {
    local vault_path=""
    local windows=()
    local bg_mode=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --vault-path)
                vault_path="$2"
                shift 2
                ;;
            --window)
                windows+=("$2")
                shift 2
                ;;
            --bg)
                bg_mode="yes"
                shift
                ;;
            --fg)
                bg_mode="no"
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                return 1
                ;;
        esac
    done

    # Interactive vault selection if not specified
    if [[ -z "$vault_path" ]]; then
        local vaults
        vaults=$(_get_vaults)

        if [[ -z "$vaults" ]]; then
            echo ""
            echo -n "Vault path: "
            read -r vault_path
        else
            local vault_array=()
            while IFS= read -r vp; do
                [[ -n "$vp" ]] && vault_array+=("$vp")
            done <<< "$vaults"

            echo ""
            echo "Select vault:"
            local idx=1
            for vp in "${vault_array[@]}"; do
                echo "  ${idx}) ${vp}"
                idx=$((idx + 1))
            done
            echo "  ${idx}) Custom path..."
            echo ""
            echo -n "Choice [1]: "
            read -r choice
            choice=${choice:-1}

            if [[ "$choice" == "$idx" ]]; then
                echo -n "Enter vault path: "
                read -r vault_path
            elif [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 && "$choice" -lt "$idx" ]]; then
                vault_path="${vault_array[$((choice - 1))]}"
            else
                log_error "Invalid choice: $choice"
                return 1
            fi
        fi
    fi

    # Validate vault path
    if [[ -z "$vault_path" ]]; then
        log_error "Vault path is required"
        return 1
    fi

    # Resolve to absolute path
    if [[ "$vault_path" = /* ]]; then
        : # already absolute
    else
        vault_path="$(cd "$vault_path" 2>/dev/null && pwd)" || {
            log_error "Vault path does not exist: $vault_path"
            return 1
        }
    fi

    if [[ ! -d "$vault_path" ]]; then
        log_error "Vault path does not exist: $vault_path"
        return 1
    fi

    # Register vault for future use
    _register_vault "$vault_path"

    # Auto-init if needed
    if ! _is_wiki_initialized "$vault_path"; then
        log_info "Wiki not initialized. Initializing..."
        _init_wiki "$vault_path"
    fi

    # Pre-flight: check RAG + LLM availability
    local rag_url
    rag_url=$(_read_env "RAG_BASE_URL" "http://localhost:8081")
    if ! curl -sf "${rag_url}/v1/health" >/dev/null 2>&1; then
        log_error "RAG service is not reachable at ${rag_url}"
        log_error "Start it first: docker compose up -d rag"
        return 1
    fi
    # Quick LLM probe: call router health directly
    local router_url
    router_url=$(_read_env "ROUTER_BASE_URL" "http://localhost:4000")
    if ! curl -sf "${router_url}/v1/health" >/dev/null 2>&1; then
        log_warn "Router is not reachable at ${router_url}. Ingest will fail if LLM is down."
    fi

    # Auto-disable WIKI_READ_ONLY for batch ingest
    # Use globals so the EXIT trap can access them after function returns
    _WIKI_RESTORE_RO="false"
    _WIKI_RAG_URL="${rag_url}"
    _WIKI_RAG_KEY="sk-rag-default"
    local wiki_status
    wiki_status=$(curl -sf "${rag_url}/v1/wiki/status" 2>/dev/null) || true
    if echo "$wiki_status" | grep -q '"read_only": true'; then
        _WIKI_RESTORE_RO="true"
        log_info "Wiki is in read-only mode. Temporarily disabling for batch ingest..."
        curl -sf -X POST "${rag_url}/v1/wiki/config" \
            -H "Authorization: Bearer ${_WIKI_RAG_KEY}" \
            -H "Content-Type: application/json" \
            -d '{"read_only": false}' >/dev/null 2>&1
        # Also sync .env
        if [[ -f "$ENV_FILE" ]]; then
            sed -i 's|^WIKI_READ_ONLY=true|WIKI_READ_ONLY=false|' "$ENV_FILE"
        fi
    fi

    # Auto-detect running vLLM model and sync WIKI_LLM_MODEL
    local wiki_llm_model
    wiki_llm_model=$(_read_env "WIKI_LLM_MODEL" "qwen")
    local active_model
    active_model=$(curl -sf "${router_url}/v1/models" \
        -H "Authorization: Bearer ${_WIKI_RAG_KEY}" 2>/dev/null \
        | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('active_model',''))" 2>/dev/null) || true
    if [[ -n "$active_model" && "$active_model" != "$wiki_llm_model" ]]; then
        log_warn "WIKI_LLM_MODEL (${wiki_llm_model}) != running model (${active_model}). Auto-switching..."
        # Update RAG runtime config
        curl -sf -X POST "${rag_url}/v1/wiki/config" \
            -H "Authorization: Bearer ${_WIKI_RAG_KEY}" \
            -H "Content-Type: application/json" \
            -d "{\"llm_model\": \"${active_model}\"}" >/dev/null 2>&1
        # Sync .env
        if [[ -f "$ENV_FILE" ]]; then
            sed -i "s|^WIKI_LLM_MODEL=.*|WIKI_LLM_MODEL=${active_model}|" "$ENV_FILE"
        fi
    fi

    # Interactive time window if not specified
    if [[ ${#windows[@]} -eq 0 ]]; then
        local now_hm
        now_hm=$(date +%H:%M)
        echo ""
        echo "Run only during specific hours? (e.g. off-peak electricity)"
        echo -n "Start time [${now_hm} = now, or Enter to run immediately]: "
        read -r win_start
        echo -n "End time [format HH:MM, e.g. 06:30, or Enter for no limit]: "
        read -r win_end
        if [[ -n "$win_start" && -n "$win_end" ]]; then
            windows+=("${win_start}-${win_end}")
            # Explain overnight windows
            local sh=${win_start%%:*} sm=${win_start##*:} eh=${win_end%%:*} em=${win_end##*:}
            local start_min=$((10#$sh * 60 + 10#$sm))
            local end_min=$((10#$eh * 60 + 10#$em))
            if [[ $start_min -gt $end_min ]]; then
                echo "  -> Overnight window: runs from ${win_start} to midnight, then midnight to ${win_end}"
            fi
        elif [[ -n "$win_end" ]]; then
            # Start now, end at specified time
            windows+=("${now_hm}-${win_end}")
            echo "  -> Runs from now (${now_hm}) until ${win_end}"
        fi
    fi

    # Interactive background mode if not specified
    if [[ -z "$bg_mode" ]]; then
        echo ""
        echo -n "Run in background? [Y/n]: "
        read -r bg_answer
        bg_answer=${bg_answer:-Y}
        if [[ "$bg_answer" =~ ^[Yy] ]]; then
            bg_mode="yes"
        else
            bg_mode="no"
        fi
    fi

    # Restore read-only mode on exit (normal or Ctrl+C)
    _restore_read_only() {
        if [[ "${_WIKI_RESTORE_RO:-false}" == "true" ]]; then
            log_info "Restoring wiki read-only mode..."
            curl -sf -X POST "${_WIKI_RAG_URL}/v1/wiki/config" \
                -H "Authorization: Bearer ${_WIKI_RAG_KEY}" \
                -H "Content-Type: application/json" \
                -d '{"read_only": true}' >/dev/null 2>&1
            if [[ -f "${SCRIPT_DIR}/.env" ]]; then
                sed -i 's|^WIKI_READ_ONLY=false|WIKI_READ_ONLY=true|' "${SCRIPT_DIR}/.env"
            fi
        fi
    }

    # Build python command
    local cmd="python3 ${BATCH_SCRIPT} run --vault-path ${vault_path}"
    for w in "${windows[@]}"; do
        cmd+=" --window ${w}"
    done

    if [[ "$bg_mode" == "yes" ]]; then
        # In background mode, pass restore info to the Python script
        # (shell trap won't work since the shell exits immediately)
        if [[ "${_WIKI_RESTORE_RO:-false}" == "true" ]]; then
            cmd+=" --restore-read-only"
        fi
        local log_file="${LOG_DIR}/wiki-batch.log"
        mkdir -p "$LOG_DIR"
        nohup $cmd >> "$log_file" 2>&1 &
        local pid=$!
        echo ""
        log_info "Running in background (PID: ${pid})"
        log_info "Log: ${log_file}"
        log_info "Check status: ./paas-controller.sh wiki-vault status"
        log_info "Stop: kill ${pid}"
    else
        trap _restore_read_only EXIT
        echo ""
        log_info "Running in foreground (Ctrl+C to stop)..."
        $cmd
    fi
}

# ── Reset ────────────────────────────────────────────────────────────────────

wiki_vault_reset() {
    local vault_path=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --vault-path)
                vault_path="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    # Interactive vault selection if not specified
    if [[ -z "$vault_path" ]]; then
        local vaults
        vaults=$(_get_vaults)
        local vault_array=()
        while IFS= read -r vp; do
            [[ -n "$vp" ]] && vault_array+=("$vp")
        done <<< "$vaults"

        if [[ ${#vault_array[@]} -eq 1 ]]; then
            vault_path="${vault_array[0]}"
        elif [[ ${#vault_array[@]} -gt 1 ]]; then
            echo "Select vault to reset:"
            local idx=1
            for vp in "${vault_array[@]}"; do
                echo "  ${idx}) ${vp}"
                idx=$((idx + 1))
            done
            echo -n "Choice [1]: "
            read -r choice
            choice=${choice:-1}
            vault_path="${vault_array[$((choice - 1))]}"
        fi
    fi

    if [[ -z "$vault_path" ]]; then
        log_error "Vault path is required"
        return 1
    fi

    python3 "$BATCH_SCRIPT" reset --vault-path "$vault_path"
}

# ── Main dispatcher ─────────────────────────────────────────────────────────

wiki_vault() {
    local subcmd="${1:-help}"
    shift 2>/dev/null || true

    case "$subcmd" in
        status)
            wiki_vault_status
            ;;
        run)
            wiki_vault_run "$@"
            ;;
        reset)
            wiki_vault_reset "$@"
            ;;
        help|--help|-h)
            echo "Usage: wiki-vault <command>"
            echo ""
            echo "Commands:"
            echo "  status              Show all vaults and ingest progress"
            echo "  run [--vault-path P] [--window HH:MM-HH:MM] [--bg|--fg]"
            echo "                      Initialize (if needed) and start batch ingest"
            echo "  reset [--vault-path P]"
            echo "                      Reset batch progress for a vault"
            echo ""
            echo "Interactive mode: run without arguments for guided setup."
            ;;
        *)
            log_error "Unknown wiki-vault command: $subcmd"
            echo "Run 'wiki-vault help' for usage."
            return 1
            ;;
    esac
}
