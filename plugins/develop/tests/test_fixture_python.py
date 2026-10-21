"""Safe-path fixture execution retains Python's command/module/file behavior."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fixture_python import run_fixture_python


@unittest.skipUnless(hasattr(sys.flags, "safe_path"), "safe-path requires Python 3.11+")
class FixturePythonTests(unittest.TestCase):
    def test_exact_trusted_root_from_unrelated_cwd_preserves_execution_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trusted, unrelated = root / "trusted", root / "unrelated"
            trusted.mkdir()
            unrelated.mkdir()
            (trusted / "fixture_value.py").write_text("VALUE = 'trusted'\n")
            (unrelated / "fixture_value.py").write_text("raise AssertionError('CWD imported')\n")
            (unrelated / "cwd_only.py").write_text("raise AssertionError('CWD imported')\n")
            code = ("import importlib.util, json, os, sys\n"
                    "from fixture_value import VALUE\n"
                    "print(json.dumps({'value': VALUE, 'safe_path': sys.flags.safe_path,\n"
                    " 'environment': os.environ['PYTHONSAFEPATH'], 'argv': sys.argv,\n"
                    " 'name': __name__, 'spec': __spec__.name if __spec__ else None,\n"
                    " 'cwd_importable': importlib.util.find_spec('cwd_only') is not None}))\n")
            runner = trusted / "fixture_runner.py"
            runner.write_text(code)
            cases = [(('-c', code, 'payload'), '-c', None),
                     (('-m', 'fixture_runner', 'payload'), str(runner.resolve()), 'fixture_runner'),
                     ((str(runner), 'payload'), str(runner), None)]
            with patch.dict(os.environ, {"PYTHONSAFEPATH": "1", "PYTHONPATH": str(unrelated)}):
                for arguments, argv0, spec in cases:
                    with self.subTest(mode=arguments[0]):
                        result = run_fixture_python(trusted, *arguments, cwd=unrelated)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(json.loads(result.stdout), {
                            "value": "trusted", "safe_path": True, "environment": "1",
                            "argv": [argv0, "payload"], "name": "__main__", "spec": spec,
                            "cwd_importable": False})
                self.assertEqual(os.environ["PYTHONPATH"], str(unrelated))
                self.assertEqual(os.environ["PYTHONSAFEPATH"], "1")


if __name__ == "__main__":
    unittest.main()
