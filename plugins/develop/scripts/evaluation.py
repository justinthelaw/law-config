#!/usr/bin/env python3
"""Explicit offline JSON validation/materialization. Python 3.10+, no dependencies.

This checks the packaged contract's small JSON Schema subset, not arbitrary
schemas. It never runs fixture commands or certifies agent/host behavior.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

CONTRACT = Path(__file__).resolve().parents[1] / "tests/evaluations/contract.json"
SCHEMA = json.loads(CONTRACT.read_text(encoding="utf-8"))


def _check(value, schema, location):
    if "$ref" in schema:
        schema = SCHEMA["$defs"][schema["$ref"].removeprefix("#/$defs/")]
    kinds = schema["type"]
    kinds = [kinds] if isinstance(kinds, str) else kinds
    matches = {
        "object": type(value) is dict, "array": type(value) is list,
        "string": type(value) is str, "integer": type(value) is int,
        "number": type(value) in (int, float), "null": value is None,
    }
    if not any(matches[kind] for kind in kinds):
        raise ValueError(f"{location}: expected {kinds}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{location}: unsupported value")
    if isinstance(value, dict):
        properties = schema["properties"]
        if set(schema["required"]) - value.keys() or value.keys() - properties.keys():
            raise ValueError(f"{location}: missing or unknown fields")
        for key, item in value.items():
            _check(item, properties[key], f"{location}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"{location}: too few items")
        for index, item in enumerate(value):
            _check(item, schema["items"], f"{location}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{location}: empty string")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{location}: invalid format")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{location}: invalid Unicode") from exc
    elif type(value) in (int, float):
        if (type(value) is float and not math.isfinite(value)) or value < schema.get("minimum", 0):
            raise ValueError(f"{location}: expected finite nonnegative value")


def _input_paths(fixture):
    paths = []
    prefixes = {}
    for item in fixture["agent"]["inputs"]:
        path = item["path"]
        # Portable literal paths only: no Windows devices, ADS, drive letters,
        # ambiguous separators or case aliases on case-insensitive filesystems.
        parts = path.split("/")
        for part in parts:
            if (not re.fullmatch(r"[A-Za-z0-9_. -]+", part)
                    or part in (".", "..") or part.endswith((".", " "))
                    or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?", part)):
                raise ValueError(f"unsafe input path: {path!r}")
        folded = path.casefold()
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            if prefixes.setdefault(prefix.casefold(), prefix) != prefix:
                raise ValueError(f"case-aliased input path: {path!r}")
        if any(folded == old or folded.startswith(old + "/")
               or old.startswith(folded + "/") for old in paths):
            raise ValueError(f"duplicate or conflicting input path: {path!r}")
        paths.append(folded)


def validate_fixture(fixture):
    """Raise ValueError for invalid public fixture data; return None otherwise."""
    _check(fixture, SCHEMA["$defs"]["fixture"], "fixture")
    _input_paths(fixture)


def fixture_digest(fixture):
    """SHA256 of sorted compact UTF-8 JSON, including prompt and input contents."""
    validate_fixture(fixture)
    payload = json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_result(result):
    """Validate attribution and a complete ledger, including explicit missing rows."""
    _check(result, SCHEMA["$defs"]["result"], "result")
    planned = [item["attempt_id"] for item in result["planned_attempts"]]
    attempts = [item["attempt_id"] for item in result["attempts"]]
    if len(set(planned)) != len(planned) or len(set(attempts)) != len(attempts):
        raise ValueError("duplicate attempt_id")
    if set(planned) != set(attempts):
        raise ValueError("every planned attempt needs a completed, blocked or missing record")
    for attempt in result["attempts"]:
        for key in ("functional", "evaluator"):
            assessment = attempt[key]
            if assessment["verdict"] != "not_run" and not assessment["evidence"]:
                raise ValueError(f"{key}: verdict requires evidence")
            if attempt["state"] != "completed" and assessment["verdict"] != "not_run":
                raise ValueError("blocked/missing attempts cannot claim a verdict")
        if attempt["state"] != "completed" and not attempt["reason"]:
            raise ValueError("blocked/missing attempts require a reason")
        if attempt["state"] == "missing":
            if (any(value is not None for value in attempt["cost"].values())
                    or attempt["application_performance"] or attempt["observations"]):
                raise ValueError("missing attempts cannot claim observations or measurements")


def _no_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"symlink prohibited: {part}")


def materialize(fixture, destination):
    """Create a new root containing only declared inputs; return path -> SHA256.

    The caller must own the parent exclusively, outside agent reach. Symlink
    checks are not a sandbox against concurrent hostile filesystem mutation.
    A failed write can leave a partial root; no existing path is overwritten.
    """
    validate_fixture(fixture)
    destination = Path(destination).absolute()
    if ".." in destination.parts:
        raise ValueError("destination cannot contain parent traversal")
    _no_symlinks(destination)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    hashes = {}
    for item in sorted(fixture["agent"]["inputs"], key=lambda item: item["path"]):
        target = destination / item["path"]
        _no_symlinks(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = item["content"].encode("utf-8")
        with target.open("xb") as output:
            output.write(content)
        hashes[item["path"]] = hashlib.sha256(content).hexdigest()
    return hashes


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path):
    """Read JSON without silently accepting duplicate keys or NaN/Infinity."""
    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_pairs, parse_constant=invalid_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("fixture", "result", "materialize"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args(argv)
    try:
        data = load_json(args.input)
        if args.kind == "materialize":
            if args.destination is None:
                parser.error("materialize requires --destination")
            output = {"files": materialize(data, args.destination), "fixture_sha256": fixture_digest(data)}
        else:
            if args.destination is not None:
                parser.error("--destination requires materialize")
            (validate_fixture if args.kind == "fixture" else validate_result)(data)
            output = {"valid": True, "kind": args.kind}
        print(json.dumps(output, sort_keys=True))
    except (ValueError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
