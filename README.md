# Law-Config

Development system configurations for `law-*` machines.

## Branch Model

- `main` is the single canonical branch.
- OS-specific differences are handled with:
  - docs: `docs/setup-linux.md` and `docs/setup-macos.md`
  - config overlays: `configs/zsh/linux.zsh` and `configs/zsh/macos.zsh`

## Directory Strategy

```text
configs/
  .zshrc              # single entrypoint; auto-selects OS config
  .gitconfig          # global git template (fill placeholders)
  gpg/
    gpg.conf
    gpg-agent.conf
  zsh/
    common.zsh        # shared shell config
    linux.zsh         # Linux-only settings
    macos.zsh         # macOS-only settings
docs/
  setup-linux.md
  setup-macos.md
scripts/
  sanitize-shell-hist
```

`configs/.zshrc` auto-detects the host OS with `uname` and sources `configs/zsh/common.zsh` plus the matching OS overlay.

## Quick Start

1. Install Zsh + Oh-My-Zsh + znap:
   - https://ohmyz.sh/#install
   - https://github.com/ohmyzsh/ohmyzsh/wiki
   - https://github.com/marlonrichert/zsh-snap#installation
2. Point your user `.zshrc` to this repository:

```bash
echo "source /absolute/path/to/law-config/configs/.zshrc" > ~/.zshrc
```

3. Apply Git template settings:

```bash
cat configs/.gitconfig | grep INSERT
cp configs/.gitconfig ~/.gitconfig
git config --list
```

4. If using commit signing, install/copy GPG defaults:

```bash
mkdir -p ~/.gnupg
cp configs/gpg/*.conf ~/.gnupg/
chmod 600 ~/.gnupg/*
chmod 700 ~/.gnupg
```

## Environment Setup Guides

- Linux: [docs/setup-linux.md](docs/setup-linux.md)
- macOS: [docs/setup-macos.md](docs/setup-macos.md)

## Runtime Manager Preference

- Python: `uv` (install/use examples in the setup guides).
- Node.js: `nvm` (install plus `nvm install/use` examples in the setup guides).

## Utility Script

- `scripts/sanitize-shell-hist <history_file>`
- Example: `scripts/sanitize-shell-hist ~/.zsh_history`
- The script writes a backup (`<history_file>.bak.<epoch>`) before rewriting history.
