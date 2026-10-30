#!/usr/bin/env python3
"""Acquire immutable sources, prepare offline dependencies and calibrate a historical task."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STATE = ROOT / "tmp/six-repo-workflow"
SPEC = json.loads((HERE / "cases.json").read_bytes())
CASES = {case["id"]: case for case in SPEC["cases"]}
COMMON_PROMPT = ("Implement the task in this checkout, including relevant tests. "
                 "You may proceed without interactive plan review. Work locally and offline. "
                 "Stop after verification and report any gaps.\n\n")
PREPARE = {
    "python": ("python -m pip install --disable-pip-version-check --no-deps -t /deps/lib "
               "pytest==8.4.2 iniconfig==2.3.0 packaging==25.0 pluggy==1.6.0 "
               "pygments==2.19.2 pretend==1.0.9"),
    "node": "npm ci --ignore-scripts --no-audit --no-fund && cp -a node_modules /deps/",
    "rust": "cargo fetch --locked",
    "golang": "go mod download",
}
RUNNER_YAML = (" && npm install --prefix /deps/check-tools --ignore-scripts --no-audit "
               "--no-fund --save-exact yaml@2.8.1")


def call(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def git(objects, *args):
    return call("git", "--git-dir", objects, *args, stdout=subprocess.PIPE).stdout.decode().strip()


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def start_state():
    if not (ROOT / ".git").exists():
        raise ValueError("Run inside a law-config checkout")
    call("git", "-C", ROOT, "check-ignore", "-q", STATE / "probe")
    if call("git", "-C", ROOT, "ls-files", "--", STATE, stdout=subprocess.PIPE).stdout:
        raise ValueError("benchmark scratch must be untracked")
    (STATE / "volatile").mkdir(parents=True, exist_ok=True)
    for name in ("TMP", "TEMP", "TMPDIR"):
        os.environ[name] = str(STATE / "volatile")
    tempfile.tempdir = str(STATE / "volatile")


def objects(case):
    return STATE / "objects" / case["id"]


def fetch(store, repo, sha):
    if not store.exists():
        call("git", "init", "-q", "--bare", store)
    if subprocess.run(["git", "--git-dir", store, "cat-file", "-e", sha + "^{commit}"],
                      stderr=subprocess.DEVNULL).returncode:
        call("git", "--git-dir", store, "fetch", "--no-tags", "--depth=2",
             "https://github.com/" + repo + ".git", sha)


def archive(store, revision, destination):
    # git archive applies export-ignore/export-subst. A private index materializes the
    # checkout, including tracked dotfiles, without populating its repository history.
    destination.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tempfile.mkdtemp()) / "index"),
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1")
    cmd = ["git", "--git-dir", store, "--work-tree", destination]
    call(*cmd, "read-tree", revision, env=env)
    call(*cmd, "-c", "core.autocrlf=false", "checkout-index", "--all", "--force",
         "--prefix", str(destination) + "/", env=env)


def tree_entries(store, revision):
    data = call("git", "--git-dir", store, "ls-tree", "-rz", revision,
                stdout=subprocess.PIPE).stdout
    return {path: meta for row in data.split(b"\0") if row
            for meta, path in [row.split(b"\t", 1)]}


def dependency_dir(case):
    recipe = PREPARE.get(case["image"], "") + (RUNNER_YAML if case["id"] == "runner-space" else "")
    key = hashlib.sha256((case["base"] + SPEC["images"][case["image"]] + recipe).encode()).hexdigest()
    return STATE / "dependencies" / case["id"] / key[:16]


def docker(case, workspace, *, online=False):
    """Only preparation has network; workers never mount a control or reference directory."""
    image = SPEC["images"][case["image"]]
    uid = f"{os.getuid()}:{os.getgid()}"
    args = ["docker", "run", "--rm", "--init", "--platform", "linux/amd64", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512",
            "--cpus", str(SPEC["cpus"]), "--memory", SPEC["memory"], "--user", uid,
            "--network", "bridge" if online else "none", "--tmpfs", "/tmp:rw,exec,size=2g",
            "-e", "HOME=/tmp", "-e", "TMPDIR=/tmp", "-e", "CARGO_TARGET_DIR=/work/target",
            "-e", "GOCACHE=/tmp/go-cache", "-e", "GOTOOLCHAIN=local", "-e", "GOPATH=/tmp/go",
            "-e", "GOMODCACHE=/deps/gomod", "-e", "PYTHONPATH=/work/src:/deps/lib",
            "-e", "CARGO_HOME=/deps/cargo", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "GOPROXY=https://proxy.golang.org" if online else "GOPROXY=off",
            "-e", "CARGO_NET_OFFLINE=" + ("false" if online else "true"),
            "--mount", f"type=bind,src={workspace},dst=/work", "-w", "/work",
            "--mount", f"type=bind,src={dependency_dir(case)},dst=/deps" + ("" if online else ",readonly")]
    return args, image


def prepare(case):
    store = objects(case)
    fetch(store, case["repo"], case["gold"])
    if git(store, "rev-parse", case["gold"] + "^1") != case["base"]:
        raise ValueError("base is not the merged change's first parent")
    stats = git(store, "diff", "--numstat", case["base"], case["gold"]).splitlines()
    counts = [row.split("\t")[:2] for row in stats]
    if [len(counts), *(sum(int(row[i]) for row in counts) for i in range(2))] != case["delta"]:
        raise ValueError("upstream change size disagrees with cohort")
    sub = case.get("submodule")
    if sub:
        if git(store, "rev-parse", case["base"] + ":" + sub["path"]) != sub["sha"]:
            raise ValueError("submodule pin mismatch")
        fetch(STATE / "objects" / "oniguruma", sub["repo"], sub["sha"])
    deps = dependency_dir(case)
    deps.mkdir(parents=True, exist_ok=True)
    image = SPEC["images"][case["image"]]
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode:
        call("docker", "pull", "--platform", "linux/amd64", image, stdout=subprocess.DEVNULL)
    if (deps / "ready").exists():
        return
    seed = Path(tempfile.mkdtemp(prefix=case["id"] + "-prepare-"))
    build_family = case["image"]
    if build_family in PREPARE:
        # A networked package manager sees the frozen dependency inputs only, never a candidate.
        if build_family == "rust":
            archive(store, case["base"], seed)
        if build_family in ("node", "golang"):
            for name in (("go.mod", "go.sum") if build_family == "golang" else
                         ("package.json", "package-lock.json")):
                (seed / name).write_bytes(call("git", "--git-dir", store, "show",
                                               case["base"] + ":" + name, stdout=subprocess.PIPE).stdout)
        args, image = docker(case, seed, online=True)
        if ca := os.environ.get("BENCHMARK_CA_FILE"):
            args += ["--mount", f"type=bind,src={Path(ca).resolve(strict=True)},dst=/prep-ca.pem,readonly",
                     "-e", "NODE_EXTRA_CA_CERTS=/prep-ca.pem", "-e", "SSL_CERT_FILE=/prep-ca.pem"]
        with (seed / "prepare.log").open("w") as log:
            recipe = PREPARE[build_family] + (RUNNER_YAML if case["id"] == "runner-space" else "")
            call(*args, image, "sh", "-ec", recipe, stdout=log,
                 stderr=subprocess.STDOUT, timeout=900)
    (deps / "ready").write_text(image + "\n")


def snapshot(case, sha, parent):
    work = parent / "work"
    archive(objects(case), sha, work)
    call("git", "init", "-q", work)
    if sub := case.get("submodule"):
        source = STATE / "objects/oniguruma"
        nested = work / sub["path"]
        call("git", "init", "-q", nested)
        call("git", "-C", nested, "fetch", "-q", "--depth=1", "--no-tags", "--no-write-fetch-head",
             source.as_uri(), sub["sha"])
        call("git", "-C", nested, "checkout", "-q", "--detach", sub["sha"])
        if tree_entries(nested / ".git", "HEAD") != tree_entries(source, sub["sha"]):
            raise ValueError("submodule tree mismatch")
        call("git", "-C", work, "update-index", "--add", "--cacheinfo",
             "160000", sub["sha"], sub["path"])
    # Preserve upstream blob bytes even in repositories with historical unnormalized CRLF.
    (work / ".git/info/attributes").write_text("* -text -ident -filter -working-tree-encoding\n")
    call("git", "-C", work, "add", "-f", ".")
    call("git", "-C", work, "-c", "user.name=Benchmark", "-c", "user.email=benchmark@invalid",
         "-c", "commit.gpgSign=false", "-c", "core.hooksPath=/dev/null",
         "commit", "-qm", "Starting checkout")
    expected = tree_entries(objects(case), sha)
    if tree_entries(work / ".git", "HEAD") != expected:
        raise ValueError(f"{case['id']}: snapshot differs from pinned paths, modes or blobs")
    if case["image"] == "node":
        with (work / ".git/info/exclude").open("a") as ignore:
            ignore.write("\n/node_modules\n")
        (work / "node_modules").symlink_to("/deps/node_modules", target_is_directory=True)
    return work


def fingerprint(case):
    paths = [HERE / "lab.py", HERE / "cases.json", HERE / "checks" / case["check"]]
    return hashlib.sha256(b"".join(bytes.fromhex(digest(p)) for p in paths)).hexdigest()


def grade(case, revision, patch=None):
    """Grade in a clean base/gold checkout, preserving build, native and hidden outcomes."""
    fixture = fingerprint(case)
    run = Path(tempfile.mkdtemp(prefix=case["id"] + "-grade-", dir=STATE / "volatile"))
    work = snapshot(case, revision, run)
    if patch:
        with patch.open("rb") as stream:
            call("git", "-C", work, "apply", "--binary", "-", stdin=stream)
    args, image = docker(case, work)
    probe = HERE / "checks" / case["check"]
    acceptance = {
        ".py": "python3 /checks/probe.py", ".mjs": "node /checks/probe.mjs",
        ".go": "go build -o /tmp/probe /checks/probe.go && /tmp/probe",
        ".rs": ("mkdir -p crates/ignore/examples && cp /checks/probe.rs crates/ignore/examples/lab_probe.rs "
                "&& cargo run --offline --locked -q -p ignore --example lab_probe"),
    }[probe.suffix]
    stages = {}
    for name, cmd in (("build", case["build"]), ("native", case["native"]), ("hidden", acceptance)):
        if name != "build" and stages["build"] != 0:
            stages[name] = None
            continue
        mount = ["--mount", f"type=bind,src={probe},dst=/checks/probe{probe.suffix},readonly"] if name == "hidden" else []
        with (run / (name + ".log")).open("w") as log:
            try:
                stages[name] = subprocess.run([*args, *mount, image, "sh", "-ec", cmd],
                                              stdout=log, stderr=subprocess.STDOUT, timeout=900).returncode
            except subprocess.TimeoutExpired:
                stages[name] = 124
    if fixture != fingerprint(case):
        raise ValueError("grader changed during execution")
    record = {"case": case["id"], "revision": revision, "fixture_sha256": fixture,
              "image": image, "patch_sha256": digest(patch) if patch else None,
              "stages": stages, "directory": str(run.relative_to(STATE))}
    if case["id"] == "marked" and stages["hidden"] in (0, 42):
        output = (run / "hidden.log").read_text().splitlines()
        rows = [json.loads(line.removeprefix("BENCH_DIAGNOSTIC ")) for line in output
                if line.startswith("BENCH_DIAGNOSTIC ")]
        if len(rows) == 1:
            record["diagnostics"] = rows[0]
    (run / "grade.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def calibrate(case):
    prepare(case)
    baseline = grade(case, case["base"])
    reference = grade(case, case["gold"])
    # Hidden programs use exit 42 only for a reached behavioral assertion.
    admitted = (baseline["stages"] == {"build": 0, "native": 0, "hidden": 42}
                and reference["stages"] == {"build": 0, "native": 0, "hidden": 0})
    row = {"admitted": admitted, "base": baseline, "gold": reference}
    receipt = STATE / "calibration" / case["id"]
    receipt.mkdir(parents=True, exist_ok=True)
    (receipt / f"{time.time_ns()}.json").write_text(json.dumps(row, indent=2) + "\n")
    print(json.dumps(row), flush=True)
    return admitted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "calibrate", "grade"])
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--patch", type=Path)
    args = parser.parse_args()
    start_state()
    case = CASES[args.case]
    if args.operation == "calibrate":
        return 0 if calibrate(case) else 2
    prepare(case)
    if args.operation == "grade":
        if args.patch is None:
            parser.error("grade requires --patch")
        row = grade(case, case["base"], args.patch)
        print(json.dumps(row))
        return int(any(value != 0 for value in row["stages"].values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
