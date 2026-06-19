#!/usr/bin/env python3
"""Prune deleted Codex threads without separating live rollouts from their state."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


UUID_RE = re.compile(
    r"(?<![0-9a-f])([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12})(?![0-9a-f])",
    re.IGNORECASE,
)
STATE_RE = re.compile(r"^state_(\d+)\.sqlite$")
DB_PATTERNS = {
    "logs": re.compile(r"^logs_(\d+)\.sqlite$"),
    "goals": re.compile(r"^goals_(\d+)\.sqlite$"),
    "memories": re.compile(r"^memories_(\d+)\.sqlite$"),
}


def extract_uuid(value: object) -> str | None:
    matches = UUID_RE.findall(str(value))
    return matches[-1].lower() if matches else None


def thread_ref(value: object) -> str | None:
    text = str(value)
    if UUID_RE.fullmatch(text):
        return text.lower()
    if text.startswith("local:") and UUID_RE.fullmatch(text[6:]):
        return text[6:].lower()
    return None


def uuid7_created_at(value: str) -> float | None:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError):
        return None
    if parsed.version != 7:
        return None
    return (parsed.int >> 80) / 1000.0


def old_enough(value: str, cutoff: float, fallback: float | None = None) -> bool:
    created_at = uuid7_created_at(value)
    timestamps = [timestamp for timestamp in (created_at, fallback) if timestamp is not None]
    return bool(timestamps) and max(timestamps) < cutoff


@contextmanager
def connect(path: Path, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    if readonly:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15)
    else:
        connection = sqlite3.connect(path, timeout=15)
        connection.execute("PRAGMA busy_timeout=15000")
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def cleanup_lock(root: Path):
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    path = Path(tempfile.gettempdir()) / f"clean-codex-{digest}.lock"
    with path.open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another cleanup is already running for {root}") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def newest_versioned_db(root: Path, pattern: re.Pattern[str]) -> Path | None:
    candidates: list[tuple[int, Path]] = []
    for path in root.glob("*.sqlite"):
        match = pattern.fullmatch(path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def size_bytes(path: Path) -> int:
    try:
        if path.is_dir() and not path.is_symlink():
            return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        return path.stat().st_size
    except OSError:
        return 0


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    raise AssertionError("unreachable")


def session_files(root: Path) -> list[tuple[Path, str | None]]:
    files: list[tuple[Path, str | None]] = []
    for dirname in ("sessions", "archived_sessions"):
        base = root / dirname
        if base.is_dir():
            files.extend((path, extract_uuid(path.name)) for path in base.rglob("*.jsonl"))
    return files


@dataclass(frozen=True)
class ThreadRow:
    thread_id: str
    rollout_path: Path
    archived: bool
    updated_at: float | None


@dataclass(frozen=True)
class FileCandidate:
    kind: str
    path: Path
    thread_id: str | None = None


class CleanupPlan:
    def __init__(self, root: Path, cutoff: float):
        self.root = root
        self.cutoff = cutoff
        self.state_db = newest_versioned_db(root, STATE_RE)
        if self.state_db is None:
            raise RuntimeError(
                f"No state_N.sqlite database found under {root}; refusing to orphan sessions"
            )
        self.legacy_state_db = root / "sqlite" / self.state_db.name
        self.related_dbs: dict[str, list[Path]] = defaultdict(list)
        for kind, pattern in DB_PATTERNS.items():
            primary = newest_versioned_db(root, pattern)
            if primary:
                self.related_dbs[kind].append(primary)
                legacy = root / "sqlite" / primary.name
                if legacy.is_file():
                    self.related_dbs[kind].append(legacy)

        self.rows = self._read_threads(self.state_db)
        self.db_ids = set(self.rows)
        self.remove_primary_ids = self._primary_ids_to_remove()
        self.keep_ids = self.db_ids - self.remove_primary_ids
        self.remove_legacy_ids = self._legacy_ids_to_remove()
        self.retired_ids = self.remove_primary_ids | self.remove_legacy_ids
        self.file_candidates = self._file_candidates()
        self.db_orphan_ids = self._related_db_orphan_ids()
        self.edge_counts = self._edge_counts()
        self.state_dependent_counts = self._state_dependent_counts()
        self.json_rewrites = self._prepare_json_rewrites()

    def _read_threads(self, path: Path) -> dict[str, ThreadRow]:
        with connect(path, readonly=True) as connection:
            if not table_exists(connection, "threads"):
                raise RuntimeError(f"Missing threads table in {path}")
            columns = table_columns(connection, "threads")
            updated_expression = (
                "updated_at_ms / 1000.0"
                if "updated_at_ms" in columns
                else "updated_at"
                if "updated_at" in columns
                else "NULL"
            )
            archived_expression = "archived" if "archived" in columns else "0"
            query = (
                "SELECT id, rollout_path, "
                f"{archived_expression}, {updated_expression} FROM threads"
            )
            result = {}
            for thread_id, rollout_path, archived, updated_at in connection.execute(query):
                normalized = str(thread_id).lower()
                normalized_rollout = Path(str(rollout_path)).expanduser()
                if not normalized_rollout.is_absolute():
                    normalized_rollout = self.root / normalized_rollout
                result[normalized] = ThreadRow(
                    thread_id=normalized,
                    rollout_path=normalized_rollout,
                    archived=bool(archived),
                    updated_at=float(updated_at) if updated_at is not None else None,
                )
            return result

    def _primary_ids_to_remove(self) -> set[str]:
        archived_root = self.root / "archived_sessions"
        result = set()
        for thread_id, row in self.rows.items():
            archived = row.archived or is_under(row.rollout_path, archived_root)
            missing = not row.rollout_path.is_file()
            if (archived or missing) and old_enough(
                thread_id, self.cutoff, row.updated_at
            ):
                result.add(thread_id)
        return result

    def _legacy_ids_to_remove(self) -> set[str]:
        if not self.legacy_state_db.is_file():
            return set()
        legacy_rows = self._read_threads(self.legacy_state_db)
        return {
            thread_id
            for thread_id, row in legacy_rows.items()
            if thread_id not in self.keep_ids
            and old_enough(thread_id, self.cutoff, row.updated_at)
        }

    def _file_candidates(self) -> list[FileCandidate]:
        result: list[FileCandidate] = []
        sessions_root = self.root / "sessions"
        archived_root = self.root / "archived_sessions"
        for path, thread_id in session_files(self.root):
            if not thread_id or not old_enough(thread_id, self.cutoff, path.stat().st_mtime):
                continue
            if is_under(path, archived_root) or (
                is_under(path, sessions_root) and thread_id not in self.keep_ids
            ):
                result.append(FileCandidate("rollout", path, thread_id))

        snapshots = self.root / "shell_snapshots"
        if snapshots.is_dir():
            for path in snapshots.glob("*.sh"):
                thread_id = extract_uuid(path.name)
                if (
                    thread_id
                    and thread_id not in self.keep_ids
                    and old_enough(thread_id, self.cutoff, path.stat().st_mtime)
                ):
                    result.append(FileCandidate("shell snapshot", path, thread_id))

        generated = self.root / "generated_images"
        if generated.is_dir():
            for path in generated.iterdir():
                thread_id = path.name.lower() if UUID_RE.fullmatch(path.name) else None
                if (
                    thread_id
                    and thread_id not in self.keep_ids
                    and old_enough(thread_id, self.cutoff, path.stat().st_mtime)
                ):
                    result.append(FileCandidate("generated image directory", path, thread_id))

        visualizations = self.root / "visualizations"
        if visualizations.is_dir():
            for path in visualizations.rglob("*"):
                thread_id = (
                    path.name.lower()
                    if path.is_dir() and UUID_RE.fullmatch(path.name)
                    else None
                )
                if (
                    thread_id
                    and thread_id not in self.keep_ids
                    and old_enough(thread_id, self.cutoff, path.stat().st_mtime)
                ):
                    result.append(FileCandidate("visualization directory", path, thread_id))

        for path in self.root.glob("state_*.sqlite.pre-orphan-prune-*.bak*"):
            result.append(FileCandidate("obsolete cleanup backup", path))
        return result

    def _distinct_ids(self, path: Path, table: str, column: str) -> set[str]:
        with connect(path, readonly=True) as connection:
            if not table_exists(connection, table):
                return set()
            return {
                str(row[0]).lower()
                for row in connection.execute(
                    f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL"
                )
            }

    def _related_db_orphan_ids(self) -> dict[Path, set[str]]:
        mapping: dict[Path, set[str]] = {}
        specs = {
            "logs": ("logs", "thread_id"),
            "goals": ("thread_goals", "thread_id"),
            "memories": ("stage1_outputs", "thread_id"),
        }
        for kind, paths in self.related_dbs.items():
            table, column = specs[kind]
            for path in paths:
                mapping[path] = {
                    thread_id
                    for thread_id in self._distinct_ids(path, table, column)
                    if thread_id not in self.keep_ids
                    and (
                        thread_id in self.retired_ids
                        or old_enough(thread_id, self.cutoff)
                    )
                }
        return mapping

    def _edge_count(self, path: Path) -> int:
        if not path.is_file():
            return 0
        with connect(path, readonly=True) as connection:
            if not table_exists(connection, "thread_spawn_edges"):
                return 0
            return sum(
                1
                for parent, child in connection.execute(
                    "SELECT parent_thread_id, child_thread_id FROM thread_spawn_edges"
                )
                if (
                    str(parent).lower() not in self.keep_ids
                    and (
                        str(parent).lower() in self.retired_ids
                        or old_enough(str(parent).lower(), self.cutoff)
                    )
                )
                or (
                    str(child).lower() not in self.keep_ids
                    and (
                        str(child).lower() in self.retired_ids
                        or old_enough(str(child).lower(), self.cutoff)
                    )
                )
            )

    def _edge_counts(self) -> dict[Path, int]:
        paths = [self.state_db]
        if self.legacy_state_db.is_file():
            paths.append(self.legacy_state_db)
        return {path: self._edge_count(path) for path in paths}

    def _state_dependent_count(self, path: Path) -> int:
        if not path.is_file():
            return 0
        total = 0
        with connect(path, readonly=True) as connection:
            for table, column in (
                ("thread_dynamic_tools", "thread_id"),
                ("agent_job_items", "assigned_thread_id"),
            ):
                if not table_exists(connection, table):
                    continue
                for (value,) in connection.execute(
                    f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"
                ):
                    thread_id = str(value).lower()
                    if thread_id not in self.keep_ids and (
                        thread_id in self.retired_ids
                        or old_enough(thread_id, self.cutoff)
                    ):
                        total += 1
        return total

    def _state_dependent_counts(self) -> dict[Path, int]:
        paths = [self.state_db]
        if self.legacy_state_db.is_file():
            paths.append(self.legacy_state_db)
        return {path: self._state_dependent_count(path) for path in paths}

    def _rewrite_jsonl(self, path: Path, field: str) -> tuple[str, int] | None:
        if not path.is_file():
            return None
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        output = []
        removed = 0
        for line in lines:
            try:
                value = json.loads(line).get(field) if line.strip() else None
            except (AttributeError, json.JSONDecodeError):
                value = None
            thread_id = value.lower() if isinstance(value, str) else None
            if (
                thread_id
                and thread_id not in self.keep_ids
                and (
                    thread_id in self.retired_ids
                    or old_enough(thread_id, self.cutoff)
                )
            ):
                removed += 1
            else:
                output.append(line)
        return "".join(output), removed

    def _prune_global_state(self, path: Path) -> tuple[str, int] | None:
        if not path.is_file():
            return None
        state = json.loads(path.read_text(encoding="utf-8"))
        atom = state.get("electron-persisted-atom-state", {})
        removed = 0

        def keep(value: object) -> bool:
            thread_id = thread_ref(value)
            return (
                thread_id is None
                or thread_id in self.keep_ids
                or (
                    thread_id not in self.retired_ids
                    and not old_enough(thread_id, self.cutoff)
                )
            )

        def prune_list(container: dict[str, Any], key: str) -> None:
            nonlocal removed
            value = container.get(key)
            if isinstance(value, list):
                replacement = [item for item in value if keep(item)]
                removed += len(value) - len(replacement)
                container[key] = replacement

        def prune_map(container: dict[str, Any], key: str) -> None:
            nonlocal removed
            value = container.get(key)
            if isinstance(value, dict):
                replacement = {item_key: item for item_key, item in value.items() if keep(item_key)}
                removed += len(value) - len(replacement)
                container[key] = replacement

        for key in ("projectless-thread-ids", "pinned-thread-ids"):
            prune_list(state, key)
        for key in (
            "thread-workspace-root-hints",
            "queued-follow-ups",
            "thread-detail-levels",
            "thread-projectless-output-directories",
            "thread-project-assignments",
        ):
            prune_map(state, key)

        sidebar = state.get("sidebar-project-thread-orders", {})
        if isinstance(sidebar, dict):
            for value in sidebar.values():
                if isinstance(value, dict):
                    prune_list(value, "threadIds")

        for key in (
            "composer-prompt-drafts-v1",
            "heartbeat-thread-permissions-by-id",
            "prompt-history",
        ):
            prune_map(atom, key)
        unread = atom.get("unread-thread-ids-by-host-v1", {})
        if isinstance(unread, dict):
            for host, values in unread.items():
                if isinstance(values, list):
                    replacement = [item for item in values if keep(item)]
                    removed += len(values) - len(replacement)
                    unread[host] = replacement

        return json.dumps(state, ensure_ascii=False, separators=(",", ":")), removed

    def _prepare_json_rewrites(self) -> dict[Path, tuple[str, int]]:
        rewrites: dict[Path, tuple[str, int]] = {}
        for path, field in (
            (self.root / "history.jsonl", "session_id"),
            (self.root / "session_index.jsonl", "id"),
        ):
            rewrite = self._rewrite_jsonl(path, field)
            if rewrite:
                rewrites[path] = rewrite
        for path in (
            self.root / ".codex-global-state.json",
            self.root / ".codex-global-state.json.bak",
        ):
            rewrite = self._prune_global_state(path)
            if rewrite:
                rewrites[path] = rewrite
        return rewrites

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
        for candidate in self.file_candidates:
            by_kind[candidate.kind]["count"] += 1
            by_kind[candidate.kind]["bytes"] += size_bytes(candidate.path)
        return {
            "codex_home": str(self.root),
            "state_db": str(self.state_db),
            "kept_threads": len(self.keep_ids),
            "removed_primary_threads": len(self.remove_primary_ids),
            "removed_legacy_threads": len(self.remove_legacy_ids),
            "dependent_thread_ids": sum(
                len(ids) for ids in self.db_orphan_ids.values()
            ),
            "dangling_spawn_edges": sum(self.edge_counts.values()),
            "state_dependent_rows": sum(self.state_dependent_counts.values()),
            "metadata_rows": sum(value[1] for value in self.json_rewrites.values()),
            "files": dict(by_kind),
            "file_count": len(self.file_candidates),
            "file_bytes": sum(size_bytes(item.path) for item in self.file_candidates),
        }


def placeholders(count: int) -> str:
    return ",".join("?" for _ in range(count))


def delete_ids(
    connection: sqlite3.Connection, table: str, column: str, values: set[str]
) -> int:
    if not values or not table_exists(connection, table):
        return 0
    before = connection.total_changes
    connection.execute(
        f"DELETE FROM {table} WHERE {column} IN ({placeholders(len(values))})",
        tuple(sorted(values)),
    )
    return connection.total_changes - before


def stale_thread_ids(plan: CleanupPlan, values: list[str]) -> set[str]:
    return {
        value
        for value in values
        if value not in plan.keep_ids
        and (value in plan.retired_ids or old_enough(value, plan.cutoff))
    }


def cleanup_state_db(path: Path, plan: CleanupPlan, removed_ids: set[str]) -> None:
    if not path.is_file():
        return
    with connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")

        if table_exists(connection, "thread_spawn_edges"):
            stale_edges = stale_thread_ids(
                plan,
                [
                    str(endpoint).lower()
                    for edge in connection.execute(
                        "SELECT parent_thread_id, child_thread_id "
                        "FROM thread_spawn_edges"
                    )
                    for endpoint in edge
                ],
            )
            delete_ids(connection, "thread_spawn_edges", "parent_thread_id", stale_edges)
            delete_ids(connection, "thread_spawn_edges", "child_thread_id", stale_edges)

        if table_exists(connection, "thread_dynamic_tools"):
            stale_tools = stale_thread_ids(
                plan,
                [
                    str(row[0]).lower()
                    for row in connection.execute(
                        "SELECT DISTINCT thread_id FROM thread_dynamic_tools"
                    )
                ],
            )
            delete_ids(connection, "thread_dynamic_tools", "thread_id", stale_tools)

        if table_exists(connection, "agent_job_items"):
            stale_assignments = stale_thread_ids(
                plan,
                [
                    str(row[0]).lower()
                    for row in connection.execute(
                        "SELECT DISTINCT assigned_thread_id FROM agent_job_items "
                        "WHERE assigned_thread_id IS NOT NULL"
                    )
                ],
            )
            if stale_assignments:
                connection.execute(
                    "UPDATE agent_job_items SET assigned_thread_id=NULL "
                    f"WHERE assigned_thread_id IN ({placeholders(len(stale_assignments))})",
                    tuple(sorted(stale_assignments)),
                )

        delete_ids(connection, "threads", "id", removed_ids)
        connection.commit()
        connection.execute("PRAGMA optimize")


def cleanup_related_db(path: Path, ids: set[str]) -> None:
    if not ids:
        return
    with connect(path) as connection:
        if table_exists(connection, "logs"):
            table, column = "logs", "thread_id"
        elif table_exists(connection, "thread_goals"):
            table, column = "thread_goals", "thread_id"
        elif table_exists(connection, "stage1_outputs"):
            table, column = "stage1_outputs", "thread_id"
        else:
            return
        connection.execute("BEGIN IMMEDIATE")
        delete_ids(connection, table, column, ids)
        connection.commit()
        connection.execute("PRAGMA optimize")


def atomic_write(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def apply_plan(plan: CleanupPlan) -> None:
    cleanup_state_db(plan.state_db, plan, plan.remove_primary_ids)
    cleanup_state_db(plan.legacy_state_db, plan, plan.remove_legacy_ids)
    for path, ids in plan.db_orphan_ids.items():
        cleanup_related_db(path, ids)

    for path, (content, removed) in plan.json_rewrites.items():
        if removed:
            atomic_write(path, content)

    for candidate in sorted(
        plan.file_candidates, key=lambda item: len(item.path.parts), reverse=True
    ):
        if not candidate.path.exists() and not candidate.path.is_symlink():
            continue
        if candidate.path.is_dir() and not candidate.path.is_symlink():
            shutil.rmtree(candidate.path)
        else:
            candidate.path.unlink()

    for dirname in ("sessions", "archived_sessions", "visualizations"):
        base = plan.root / dirname
        if not base.is_dir():
            continue
        directories = sorted(
            (path for path in base.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for path in directories:
            try:
                path.rmdir()
            except OSError:
                pass

    checked = {plan.state_db, plan.legacy_state_db, *plan.db_orphan_ids}
    for path in checked:
        if not path.is_file():
            continue
        with connect(path, readonly=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity check failed for {path}: {result}")

    remaining = CleanupPlan(plan.root, plan.cutoff)
    summary = remaining.summary()
    if (
        summary["removed_primary_threads"]
        or summary["removed_legacy_threads"]
        or summary["dependent_thread_ids"]
        or summary["dangling_spawn_edges"]
        or summary["state_dependent_rows"]
        or summary["metadata_rows"]
        or summary["file_count"]
    ):
        raise RuntimeError(f"Post-cleanup consistency audit still found work: {summary}")


def print_summary(summary: dict[str, Any], *, applied: bool) -> None:
    verb = "Removed" if applied else "Would remove"
    print(f"Session consistency for: {summary['codex_home']}")
    print(f"  State database: {summary['state_db']}")
    print(f"  Preserved registered threads: {summary['kept_threads']}")
    print(
        f"  {verb} thread rows: "
        f"{summary['removed_primary_threads']} primary, "
        f"{summary['removed_legacy_threads']} legacy"
    )
    print(
        f"  {verb} dependent SQLite thread IDs: "
        f"{summary['dependent_thread_ids']}"
    )
    print(f"  {verb} dangling spawn edges: {summary['dangling_spawn_edges']}")
    print(f"  {verb} stale state-dependent rows: {summary['state_dependent_rows']}")
    print(f"  {verb} stale metadata entries: {summary['metadata_rows']}")
    for kind, details in sorted(summary["files"].items()):
        print(
            f"  {verb} {kind}: {details['count']} "
            f"({format_bytes(details['bytes'])})"
        )
    print(f"  Candidate file space: {format_bytes(summary['file_bytes'])}")


def main() -> int:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    parser.add_argument("--grace-minutes", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("codex_home", type=Path)
    args = parser.parse_args()

    root = args.codex_home.expanduser().resolve()
    cutoff = time.time() - args.grace_minutes * 60
    plan = CleanupPlan(root, cutoff)
    summary = plan.summary()
    if args.apply:
        with cleanup_lock(root):
            plan = CleanupPlan(root, cutoff)
            summary = plan.summary()
            apply_plan(plan)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_summary(summary, applied=args.apply)
        if args.apply:
            print("  SQLite integrity and post-cleanup reference audit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
