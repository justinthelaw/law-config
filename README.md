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

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for workflow and pull request expectations.

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for supported versions and vulnerability reporting.

## Support

See [docs/SUPPORT.md](docs/SUPPORT.md) for bug, feature, and question routing.

## License

MIT License. See [LICENSE](LICENSE).
