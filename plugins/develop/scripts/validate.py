#!/usr/bin/env python3
"""Offline package lint, not a full JSON Schema validator or agent behavior test.

Requires Python 3.10+. Supported metadata is deliberately narrow: two simple
scalar frontmatter fields, a two-level UI mapping with JSON-quoted strings and
an optional boolean policy. Package icons must be noninterlaced 8-bit RGB/RGBA
PNGs, at most 1 MiB compressed and 64 MiB of decoded scanlines. Only IHDR, PLTE,
IDAT, IEND and opaque caBX content-credential chunks are supported. No dependencies.
"""
import argparse
import ast
import json
from pathlib import Path
import re
import struct
import sys
import zlib

# Resolve the packaged sibling even when Python safe-path mode omits the
# script directory. Never import from the caller's current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_codex_manifest import codex_manifest, load_json, openai_extension
from validate_context_hooks import HOOK_PATH, validate_context_hooks

SKILLS = {"develop", "iterate", "upgrade", "upgrade-codex", "clean", "deep-clean", "adversarial-loop", "kaizen"}
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MAX_ICON_BYTES = 1024 * 1024
MAX_SCANLINE_BYTES = 64 * 1024 * 1024
INTERFACE_FIELDS = {"display_name", "short_description", "default_prompt", "icon_small", "icon_large"}


