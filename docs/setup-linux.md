# Linux Setup

## Base Packages

```bash
sudo apt-get -y install zsh curl
sudo apt-get -y install build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev \
  libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
sudo apt-get -y install libvirt-daemon-system libvirt-clients qemu-kvm qemu-utils virt-manager ovmf
```

## Container, GPU, and Network Tooling

- Docker Engine install: <https://docs.docker.com/engine/install/>
- CUDA install: <https://developer.nvidia.com/cuda-downloads>
- NVIDIA Container Toolkit install: <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>
- Tailscale install: <https://tailscale.com/download/linux>

Run the official Docker, CUDA, NVIDIA Container Toolkit, and Tailscale repository setup steps before installing the packages below.

```bash
sudo apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo apt-get -y install cuda
sudo apt-get -y install nvidia-container-toolkit
sudo apt-get -y install tailscale
sudo tailscale login
sudo tailscale up
```

## Dev Tools

- Python (uv) docs: <https://docs.astral.sh/uv/getting-started/installation/>
- Go install docs: <https://go.dev/doc/install>
- Node/NVM docs: <https://github.com/nvm-sh/nvm>

## Python via uv (Preferred)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After opening a new shell:

```bash
uv python install 3.14
uv python pin 3.14
uv venv
```

## Node.js via nvm

```bash
PROFILE=/dev/null bash -c 'curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.5/install.sh | bash'
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm install --lts
nvm alias default 'lts/*'
nvm use --lts
npm install --global npm@latest
node -v
npm -v
```

Use the default HTTPS nvm mirror settings unless a trusted internal mirror is required.

## Registry Login

```bash
docker login ghcr.io
docker login
```
