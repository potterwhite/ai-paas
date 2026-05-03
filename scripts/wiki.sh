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

# Wiki management functions for ai-paas controller

# Source core functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${SCRIPT_DIR}/scripts/core.sh"

# Schema source directory (where the template schema files live)
WIKI_SCHEMA_SOURCE="${SCRIPT_DIR}/docs/zh/3-highlights/wiki-schema"

# Initialize wiki structure in a vault
# Usage: init_wiki --vault-path <path> [--wiki-path <name>] [--schema-path <name>]
init_wiki() {
    local vault_path=""
    local wiki_path="_wiki"
    local schema_path="_schema"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --vault-path)
                vault_path="$2"
                shift 2
                ;;
            --wiki-path)
                wiki_path="$2"
                shift 2
                ;;
            --schema-path)
                schema_path="$2"
                shift 2
                ;;
            *)
                log_error "Unknown argument: $1"
                echo "Usage: $0 init-wiki --vault-path <path> [--wiki-path <name>] [--schema-path <name>]"
                return 1
                ;;
        esac
    done

    # Validate required arguments
    if [[ -z "$vault_path" ]]; then
        log_error "--vault-path is required"
        echo "Usage: $0 init-wiki --vault-path <path> [--wiki-path <name>] [--schema-path <name>]"
        return 1
    fi

    # Resolve to absolute path
    vault_path="$(cd "$vault_path" 2>/dev/null && pwd)" || {
        log_error "Vault path does not exist: $vault_path"
        return 1
    }

    local wiki_dir="${vault_path}/${wiki_path}"
    local schema_dir="${vault_path}/${schema_path}"

    log_info "Initializing Wiki in vault: ${vault_path}"
    log_info "  Wiki directory:   ${wiki_path}/"
    log_info "  Schema directory: ${schema_path}/"

    # Check if already initialized
    if [[ -d "$wiki_dir" ]] || [[ -d "$schema_dir" ]]; then
        log_warn "Wiki or schema directory already exists."
        if ! confirm "Overwrite existing initialization?"; then
            log_info "Cancelled."
            return 0
        fi
    fi

    # Create wiki directory structure
    log_info "Creating wiki directory structure..."
    mkdir -p "${wiki_dir}"/{entity,concept,source,synthesis,question}

    # Create schema directory
    log_info "Creating schema directory..."
    mkdir -p "${schema_dir}/templates"

    # Generate initial index.md
    log_info "Generating ${wiki_path}/index.md..."
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

## 领域

（待填充：运行 ingest 后自动生成）

## 技术概念

（待填充：运行 ingest 后自动生成）

## 最近文档

（待填充：运行 ingest 后自动生成）

## 综合分析

（待填充：运行 ingest 后自动生成）
INDEXEOF
    sed -i "s/__DATE__/$(date +%Y-%m-%d)/g" "${wiki_dir}/index.md"

    # Generate initial hot.md
    log_info "Generating ${wiki_path}/hot.md..."
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

    # Generate initial log.md
    log_info "Generating ${wiki_path}/log.md..."
    cat > "${wiki_dir}/log.md" << LOGEOF
# Wiki 操作日志

> 追加写入，不修改已有记录

## [$(date +%Y-%m-%d\ %H:%M)] init | Wiki 初始化
- 操作: 初始化 wiki 目录结构
- Wiki 路径: ${wiki_path}/
- Schema 路径: ${schema_path}/
LOGEOF

    # Copy schema files with path substitution
    if [[ -d "$WIKI_SCHEMA_SOURCE" ]]; then
        log_info "Copying schema files..."

        # Copy main schema files
        for schema_file in ingest.md query.md lint.md; do
            if [[ -f "${WIKI_SCHEMA_SOURCE}/${schema_file}" ]]; then
                sed "s|_wiki/|${wiki_path}/|g; s|_schema/|${schema_path}/|g" \
                    "${WIKI_SCHEMA_SOURCE}/${schema_file}" > "${schema_dir}/${schema_file}"
            fi
        done

        # Copy templates
        if [[ -d "${WIKI_SCHEMA_SOURCE}/templates" ]]; then
            for template_file in "${WIKI_SCHEMA_SOURCE}/templates/"*.md; do
                if [[ -f "$template_file" ]]; then
                    sed "s|_wiki/|${wiki_path}/|g; s|_schema/|${schema_path}/|g" \
                        "$template_file" > "${schema_dir}/templates/$(basename "$template_file")"
                fi
            done
        fi

        log_info "Schema files copied with path substitution."
    else
        log_warn "Schema source not found at ${WIKI_SCHEMA_SOURCE}"
        log_warn "Schema files not copied. You can manually add them to ${schema_path}/"
    fi

    # Summary
    echo ""
    log_info "Wiki initialization complete!"
    echo ""
    echo "  Directory structure:"
    echo "    ${vault_path}/"
    echo "    ├── ${wiki_path}/"
    echo "    │   ├── index.md"
    echo "    │   ├── hot.md"
    echo "    │   ├── log.md"
    echo "    │   ├── entity/"
    echo "    │   ├── concept/"
    echo "    │   ├── source/"
    echo "    │   ├── synthesis/"
    echo "    │   └── question/"
    echo "    └── ${schema_path}/"
    echo "        ├── ingest.md"
    echo "        ├── query.md"
    echo "        ├── lint.md"
    echo "        └── templates/"
    echo ""
    echo "  Next steps:"
    echo "    1. Review schema files in ${schema_path}/"
    echo "    2. Run ingest to populate wiki pages"
    echo "    3. Use query to ask questions against the wiki"
}
