# AGENTS.md

## Purpose

- Maintain shared development environment configuration for `law-*` machines.
- Scope is dotfiles and helper scripts, not an application/service.

## Repo Layout

- `configs/.zshrc`: Zsh entrypoint; auto-loads shared + OS-specific config.
- `configs/zsh/common.zsh`: shared Zsh behavior for all environments.
- `configs/zsh/linux.zsh`: Linux-only shell overrides.
- `configs/zsh/macos.zsh`: macOS-only shell overrides.
- `configs/.gitconfig`: template global Git config with required placeholder values.
- `configs/gpg/*`: baseline GPG config snippets for signing setup.
- `scripts/sanitize-shell-hist`: utility to sanitize shell history files safely.
- `docs/setup-linux.md` and `docs/setup-macos.md`: environment-specific bootstrap docs.
- `README.md`: high-level setup and config selection model.

## Scripts

- `scripts/sanitize-shell-hist <history_file>`
- Example: `scripts/sanitize-shell-hist ~/.zsh_history`
- Behavior: normalizes history entries, removes sensitive/failed commands, drops empty lines, deduplicates, and writes a timestamped backup (`<history_file>.bak.<epoch>`).
- Safety: edits in place; always verify the generated backup before deleting old history files.

## Important Development Notes

- `main` is the single canonical branch.
- Keep OS-specific behavior in `docs/setup-linux.md`, `docs/setup-macos.md`, `configs/zsh/linux.zsh`, and `configs/zsh/macos.zsh`.
- `configs/.gitconfig` must be personalized before use (`<INSERT ...>` fields for identity, key, token).
- `configs/.zshrc` and `configs/zsh/*` assume external tools exist (Oh-My-Zsh, znap, uv, nvm, Go, Docker-related binaries).
- Keep shell/script changes portable for Linux and macOS (`scripts/sanitize-shell-hist` branches by `$OSTYPE`).
- `.zshrc.zwc` is a compiled artifact; update it only when intentionally recompiling.
- Do not commit secrets, personal tokens, or host-specific credentials.

## Quick Validation

- Shell syntax check: `bash -n scripts/sanitize-shell-hist`
- Optional smoke test: run script against a temp copy of a history file, not your only live history file.
