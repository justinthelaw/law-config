from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/develop/scripts/probe.py"


class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()

    def probe(self, build):
        return subprocess.run([sys.executable, str(SCRIPT), "--scratch", str(self.scratch), "--", *build],
                              cwd=self.root, text=True, capture_output=True)

    def test_help_shows_example(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--scratch tmp/task -- cc caller.c -o "{exe}"', result.stdout)

    def test_compile_failure_never_runs_stale_executable(self):
        stale = self.scratch / "probe"
        stale.write_text("stale")
        result = self.probe([sys.executable, "-c", "import sys; print('compiler error'); sys.exit(7)", "{exe}"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("compiler error", result.stdout)
        self.assertIn("status 7", result.stderr)
        self.assertEqual(stale.read_text(), "stale")
        self.assertEqual(list(self.scratch.iterdir()), [stale])

    def test_compile_success_without_executable_is_failure(self):
        result = self.probe([sys.executable, "-c", "pass", "{exe}"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("executable not produced", result.stderr)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_missing_scratch_reports_setup_failure(self):
        self.scratch = self.root / "missing"
        result = self.probe([sys.executable, "-c", "pass", "{exe}"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("probe failed", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    @unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
    def test_real_compiler_and_caller_behavior(self):
        source = self.root / "caller.c"
        source.write_text('#include <stdio.h>\nint main(void) { puts("caller output"); return RESULT; }\n')
        for code, expected in [(0, 0), (3, 1)]:
            result = self.probe(["cc", f"-DRESULT={code}", "caller.c", "-o", "{exe}"])
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertIn("caller output", result.stdout)
            self.assertIn("behavior passed" if not code else "status 3", result.stdout + result.stderr)
            self.assertEqual(list(self.scratch.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
