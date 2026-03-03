#########################
# LAW CONFIG ENTRYPOINT #
#########################

# Prevent duplicate loading when this file is sourced more than once.
if [[ -n "${LAW_CONFIG_LOADED:-}" ]]; then
    return
fi
typeset -g LAW_CONFIG_LOADED=1

# Resolve paths relative to this repository.
typeset -g LAW_CONFIG_CONFIG_DIR="${${(%):-%N}:A:h}"
typeset -g LAW_CONFIG_ROOT="${LAW_CONFIG_CONFIG_DIR:h}"

source "${LAW_CONFIG_CONFIG_DIR}/zsh/common.zsh"

case "$(uname -s)" in
    Darwin)
        source "${LAW_CONFIG_CONFIG_DIR}/zsh/macos.zsh"
        ;;
    Linux)
        source "${LAW_CONFIG_CONFIG_DIR}/zsh/linux.zsh"
        ;;
    *)
        echo "law-config: unsupported OS; loaded common zsh settings only." >&2
        ;;
esac
