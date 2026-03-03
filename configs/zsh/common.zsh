####################
# DEFAULT ZSH CONFIG
####################

# Path to your oh-my-zsh installation.
export ZSH="$HOME/.oh-my-zsh"

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
[[ -r "$HOME/Repos/znap/znap.zsh" ]] ||
    git clone --depth 1 -- \
        https://github.com/marlonrichert/zsh-snap.git "$HOME/Repos/znap"
source "$HOME/Repos/znap/znap.zsh" # Start Znap

# Faster terminal startup, clean CLI
znap prompt sindresorhus/pure

# Znap install plugins
znap source zsh-users/zsh-autosuggestions
znap source zsh-users/zsh-syntax-highlighting
znap source zdharma-continuum/fast-syntax-highlighting
znap source marlonrichert/zsh-autocomplete

######
# NVM
######

if [[ -z "${NVM_DIR:-}" ]]; then
    if [[ -d "$HOME/.nvm" ]]; then
        export NVM_DIR="$HOME/.nvm"
    elif [[ -d "$HOME/.config/nvm" ]]; then
        export NVM_DIR="$HOME/.config/nvm"
    else
        export NVM_DIR="$HOME/.nvm"
    fi
fi
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"                   # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion" # This loads nvm bash_completion

#####
# GO
#####

[[ -d "/usr/local/go/bin" ]] && export PATH="$PATH:/usr/local/go/bin"

######
# NVCR
######

for ngc_dir in "${NGC_CLI_DIR:-}" "$HOME/dev/ngc-cli" "/root/dev/ngc-cli"; do
    if [[ -n "$ngc_dir" && -d "$ngc_dir" ]]; then
        export PATH="$PATH:$ngc_dir"
        break
    fi
done

#####
# LAW
#####

if [[ -n "${LAW_CONFIG_ROOT:-}" && -d "${LAW_CONFIG_ROOT}/scripts" ]]; then
    export PATH="$PATH:${LAW_CONFIG_ROOT}/scripts"
fi

#########
# ALIASES
#########

# Docker
alias dclean="docker system prune -a -f && docker volume prune -f"

# Git
alias gitup='find . -maxdepth 1 -type d -exec sh -c "(cd {} && [ -d .git ] && echo \"\nUpdating {}\n\" && git fetch && git pull)" ";"'
alias gitclean='git branch | grep -vE "^\*|main|master" | awk "{print \$1}" | xargs -n 1 git branch -D'

# VSCode
[[ -x "/snap/bin/code" ]] && alias code="/snap/bin/code"

# Cleaning
if [[ -d "$HOME/.cache" ]]; then
    alias cacheclean="find ~/.cache/ -type f -atime +7 ! -path '*pre-commit*' ! -path '*uv*' -delete"
elif [[ -d "$HOME/Library/Caches" ]]; then
    alias cacheclean="find ~/Library/Caches/ -type f -atime +7 ! -path '*pre-commit*' ! -path '*uv*' -delete"
fi
