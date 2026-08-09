# Linux Setup

## Base Packages

```bash
sudo apt-get update
sudo apt-get -y install zsh curl git gnupg iproute2 isc-dhcp-client
sudo apt-get -y install build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev \
  libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
sudo apt-get -y install libvirt-daemon-system libvirt-clients qemu-kvm qemu-utils ovmf
```

For graphical virtual-machine management on a desktop host, install
`virt-manager` separately:

```bash
sudo apt-get -y install virt-manager
```

## Clone the Repository

```bash
mkdir -p ~/Repos
git clone https://github.com/justinthelaw/law-config.git ~/Repos/law-config
cd ~/Repos/law-config
```

## GPG Configuration

```bash
mkdir -p ~/.gnupg
for file in configs/gpg/*.conf; do
  target="$HOME/.gnupg/$(basename "$file")"
  [[ -f "$target" ]] && cp "$target" "$target.bak.$(date +%s).$$"
  install -m 600 "$file" "$target"
done
chmod 700 ~/.gnupg
```

## Container, GPU, and Network Tooling

- Docker Engine install: <https://docs.docker.com/engine/install/ubuntu/>
- CUDA install: <https://developer.nvidia.com/cuda-downloads>
- NVIDIA Container Toolkit install: <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>
- Tailscale install: <https://tailscale.com/download/linux>

Run the official Docker, CUDA, NVIDIA Container Toolkit, and Tailscale repository setup steps before installing the packages below.

```bash
sudo apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo apt-get -y install cuda
sudo apt-get -y install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
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
uv python pin --global 3.14
```

Create virtual environments inside individual projects with `uv venv`; do not create one in this configuration repository.

## Node.js via nvm

```bash
export NVM_DIR="${XDG_CONFIG_HOME:-$HOME/.nvm}"
[[ -z "${XDG_CONFIG_HOME:-}" ]] || NVM_DIR="$XDG_CONFIG_HOME/nvm"
PROFILE=/dev/null bash -c 'curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.6/install.sh | bash'
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

Before using Docker without `sudo`, follow Docker's [post-install steps](https://docs.docker.com/engine/install/linux-postinstall/). Use a personal access token on headless systems and configure a Docker credential store so credentials are not left base64-encoded in `~/.docker/config.json`; see the [Docker login documentation](https://docs.docker.com/reference/cli/docker/login/).
