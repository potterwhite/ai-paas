# Copyright (c) 2026 PotterWhite
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# bash completion for paas-controller.sh
# Install: source this file, or add to ~/.bash_completion
# Usage: Add to ~/.bashrc: source /path/to/paas-controller-completion.bash

_paas_controller_completion() {
    local cur prev words cword
    _init_completion || return

    local commands="status start start-all stop stop-all restart restart-all logs prepare clean-data clean-models cleanall check-deps fix-permissions reset-router rebuild-comfyui disk-usage help"
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
