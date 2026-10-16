#!/usr/bin/env python3
"""Read-only deep metadata inventory. The only write is an exclusive JSONL report.

Adapted from ChatGPT Question and Answer conservative-machine-cleanup inventory.
Traversal permission is independent of cleanup eligibility; no record authorizes removal.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import heapq
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import unicodedata


WINDOWS_SKIP = 0x400 | 0x1000 | 0x40000 | 0x400000  # reparse/offline/recall
MAC_DATALESS = 0x40000000
LOCAL_LINUX_FS = {
    "ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "f2fs", "jfs", "reiserfs",
    "vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "hfs", "hfsplus", "apfs",
    "tmpfs", "ramfs", "overlay", "aufs", "squashfs", "erofs", "bcachefs",
}
CLOUD_NAMES = {
    "cloudstorage", "mobile documents", "dropbox", "google drive", "googledrive",
    "icloud", "backups", "backup", "time machine backups", ".snapshots", ".snapshot",
}


def folded(value):
    return unicodedata.normalize("NFC", value).casefold()


def path_key(path):
    return os.path.normcase(os.path.abspath(path))


def inside(path, parent):
    try:
        return os.path.commonpath((path_key(path), path_key(parent))) == path_key(parent)
    except ValueError:
        return False


def identity(info):
    return (info.st_dev, info.st_ino)


def cloud_name(name):
    value = folded(name)
    return value in CLOUD_NAMES or value == "onedrive" or value.startswith("onedrive - ")


def skip_attributes(info):
    if getattr(info, "st_file_attributes", 0) & WINDOWS_SKIP:
        return "reparse_or_offline_placeholder"
    if getattr(info, "st_flags", 0) & MAC_DATALESS:
        return "dataless_placeholder"
    if stat.S_ISLNK(info.st_mode):
        return "symlink"
    return None


def mount_unescape(value):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def linux_mounts(text):
    mounts = []
    for line in text.splitlines():
        before, after = line.split(" - ", 1)
        mounts.append((Path(mount_unescape(before.split()[4])), after.split()[0]))
    return mounts


def mounted_filesystems(root):
    """Fail closed when the root's local filesystem cannot be established."""
    if sys.platform == "win32":
        import ctypes
        if str(root).startswith("\\\\"):
            raise ValueError("network roots are outside the audit boundary")
        kind = ctypes.windll.kernel32.GetDriveTypeW(str(root.anchor))
        if kind not in (2, 3, 6):  # removable, fixed, RAM disk
            raise ValueError("root is not a verified local drive")
        return []
    if sys.platform.startswith("linux"):
        mounts = linux_mounts(Path("/proc/self/mountinfo").read_text())
        allowed = lambda fs: fs in LOCAL_LINUX_FS
    elif sys.platform == "darwin":
        result = subprocess.run(
            ["/sbin/mount"], capture_output=True, text=True, check=True, timeout=10
        )
        mounts = []
        for line in result.stdout.splitlines():
            match = re.match(r".* on (.*) \((.*)\)$", line)
            if match:
                mounts.append((Path(match[1]), match[2]))
        allowed = lambda fs: "local" in fs.split(", ")
    else:
        raise ValueError("supported platforms: macOS, Linux, Windows")
    containing = [(path, fs) for path, fs in mounts if inside(root, path)]
    if not containing:
        raise ValueError("root filesystem could not be identified")
    _, fs = max(containing, key=lambda item: len(str(item[0])))
    if not allowed(fs):
        raise ValueError("network, virtual, or unknown root filesystem")
    return [{"path": str(path), "filesystem": fs, "verified_local": allowed(fs)}
            for path, fs in mounts if path != root and inside(path, root)]


def boundaries(root):
    return {path_key(item["path"]) for item in mounted_filesystems(root)}


