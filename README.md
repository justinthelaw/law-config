# Law-Config

Development system configurations for all of my devices, aptly named `law-*`.

## Pre-Requisites

At this point of the development system setup and configuration process, I should have already done the following:

1. Updated and security patched all base OS packages (git, e.g.)
2. Installed `Brave Browser` and added it to the sync-chain
3. Added the following basic packages:

```bash
# cURL is required for some of the later pre-req instructions
sudo apt-get -y install curl

# Python, NVIDIA CUDA, Rust, C++, Znap, etc. essentials
sudo apt-get -y install build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev curl \
libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

# Virtual machine and emulation management
sudo apt-get -y install libvirt-daemon-system libvirt-clients qemu-kvm qemu-utils virt-manager ovmf 

# Containerization tooling and capability
# Requires pre-req instructions here: https://docs.docker.com/engine/install/
sudo apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# NVIDIA CUDA toolkit
# Requires pre-req instructions here: https://developer.nvidia.com/cuda-downloads
sudo apt-get -y install cuda

# NVIDIA Container Toolkit
# Requires pre-req instructions here: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
sudo apt-get -y install nvidia-container-toolkit

# Tailscale for teams
# Requires pre-req instructions here: https://tailscale.com/download/linux
sudo apt-get -y install tailscale
```

4. Enabled `ufw`, ensuring `tailscale` and `ssh` are in traffic rules
5. Connected to team's nodes and network on `tailscale`

## Usage

### Zsh and Oh-My-Zsh

Zsh and Oh-My-Zsh add a lot of functionality, and therefore it is important for me to set this up as soon as possible.
