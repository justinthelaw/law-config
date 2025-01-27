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

source $ZSH/oh-my-zsh.sh

#################
# ZNAP PLUGIN MGR
#################

# Znap ZSH plugin manager
[[ -r ~/Repos/znap/znap.zsh ]] ||
    git clone --depth 1 -- \
        https://github.com/marlonrichert/zsh-snap.git ~/Repos/znap
source ~/Repos/znap/znap.zsh # Start Znap

# Faster terminal startup, clean CLI
znap prompt sindresorhus/pure

# Znap install plugins
znap source zsh-users/zsh-autosuggestions
znap source zsh-users/zsh-syntax-highlighting
znap source zdharma-continuum/fast-syntax-highlighting
znap source marlonrichert/zsh-autocomplete

#######
# PYENV
#######

# Load pyenv automatically
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Load pyenv-virtualenv automatically
eval "$(pyenv virtualenv-init -)"

######
# NVM
######

export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"                   # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion" # This loads nvm bash_completion

#####
# GO
#####

export PATH=$PATH:/usr/local/go/bin

#################
# ROOTLESS DOCKER
#################

export XDG_RUNTIME_DIR=/run/user/$UID

############
# CONTAINERD
############

export XDG_RUNTIME_DIR=/run/containerd

#########
# ALIASES
#########

# UDS
alias k="uds zarf tools kubectl"
alias kubectl="uds zarf tools kubectl"
alias zarf='uds zarf'
alias k9s='uds zarf tools monitor'
alias udsclean="uds zarf tools clear-cache && rm -rf ~/.uds-cache && rm -rf /tmp/zarf-*"

# Docker
alias dclean="docker system prune -a -f && docker volume prune -f"

# Git
alias gitup='find . -maxdepth 1 -type d -exec sh -c "(cd {} && [ -d .git ] && echo \"\nUpdating {}\n\" && git fetch && git pull)" ";"'

# VSCode
alias code="/snap/bin/code"

# MacOS
export GPG_TTY=$(tty)
gpgconf --launch gpg-agent
