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
# Read instructions here: https://docs.docker.com/engine/install/
sudo apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# NVIDIA CUDA toolkit
# Read instructions here: https://developer.nvidia.com/cuda-downloads
sudo apt-get -y install cuda

# NVIDIA Container Toolkit
# Read instructions here: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
sudo apt-get -y install nvidia-container-toolkit

# Tailscale for teams
# Read instructions here: https://tailscale.com/download/linux
sudo apt-get -y install tailscale
```

4. Enabled `ufw`, ensuring `tailscale` and `ssh` are in traffic rules
5. Connected to team's `tailscale` and approved device on the network

```bash
# Login to tailscale with your email
sudo tailscale login

# Add device to the network, with optional flags and capabilities, e.g. SSH access
sudo tailscale up # --ssh
```

## Usage

All of the following instruction assume that you have cloned down this Git repository's source code and configuration files.

### Zsh and Oh-My-Zsh

Zsh and Oh-My-Zsh add a lot of functionality, and therefore it is important for me to set this up as soon as possible.

To use the pre-configured `.zshrc` in this repository, simply do the following:

```bash
# Install Oh-My-Zsh for Zsh
# Read instructions here: https://ohmyz.sh/#install
# Read instructions here: https://github.com/ohmyzsh/ohmyzsh/wiki
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Install Znap as your Zsh plugin manager
# Read instructions here: https://github.com/marlonrichert/zsh-snap#installation
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

# Copy the `.gitconfig` to your desired root directory
cp configs/.gitconfig path/to/user/root/directory

# Check to see the new settings are in place
git config --list
```

### Remote Registries

Logging in to the following registries is recommended:

```bash
# use your username and harbor key
docker login registry1.dso.mil

# use your username and self-generated PAT
docker login ghcr.io

# use your username and password
docker login
```

### PyEnv

PyEnv is an single-purpose utility that enables easy management of Python versions and virtual environments.

```bash
# Read instructions here: https://github.com/pyenv/pyenv?tab=readme-ov-file#getting-pyenv
curl https://pyenv.run | bash

# Add the following to your shell's *rc
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc

# Reactivate shell
source ~/.zshrc
```

### UDS Development

The following are minimal dependencies for Unicorn Delivery Service (UDS) development:

```bash
# Download and install latest UDS CLI: https://github.com/defenseunicorns/uds-cli/releases
# INFO: requires your `sudo` password
wget -O uds https://github.com/defenseunicorns/uds-cli/releases/download/v0.10.4/uds-cli_v0.10.4_Linux_amd64 && \
        sudo chmod +x uds && \
        sudo mv uds /usr/local/bin/

# Download and install K3d according to this restriction: https://github.com/defenseunicorns/uds-core#prerequisites
# Read instructions here: https://k3d.io/v5.6.3/#install-script
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
```
