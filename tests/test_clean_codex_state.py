import importlib.util
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "clean-codex-state.py"
SPEC = importlib.util.spec_from_file_location("clean_codex_state", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
clean_codex_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = clean_codex_state
SPEC.loader.exec_module(clean_codex_state)


LIVE_PARENT = "11111111-1111-4111-8111-111111111111"
LIVE_CHILD = "22222222-2222-4222-8222-222222222222"
STALE_PARENT = "33333333-3333-4333-8333-333333333333"
STALE_CHILD = "44444444-4444-4444-8444-444444444444"


class CleanCodexStateTests(unittest.TestCase):
    def create_state_db(
        self,
        root: Path,
        *,
        stale_id: str,
        edges: list[tuple[str, str]],
    ) -> Path:
        sessions = root / "sessions"
        sessions.mkdir()
        live_parent_path = sessions / f"{LIVE_PARENT}.jsonl"
        live_child_path = sessions / f"{LIVE_CHILD}.jsonl"
        live_parent_path.write_text("{}\n", encoding="utf-8")
        live_child_path.write_text("{}\n", encoding="utf-8")

        stale_path = root / "sessions" / f"{stale_id}.jsonl"
        db_path = root / "state_1.sqlite"
        with sqlite3.connect(db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    rollout_path TEXT NOT NULL,
                    archived INTEGER NOT NULL,
                    updated_at REAL
                );
                CREATE TABLE thread_spawn_edges (
                    parent_thread_id TEXT NOT NULL,
                    child_thread_id TEXT NOT NULL
                );
                CREATE TABLE thread_dynamic_tools (thread_id TEXT NOT NULL);
                CREATE TABLE agent_job_items (assigned_thread_id TEXT);
                """
            )
            connection.executemany(
                "INSERT INTO threads VALUES (?, ?, ?, ?)",
                [
                    (LIVE_PARENT, str(live_parent_path), 0, 0.0),
                    (LIVE_CHILD, str(live_child_path), 0, 0.0),
                    (stale_id, str(stale_path), 1, 0.0),
                ],
            )
            connection.executemany(
                "INSERT INTO thread_spawn_edges VALUES (?, ?)",
                edges,
            )
            connection.executemany(
                "INSERT INTO thread_dynamic_tools VALUES (?)",
                [(LIVE_PARENT,), (stale_id,)],
            )
            connection.executemany(
                "INSERT INTO agent_job_items VALUES (?)",
                [(LIVE_PARENT,), (stale_id,)],
            )
        return db_path

    def apply_plan(self, root: Path) -> None:
        cutoff = time.time() - 60
        plan = clean_codex_state.CleanupPlan(root, cutoff)
        clean_codex_state.apply_plan(plan)

    def read_edges(self, db_path: Path) -> set[tuple[str, str]]:
        with sqlite3.connect(db_path) as connection:
            return {
                (str(parent), str(child))
                for parent, child in connection.execute(
                    "SELECT parent_thread_id, child_thread_id "
                    "FROM thread_spawn_edges"
                )
            }

    def test_stale_parent_edge_does_not_delete_live_child_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = self.create_state_db(
                root,
                stale_id=STALE_PARENT,
                edges=[
                    (STALE_PARENT, LIVE_CHILD),
                    (LIVE_PARENT, LIVE_CHILD),
                ],
            )

            self.apply_plan(root)

            self.assertEqual(self.read_edges(db_path), {(LIVE_PARENT, LIVE_CHILD)})

    def test_stale_child_edge_is_removed_without_dropping_live_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = self.create_state_db(
                root,
                stale_id=STALE_CHILD,
                edges=[
                    (LIVE_PARENT, STALE_CHILD),
                    (LIVE_PARENT, LIVE_CHILD),
                ],
            )

            self.apply_plan(root)

            self.assertEqual(self.read_edges(db_path), {(LIVE_PARENT, LIVE_CHILD)})

            with sqlite3.connect(db_path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT thread_id FROM thread_dynamic_tools"
                    ).fetchall(),
                    [(LIVE_PARENT,)],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT assigned_thread_id FROM agent_job_items "
                        "ORDER BY assigned_thread_id IS NULL, assigned_thread_id"
                    ).fetchall(),
                    [(LIVE_PARENT,), (None,)],
                )


if __name__ == "__main__":
    unittest.main()
