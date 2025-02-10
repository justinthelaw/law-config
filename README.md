# Law-Config

Development system configurations for all of my devices, aptly named `law-*`.

## Pre-Requisites

At this point of the development system setup and configuration process, I should have already done the following:

1. Updated and security patched all base OS packages (git, e.g.)
2. Installed `Brave Browser` and added it to the sync-chain (`brew install brave-browser`)

Read instructions here: https://tailscale.com/download/macos

## Usage

All of the following instruction assume that you have cloned down this Git repository's source code and configuration files.

### Zsh and Oh-My-Zsh

Zsh and Oh-My-Zsh add a lot of functionality, and therefore it is important for me to set this up as soon as possible.

To use the pre-configured `.zshrc` in this repository, simply do the following:

Read instructions here:

- https://ohmyz.sh/#install
- https://github.com/ohmyzsh/ohmyzsh/wiki
- https://github.com/marlonrichert/zsh-snap#installation

```bash
# Install Oh-My-Zsh for Zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Install Znap as your Zsh plugin manager
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

#### Install Chainguard CLI

Read instructions here: https://edu.chainguard.dev/chainguard/administration/how-to-install-chainctl/

```bash
curl -o chainctl "https://dl.enforce.dev/chainctl/latest/chainctl_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/aarch64/arm64/')"
sudo install -o $UID -g $(id -g) -m 0755 chainctl /usr/local/bin/
```

#### Install Rancher Desktop

```bash
brew install --cask rancher
```

#### Logging In

Logging in to the following registries is recommended:

```bash
# use your username and harbor key
docker login registry1.dso.mil

# use your username and self-generated PAT
docker login ghcr.io

# use your username and password
docker login

# use the SSO prompt
chainctl auth configure-docker --headless
```

### PyEnv

PyEnv is an single-purpose utility that enables easy management of Python versions and virtual environments.

Read instructions here: https://github.com/pyenv/pyenv?tab=readme-ov-file#getting-pyenv

```bash
brew install pyenv
```

### Go

Golang installation instructions here: https://go.dev/doc/install

```bash
brew install go
```

### Node

NVM, NPM, and Node.js instructions here: https://github.com/nvm-sh/nvm

```bash
brew install nvm
```

### UDS Development

The following are minimal dependencies for Unicorn Delivery Service (UDS) development:

Read instructions here : https://github.com/defenseunicorns/uds-cli/releases

```bash
brew tap defenseunicorns/tap && brew install uds
```

Read instructions here: https://k3d.io/stable/

```bash
brew install k3d
```
