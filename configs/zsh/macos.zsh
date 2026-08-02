###################
# MACOS OVERRIDES #
###################

if [[ -t 0 ]]; then
    export GPG_TTY="$(tty 2>/dev/null)"
fi
if command -v gpgconf >/dev/null 2>&1; then
    gpgconf --launch gpg-agent >/dev/null 2>&1
fi
