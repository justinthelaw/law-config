# macOS Setup

## Base Packages

```bash
brew install --cask brave-browser tailscale-app
brew install git gnupg go uv
```

- Tailscale docs: <https://tailscale.com/download/macos>
- Python (uv) docs: <https://docs.astral.sh/uv/getting-started/installation/>
- Go docs: <https://go.dev/doc/install>
- Node/NVM docs: <https://github.com/nvm-sh/nvm>

## Clone the Repository

```bash
mkdir -p ~/Repos
git clone https://github.com/justinthelaw/law-config.git ~/Repos/law-config
cd ~/Repos/law-config
```

## Python via uv (Preferred)

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

## Container and Registry Tooling

### Install Rancher Desktop

```bash
brew install --cask rancher
```

Launch Rancher Desktop once and complete its setup before using `docker`.

### Registry Login

```bash
docker login ghcr.io
docker login
```

Use a personal access token and keep a configured credential store enabled; see the [Docker login documentation](https://docs.docker.com/reference/cli/docker/login/).
