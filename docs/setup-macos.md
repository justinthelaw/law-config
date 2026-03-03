# macOS Setup

## Base Packages

```bash
brew install --cask brave-browser tailscale
brew install go gpg uv
```

- Tailscale docs: <https://tailscale.com/download/macos>
- Python (uv) docs: <https://docs.astral.sh/uv/getting-started/installation/>
- Go docs: <https://go.dev/doc/install>
- Node/NVM docs: <https://github.com/nvm-sh/nvm>

## Python via uv (Preferred)

```bash
uv python install 3.12
uv python pin 3.12
uv venv
```

## Node.js via nvm

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm install --lts
nvm alias default 'lts/*'
nvm use --lts
node -v
npm -v
```

## GPG Configuration

```bash
mkdir -p ~/.gnupg
cp configs/gpg/*.conf ~/.gnupg/
chown -R "$(whoami)" ~/.gnupg/
chmod 600 ~/.gnupg/*
chmod 700 ~/.gnupg
```

## Container and Registry Tooling

### Install Rancher Desktop

```bash
brew install --cask rancher
```

### Registry Login

```bash
docker login ghcr.io
docker login
```
