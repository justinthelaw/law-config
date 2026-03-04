# Contributing

Thanks for improving Justin's shared machine configuration repository.

## Ground Rules

- Keep OS-specific behavior isolated to Linux and macOS overlays.
- Keep changes minimal and explain why behavior changed.
- Never commit secrets, personal tokens, or host-specific credentials.

## Development Workflow

1. Create a branch from `main`.
2. Make focused changes.
3. Run checks locally.
4. Open a pull request with clear validation notes.

## Validation

Run these checks before pushing:

```bash
pre-commit run --all-files
bash -n scripts/sanitize-shell-hist
```

If changing docs, verify links and command examples.

## Pre-commit

Install hooks once per clone:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Pull Request Expectations

- Describe the problem and rationale.
- Include Linux/macOS impact notes when applicable.
- Document manual validation steps in the PR description.
