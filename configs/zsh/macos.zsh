###################
# MACOS OVERRIDES #
###################

export GPG_TTY="$(tty)"
if command -v gpgconf >/dev/null 2>&1; then
    gpgconf --launch gpg-agent >/dev/null 2>&1
fi
