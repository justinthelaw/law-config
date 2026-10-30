"""Reapply every proposal to a clean tree and retain each independent stage."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import environment as E

# These are the original six preregistered executable checks.
LEGACY_COMMAND = {
    ".py": "python3 /oracle/check.py",
    ".mjs": "node /oracle/check.mjs",
    ".go": "go build -o /tmp/probe /oracle/check.go && /tmp/probe",
    ".rs": "mkdir -p crates/ignore/examples && cp /oracle/check.rs crates/ignore/examples/panel_case.rs && cargo run --locked --offline -q -p ignore --example panel_case",
}


def command(case):
    if E.COHORT:
        return E.COHORT.command(case)
    path = next((E.HERE / "checks").glob(case["id"] + ".*"))
    ext = path.suffix
    cmd = {".py": "PYTHONPATH=.:src:/deps/lib python3 /oracle/probe.py",
           ".mjs": "node /oracle/probe.mjs",
           ".sh": "sh /oracle/probe.sh",
           ".go": "go build -o /tmp/probe /oracle/probe.go && /tmp/probe",
           ".cpp": "g++ -std=c++17 -Iinclude /oracle/probe.cpp -o /tmp/check && /tmp/check",
           ".rb": "RUBYLIB=rspec-core/lib:rspec-support/lib:rspec-expectations/lib:rspec-mocks/lib ruby /oracle/probe.rb",
           ".java": "java -cp target/panel-classes /oracle/probe.java"}[ext]
    return path, "/oracle/probe" + ext, cmd


def stage(case, work, output, name, cmd, mount=None, *, extra_mounts=(), toolchain=None, operation=None):
    args, image = E.lab.docker(case, work)
    args.extend(["-e", "PANEL_STAGE=" + (operation or name)])
    for src, dst in ([mount] if mount else []) + list(extra_mounts):
        args += ["--mount", f"type=bind,src={src},dst={dst},readonly"]
    t0 = time.monotonic()
    with (output / (name + ".log")).open("xb") as log:
        try:
            rc = subprocess.run([*args, toolchain or image, "sh", "-ec", cmd], stdout=log,
                                stderr=subprocess.STDOUT, timeout=1800).returncode
        except subprocess.TimeoutExpired:
            rc = 124
    return {"exit": rc, "seconds": time.monotonic() - t0, "command": cmd,
            "log_sha256": E.sha(output / (name + ".log"))}


def snapshot(case, revision, parent):
    work = E.lab.snapshot(case, revision, parent)
    with (work / ".git/info/exclude").open("a") as f:
        f.write("\n/build-panel/\n/build/\n/target/\n.pytest_cache/\n__pycache__/\n.hypothesis/\n")
        if case["id"] == "pytest":
            import shutil
            shutil.copyfile(E.dependencies(case) / "public/_version.py", work / "src/_pytest/_version.py")
            f.write("/src/_pytest/_version.py\n")
    return work


def grade(case, revision, output, patch=None, phases=None, target=None):
    output.mkdir(parents=True, exist_ok=False)
    work = snapshot(case, revision, output)
    stages = {}
    record = {"case": case["id"], "base": revision, "patch_sha256": E.sha(patch) if patch else None,
              "directory": str(output.relative_to(E.STATE)), "stages": stages}
    if patch:
        options = ["--index"] if target else []
        r = subprocess.run(["git", "-C", work, "apply", *options, "--binary", "--", patch], capture_output=True)
        (output / "apply.log").write_bytes(r.stderr)
        record["applied"] = r.returncode == 0
        record["apply_log_sha256"] = E.sha(output / "apply.log")
        if r.returncode:
            E.save(output / "grade.json", record)
            return record
        if target:
            record["replayed_tree"] = E.lab.git(work / ".git", "write-tree")
            record["target_tree"] = E.lab.git(E.lab.objects(case), "rev-parse", target + "^{tree}")
            if record["replayed_tree"] != record["target_tree"]:
                raise ValueError("replayed upstream patch differs from the merged tree: " + case["id"])
    if phases is None:
        phases = ["build", "native", "contract", "preserve"]
        if case.get("independent"):
            phases.append("independent")
    for name in phases:
        if name != "build" and stages.get("build", {}).get("exit") not in (None, 0):
            stages[name] = {"exit": None, "reason": "build failed"}
            continue
        if name in ("build", "native"):
            stages[name] = stage(case, work, output, name, case[name])
        elif E.COHORT:
            if name == "contract":
                stages.update(E.COHORT.checks(E, stage, case, work, output))
        elif name == "contract" and case.get("legacy"):
            path = E.WORKFLOW / "checks" / case["check"]
            stages[name] = stage(case, work, output, name, LEGACY_COMMAND[path.suffix],
                                 (path, "/oracle/check" + path.suffix))
        else:
            path, dest, cmd = command(case)
            stages[name] = stage(case, work, output, name, cmd, (path, dest))
    E.save(output / "grade.json", record)
    return record


def calibrate(case, phases=None):
    E.prepare(case)
    location = E.CACHE / "calibration" / case["id"] / str(time.time_ns())
    location.mkdir(parents=True)
    merged = location / "upstream.patch"
    merged.write_bytes(E.original_diff(case))
    results = {}
    for name in ("base", "gold"):
        result = grade(case, case["base"], location / name, phases=phases,
                       patch=merged if name=="gold" else None,
                       target=case["gold"] if name=="gold" else None)
        results[name] = {key: row["exit"] for key, row in result["stages"].items()}
        print(case["id"], name, results[name], flush=True)
    good = (phases is None and all(results["base"][s] == results["gold"][s] == 0
                                  for s in ("build", "native", "preserve"))
            and results["base"]["contract"] == 42 and results["gold"]["contract"] == 0
            and all(r.get("independent") in (None, 0, 42) for r in results.values()))
    E.save(location / "admission.json", {"passed": good, "case": case["id"], "results": results,
           "fingerprint": fixture_hash(case, phases),"workers":E.worker_ids(case),
           "deps_sha256":E.dependency_digest(case)})
    return good


def fixture_hash(case, phases=None):
    import hashlib, json
    paths = [E.HERE / "grading.py", E.HERE / "environment.py",
             E.WORKFLOW/"lab.py",E.WORKFLOW/"guest.py", *E.public_files(case)]
    if phases is None:
        paths += [command(case)[0]]
        if case.get("legacy") and not E.COHORT:
            paths += [E.WORKFLOW / "checks" / case["check"]]
    h = hashlib.sha256(json.dumps(case, sort_keys=True).encode())
    for p in paths:
        h.update(bytes.fromhex(E.sha(p)))
    return h.hexdigest()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("case", choices=E.CASES)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    E.configure()
    passed = calibrate(E.CASES[args.case], ["build", "native"] if args.smoke else None)
    raise SystemExit(0 if passed or args.smoke else 2)
