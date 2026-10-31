# Metadata inventory

Use the existing helper: `python3 /absolute/skill/scripts/inventory.py --help`. Set a private output directory (POSIX 0700; owner-only Windows ACL); `--output` must be a new JSONL file there. Never overwrite/publish private reports.

- `--root`: one selected local root/volume; `--output`: report; repeat `--exclude` for protected subtrees. `--codex-home` only classifies, never expands scope. `--max-nodes`/`--max-seconds` require user-requested limits; reaching either means incomplete coverage. Resume by safe rerun without overlapping totals.
- Resolve the selected root alias once; reject network/virtual roots. Never follow discovered symlinks/junctions/reparse points, mounted descendants (including same-device), placeholders or known cloud/backup trees. Report vanished/replaced/inaccessible nodes and gaps.
- Read metadata only, including hidden entries/Git metadata; no content reads or Git maintenance. Concurrent totals are observations, not a frozen snapshot. Deduplicate hardlinks/non-overlapping directory totals; separate logical length/allocated storage. Size/classification proves neither reclaimability nor authority.

## Provenance

Helper/tests adapted from `openai/chatgpt-question-answer` commit `b1a377f64a3dcf74eeb5dcbec5a47a171453cef1`, `skills/conservative-machine-cleanup/scripts/inventory.py` and `skills/conservative-machine-cleanup/tests/`. Provenance is not a donor-license assertion.
