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

    def test_rejects_symlink_history_without_modifying_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            target = directory / "real-history"
            history = directory / "history"
            original = "echo keep\nTOKEN=abc\n"
            target.write_text(original, encoding="utf-8")
            history.symlink_to(target)

            result = self.run_sanitizer(history)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("regular, non-symlink file", result.stderr)
            self.assertTrue(history.is_symlink())
            self.assertEqual(history.read_text(encoding="utf-8"), original)
            self.assertEqual(list(directory.glob("history.bak.*")), [])
            self.assertEqual(list(directory.glob(".sanitize_hist.*")), [])

    def test_rejects_non_regular_history_without_creating_work_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            history = directory / "history"
            history.mkdir()

            result = self.run_sanitizer(history)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("regular, non-symlink file", result.stderr)
            self.assertEqual(list(directory.glob("history.bak.*")), [])
            self.assertEqual(list(directory.glob(".sanitize_hist.*")), [])

    def test_aborts_if_history_path_is_replaced_during_sanitization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            history = directory / "history"
            target = directory / "real-history"
            marker = directory / "swap-complete"
            original = "echo keep\nTOKEN=abc\n"
            history.write_text(original, encoding="utf-8")
            target.write_text("echo protected\nTOKEN=target\n", encoding="utf-8")

            bin_dir = directory / "bin"
            bin_dir.mkdir()
            swapping_grep = bin_dir / "grep"
            swapping_grep.write_text(
                "#!/bin/sh\n"
                "if [ ! -e \"$TEST_SWAP_MARKER\" ]; then\n"
                "  touch \"$TEST_SWAP_MARKER\"\n"
                "  mv \"$TEST_HISTORY\" \"$TEST_HISTORY.replaced\"\n"
                "  ln -s \"$TEST_TARGET\" \"$TEST_HISTORY\"\n"
                "fi\n"
                "exec /usr/bin/grep \"$@\"\n",
                encoding="utf-8",
            )
            swapping_grep.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "TEST_HISTORY": str(history),
                "TEST_TARGET": str(target),
                "TEST_SWAP_MARKER": str(marker),
            }

            result = self.run_sanitizer(history, env=env)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("changed during sanitization", result.stderr)
            self.assertTrue(history.is_symlink())
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "echo protected\nTOKEN=target\n",
            )
            self.assertEqual(
                (directory / "history.replaced").read_text(encoding="utf-8"),
                original,
            )
            self.assertEqual(list(directory.glob(".sanitize_hist.*")), [])


if __name__ == "__main__":
    unittest.main()
