#!/usr/bin/env python3
"""Emit compact, read-only Git repository and recursive-submodule inventories."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

sys.dont_write_bytecode = True

_SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if _SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, _SCRIPT_DIRECTORY)

from pipeline_support import (
    Runner,
    Target,
    WatchError,
    discover_roots,
    discover_targets,
    ordered_push_targets,
    redact,
    run_command,
)


def parse_status(output: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse NUL-delimited porcelain without guessing quoted or renamed paths."""
    headers: dict[str, Any] = {}
    changes: list[dict[str, Any]] = []
    records = iter(output.split("\0"))
    for record in records:
        if not record:
            continue
        if record.startswith("# "):
            key, _, value = record[2:].partition(" ")
            if key == "branch.ab":
                ahead, behind = value.split()
                headers.update(ahead=int(ahead), behind=abs(int(behind)))
            elif key in {"branch.head", "branch.oid", "branch.upstream"}:
                headers[key.removeprefix("branch.")] = value
            continue
        if record.startswith("? "):
            changes.append({"path": record[2:], "status": "??"})
            continue
        kind = record[:1]
        if kind not in {"1", "2", "u"}:
            raise WatchError(f"Unsupported Git status record: {record[:120]}")
        width = {"1": 8, "2": 9, "u": 10}[kind]
        fields = record.split(" ", width)
        if len(fields) != width + 1:
            raise WatchError(f"Malformed Git status record: {record[:120]}")
        item: dict[str, Any] = {
            "path": fields[-1],
            "status": fields[1].replace(".", " "),
        }
        if fields[2] != "N...":
            item["submodule"] = fields[2]
        if kind == "2":
            try:
                item["from"] = next(records)
            except StopIteration as exc:
                raise WatchError("Git rename record is missing its original path") from exc
            if not item["from"]:
                raise WatchError("Git rename record is missing its original path")
        if kind == "u":
            item["conflict"] = True
        changes.append(item)
    changes.sort(key=lambda item: (str(item["path"]), str(item.get("from", ""))))
    return headers, changes