def category(path, codex_homes, root=None):
    """Path hints only; never a disposability decision."""
    home = next((h for h in codex_homes if inside(path, h)), None)
    parts = path.parts
    if home is None:
        positions = [i for i, p in enumerate(parts) if folded(p) == ".codex"]
        if positions:
            home = Path(*parts[:positions[-1] + 1])
    if home is not None:
        rel = path.relative_to(home).parts
        low = tuple(folded(p) for p in rel)
        if not rel:
            return "codex-state", str(home)
        first = low[0]
        if first == "worktrees":
            return "codex-worktrees", str(home.joinpath(*rel[:2]))
        if low[:2] == ("plugins", "cache"):
            return "codex-plugin-installations", str(home.joinpath(*rel[:5]))
        if low[:2] in (("plugins", "data"),) or first == "agent-plugins":
            return "codex-plugin-data", str(home.joinpath(*rel[:2]))
        if low[:2] in (("cache", "remote_plugin_catalog"), (".tmp", "plugins")):
            return "codex-plugin-catalogs", str(home.joinpath(*rel[:2]))
        if first in ("sessions", "archived_sessions"):
            return "codex-" + first.replace("_", "-"), str(home / rel[0])
        if first in ("tmp", ".tmp", "shell_snapshots"):
            return "codex-runtime-scratch", str(home.joinpath(*rel[:2]))
        if first in ("automations", "skills", "visualizations"):
            return "codex-" + first, str(home.joinpath(*rel[:2]))
        return "codex-state", str(home / rel[0])
    start = len(root.parts) - 1 if root is not None else 0
    for i, part in enumerate(parts):
        if i < start:
            continue
        low = folded(part)
        if low == ".git":
            return "git-metadata", str(Path(*parts[:i + 1]))
    for i, part in enumerate(parts):
        if i < start:
            continue
        low = folded(part)
        if low in ("tmp", "temp", "scratch", ".tmp"):
            return "possible-scratch", str(Path(*parts[:i + 1]))
        if low in ("cache", "caches", ".cache", "__pycache__", ".pytest_cache",
                   ".ruff_cache", ".mypy_cache", "node_modules", ".venv", "target", "dist", "build"):
            return "cache-or-build-review", str(Path(*parts[:i + 1]))
    return "other", None


def empty_total():
    return {"files": 0, "unique_files": 0, "logical_bytes": 0,
            "allocated_bytes_known": 0, "allocation_unknown_files": 0}


def add_total(total, size, allocated, unique):
    total["files"] += 1
    if unique:
        total["unique_files"] += 1
        total["logical_bytes"] += size
        if allocated is None:
            total["allocation_unknown_files"] += 1
        else:
            total["allocated_bytes_known"] += allocated


