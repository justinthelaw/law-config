####################
# DEFAULT ZSH CONFIG
####################

source "${LAW_CONFIG_CONFIG_DIR}/zsh/env.zsh"

# Path to your oh-my-zsh installation.
export ZSH="${ZSH:-$HOME/.oh-my-zsh}"

# Disable for sindresorhus/pure
ZSH_THEME=""

plugins=(
    git
)

source "$ZSH/oh-my-zsh.sh"

#################
# ZNAP PLUGIN MGR
#################

# Znap ZSH plugin manager
typeset -g LAW_CONFIG_ZNAP_DIR="${LAW_CONFIG_ZNAP_DIR:-$HOME/Repos/znap}"
typeset -g LAW_CONFIG_ZNAP_REF="${LAW_CONFIG_ZNAP_REF:-25754a45d9ceafe6d7d082c9ebe40a08cb85a4f0}"

if [[ ! -r "$LAW_CONFIG_ZNAP_DIR/znap.zsh" ]]; then
    if command -v git >/dev/null 2>&1; then
        git clone --depth 1 -- https://github.com/marlonrichert/zsh-snap.git "$LAW_CONFIG_ZNAP_DIR"
        git -C "$LAW_CONFIG_ZNAP_DIR" fetch --depth 1 origin "$LAW_CONFIG_ZNAP_REF" >/dev/null 2>&1
        git -C "$LAW_CONFIG_ZNAP_DIR" checkout --detach "$LAW_CONFIG_ZNAP_REF" >/dev/null 2>&1
    else
        echo "law-config: git is required to install znap." >&2
    fi
fi

if [[ -r "$LAW_CONFIG_ZNAP_DIR/znap.zsh" ]]; then
    source "$LAW_CONFIG_ZNAP_DIR/znap.zsh" # Start Znap
else
    echo "law-config: znap was not installed; skipping znap plugins." >&2
    return
fi

# Faster terminal startup, clean CLI
znap prompt sindresorhus/pure

# Znap install plugins
znap source marlonrichert/zsh-autocomplete
znap source zsh-users/zsh-autosuggestions

autoload -Uz add-zsh-hook
_law_load_syntax_highlighting() {
    add-zsh-hook -d precmd _law_load_syntax_highlighting
    znap source zdharma-continuum/fast-syntax-highlighting
}
add-zsh-hook precmd _law_load_syntax_highlighting

#########
# ALIASES
#########

# Docker
alias dclean="docker system prune -a -f && docker volume prune -f"

# Git
gitup() {
    local dir

    for dir in ./*(/N); do
        [[ -d "$dir/.git" ]] || continue
        printf '\nUpdating %s\n\n' "$dir"
        git -C "$dir" fetch --all --prune && git -C "$dir" pull --ff-only
    done
}

gitclean() {
    local branch
    local current

    current="$(git branch --show-current)"
    git for-each-ref --format='%(refname:short)' refs/heads | while IFS= read -r branch; do
        case "$branch" in
            "$current" | main | master) continue ;;
        esac
        git branch -D -- "$branch"
    done
}

# VSCode
[[ -x "/snap/bin/code" ]] && alias code="/snap/bin/code"
