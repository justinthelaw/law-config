#!/usr/bin/env python3
"""Offline package lint, not a full JSON Schema validator or agent behavior test.

Requires Python 3.10+. This repository deliberately uses two simple scalar YAML
frontmatter fields and JSON-compatible quoted UI strings; no YAML dependency.
"""
import argparse
import ast
import json
from pathlib import Path
import re
import sys

# Resolve the packaged sibling even when Python safe-path mode omits the
# script directory. Never import from the caller's current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_codex_manifest import codex_manifest

SKILLS = {"develop", "iterate", "upgrade", "clean", "adversarial-loop", "kaizen"}
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def validate(root, marketplace_root=None):
    root = root.resolve()
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    def read_json(relative, base=root):
        try:
            return json.loads((base / relative).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{relative}: {exc}")
            return {}

    def check_icon(value, base, label):
        if not isinstance(value, str) or not value.startswith("./"):
            errors.append(f"{label}: use a relative ./ asset path")
            return
        target = (base / value).resolve()
        if not target.is_relative_to(base.resolve()):
            errors.append(f"{label}: asset escapes its package")
            return
        try:
            data = target.read_bytes()
            check(len(data) <= 1024 * 1024, f"{label}: icon exceeds 1 MiB")
            check(data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR",
                  f"{label}: expected a PNG image")
            width = int.from_bytes(data[16:20], "big")
            height = int.from_bytes(data[20:24], "big")
            check(width == height and width >= 64, f"{label}: use a square icon at least 64px")
        except OSError as exc:
            errors.append(f"{label}: {exc}")

    manifest = read_json("plugin.json")
    check(isinstance(manifest, dict), "plugin.json: expected an object")
    if not isinstance(manifest, dict):
        manifest = {}
    check(manifest.get("$schema") == SCHEMA, "plugin.json: portable schema missing")
    check(manifest.get("name") == "develop", "plugin.json: name must be develop")
    check(bool(re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", "")))), "plugin.json: use a release version")
    check(manifest.get("repository") == "https://github.com/justinthelaw/law-config.git", "plugin.json: unexpected source repository")
    check(not any(key in manifest for key in ("dependencies", "mcpServers", "hooks")), "plugin.json: keep this package skills-only; no invented dependencies")
    interface = manifest.get("extensions", {}).get("com.openai", {}).get("interface", {})
    for key in ("logo", "composerIcon"):
        check_icon(interface.get(key), root, f"plugin.json: {key}")

    # Older Codex clients ingest this file, with paths relative to the package
    # root. Validate the shipped artifact without regenerating it during lint.
    codex = read_json(".codex-plugin/plugin.json")
    check(codex == codex_manifest(manifest),
          ".codex-plugin/plugin.json: regenerate from plugin.json; expected matching metadata, top-level interface and skills")

    # Repository catalogs are not part of the installed plugin payload.
    if marketplace_root is not None:
        marketplace_root = marketplace_root.resolve()
        catalog = read_json(".agents/plugins/marketplace.json", marketplace_root)
        try:
            entry, = [item for item in catalog["plugins"]
                      if isinstance(item, dict) and item.get("name") == "develop"]
            source = entry["source"]
            check(source["source"] == "local" and source["path"] == "./plugins/develop",
                  "catalog: develop must use local source ./plugins/develop")
            target = (marketplace_root / source["path"]).resolve()
            check(target.is_relative_to(marketplace_root) and target == root,
                  "catalog: source must resolve to this package inside the repository")
        except (KeyError, TypeError, ValueError):
            errors.append("catalog: expected exactly one develop entry with a local source")

    skill_paths = sorted((root / "skills").glob("*/SKILL.md"))
    check({p.parent.name for p in skill_paths} == SKILLS, "skills: expected exactly six entry points")
    for path in skill_paths:
        text = path.read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        if not frontmatter:
            errors.append(f"{path.relative_to(root)}: missing frontmatter")
            continue
        fields = {}
        for line in frontmatter[1].splitlines():
            key, separator, value = line.partition(": ")
            check(bool(separator) and key not in fields, f"{path.relative_to(root)}: invalid or duplicate scalar field")
            fields[key] = value
        check(set(fields) == {"name", "description"}, f"{path.relative_to(root)}: use name and description only")
        check(fields.get("name") == path.parent.name, f"{path.relative_to(root)}: name must match directory")
        description = fields.get("description", "")
        check(0 < len(description) <= 1024 and ": " not in description, f"{path.relative_to(root)}: invalid simple description scalar")
        check(len(text.splitlines()) < 500, f"{path.relative_to(root)}: split oversized skill")
        check("TODO" not in text and "TBD" not in text, f"{path.relative_to(root)}: unfinished template")
        ui_path = path.parent / "agents/openai.yaml"
        try:
            ui = ui_path.read_text(encoding="utf-8")
            values = dict(re.findall(r'^  (display_name|short_description|default_prompt): (".*")$', ui, re.M))
            values = {key: json.loads(value) for key, value in values.items()}
            check(len(values) == 3, f"{ui_path.relative_to(root)}: missing interface fields")
            check(25 <= len(values.get("short_description", "")) <= 64, f"{ui_path.relative_to(root)}: short_description length")
            check("$" + path.parent.name in values.get("default_prompt", ""), f"{ui_path.relative_to(root)}: prompt must name its skill")
            icons = dict(re.findall(r'^  (icon_small|icon_large): (".*")$', ui, re.M))
            for key in ("icon_small", "icon_large"):
                check_icon(json.loads(icons.get(key, "null")), path.parent,
                           f"{ui_path.relative_to(root)}: {key}")
        except (OSError, ValueError) as exc:
            errors.append(f"{ui_path.relative_to(root)}: {exc}")

    # Delivery helpers ship inside the owning skill. Check their local import
    # closure without importing code or relying on the author's checkout.
    helper_root = root / "skills/iterate/scripts"
    pending = ["repository_inventory", "watch_pipelines"]
    inspected = set()
    while pending:
        module = pending.pop()
        if module in inspected:
            continue
        inspected.add(module)
        path = helper_root / f"{module}.py"
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            errors.append(f"delivery helper escapes package or is a symlink: {module}")
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"delivery helper {module}: {exc}")
            continue
        for node in ast.walk(tree):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            )
            pending.extend(name for name in names if name.startswith("pipeline_") or name == "watch_pipelines")

    for path in [root / "INSTALL.md", *sorted((root / "skills").rglob("*.md"))]:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(root)}")
            continue
        text = path.read_text(encoding="utf-8")
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if re.match(r"^(https?://|mailto:|#)", link):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            check(target.is_relative_to(root) and target.exists(), f"{path.relative_to(root)}: broken or escaping link {link}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--marketplace-root", type=Path,
                        help="Also validate the catalog at this repository root")
    args = parser.parse_args()
    try:
        errors = validate(args.root, args.marketplace_root)
    except (OSError, UnicodeError) as exc:
        errors = [str(exc)]
    for error in errors:
        print("FAIL:", error, file=sys.stderr)
    if errors:
        return 1
    print("PASS: package structure, six skills, references, and contextual marketplace checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