def change_counts(changes: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = {"staged": 0, "unstaged": 0, "untracked": 0, "conflicts": 0}
    for change in changes:
        status = str(change["status"])
        if status == "??":
            counts["untracked"] += 1
        else:
            counts["staged"] += status[0] not in {" ", "?"}
            counts["unstaged"] += status[1] not in {" ", "?"}
            counts["conflicts"] += bool(change.get("conflict"))
    return {name: count for name, count in counts.items() if count}


def diff_summary(target: Target, runner: Runner, *, staged: bool) -> dict[str, int]:
    arguments = ["git", "diff"]
    if staged:
        arguments.append("--cached")
    arguments.extend(["--numstat", "-z", "--no-renames", "--no-ext-diff", "--no-textconv", "--"])
    output = runner(arguments, cwd=target.path) or ""
    summary = {"files": 0, "added": 0, "removed": 0, "binary": 0}
    for record in output.split("\0"):
        if not record:
            continue
        try:
            added, removed, _ = record.split("\t", 2)
        except ValueError as exc:
            raise WatchError(f"Malformed Git diff summary for {target.label}") from exc
        summary["files"] += 1
        if added == "-" or removed == "-":
            summary["binary"] += 1
        else:
            summary["added"] += int(added)
            summary["removed"] += int(removed)
    return {name: value for name, value in summary.items() if value or name == "files"}


def bounded_patch(text: str, max_lines: int, max_chars: int) -> str:
    lines = redact(text).splitlines()
    if len(lines) > max_lines:
        if max_lines == 1:
            lines = lines[-1:]
        else:
            before = max(1, (max_lines - 1) // 3)
            after = max_lines - before - 1
            omitted = len(lines) - before - after
            tail = lines[-after:] if after else []
            lines = [*lines[:before], f"[omitted {omitted} patch lines]", *tail]
    output = "\n".join(lines)
    if len(output) > max_chars:
        marker = "\n[patch characters omitted]\n"
        available = max_chars - len(marker)
        if available <= 0:
            output = output[-max_chars:]
        else:
            before = available // 3
            after = available - before
            output = f"{output[:before]}{marker}{output[-after:]}"
    # The character-truncation marker can introduce new lines. Enforce both
    # independent bounds on the final excerpt, including very small budgets.
    final_lines = output.splitlines()
    if len(final_lines) > max_lines:
        output = "\n".join(final_lines[-max_lines:])
    return output


def validate_patch_paths(paths: Sequence[str]) -> None:
    for path in paths:
        if (not path or "\0" in path or Path(path).drive
                or any(part in {"", ".", ".."} for part in path.split("/"))
                or Path(path).as_posix() != path):
            raise WatchError("A patch file path must be a canonical repository-relative filename")
    if any(other.startswith(path + "/") for path in paths for other in paths):
        raise WatchError("Patch file paths overlap; select each parent or descendant separately")


def exclude_descendants(path: str, selected_paths: Sequence[str]) -> str:
    """Exclude child paths without excluding a file or gitlink at this name."""
    escaped = "".join("\\" + char if char in "\\*?[]" else char for char in path)
    pattern = escaped + "/**"
    # Git also tries the glob text literally. Each extra /** matches the same
    # descendants but moves that literal prefix past any selected filename.
    while any(other == pattern or other.startswith(pattern + "/") for other in selected_paths):
        pattern += "/**"
    # A root-relative glob keeps Git for Windows from treating its escapes as separators.
    return f":(top,exclude,glob){pattern}"


def worktree_identity(root: Path, path: str) -> tuple[tuple[Any, ...], str | None]:
    """Verify native entry spelling without following symlinks or guessing case rules."""
    def fingerprint(info, *, leaf=False):
        symlink = stat.S_ISLNK(info.st_mode)
        reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if (symlink or reparse) and not (leaf and symlink):
            raise ValueError("symlink or reparse path")
        if not info.st_ino or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode) or leaf and symlink):
            raise ValueError("unavailable filesystem identity")
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    secure = (os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
              and os.scandir in os.supports_fd and hasattr(os, "O_NOFOLLOW"))
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    identities = []
    current, descriptor = root, None
    try:
        if secure:
            descriptor = os.open(root, flags)
        parts = path.split("/")
        for position, component in enumerate(parts):
            parent = os.fstat(descriptor) if descriptor is not None else current.lstat()
            identities.append((str(current), fingerprint(parent)))
            if not stat.S_ISDIR(parent.st_mode):
                raise ValueError("unavailable parent directory identity")
            with os.scandir(descriptor if descriptor is not None else current) as entries:
                exact = any(os.fsencode(entry.name) == os.fsencode(component) for entry in entries)
            candidate = current / component
            try:
                info = (os.stat(component, dir_fd=descriptor, follow_symlinks=False)
                        if descriptor is not None else candidate.lstat())
            except FileNotFoundError:
                identities.append((path, "missing"))
                break
            if not exact:
                raise ValueError("ambiguous filesystem spelling")
            identities.append((str(candidate), fingerprint(info, leaf=position == len(parts) - 1)))
            if position < len(parts) - 1 and descriptor is not None:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                try:
                    if fingerprint(os.fstat(next_descriptor)) != fingerprint(info):
                        raise ValueError("changed filesystem identity")
                except BaseException:
                    os.close(next_descriptor)
                    raise
                os.close(descriptor)
                descriptor = next_descriptor
            current = candidate
    except (OSError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, ValueError) else "unavailable filesystem identity"
        return (), f"Unstaged patch withheld for {path!r}: {detail}"
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return tuple(identities), None


