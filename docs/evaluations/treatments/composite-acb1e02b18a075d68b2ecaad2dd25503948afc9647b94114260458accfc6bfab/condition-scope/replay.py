"""Replay the frozen Werkzeug checks against a sealed pilot result."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

BASE_REVISION = "15fc22b699ecacd04824092453c0cd2a8c4a3a67"
TEST_FILES = ("test_internal.py", "test_test.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="sealed pilot result.json")
    parser.add_argument("name", help="name for the isolated replay")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", args.name):
        parser.error("name must contain 1–40 letters, numbers, underscores or hyphens")

    repo = Path.cwd().resolve()
    top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    if Path(top).resolve() != repo:
        raise ValueError("run from the repository root")
    result = args.result.resolve(strict=True)
    fixtures = Path(__file__).resolve().parent / "fixtures"
    manifest = json.loads((fixtures / "manifest.json").read_text())
    for relative, expected in manifest["files"].items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or digest(fixtures / path) != expected:
            raise ValueError(f"fixture differs: {relative}")

    task_root = repo / "tmp/pr-quality-panel/condition-scope-treatment/release/portable-work"
    if any(parent.is_symlink() for parent in (task_root, *task_root.parents) if parent != repo.parent):
        raise ValueError("temporary path contains a symlink")
    task_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "check-ignore", "-q", str(task_root)], check=True)
    if subprocess.check_output(["git", "ls-files", "--", str(task_root)]):
        raise ValueError("temporary path contains tracked files")
    work = Path(tempfile.mkdtemp(prefix=f"{args.name}-", dir=task_root))
    output = work / "tmp/pr-quality-panel/condition-scope-measure"
    output.mkdir(parents=True)
    scratch = output / "scratch"
    scratch.mkdir()
    for relative in manifest["files"]:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixtures / relative, destination)

    (work / "docs").mkdir()
    (work / "docs/evaluations").symlink_to(repo / "docs/evaluations", target_is_directory=True)
    environment = os.environ.copy()
    environment.update(TMPDIR=str(scratch), TMP=str(scratch), TEMP=str(scratch),
                       OAIPKG_DISABLE_META_MISSING="1", PYTHONDONTWRITEBYTECODE="1")
    if not {0, 1}.issubset(os.sched_getaffinity(0)):
        raise ValueError("the existing assessor requires CPUs 0 and 1")

    sys.path[:0] = [str(repo / "docs/evaluations"), str(repo / "docs/evaluations/tools")]
    import native_panel

    native_panel.E.configure()
    case = native_panel.E.CASES["werkzeug"]
    if case["base"] != BASE_REVISION:
        raise ValueError("the configured Werkzeug base differs")
    objects = native_panel.E.lab.objects(case)
    for filename in TEST_FILES:
        original = subprocess.check_output([
            "git", "--git-dir", str(objects), "show", f"{BASE_REVISION}:tests/{filename}"
        ])
        expected = manifest["original_tests"][f"tests/{filename}"]
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError(f"original test differs: {filename}")
        (output / "consumer-fixture" / filename).write_bytes(original)
    registration = json.loads((output / "registration.json").read_text())
    positive_patch = output / "positive.patch"
    if digest(positive_patch) != registration["positive_patch_sha256"]:
        raise ValueError("positive patch differs")
    grade = native_panel.C.grading.grade(case, BASE_REVISION, output / "positive", positive_patch, phases=[])
    if not grade.get("applied"):
        raise ValueError("positive patch did not apply")

    replay = output / f"{args.name}-replay.json"
    assessed = output / f"{args.name}-assessed.json"
    commands = (
        [output / "measure.py", "replay", "--target", result, "--output", replay.name],
        [output / "assess_v2.py", result, replay, f"{args.name}-assessed"],
        [output / "modules.py", result, assessed, f"{args.name}-modules"],
    )
    for command in commands:
        subprocess.run([sys.executable, "-B", *map(str, command)], cwd=work, env=environment, check=True)
    print(f"Replay workspace: {work}")
    print(f"Replay output: {output}")


if __name__ == "__main__":
    main()
