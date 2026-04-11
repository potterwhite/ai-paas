#!/bin/bash
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
        stop)
            stop_services
            ;;
        restart)
            restart_services
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