def repository_snapshot(
    target: Target,
    roots: Sequence[Target],
    runner: Runner,
    *,
    max_paths: int,
    patch: bool,
    paths: Sequence[str],
    max_patch_lines: int,
    max_patch_chars: int,
) -> dict[str, Any]:
    validate_patch_paths(paths)
    output = runner(
        ["git", "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"],
        cwd=target.path,
    ) or ""
    headers, changes = parse_status(output)
    if headers.get("oid") and headers["oid"] != target.head:
        raise WatchError(f"Repository HEAD changed during inventory: {target.path}")
    if headers.get("head") and headers["head"] != target.branch:
        raise WatchError(f"Repository branch changed during inventory: {target.path}")
    changed_paths = {str(item[key]) for item in changes for key in ("path", "from") if key in item}
    gitlink_paths = {
        str(item[key]) for item in changes if "submodule" in item
        for key in ("path", "from") if key in item
    }
    for path in paths:
        selected = target.path / path
        has_descendants = any(changed.startswith(path + "/") for changed in changed_paths)
        if path in gitlink_paths and has_descendants:
            raise WatchError(f"Patch gitlink has an ambiguous directory transition: {path!r}")
        if path not in changed_paths and (
            has_descendants
            or (selected.is_dir() and not selected.is_symlink())
        ):
            raise WatchError(f"Patch path is a directory, not an exact changed file or gitlink: {path!r}")
    relative = target.path.relative_to(target.root)
    relative_path = relative.as_posix() if relative.parts else "."
    ancestors = [
        candidate for candidate in roots
        if candidate.path != target.path and target.path.is_relative_to(candidate.path)
    ]
    parent = max(ancestors, key=lambda candidate: candidate.depth, default=None)
    parent_path = None
    if parent:
        parent_relative = parent.path.relative_to(target.root)
        parent_path = parent_relative.as_posix() if parent_relative.parts else "."
    counts = change_counts(changes)
    snapshot: dict[str, Any] = {
        "path": relative_path,
        "parent": parent_path,
        "repository": target.repository,
        "branch": target.branch,
        "upstream": f"{target.remote}/{target.upstream_branch}",
        "head": target.head,
        "changes": changes[:max_paths],
    }
    if "ahead" in headers:
        snapshot["ahead"] = headers["ahead"]
        snapshot["behind"] = headers["behind"]
    if counts:
        snapshot["counts"] = counts
    if len(changes) > max_paths:
        snapshot["omitted_paths"] = len(changes) - max_paths
    for category in ("staged", "unstaged"):
        if not counts.get(category):
            continue
        staged = category == "staged"
        snapshot.setdefault("diff", {})[category] = diff_summary(target, runner, staged=staged)
        if patch:
            excerpt, reasons = "", []
            groups = [paths] if staged or not paths else [[path] for path in paths]
            for selected_paths in groups:
                identity = None
                if selected_paths and not staged:
                    identity, reason = worktree_identity(target.path, selected_paths[0])
                    if reason:
                        reasons.append(reason)
                        continue
                arguments = ["git", "diff"]
                if staged:
                    arguments.append("--cached")
                if selected_paths:
                    arguments.append("--submodule=short")
                arguments.extend([
                    "--no-ext-diff", "--no-textconv", "--no-color", "--unified=2", "--",
                    *(f":(literal){path}" for path in selected_paths),
                    *(exclude_descendants(path, selected_paths) for path in selected_paths),
                ])
                output = runner(arguments, cwd=target.path) or ""
                if identity is not None:
                    after, reason = worktree_identity(target.path, selected_paths[0])
                    if reason or identity != after:
                        reasons.append(reason or f"Unstaged patch withheld for {selected_paths[0]!r}: working-tree identity changed during capture")
                        continue
                excerpt = bounded_patch("\n".join(part for part in (excerpt, output) if part), max_patch_lines, max_patch_chars)
            if reasons:
                snapshot.setdefault("patch_withheld", {})[category] = "; ".join(reasons)
            if excerpt:
                snapshot.setdefault("patch", {})[category] = excerpt
    return snapshot


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--repo", type=Path, action="append", default=[])
    argument_parser.add_argument("--cwd", type=Path, default=Path.cwd())
    argument_parser.add_argument("--include-siblings", action="store_true")
    argument_parser.add_argument("--github-host", action="append", default=[], help="Explicitly verified GitHub Enterprise hostname (repeatable)")
    argument_parser.add_argument("--max-paths", type=int, default=30)
    argument_parser.add_argument("--patch", action="store_true")
    argument_parser.add_argument(
        "--path", action="append", default=[],
        help="Exact file relative to each explicit --repo checkout, or the current checkout; "
             "implicit submodules and siblings retain metadata only (repeatable)",
    )
    argument_parser.add_argument("--max-patch-lines", type=int, default=40)
    argument_parser.add_argument("--max-patch-chars", type=int, default=4000)
    return argument_parser


def main(argv: Sequence[str] | None = None) -> int:
    options = parser().parse_args(argv)
    if min(options.max_paths, options.max_patch_lines, options.max_patch_chars) <= 0:
        raise WatchError("Inventory limits must be positive")
    if options.path and not options.patch:
        raise WatchError("A patch path requires --patch")
    validate_patch_paths(options.path)
    roots = discover_roots(
        options.cwd, options.repo, run_command,
        include_siblings=options.include_siblings and not options.path,
    )
    patch_roots = set(roots)
    if options.path and options.include_siblings:
        roots = discover_roots(options.cwd, options.repo, run_command, include_siblings=True)
    discovered = discover_targets(roots, run_command, deduplicate=False, github_hosts=options.github_host)
    for root in roots:
        targets = [target for target in discovered if target.root == root]
        snapshots = [
            repository_snapshot(
                target,
                targets,
                run_command,
                max_paths=options.max_paths,
                patch=options.patch and (not options.path or target.path == root and root in patch_roots),
                paths=options.path if target.path == root and root in patch_roots else [],
                max_patch_lines=options.max_patch_lines,
                max_patch_chars=options.max_patch_chars,
            )
            for target in ordered_push_targets(targets)
        ]
        event = {
            "event": "inventory",
            "root": str(root),
            "repositories": snapshots,
        }
        print(json.dumps(event, separators=(",", ":"), ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WatchError as error:
        event = {"event": "blocked", "reason": str(error)}
        print(json.dumps(event, separators=(",", ":"), ensure_ascii=True), flush=True)
        raise SystemExit(2)
