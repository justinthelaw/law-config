#!/usr/bin/env python3
"""Generate the Codex compatibility manifest from the portable plugin manifest."""
import argparse
import json
from pathlib import Path
import sys

IDENTITY_FIELDS = (
    "name", "version", "description", "author", "homepage", "repository",
    "license", "keywords",
)


def codex_manifest(manifest):
    return {
        **{key: manifest[key] for key in IDENTITY_FIELDS if key in manifest},
        "skills": "./skills/",
        "interface": manifest.get("extensions", {}).get("com.openai", {}).get("interface", {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        manifest = json.loads((args.root / "plugin.json").read_text(encoding="utf-8"))
        content = json.dumps(codex_manifest(manifest), indent=2) + "\n"
        target = args.root / ".codex-plugin/plugin.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1
    print("Generated .codex-plugin/plugin.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
