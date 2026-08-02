import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sanitize-shell-hist"


class SanitizeShellHistoryTests(unittest.TestCase):
    def run_sanitizer(
        self, history: Path, *, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), str(history)],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_sanitizes_once_and_preserves_unsanitized_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history"
            original = (
                ": 1651737463:0; echo keep\n"
                "echo duplicate\n"
                "TOKEN=abc\n"
                "echo duplicate\n"
            )
            history.write_text(original, encoding="utf-8")

            result = self.run_sanitizer(history)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                history.read_text(encoding="utf-8"),
                "echo keep\necho duplicate\n",
            )
            backups = list(history.parent.glob("history.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
            self.assertEqual(list(history.parent.glob(".sanitize_hist.*")), [])

    def test_filter_failure_leaves_original_history_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            history = directory / "history"
            original = ": 1651737463:0; echo keep\nTOKEN=abc\n"
            history.write_text(original, encoding="utf-8")

            bin_dir = directory / "bin"
            bin_dir.mkdir()
            failing_grep = bin_dir / "grep"
            failing_grep.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
            failing_grep.chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

            result = self.run_sanitizer(history, env=env)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(history.read_text(encoding="utf-8"), original)
            backups = list(history.parent.glob("history.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
            self.assertEqual(list(history.parent.glob(".sanitize_hist.*")), [])


if __name__ == "__main__":
    unittest.main()
