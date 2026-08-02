###################
# LINUX OVERRIDES #
###################

# Linux network helper.
ethernet() {
    local interface="${1:-}"

    if [[ -z "$interface" ]]; then
        echo "Usage: ethernet <network-interface>" >&2
        return 2
    fi
    command -v ip >/dev/null 2>&1 || {
        echo "ethernet: ip command is required" >&2
        return 1
    }
    command -v dhclient >/dev/null 2>&1 || {
        echo "ethernet: dhclient command is required" >&2
        return 1
    }
    sudo ip link set "$interface" up && sudo dhclient "$interface"
}
