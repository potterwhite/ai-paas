# bash completion for paas-controller.sh
# Install: source this file, or add to ~/.bash_completion
# Usage: Add to ~/.bashrc: source /path/to/paas-controller-completion.bash

_paas_controller_completion() {
    local cur prev words cword
    _init_completion || return

    local commands="status start stop restart logs prepare clean-data clean-models cleanall check-deps fix-permissions reset-router disk-usage help"
    local log_containers="ai_vllm ai_litellm ai_whisper ai_webapp ai_comfyui ai_router ai_router_redis all"
    local prepare_subcommands="comfyui vllm"

    # If first word, suggest commands
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    # Second word depends on first command
    case "${words[1]}" in
        logs|log)
            COMPREPLY=( $(compgen -W "$log_containers" -- "$cur") )
            ;;
        prepare)
            COMPREPLY=( $(compgen -W "$prepare_subcommands" -- "$cur") )
            ;;
        *)
            # No completion for other commands
            COMPREPLY=()
            ;;
    esac
}

complete -F _paas_controller_completion paas-controller.sh
complete -F _paas_controller_completion ./paas-controller.sh
