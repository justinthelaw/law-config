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


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(text):
    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    try:
        return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds parser limit") from exc


def openai_extension(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("plugin.json: expected an object")
    extensions = manifest.get("extensions", {})
    if not isinstance(extensions, dict):
        raise ValueError("plugin.json: extensions must be an object")
    extension = extensions.get("com.openai", {})
    if not isinstance(extension, dict):
        raise ValueError("plugin.json: extensions.com.openai must be an object")
    if not isinstance(extension.get("interface", {}), dict):
        raise ValueError("plugin.json: extensions.com.openai.interface must be an object")
    return extension


def codex_manifest(manifest):
    extension = openai_extension(manifest)
    return {
        **{key: manifest[key] for key in IDENTITY_FIELDS if key in manifest},
        "skills": "./skills/",
        "interface": extension.get("interface", {}),
        **({"hooks": extension["hooks"]} if "hooks" in extension else {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        with (args.root / "plugin.json").open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("plugin.json: metadata exceeds 1 MiB")
        manifest = load_json(data.decode("utf-8"))
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
