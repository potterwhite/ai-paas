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

# ai-paas Controller Script - Modular version organized by help categories
# Provides safe operations for data cleanup, model management, and system maintenance

# Set error handling
set -euo pipefail

# Source all modular components organized by help category
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/scripts/core.sh"
source "${SCRIPT_DIR}/scripts/service.sh"
source "${SCRIPT_DIR}/scripts/monitoring.sh"
source "${SCRIPT_DIR}/scripts/data_models.sh"
source "${SCRIPT_DIR}/scripts/maintenance.sh"

# Main command dispatcher
main() {
    check_dir

    case "${1:-help}" in
        status)
            show_containers
            check_deps 2>/dev/null || true
            ;;
        logs|log)
            shift
            show_logs "$@"
            ;;
        start)
            start_services
            ;;
        start-all)
            start_all_services
            ;;
        stop)
            stop_services
            ;;
        stop-all)
            stop_all_services
            ;;
        restart)
            restart_services
            ;;
        restart-all)
            restart_all_services
            ;;
        clean-data)
            clean_data
            ;;
        clean-models)
            clean_models
            ;;
        cleanall)
            cleanall
            ;;
        check-deps)
            check_deps
            ;;
        disk-usage)
            show_disk_usage
            ;;
        prepare)
            shift
            prepare "$@"
            ;;
        rebuild-comfyui)
            rebuild_comfyui
            ;;
        fix-permissions)
            fix_permissions
            ;;
        reset-router)
            reset_router
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"