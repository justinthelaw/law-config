# Law-Config

## Project Purpose

Shared development system configuration for `law-*` machines.

This repository contains shell, Git, and GPG baseline configuration plus setup documentation for Linux and macOS.

## Quick Start

1. Install Zsh + Oh-My-Zsh + znap:
   - https://ohmyz.sh/#install
   - https://github.com/ohmyzsh/ohmyzsh/wiki
   - https://github.com/marlonrichert/zsh-snap#installation
2. Point your user `.zshrc` to this repository:

```bash
grep -qxF "source /absolute/path/to/law-config/configs/.zshrc" ~/.zshrc ||
  printf "\nsource /absolute/path/to/law-config/configs/.zshrc\n" >> ~/.zshrc
```

3. Apply Git template settings:

```bash
grep INSERT configs/.gitconfig
[[ -f ~/.gitconfig ]] && cp ~/.gitconfig ~/.gitconfig.bak.$(date +%s).$$
cp configs/.gitconfig ~/.gitconfig
git config --list
```

4. If using commit signing, install/copy GPG defaults:

```bash
mkdir -p ~/.gnupg
for file in configs/gpg/*.conf; do
  target="$HOME/.gnupg/$(basename "$file")"
  [[ -f "$target" ]] && cp "$target" "$target.bak.$(date +%s).$$"
  cp "$file" "$target"
done
chmod 600 ~/.gnupg/*
chmod 700 ~/.gnupg
```

## Development

### Branch model

- `main` is the canonical branch.
- OS-specific differences are isolated in:
  - docs: `docs/setup-linux.md`, `docs/setup-macos.md`
  - overlays: `configs/zsh/linux.zsh`, `configs/zsh/macos.zsh`

### Directory strategy

```text
configs/
  .zshrc
  .gitconfig
  gpg/
    gpg.conf
    gpg-agent.conf
  zsh/
    common.zsh
    env.zsh
    linux.zsh
    macos.zsh
docs/
  setup-linux.md
  setup-macos.md
  CONTRIBUTING.md
  SECURITY.md
  SUPPORT.md
  CODE_OF_CONDUCT.md
scripts/
  clean-codex
  clean-codex-state.py
  sanitize-shell-hist
```

### Validation

```bash
python3 -m pip install pre-commit==4.6.0
pre-commit run --all-files
python3 -m unittest discover -s tests
zsh -n configs/.zshrc configs/zsh/*.zsh
```

### Maintenance Notes

- Keep Oh My Zsh updated with `omz update`, especially before enabling bundled themes or plugins beyond the repo default.
- Install nvm from a tagged release and keep the default HTTPS mirror settings unless a trusted internal mirror is required.
- Review `configs/.gitconfig` placeholders before copying it into `~/.gitconfig`.

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for workflow and pull request expectations.

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for supported versions and vulnerability reporting.

## Support

See [docs/SUPPORT.md](docs/SUPPORT.md) for bug, feature, and question routing.

## License

MIT License. See [LICENSE](LICENSE).
