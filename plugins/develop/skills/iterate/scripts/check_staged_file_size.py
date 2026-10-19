#!/usr/bin/env python3
"""Explicit, offline staged authored-file size check; Python 3.10+ and Git."""

# SPDX-License-Identifier: Apache-2.0
# Adapted from justinthelaw/codexops scripts/check-staged-file-size.py at
# 5f565a78956d9098d88c5e923e6f46142d78c16b (Apache-2.0).
# Modified for portable explicit profiles and configurable byte limits.

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import threading


MAX_BYTES = 20_000  # 5,000 estimated tokens at four bytes per token.
PREFIX_BYTES = 8_192
PROFILE_BYTES = 65_536
LOCKFILES = {
    "bun.lock", "bun.lockb", "Cargo.lock", "Chart.lock", "composer.lock",
    "Gemfile.lock", "go.sum", "go.work.sum", "npm-shrinkwrap.json",
    "package-lock.json", "Pipfile.lock", "pnpm-lock.yaml", "poetry.lock",
    "uv.lock", "yarn.lock",
}
GENERATED_DIRS = {
    ".git", ".next", ".run", ".venv", "__pycache__", "build", "coverage",
    "dist", "node_modules", "vendor",
}
BINARY_SUFFIXES = {
    ".avif", ".bz2", ".dll", ".dylib", ".exe", ".gif", ".gz", ".ico",
    ".jpeg", ".jpg", ".mov", ".mp3", ".mp4", ".otf", ".pdf", ".png",
    ".so", ".tar", ".ttf", ".wasm", ".wav", ".webp", ".whl", ".woff",
    ".woff2", ".xz", ".zip", ".zst",
}
GENERATED_HEADER = re.compile(
    rb"(?im)^[ \t]*(?://|\#|/\*|\*|<!--|--|;)[ \t]*"
    rb"(?:code generated\b[^\r\n]*do not edit|@generated\b|auto[- ]generated\b)"
)


def git(*arguments, input_data=None, environment=None):
    """Keep inspection read-only and ignore replacement objects for size checks."""
    env = dict(os.environ if environment is None else environment,
               GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1")
    result = subprocess.run(
        ["git", *arguments], input=input_data, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, env=env, timeout=30, check=True,
    )
    return result.stdout


def repository_root(directory):
    """Reject foreign selectors for --repo while retaining its temporary index."""
    if directory is not None:
        os.chdir(directory)
    selectors = {"GIT_WORK_TREE": "--show-toplevel", "GIT_DIR": "--absolute-git-dir",
                 "GIT_COMMON_DIR": "--git-common-dir"}
    selected_environment = dict(os.environ)
    if directory is not None:
        for name in (*selectors, "GIT_INDEX_FILE"):
            selected_environment.pop(name, None)

    def git_path(option, environment):
        return Path(os.fsdecode(git("rev-parse", option, environment=environment)
                                .removesuffix(b"\n"))).resolve()

    selected = {name: git_path(option, selected_environment)
                for name, option in selectors.items()}
    if directory is not None:
        for name, option in selectors.items():
            if git_path(option, os.environ) != selected[name]:
                raise ValueError("inherited Git selectors conflict with --repo")
    index = None
    if "GIT_INDEX_FILE" in os.environ:
        index = Path(os.environ["GIT_INDEX_FILE"]).resolve()
        if directory is not None and not index.is_relative_to(selected["GIT_DIR"]):
            raise ValueError("explicit --repo requires an index inside its Git directory")
    # Preserve relative hook paths across the subsequent chdir to the root.
    for name, value in selected.items():
        if name in os.environ:
            os.environ[name] = str(value)
    if index is not None:
        os.environ["GIT_INDEX_FILE"] = str(index)
    return selected["GIT_WORK_TREE"]


def positive_integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)) or int(value) < 1:
        raise ValueError("max_bytes must be a positive integer")
    return int(value)


