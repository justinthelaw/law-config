# Contributing

Branch from `main`; keep changes focused and Linux/macOS behavior separate.
Never commit secrets, personal tokens, or host-specific credentials.

## Validation

Run these checks before pushing:

```bash
uv tool run --python 3.15 pre-commit@4.6.2 run --all-files --hook-stage pre-commit
uv tool run --python 3.15 pre-commit@4.6.2 run --all-files --hook-stage pre-push
for file in configs/.zshrc configs/zsh/*.zsh; do zsh -n "$file" || exit $?; done
uv run --python 3.15 python -m unittest discover -s tests -v
```

Use stable hook tags and run both stages before changing revisions.
Verify documentation links and command examples.

## Pre-commit

Install hooks once per clone:

```bash
uv tool install --python 3.15 pre-commit==4.6.2
uv tool update-shell
```

Open a new shell, then install the hooks:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Pull Requests

Explain the change, Linux/macOS impacts, and validation results, including manual checks.
