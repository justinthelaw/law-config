import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sanitize-shell-hist"


class SanitizeShellHistoryTests(unittest.TestCase):
    def run_sanitizer(self, history_file: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), str(history_file)],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_sanitizes_history_and_keeps_last_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history"
            history.write_text(
                "\n".join(
                    [
                        ": 1651737463:0; echo keep",
                        "echo duplicate",
                        "PASSWORD=hunter2",
                        "zsh: command not found: nope",
                        "echo bad;;",
                        "echo duplicate",
                        "   ",
                        " echo spaced ",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_sanitizer(history)

            self.assertIn(f"Backup: {history}.bak.", result.stdout)
            self.assertEqual(
                history.read_text(encoding="utf-8").splitlines(),
                ["echo keep", "echo duplicate", "echo spaced"],
            )

    def test_all_filtered_input_exits_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "history"
            history.write_text(
                "TOKEN=abc\npassword=hunter2\necho bad;;\n",
                encoding="utf-8",
            )

            self.run_sanitizer(history)

            self.assertEqual(history.read_text(encoding="utf-8"), "")

    def test_backup_names_do_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            history = directory / "history"
            history.write_text("echo first\n", encoding="utf-8")
            self.run_sanitizer(history)

            history.write_text("echo second\n", encoding="utf-8")
            self.run_sanitizer(history)

            self.assertGreaterEqual(len(list(directory.glob("history.bak.*"))), 2)


if __name__ == "__main__":
    unittest.main()
