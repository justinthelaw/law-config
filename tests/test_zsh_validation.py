"""Exercise the workflow's Zsh check against every configuration file."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest



@unittest.skipUnless(shutil.which("zsh"), "Zsh is required for syntax validation")
class ZshValidationTests(unittest.TestCase):
    def test_rejects_invalid_overlay(self):
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/lint.yml"
        step = workflow.read_text().split("- name: Check Zsh Configuration Syntax\n", 1)[1]
        run = step.split("\n      - name:", 1)[0].split("run: ", 1)[1]
        command = textwrap.dedent(run[2:]) if run.startswith("|\n") else run.strip()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs/zsh").mkdir(parents=True)
            (root / "configs/.zshrc").write_text(":\n")
            overlay = root / "configs/zsh/common.zsh"
            overlay.write_text("if\n")
            result = subprocess.run(["bash", "-e", "-c", command], cwd=root,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            overlay.write_text(":\n")
            result = subprocess.run(["bash", "-e", "-c", command], cwd=root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
