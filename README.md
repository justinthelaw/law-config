# Law-Config

Development system configurations for all of my devices, aptly named `law-*`.

## Pre-Requisites

At this point of the development system setup and configuration process, I should have already done the following:

1. Updated and security patched all base OS packages (git, e.g.)
2. Installed `Brave Browser` and added it to the sync-chain
3. Added the following basic packages:

```bash
# Zsh
sudo apt-get -y install zsh

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

All of the following instruction assume that you have cloned down this Git repository's source code and configuration files.

### Zsh and Oh-My-Zsh

Zsh and Oh-My-Zsh add a lot of functionality, and therefore it is important for me to set this up as soon as possible.

To use the pre-configured `.zshrc` in this repository, simply do the following:

```bash
# Install Oh-My-Zsh for Zsh
# Requires pre-req instructions here: https://ohmyz.sh/#install
# Requires pre-req instructions here: https://github.com/ohmyzsh/ohmyzsh/wiki
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Install Znap as your Zsh plugin manager
# Requires pre-req instructions here: https://github.com/marlonrichert/zsh-snap#installation
# INFO: feel free to change the `~/Repo/` location as you please
git clone --depth 1 -- \
        https://github.com/marlonrichert/zsh-snap.git ~/Repos/znap

# Add a singular pointer from your `.zshrc` to to this Git repository's `.zshrc`
# WARNING: this overwrites anything already in your existing `.zshrc`
# WARNING: you cannot delete this repository from your machine. else you wil lose the pointer
# INFO: Recommend using an absolute path to this repository
echo "source path/to/law-config/configs/.zshrc" > ~/.zshrc
```

### Git

The Git config in this repository contains some place holders for the user to replace. Once filled-in, you can copy the `.gitconfig` to your user's root directory, replacing the existing one.

The following assumes that you are within the root of this Git repository.

```bash
# Check on what needs to be filled in
cat configs/.gitconfig | grep INSERT

# Find your current `.gitconfig` location
git config --list --show-origin

# Copy the `.gitconfig` to your root directory
cp configs/.gitconfig path/to/user/root/directory

# Check to see the new settings are in place
git config --list
```
