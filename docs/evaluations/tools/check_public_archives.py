"""Verify the exact public archives exempted from the added-file size limit."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

# Audited immutable archives; changes require a separate provenance review.
ARCHIVES = {
    'docs/evaluations/treatments/fdc34c55ece9/package.patch':
        '54483c49e5bfce17043e28e5af1546952de88e4ac200cdc4fe0e9d753d375a84',
    'docs/evaluations/treatments/6f23f7f98c26/package.patch':
        '92d91d268347f6040e678a3b8c58ed5cd2e5d10b9117a8d3455446b04480b271',
    'docs/evaluations/treatments/a4465fb13180/package.patch':
        '0e47cce3857da042ff7a837d5783a7775a803a2c9de24bd04c5c2690ceb826f5',
    'docs/evaluations/treatments/a826a2341b6c/package.patch':
        '1ea7b7fc21fa30fcebf44178f93bc46e201fd673483dfab7f26531db29fd446f',
    'docs/evaluations/treatments/5b59b578a1bc/package.patch':
        '8c08f7665b95f2e180027dd98d203564da6bd8d9053c8ff1cb24218c1165dc69',
    'docs/evaluations/runs/pr-quality-panel-v2/baseline-53a8bd549c93/submissions.jsonl':
        'a3b37b03a7ce07ebe6a72bd3aa33b96284b6708d15b6957eddc158452b25a136',
}


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    failures = []
    for relative, expected in ARCHIVES.items():
        path = root / relative
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("expected a regular archive")
            with path.open("rb") as stream:
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                actual = digest.hexdigest()
            if actual != expected:
                raise ValueError("SHA-256 differs from the audited archive")
        except (OSError, ValueError) as error:
            failures.append(f"{relative}: {error}")
    for failure in failures:
        print(failure, file=sys.stderr)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
