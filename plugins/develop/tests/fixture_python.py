"""Execute trusted, materialized Python fixtures without implicit CWD imports."""
import os
from pathlib import Path
import subprocess
import sys


def run_fixture_python(root, *arguments, cwd=None, timeout=20):
    """Trust only this fixture root; retain normal -m, -c and file semantics.

    The child gets an exact import root rather than disabling PYTHONSAFEPATH or
    inheriting unrelated PYTHONPATH entries. This is test setup, not a sandbox.
    """
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("fixture root must be a directory")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root)
    return subprocess.run([sys.executable, "-B", *arguments],
                          cwd=root if cwd is None else cwd, env=environment,
                          capture_output=True, text=True, check=False,
                          timeout=timeout)
