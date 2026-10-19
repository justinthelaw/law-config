# Law-Config

Shell, Git, and GPG configuration for `law-*` machines, plus the Develop plugin.
Start with [Linux setup](docs/setup-linux.md) or [macOS setup](docs/setup-macos.md).

This repository also maintains Develop and its `law-config` Git marketplace.

| Goal | Start here |
| --- | --- |
| Configure a machine | [Linux](docs/setup-linux.md) · [macOS](docs/setup-macos.md) |
| Use Develop's development and maintenance workflows | [Skill calls and bounded refactoring](plugins/develop/README.md) · [Install and sync](plugins/develop/INSTALL.md) |
| Contribute changes | [Required checks](docs/CONTRIBUTING.md#validation) · [Repository instructions](AGENTS.md) |

## Quick Start

1. After installing Git with the appropriate setup guide, clone the repository
   and work from its root:

```bash
mkdir -p ~/Repos
git clone https://github.com/justinthelaw/law-config.git ~/Repos/law-config
cd ~/Repos/law-config
```

2. Install Zsh + Oh-My-Zsh + znap:
   - https://ohmyz.sh/#install
   - https://github.com/ohmyzsh/ohmyzsh/wiki
   - https://github.com/marlonrichert/zsh-snap#installation
3. Replace the generated Oh My Zsh initialization block in your user `.zshrc`
   (the `ZSH`, `ZSH_THEME`, `plugins`, and `oh-my-zsh.sh` lines) with this
   repository entrypoint. It must be the only place that sources
   `oh-my-zsh.sh`:

```bash
source /absolute/path/to/law-config/configs/.zshrc
```

4. Personalize every `<INSERT ...>` value, then include the Git template without replacing existing global settings:

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

5. Install the GPG defaults after backing up only the files this repository manages:

```bash
mkdir -p ~/.gnupg
for file in configs/gpg/*.conf; do
  target="$HOME/.gnupg/$(basename "$file")"
  [[ -f "$target" ]] && cp "$target" "$target.bak.$(date +%s).$$"
  install -m 600 "$file" "$target"
done
chmod 700 ~/.gnupg
```

## Reference

- [Contributing](docs/CONTRIBUTING.md)
- [Security and private reporting](docs/SECURITY.md)
- [Support](docs/SUPPORT.md)
- [MIT License](LICENSE)
- [Develop Apache-2.0 License](plugins/develop/LICENSE)

The configuration and helper scripts use the repository's MIT license. The
Develop package under `plugins/develop/` retains its Apache-2.0 license.
