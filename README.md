# Law-Config

## Project Purpose

Shared development system configuration for `law-*` machines.

This repository contains shell, Git, and GPG baseline configuration plus setup documentation for Linux and macOS.

Start with the environment guide for your machine:

- [Linux setup](docs/setup-linux.md)
- [macOS setup](docs/setup-macos.md)

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

3. Personalize every `<INSERT ...>` value, then include the Git template without replacing existing global settings:

```bash
if grep -q '<INSERT' configs/.gitconfig; then
  echo "Personalize configs/.gitconfig before installing it." >&2
  exit 1
fi
template_path="$(pwd -P)/configs/.gitconfig"
git config --global --get-all include.path | grep -qxF "$template_path" ||
  git config --global --add include.path "$template_path"
git config --list
```

The template enables GPG commit signing; remove the signing settings before installation if signing is not wanted.

4. Install the GPG defaults after backing up only the files this repository manages:

```bash
mkdir -p ~/.gnupg
for file in configs/gpg/*.conf; do
  target="$HOME/.gnupg/$(basename "$file")"
  [[ -f "$target" ]] && cp "$target" "$target.bak.$(date +%s).$$"
  install -m 600 "$file" "$target"
done
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
