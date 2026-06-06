##########################
# SHARED ZSH ENVIRONMENT #
##########################

# Environment shared by interactive shells and non-interactive Codex command
# shells. Keep prompts, aliases, completion, and plugin setup out of this file.

typeset -g LAW_CONFIG_ZSH_DIR="${${(%):-%N}:A:h}"
typeset -g LAW_CONFIG_CONFIG_DIR="${LAW_CONFIG_ZSH_DIR:h}"
typeset -g LAW_CONFIG_ROOT="${LAW_CONFIG_CONFIG_DIR:h}"

_law_path_append_unique() {
    local path_entry="$1"
    [[ -n "$path_entry" && -d "$path_entry" ]] || return
    case ":$PATH:" in
        *":$path_entry:"*) ;;
        *) export PATH="$PATH:$path_entry" ;;
    esac
}

if [[ -z "${NVM_DIR:-}" ]]; then
    if [[ -d "$HOME/.nvm" ]]; then
        export NVM_DIR="$HOME/.nvm"
    elif [[ -d "$HOME/.config/nvm" ]]; then
        export NVM_DIR="$HOME/.config/nvm"
    else
        export NVM_DIR="$HOME/.nvm"
    fi
fi
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && . "$NVM_DIR/bash_completion"

_law_path_append_unique "/usr/local/go/bin"

for ngc_dir in "${NGC_CLI_DIR:-}" "$HOME/dev/ngc-cli" "/root/dev/ngc-cli"; do
    if [[ -n "$ngc_dir" && -d "$ngc_dir" ]]; then
        _law_path_append_unique "$ngc_dir"
        break
    fi
done

_law_path_append_unique "$LAW_CONFIG_ROOT/scripts"

if [[ "$(uname -s)" == "Linux" ]]; then
    if [[ -d "/run/user/$UID" ]]; then
        export XDG_RUNTIME_DIR="/run/user/$UID"
    elif [[ -d "/run/containerd" ]]; then
        export XDG_RUNTIME_DIR="/run/containerd"
    fi
fi

unset -f _law_path_append_unique
unset ngc_dir
