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
typeset -g LAW_CONFIG_ZNAP_REF="${LAW_CONFIG_ZNAP_REF:-7a954d507c02269e0c42737a460e5a94dc9b2992}"

_law_znap_at_pinned_ref() {
    [[ -r "$LAW_CONFIG_ZNAP_DIR/znap.zsh" ]] || return 1
    [[ "$(git -C "$LAW_CONFIG_ZNAP_DIR" rev-parse HEAD 2>/dev/null)" == "$LAW_CONFIG_ZNAP_REF" ]]
}

if ! _law_znap_at_pinned_ref; then
    if ! command -v git >/dev/null 2>&1; then
        echo "law-config: git is required to install znap." >&2
    elif [[ ! -e "$LAW_CONFIG_ZNAP_DIR" ]]; then
        mkdir -p "${LAW_CONFIG_ZNAP_DIR:h}" &&
            git clone --no-checkout --filter=blob:none -- https://github.com/marlonrichert/zsh-snap.git "$LAW_CONFIG_ZNAP_DIR" >/dev/null 2>&1 &&
            git -C "$LAW_CONFIG_ZNAP_DIR" fetch --depth 1 origin "$LAW_CONFIG_ZNAP_REF" >/dev/null 2>&1 &&
            git -C "$LAW_CONFIG_ZNAP_DIR" checkout --detach "$LAW_CONFIG_ZNAP_REF" >/dev/null 2>&1 ||
            echo "law-config: unable to install the pinned znap revision." >&2
    elif [[ -d "$LAW_CONFIG_ZNAP_DIR/.git" ]]; then
        git -C "$LAW_CONFIG_ZNAP_DIR" fetch --depth 1 origin "$LAW_CONFIG_ZNAP_REF" >/dev/null 2>&1 &&
            git -C "$LAW_CONFIG_ZNAP_DIR" checkout --detach "$LAW_CONFIG_ZNAP_REF" >/dev/null 2>&1 ||
            echo "law-config: unable to select the pinned znap revision." >&2
    else
        echo "law-config: znap path exists but is not a Git checkout: $LAW_CONFIG_ZNAP_DIR" >&2
    fi
fi

if _law_znap_at_pinned_ref; then
    source "$LAW_CONFIG_ZNAP_DIR/znap.zsh" # Start Znap

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
else
    echo "law-config: pinned znap revision is unavailable; skipping znap plugins." >&2
fi
unset -f _law_znap_at_pinned_ref

#########
# ALIASES
#########

# Docker: retain Docker's interactive confirmation and preserve volumes.
alias dclean="docker system prune"

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
        git branch -d -- "$branch"
    done
}

# VSCode
[[ -x "/snap/bin/code" ]] && alias code="/snap/bin/code"
