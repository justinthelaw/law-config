# Inventory operation

Run `python3 /absolute/skill/scripts/inventory.py --help` for the installed helper's options. Choose a private output directory (mode 0700 on POSIX; verify owner-only ACL on Windows). `--output` must be a new file in that directory; never overwrite a report or publish private inventory paths.

Use `--root` for one selected local volume/root, `--output` for JSONL, repeated `--exclude` for protected subtrees inside it, and `--codex-home` only for classification. It never expands scope. Optional `--max-nodes` and `--max-seconds` apply only when explicitly requested; reaching them means incomplete coverage. Resume by a safe rerun and do not add overlapping totals.

Resolve a user-selected root alias once. Do not follow discovered symlinks, junctions, reparse points, mounted descendants (including same-device mounts), placeholders or known cloud/backup trees. Reject network/virtual roots. Surface replaced/vanished nodes, inaccessible regions and coverage limitations. Inspect metadata only, including hidden directories and Git metadata; no Git maintenance or content reads are needed.

The aggregate summary is observed concurrent filesystem activity, not a frozen snapshot. Account for hardlinks, avoid overlapping directory totals, and distinguish logical file length from allocated storage. Neither inventory size nor the helper's classifications establish reclaimability or authorize removal.

## Source provenance

The bundled inventory helper and regression tests were adapted from `openai/chatgpt-question-answer` at commit `b1a377f64a3dcf74eeb5dcbec5a47a171453cef1`, under `skills/conservative-machine-cleanup/scripts/inventory.py` and `skills/conservative-machine-cleanup/tests/`. This records source provenance; it does not assert a donor license.
