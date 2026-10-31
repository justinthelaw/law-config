#!/usr/bin/env python3
"""Compile and run a caller in a fresh private directory under supplied scratch."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Example: --scratch tmp/task -- cc caller.c -o "{exe}". '
               'Use the project toolchain and flags. Exit 0: pass, 1: behavioral failure, 2: compile or setup failure.',
    )
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("build", nargs=argparse.REMAINDER, help="compiler argv after --, with {exe} output path")
    args = parser.parse_args()
    build = args.build[1:] if args.build[:1] == ["--"] else args.build
    if not build or not any("{exe}" in arg for arg in build):
        parser.error("compiler argv must contain {exe}")
    try:
        with tempfile.TemporaryDirectory(prefix="develop-probe-", dir=args.scratch.resolve()) as temp:
            exe = str(Path(temp) / ("probe.exe" if os.name == "nt" else "probe"))
            env = dict(os.environ, TMPDIR=temp, TMP=temp, TEMP=temp)
            result = subprocess.run([arg.replace("{exe}", exe) for arg in build], env=env)
            if result.returncode:
                print(f"compile failed: status {result.returncode}", file=sys.stderr)
                return 2
            if not Path(exe).is_file():
                print("compile failed: executable not produced", file=sys.stderr)
                return 2
            result = subprocess.run([exe], env=env)
            if result.returncode:
                print(f"behavior failed: status {result.returncode}", file=sys.stderr)
                return 1
            print("behavior passed")
            return 0
    except OSError as error:
        print(f"probe failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