def relative_path(value):
    if (not isinstance(value, str) or not value or "\0" in value
            or "\\" in value or ":" in value):
        raise ValueError("profile paths must be repository-relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value or value == ".":
        raise ValueError("profile paths must be canonical and contained in the repository")
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate profile field")
        result[key] = value
    return result


def load_profile(root, name):
    """Only this explicit configuration is read from the working tree."""
    if name is None:
        return {}
    relative = relative_path(name)
    target = root
    for part in relative.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("profile paths must not traverse symlinks")
    if not target.resolve().is_relative_to(root) or not stat.S_ISREG(target.stat().st_mode):
        raise ValueError("profile must be a regular file inside the repository")
    with target.open("rb") as stream:
        data = stream.read(PROFILE_BYTES + 1)
    if len(data) > PROFILE_BYTES:
        raise ValueError("profile exceeds 64 KiB")
    profile = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    if (not isinstance(profile, dict) or type(profile.get("schema_version")) is not int
            or profile["schema_version"] != 1
            or profile.keys() - {"schema_version", "max_bytes", "exclude_paths", "exclude_prefixes"}):
        raise ValueError("unsupported profile schema or fields")
    if "max_bytes" in profile:
        if type(profile["max_bytes"]) is not int:
            raise ValueError("max_bytes must be an integer")
        positive_integer(profile["max_bytes"])
    for key in ("exclude_paths", "exclude_prefixes"):
        values = profile.get(key, [])
        if not isinstance(values, list):
            raise ValueError("profile exclusions must be arrays")
        profile[key] = [relative_path(value).as_posix() for value in values]
    return profile


def excluded(path, profile):
    relative = PurePosixPath(os.fsdecode(path))
    name = relative.as_posix()
    return (
        name in profile.get("exclude_paths", [])
        or any(name == prefix or name.startswith(prefix + "/")
               for prefix in profile.get("exclude_prefixes", []))
        or any(part in GENERATED_DIRS for part in relative.parts)
        or any(part == ".env" or part.startswith(".env.") for part in relative.parts)
        or relative.name in {"auth.json", "credentials.json", ".npmrc", ".netrc"}
        or relative.suffix.lower() in BINARY_SUFFIXES | {".key", ".pem", ".p12", ".pfx"}
        or relative.name in LOCKFILES
        or relative.name.startswith("zz_generated.")
        or relative.name.endswith((".pb.go", "_pb2.py", "_pb2_grpc.py", ".min.js", ".min.css", ".map"))
    )


def staged_files(profile):
    records = git(
        "diff", "--cached", "--raw", "--no-abbrev", "--no-renames",
        "--no-relative", "--diff-filter=ACMRTU", "--no-ext-diff", "--no-textconv", "-z",
    ).split(b"\0")
    if records[-1] != b"" or len(records) % 2 != 1:
        raise ValueError("staged-file metadata could not be inspected")
    files = []
    for index in range(0, len(records) - 1, 2):
        fields = records[index].split()
        if len(fields) != 5 or not fields[0].startswith(b":") or fields[4] == b"U":
            raise ValueError("staged-file metadata is invalid or unmerged")
        path = records[index + 1]
        if fields[1] not in {b"100644", b"100755"} or excluded(path, profile):
            continue
        oid = fields[3]
        if not re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", oid):
            raise ValueError("a staged object identity could not be inspected")
        files.append((path, oid))
    return files


def blob_sizes(files):
    oids = sorted({oid for _, oid in files})
    output = git(
        "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_data=b"\n".join(oids) + b"\n",
    )
    sizes = {}
    for record in output.splitlines():
        oid, kind, size = record.split()
        if kind != b"blob" or not size.isdigit() or oid in sizes:
            raise ValueError("a staged blob size could not be inspected")
        sizes[oid] = int(size)
    if set(sizes) != set(oids):
        raise ValueError("staged blob sizes are incomplete")
    return sizes


def generated_attributes(files):
    attributes = (b"linguist-generated", b"linguist-vendored")
    output = git(
        "check-attr", "--cached", "-z", "--stdin", *(attr.decode() for attr in attributes),
        input_data=b"\0".join(path for path, _ in files) + b"\0",
    ).split(b"\0")
    if output[-1] != b"" or len(output) != len(files) * 6 + 1:
        raise ValueError("staged generated-file attributes could not be inspected")
    generated = set()
    for index, (path, _) in enumerate(files):
        for offset, attribute in enumerate(attributes):
            actual_path, actual_attribute, value = output[index * 6 + offset * 3:index * 6 + offset * 3 + 3]
            if (actual_path, actual_attribute) != (path, attribute):
                raise ValueError("staged generated-file attributes do not match candidates")
            if value in {b"set", b"true"}:
                generated.add(path)
    return generated


def blob_prefix(oid, size):
    count = min(PREFIX_BYTES, size)
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1")
    process = subprocess.Popen(
        ["git", "cat-file", "blob", oid.decode("ascii")],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
    )
    chunks = []

    def read_prefix():
        try:
            chunks.append(process.stdout.read(count))
        except OSError:
            pass  # The missing chunk below fails closed.

    # A pipe read itself can block; wait() alone cannot bound it. A reader thread
    # works for subprocess pipes on Windows as well as POSIX systems.
    reader = threading.Thread(target=read_prefix, daemon=True)
    reader.start()
    try:
        reader.join(timeout=10)
        if reader.is_alive():
            process.kill()
            process.wait(timeout=10)
            reader.join(timeout=10)
            raise ValueError("a staged blob prefix timed out")
    finally:
        process.stdout.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise ValueError("a staged blob prefix could not be inspected") from None
    # Closing early can give Git SIGPIPE; only the bounded prefix is needed.
    if len(chunks) != 1 or len(chunks[0]) != count:
        raise ValueError("a staged blob prefix is incomplete")
    return chunks[0]


def report(oversized, max_bytes):
    print(f"Staged authored files exceed {max_bytes:,} bytes (approximate tokens at bytes/4):", file=sys.stderr)
    for path, size in oversized[:10]:
        name = json.dumps(os.fsdecode(path), ensure_ascii=True)
        print(f"  {name}: {size:,} bytes (~{(size + 3) // 4:,} tokens)", file=sys.stderr)
    if len(oversized) > 10:
        print(f"  ...and {len(oversized) - 10} more files", file=sys.stderr)
    print(
        "\nFor a large document or corpus, refine the search first: narrow paths and "
        "search specific terms, headings, or symbols with rg -n, then read relevant "
        "bounded sections. Refine noisy queries before widening scope; preserve complete "
        "coverage when the task requires it. Do not read the whole corpus by default.\n"
        "For authored code, split cohesive responsibilities into focused modules, update "
        "callers/imports, and run the owner's checks before restaging. Do not shave comments "
        "or whitespace, or fragment documents, merely to get below the limit. Mark genuine "
        "generated/vendor content through reviewed .gitattributes; do not exempt authored "
        "code to silence this check. This helper does not edit or stage files.",
        file=sys.stderr,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="Selected checkout (default: current working directory)")
    parser.add_argument("--profile", help="Explicit repository-relative JSON profile; no automatic discovery")
    parser.add_argument("--max-bytes", type=positive_integer, help="Positive byte limit, overriding profile/default 20000")
    args = parser.parse_args(argv)
    root = repository_root(args.repo)
    os.chdir(root)
    profile = load_profile(root, args.profile)
    max_bytes = args.max_bytes if args.max_bytes is not None else profile.get("max_bytes", MAX_BYTES)
    files = staged_files(profile)
    if not files:
        return 0
    sizes = blob_sizes(files)
    candidates = [(path, oid) for path, oid in files if sizes[oid] > max_bytes]
    if not candidates:
        return 0
    generated = generated_attributes(candidates)
    oversized = []
    for path, oid in candidates:
        if path in generated:
            continue
        prefix = blob_prefix(oid, sizes[oid])
        if b"\0" not in prefix and not GENERATED_HEADER.search(prefix):
            oversized.append((path, sizes[oid]))
    if oversized:
        report(oversized, max_bytes)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("Unable to inspect staged file sizes; check the Git index and explicit profile, then retry.", file=sys.stderr)
        sys.exit(1)
