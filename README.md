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
  clean-codex.sh
  sanitize-shell-hist
```

### Validation

```bash
pre-commit run --all-files
```

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for workflow and pull request expectations.

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for supported versions and vulnerability reporting.

## Support

See [docs/SUPPORT.md](docs/SUPPORT.md) for bug, feature, and question routing.

## License

This repository currently has no dedicated license file. Add one before broad public reuse.
