##########################
# SHARED ZSH ENVIRONMENT #
##########################

# Environment shared by interactive shells and non-interactive Codex command
# shells. Keep prompts, aliases, completion, and plugin setup out of this file.

typeset -g LAW_CONFIG_ZSH_DIR="${${(%):-%N}:A:h}"
typeset -g LAW_CONFIG_CONFIG_DIR="${LAW_CONFIG_ZSH_DIR:h}"
typeset -g LAW_CONFIG_ROOT="${LAW_CONFIG_CONFIG_DIR:h}"

if [[ -t 0 ]]; then
    export GPG_TTY="$(tty 2>/dev/null)"
fi

_law_path_append_unique() {
    local path_entry="$1"
    [[ -n "$path_entry" && -d "$path_entry" ]] || return
    case ":$PATH:" in
        *":$path_entry:"*) ;;
        *) export PATH="$PATH:$path_entry" ;;
    esac
}

if [[ -z "${NVM_DIR:-}" ]]; then
    if [[ -n "${XDG_CONFIG_HOME:-}" && -d "$XDG_CONFIG_HOME/nvm" ]]; then
        export NVM_DIR="$XDG_CONFIG_HOME/nvm"
    elif [[ -d "$HOME/.nvm" ]]; then
        export NVM_DIR="$HOME/.nvm"
    elif [[ -n "${XDG_CONFIG_HOME:-}" ]]; then
        export NVM_DIR="$XDG_CONFIG_HOME/nvm"
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

_law_runtime_dir_valid() {
    local directory="$1"
    local mode

    [[ -n "$directory" && -d "$directory" && -O "$directory" ]] || return 1
    if mode="$(stat -f %Lp "$directory" 2>/dev/null)"; then
        :
    elif mode="$(stat -c %a "$directory" 2>/dev/null)"; then
        :
    else
        return 1
    fi
    [[ "$mode" == 700 ]]
}

if [[ "$(uname -s)" == "Linux" ]]; then
    if ! _law_runtime_dir_valid "${XDG_RUNTIME_DIR:-}"; then
        if _law_runtime_dir_valid "/run/user/$UID"; then
            export XDG_RUNTIME_DIR="/run/user/$UID"
        else
            unset XDG_RUNTIME_DIR
        fi
    fi
fi

unset -f _law_path_append_unique
unset -f _law_runtime_dir_valid
unset ngc_dir
