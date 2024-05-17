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

##################
# ZNAP PLUGIN MGR
##################

# Znap ZSH plugin manager
[[ -r ~/Repos/znap/znap.zsh ]] ||
    git clone --depth 1 -- \
        https://github.com/marlonrichert/zsh-snap.git ~/Repos/znap
source ~/Repos/znap/znap.zsh  # Start Znap

# Faster terminal startup, clean CLI
znap prompt sindresorhus/pure

# Znap install plugins
znap source zsh-users/zsh-autosuggestions
znap source zsh-users/zsh-syntax-highlighting
znap source zdharma-continuum/fast-syntax-highlighting
znap source marlonrichert/zsh-autocomplete

# Load pyenv automatically
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Load pyenv-virtualenv automatically
eval "$(pyenv virtualenv-init -)"

#########
# ALIASES
#########

# UDS
alias k="uds zarf tools kubectl"
alias kubectl="uds zarf tools kubectl"
alias zarf='uds zarf'
alias k9s='uds zarf tools monitor'
alias udsclean="uds zarf tools clear-cache && rm -rf ~/.uds-cache && rm -rf ~/.zarf-cache"

# Docker
alias dclean="docker system prune -a -f && docker volume prune -f"

# Git
alias gitup='find . -maxdepth 1 -type d -exec sh -c "(cd {} && [ -d .git ] && echo \"\nUpdating {}\n\" && git fetch && git pull)" ";"'