def parse_ui_metadata(text):
    """Parse this package's YAML subset; reject other syntax, keys and mappings.

    Only an optional initial document marker, whole-line comments, unquoted
    keys, two-space child indentation and one-line values are supported.
    """
    result = {}
    section = None
    lines = [line.rstrip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if lines and lines[0] == "---":
        lines.pop(0)
    for line in lines:
        if line in ("interface:", "policy:"):
            section = line[:-1]
            if section in result:
                raise ValueError(f"duplicate mapping {section}")
            result[section] = {}
            continue
        match = re.fullmatch(r"  ([a-z_]+): (.+)", line)
        if section is None or match is None:
            raise ValueError(f"unsupported metadata mapping: {line}")
        key, raw = match.groups()
        allowed = INTERFACE_FIELDS if section == "interface" else {"allow_implicit_invocation"}
        if key not in allowed or key in result[section]:
            raise ValueError(f"unknown or duplicate {section} field: {key}")
        if section == "interface":
            value = json.loads(raw)
            if not isinstance(value, str):
                raise ValueError(f"{key}: require a JSON-quoted string")
        else:
            if raw not in ("true", "false"):
                raise ValueError("allow_implicit_invocation: require a boolean")
            value = raw == "true"
        result[section][key] = value
    if set(result.get("interface", {})) != INTERFACE_FIELDS:
        raise ValueError("interface: require exactly the five supported fields")
    if "policy" in result and set(result["policy"]) != {"allow_implicit_invocation"}:
        raise ValueError("policy: require allow_implicit_invocation")
    return result


def validate_png(data):
    """Check complete critical chunks and bounded decoded RGB/RGBA scanlines.

    All 8-bit channel values are valid. The five permitted row filters are
    reversible for every byte value, so pixel reconstruction adds no validity
    check; decoding verifies exact row lengths and filter bytes instead.
    The shipped caBX metadata is opaque to image decoding. Other ancillary
    types are unsupported: framing and CRC alone cannot validate their payloads.
    """
    if len(data) > MAX_ICON_BYTES:
        raise ValueError("icon exceeds 1 MiB")
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("expected a PNG image")
    offset = 8
    width = height = stride = 0
    compressed = bytearray()
    seen = set()
    idat_closed = False
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError("truncated PNG chunk")
        length, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + length + 12
        if end > len(data):
            raise ValueError("truncated PNG chunk payload")
        if not re.fullmatch(b"[A-Za-z]{2}[A-Z][A-Za-z]", kind):
            raise ValueError("invalid PNG chunk type")
        payload = data[offset + 8:end - 4]
        crc, = struct.unpack_from(">I", data, end - 4)
        if zlib.crc32(kind + payload) != crc:
            raise ValueError(f"invalid PNG {kind.decode()} CRC")
        if not seen and kind != b"IHDR":
            raise ValueError("PNG must begin with IHDR")
        if kind == b"IHDR":
            if seen or length != 13:
                raise ValueError("require one 13-byte PNG IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if width != height or width < 64:
                raise ValueError("use a square icon at least 64px")
            if depth != 8 or color not in (2, 6) or compression or filtering or interlace:
                raise ValueError("require a noninterlaced 8-bit RGB/RGBA PNG")
            stride = 1 + width * (3 if color == 2 else 4)
            if stride * height > MAX_SCANLINE_BYTES:
                raise ValueError("decoded PNG scanlines exceed 64 MiB")
        elif kind == b"PLTE":
            if b"PLTE" in seen or b"IDAT" in seen or not 0 < length <= 768 or length % 3:
                raise ValueError("invalid PNG palette")
        elif kind == b"IDAT":
            if idat_closed:
                raise ValueError("PNG IDAT chunks must be consecutive")
            compressed.extend(payload)
        elif kind == b"IEND":
            if length or b"IDAT" not in seen or end != len(data):
                raise ValueError("invalid PNG end or trailing data")
        elif kind != b"caBX":
            raise ValueError(f"unsupported PNG chunk {kind.decode()}")
        if b"IDAT" in seen and kind != b"IDAT":
            idat_closed = True
        seen.add(kind)
        offset = end
    if b"IEND" not in seen:
        raise ValueError("missing PNG IEND")
    expected = stride * height
    decoder = zlib.decompressobj()
    # One extra byte detects excess output without an unbounded flush/decompress.
    decoded = decoder.decompress(compressed, expected + 1)
    if (len(decoded) != expected or not decoder.eof
            or decoder.unconsumed_tail or decoder.unused_data):
        raise ValueError("invalid, truncated or excessive PNG scanline data")
    if any(decoded[index] > 4 for index in range(0, expected, stride)):
        raise ValueError("invalid PNG scanline filter")


def validate(root, marketplace_root=None):
    root = root.resolve()
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    def contained_text(path, base=root):
        if not path.resolve().is_relative_to(base.resolve()):
            raise ValueError("metadata escapes its package")
        return path.read_text(encoding="utf-8")

    def read_json(relative, base=root):
        try:
            path = base / relative
            if not path.resolve().is_relative_to(base.resolve()):
                raise ValueError("metadata escapes its package")
            with path.open("rb") as stream:
                data = stream.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError("metadata exceeds 1 MiB")
            return load_json(data.decode("utf-8"))
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{relative}: {exc}")
            return {}

    inspected_icons = set()

    def check_icon(value, base, label):
        if not isinstance(value, str) or not value.startswith("./"):
            errors.append(f"{label}: use a relative ./ asset path")
            return
        try:
            target = (base / value).resolve()
            if not target.is_relative_to(base.resolve()) or not target.is_relative_to(root):
                raise ValueError("asset escapes its package")
            if target in inspected_icons:
                return
            with target.open("rb") as stream:
                validate_png(stream.read(MAX_ICON_BYTES + 1))
            inspected_icons.add(target)
        except (OSError, ValueError, RuntimeError, zlib.error) as exc:
            errors.append(f"{label}: {exc}")

    manifest = read_json("plugin.json")
    check(isinstance(manifest, dict), "plugin.json: expected an object")
    if not isinstance(manifest, dict):
        manifest = {}
    check(manifest.get("$schema") == SCHEMA, "plugin.json: portable schema missing")
    check(manifest.get("name") == "develop", "plugin.json: name must be develop")
    check(bool(re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", "")))), "plugin.json: use a release version")
    check(manifest.get("repository") == "https://github.com/justinthelaw/law-config.git", "plugin.json: unexpected source repository")
    check(not any(key in manifest for key in ("dependencies", "mcpServers", "hooks")),
          "plugin.json: eight skills plus the native context guard only; no root hooks, dependencies or MCP")
    # Both discovery formats remain forbidden; the native guard adds no server
    # or service dependency and is registered only through the OpenAI adapter.
    for relative in ("mcp.json", ".mcp.json"):
        component = root / relative
        check(not component.exists() and not component.is_symlink(),
              f"{relative}: eight skills plus the native context guard only; unexpected MCP declaration")
    try:
        extension = openai_extension(manifest)
    except ValueError as exc:
        errors.append(str(exc))
        extension = {}
    check(set(extension) == {"interface", "hooks"},
          "plugin.json: extensions.com.openai permits only interface and the native context guard hooks")
    check(extension.get("hooks") == HOOK_PATH,
          "plugin.json: extensions.com.openai.hooks must be ./hooks/hooks.json")
    interface = extension.get("interface", {})
    for key in ("logo", "composerIcon"):
        check_icon(interface.get(key), root, f"plugin.json: {key}")

    # Older Codex clients ingest this file, with paths relative to the package
    # root. Validate the shipped artifact without regenerating it during lint.
    codex = read_json(".codex-plugin/plugin.json")
    try:
        check(codex == codex_manifest(manifest),
              ".codex-plugin/plugin.json: regenerate from plugin.json; expected matching metadata, top-level interface, skills and hooks")
    except ValueError as exc:
        errors.append(f".codex-plugin/plugin.json: cannot derive from invalid portable metadata: {exc}")
    errors.extend(validate_context_hooks(root))

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
    skill_directories = {p.name for p in (root / "skills").iterdir() if p.is_dir()}
    check({p.parent.name for p in skill_paths} == skill_directories == SKILLS,
          "skills: expected exactly eight entry points")
    for path in skill_paths:
        try:
            text = contained_text(path)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
            continue
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
            ui = parse_ui_metadata(contained_text(ui_path))
            if path.parent.name in {"upgrade-codex", "deep-clean"}:
                check(ui.get("policy", {}).get("allow_implicit_invocation") is False,
                      f"{ui_path.relative_to(root)}: require one policy block with allow_implicit_invocation: false")
            values = ui["interface"]
            check(25 <= len(values["short_description"]) <= 64, f"{ui_path.relative_to(root)}: short_description length")
            check("$" + path.parent.name in values["default_prompt"], f"{ui_path.relative_to(root)}: prompt must name its skill")
            for key in ("icon_small", "icon_large"):
                check_icon(values[key], path.parent,
                           f"{ui_path.relative_to(root)}: {key}")
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{ui_path.relative_to(root)}: {exc}")
            if path.parent.name in {"upgrade-codex", "deep-clean"}:
                errors.append(f"{ui_path.relative_to(root)}: require one policy block with allow_implicit_invocation: false")

    # Delivery helpers ship inside the owning skill. Check their local import
    # closure without importing code or relying on the author's checkout.
    helper_root = root / "skills/iterate/scripts"
    pending = ["repository_inventory", "watch_pipelines", "check_staged_file_size"]
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
        try:
            text = contained_text(path)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
            continue
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
    print("PASS: package structure, eight skills, native context guard, references, and contextual marketplace checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
