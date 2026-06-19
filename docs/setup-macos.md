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
node -v
npm -v
```

Use the default HTTPS nvm mirror settings unless a trusted internal mirror is required.

## GPG Configuration

```bash
mkdir -p ~/.gnupg
for file in configs/gpg/*.conf; do
  target="$HOME/.gnupg/$(basename "$file")"
  [[ -f "$target" ]] && cp "$target" "$target.bak.$(date +%s).$$"
  cp "$file" "$target"
done
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
