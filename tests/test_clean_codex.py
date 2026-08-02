import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "clean-codex"
THREAD_ID = "33333333-3333-4333-8333-333333333333"


class CleanCodexTests(unittest.TestCase):
    def test_recent_archived_thread_keeps_older_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            archived = codex_home / "archived_sessions"
            archived.mkdir()
            rollout = archived / f"{THREAD_ID}.jsonl"
            rollout.write_text("{}\n", encoding="utf-8")
            old_time = time.time() - 7200
            os.utime(rollout, (old_time, old_time))

            database = codex_home / "state_1.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE threads ("
                    "id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL, "
                    "updated_at INTEGER, archived INTEGER)"
                )
                connection.execute(
                    "INSERT INTO threads VALUES (?, ?, ?, ?)",
                    (THREAD_ID, str(rollout), int(time.time()), 1),
                )

            result = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "--prune-orphans",
                    "--dry-run",
                    "--force",
                    str(codex_home),
                ],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "CLEAN_CODEX_GRACE_MINUTES": "15"},
            )

            self.assertIn("Preserved registered threads: 1", result.stdout)
            self.assertIn("Would remove thread rows: 0 primary, 0 legacy", result.stdout)
            self.assertNotIn("Would remove rollout:", result.stdout)


if __name__ == "__main__":
    unittest.main()