class Inventory:
    def __init__(self, root, output, *, codex_homes=(), excludes=(), mounts=(),
                 max_nodes=0, max_seconds=0, clock=time.monotonic):
        self.root = Path(root)
        self.output = output
        self.codex_homes = tuple(sorted(map(Path, codex_homes), key=lambda p: -len(str(p))))
        self.excludes = tuple(map(Path, excludes))
        self.mounts = set(mounts)
        self.max_nodes, self.max_seconds, self.clock = max_nodes, max_seconds, clock
        self.start = self.clock()
        self.progress_at = self.start
        self.nodes = 0
        self.directories_scanned = 0
        self.gaps = Counter()
        self.seen_files = set()
        self.totals = empty_total()
        self.groups, self.children = {}, {}
        self.largest = []
        self.identity_unknown_files = 0
        self.halted = False
        self.root_info = os.stat(self.root, follow_symlinks=False)
        self.root_fd = None

    def emit(self, **record):
        self.output.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")

    def gap(self, path, reason, **details):
        self.gaps[reason] += 1
        self.emit(type="gap", path=str(path), reason=reason, **details)

    def time_over(self):
        return bool(self.max_seconds and self.clock() - self.start >= self.max_seconds)

    def progress(self):
        now = self.clock()
        if now - self.progress_at >= 5:
            print(json.dumps({"nodes": self.nodes, "directories_scanned": self.directories_scanned,
                              "gap_records": sum(self.gaps.values())}), file=sys.stderr, flush=True)
            self.output.flush()
            self.progress_at = now

    def skip(self, path, info):
        reason = skip_attributes(info)
        if reason:
            return reason
        if any(inside(path, ex) for ex in self.excludes):
            return "explicit_exclusion"
        if path != self.root and (path_key(path) in self.mounts or info.st_dev != self.root_info.st_dev):
            return "mount_boundary"
        if stat.S_ISDIR(info.st_mode) and cloud_name(path.name):
            return "cloud_or_backup_tree"
        return None

    @contextmanager
    def directory(self, parts, expected):
        if self.root_fd is not None:
            fd = os.dup(self.root_fd)
            try:
                for part in parts:
                    before = os.stat(part, dir_fd=fd, follow_symlinks=False)
                    if skip_attributes(before) or not stat.S_ISDIR(before.st_mode):
                        raise OSError("directory became a link or placeholder")
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = child
                if identity(os.fstat(fd)) != expected:
                    raise OSError("directory identity changed")
                yield fd
            finally:
                os.close(fd)
        else:
            path = self.checked_windows_directory(parts, expected)
            yield path
            after = os.stat(path, follow_symlinks=False)
            if skip_attributes(after) or identity(after) != expected:
                raise OSError("directory identity changed during enumeration")

    def checked_windows_directory(self, parts, expected):
        path = self.root
        for part in (None, *parts):
            if part is not None:
                path /= part
            info = os.stat(path, follow_symlinks=False)
            if skip_attributes(info) or not stat.S_ISDIR(info.st_mode):
                raise OSError("directory became a link or placeholder")
        if identity(info) != expected:
            raise OSError("directory identity changed")
        return path

    def node(self, path, info):
        self.nodes += 1
        kind = ("directory" if stat.S_ISDIR(info.st_mode) else
                "file" if stat.S_ISREG(info.st_mode) else "link" if stat.S_ISLNK(info.st_mode) else "special")
        reason = self.skip(path, info)
        label, group = category(path, self.codex_homes, self.root)
        size = info.st_size if kind == "file" and not reason else 0
        allocated = getattr(info, "st_blocks", None)
        allocated = allocated * 512 if allocated is not None and kind == "file" and not reason else None
        unique = False
        if kind == "file" and not reason:
            key = identity(info)
            if not info.st_ino:
                self.identity_unknown_files += 1
                unique = True
            else:
                unique = key not in self.seen_files
                self.seen_files.add(key)
            add_total(self.totals, size, allocated, unique)
            rel = path.relative_to(self.root)
            child = str(self.root / rel.parts[0])
            add_total(self.children.setdefault(child, empty_total()), size, allocated, unique)
            if group:
                add_total(self.groups.setdefault((label, group), empty_total()), size, allocated, unique)
            if unique:
                entry = (allocated if allocated is not None else size, size, str(path), allocated)
                heapq.heappush(self.largest, entry)
                if len(self.largest) > 50:
                    heapq.heappop(self.largest)
        self.emit(type="node", path=str(path), kind=kind, category=label,
                  group=group, logical_bytes=size if kind == "file" and not reason else None,
                  allocated_bytes=allocated, counted_unique=unique, mtime_ns=info.st_mtime_ns,
                  owner_uid=getattr(info, "st_uid", None) if os.name != "nt" else None,
                  atime_ns=getattr(info, "st_atime_ns", None),
                  ctime_ns=getattr(info, "st_ctime_ns", None),
                  ownership_matches_current_user=(info.st_uid == os.getuid())
                    if hasattr(os, "getuid") else None,
                  cleanup_eligibility="unverified",
                  device=info.st_dev, inode=info.st_ino, skip=reason)
        if reason:
            self.gap(path, reason)
        self.progress()
        return kind == "directory" and not reason

    def run(self):
        stack = []
        try:
            if self.skip(self.root, self.root_info):
                self.node(self.root, self.root_info)
                raise ValueError("root is outside the traversal boundary")
            if os.name != "nt":
                self.root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                if identity(os.fstat(self.root_fd)) != identity(self.root_info):
                    raise OSError("root identity changed")
            if self.node(self.root, self.root_info):
                stack.append(((), identity(self.root_info)))
            while stack and not self.halted:
                parts, expected = stack.pop()
                path = self.root.joinpath(*parts)
                pending = []
                try:
                    with self.directory(parts, expected) as handle:
                        entries = []
                        with os.scandir(handle) as listing:
                            for entry in listing:
                                if self.time_over() or (self.max_nodes and self.nodes + len(entries) >= self.max_nodes):
                                    self.gap(path, "budget", phase="enumeration", buffered_entries=len(entries))
                                    self.halted = True
                                    break
                                entries.append(entry)
                                self.progress()
                        for index, entry in enumerate(sorted(entries, key=lambda e: (folded(e.name), e.name))):
                            if self.time_over():
                                self.gap(path, "budget", phase="metadata", unprocessed_entries=len(entries) - index)
                                self.halted = True
                                break
                            child = path / entry.name
                            try:
                                # On Windows check cached cloud attributes before any further probe
                                if os.name == "nt":
                                    self.checked_windows_directory(parts, expected)
                                    cached = entry.stat(follow_symlinks=False)
                                    if skip_attributes(cached):
                                        self.node(child, cached)
                                        continue
                                    info = os.stat(child, follow_symlinks=False)
                                else:
                                    info = os.stat(entry.name, dir_fd=handle, follow_symlinks=False)
                                if self.node(child, info):
                                    pending.append(((*parts, entry.name), identity(info)))
                            except OSError as error:
                                self.gap(child, "metadata_error", error=type(error).__name__, errno=error.errno)
                        if not self.halted:
                            self.directories_scanned += 1
                    stack.extend(reversed(pending))
                except OSError as error:
                    self.gap(path, "directory_error", error=type(error).__name__, errno=error.errno)
            if self.halted:
                self.gap(self.root, "unvisited_frontier", pending_directories=len(stack))
        except KeyboardInterrupt:
            self.halted = True
            self.gap(self.root, "interrupted", pending_directories=len(stack))
        finally:
            if self.root_fd is not None:
                os.close(self.root_fd)
                self.root_fd = None
        summary = {
            "type": "summary", "root": str(self.root), "nodes": self.nodes,
            "directories_scanned": self.directories_scanned,
            "complete_within_boundaries": not self.halted and not any(
                self.gaps[k] for k in ("metadata_error", "directory_error", "interrupted")),
            "exhaustive": not self.halted and not self.gaps,
            "gaps": dict(sorted(self.gaps.items())), "file_totals": self.totals,
            "identity_unknown_files": self.identity_unknown_files,
            "groups": [{"category": label, "path": path, **total}
                       for (label, path), total in sorted(self.groups.items())],
            "root_children": [{"path": path, **total} for path, total in sorted(self.children.items())],
            "largest_files": [{"path": path, "logical_bytes": size, "allocated_bytes": allocated}
                              for _, size, path, allocated in sorted(self.largest, key=lambda e: (-e[0], -e[1], e[2]))],
            "elapsed_seconds": round(self.clock() - self.start, 3),
            "cleanup_actions": 0,
        }
        self.emit(**summary)
        self.output.flush()
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path.home()))
    parser.add_argument("--output", required=True)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--codex-home", action="append", default=[])
    parser.add_argument("--max-nodes", type=int, default=0)
    parser.add_argument("--max-seconds", type=float, default=0)
    args = parser.parse_args(argv)
    if args.max_nodes < 0 or args.max_seconds < 0 or not math.isfinite(args.max_seconds):
        parser.error("budgets must be nonnegative; zero means unlimited")
    try:
        requested = Path(os.path.abspath(Path(args.root).expanduser()))
        if os.name == "nt" and str(requested).startswith("\\\\"):
            raise ValueError("network and device-namespace roots are outside the audit boundary")
        # Reject placeholders/cloud ancestry before resolving the requested root alias
        for part in reversed((requested, *requested.parents)):
            info = os.stat(part, follow_symlinks=False)
            attrs = getattr(info, "st_file_attributes", 0)
            if attrs & WINDOWS_SKIP or getattr(info, "st_flags", 0) & MAC_DATALESS or cloud_name(part.name):
                raise ValueError("root is within a reparse, placeholder, cloud, or backup tree")
        root = requested.resolve(strict=True)
        for part in reversed((root, *root.parents)):
            info = os.stat(part, follow_symlinks=False)
            if skip_attributes(info) or cloud_name(part.name):
                raise ValueError("resolved root is within a link, placeholder, cloud, or backup tree")
        info = os.stat(root, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("root must be a directory")
        volumes = mounted_filesystems(root)
        mounts = {path_key(item["path"]) for item in volumes}
        output = Path(args.output).expanduser().absolute()
        parent = output.parent.resolve(strict=True)
        if os.name != "nt":
            parent_info = parent.stat()
            if parent_info.st_uid != os.getuid() or stat.S_IMODE(parent_info.st_mode) & 0o077:
                raise ValueError("output parent must be private and current-user-owned")
        output = parent / output.name
        excludes = []
        for value in args.exclude:
            exclusion = Path(os.path.abspath(Path(value).expanduser()))
            if inside(exclusion, requested):
                exclusion = root / exclusion.relative_to(requested)
            if not inside(exclusion, root):
                raise ValueError("exclusions must be under the requested or resolved root")
            excludes.append(exclusion)
        excludes.append(output)
        homes = args.codex_home or [os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")]
        homes = [Path(p).expanduser().resolve() for p in homes]
        usage = shutil.disk_usage(root)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            scanner = Inventory(root, stream, codex_homes=homes, excludes=excludes, mounts=mounts,
                                max_nodes=args.max_nodes, max_seconds=args.max_seconds)
            scanner.emit(type="header", schema_version=1, requested_root=str(requested),
                         resolved_root=str(root), platform=sys.platform, started_unix_ns=time.time_ns(),
                         codex_homes=list(map(str, homes)), exclusions=list(map(str, excludes)),
                         mounted_filesystems=volumes,
                         volume_policy="mounted descendants require separate verified-local scans",
                         max_nodes=args.max_nodes, max_seconds=args.max_seconds,
                         filesystem_capacity_bytes=usage.total, filesystem_free_bytes=usage.free,
                         snapshot=False, reads_file_bodies=False)
            summary = scanner.run()
        print(json.dumps({"report": str(output), "nodes": summary["nodes"],
                          "exhaustive": summary["exhaustive"], "gaps": summary["gaps"]}))
        return 0 if summary["complete_within_boundaries"] else 2
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Audit unavailable or incomplete: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
