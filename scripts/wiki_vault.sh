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
            echo -n "Vault path: "
            read -r vault_path
        else
            local vault_array=()
            while IFS= read -r vp; do
                [[ -n "$vp" ]] && vault_array+=("$vp")
            done <<< "$vaults"

            if [[ ${#vault_array[@]} -eq 1 ]]; then
                vault_path="${vault_array[0]}"
                log_info "Using vault: ${vault_path}"
            else
                echo ""
                echo "Select vault:"
                local idx=1
                for vp in "${vault_array[@]}"; do
                    echo "  ${idx}) ${vp}"
                    idx=$((idx + 1))
                done
                echo ""
                echo -n "Choice [1]: "
                read -r choice
                choice=${choice:-1}
                vault_path="${vault_array[$((choice - 1))]}"
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

    # Interactive time window if not specified
    if [[ ${#windows[@]} -eq 0 ]]; then
        echo ""
        echo "Time window (e.g. 22:00-06:30, or Enter for 24/7): "
        read -r window_input
        if [[ -n "$window_input" ]]; then
            windows+=("$window_input")
        fi
    fi

    # Interactive background mode if not specified
    if [[ -z "$bg_mode" ]]; then
        echo ""
        echo -n "Run in background? (Y/n): "
        read -r bg_answer
        bg_answer=${bg_answer:-Y}
        if [[ "$bg_answer" =~ ^[Yy] ]]; then
            bg_mode="yes"
        else
            bg_mode="no"
        fi
    fi

    # Build python command
    local cmd="python3 ${BATCH_SCRIPT} run --vault-path ${vault_path}"
    for w in "${windows[@]}"; do
        cmd+=" --window ${w}"
    done

    if [[ "$bg_mode" == "yes" ]]; then
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
