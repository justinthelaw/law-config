###################
# LINUX OVERRIDES #
###################

# Prefer the per-user runtime dir for rootless tooling.
if [[ -d "/run/user/$UID" ]]; then
    export XDG_RUNTIME_DIR="/run/user/$UID"
elif [[ -d "/run/containerd" ]]; then
    export XDG_RUNTIME_DIR="/run/containerd"
fi

# Linux network helper.
alias ethernet="sudo ip link set eno0 up && sudo dhclient eno0"
