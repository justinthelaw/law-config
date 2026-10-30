"""Measure the public build/test command in the exact offline worker used by Codex."""
import argparse
import math
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import environment as E
from grading import snapshot, fixture_hash


def measure(case):
    E.prepare(case)
    folder = E.CACHE / "cold" / case["id"] / str(time.time_ns())
    (folder / "profile/skills").mkdir(parents=True)
    cli = Path(os.environ["BENCHMARK_CODEX"]).resolve(strict=True)
    bwrap = cli.parent.parent / "codex-resources/bwrap"
    if E.sha(cli) != E.host.CLI_SHA256 or E.sha(bwrap) != E.host.BWRAP_SHA256:
        raise ValueError("wrong native distribution")
    work = snapshot(case, case["base"], folder)
    args = E.guest.args(case, folder, work, cli, bwrap, None, "", verification=True)
    t = time.monotonic()
    with (folder / "worker.log").open("xb") as log:
        with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT) as proc:
            try:
                rc = proc.wait(timeout=10800)
            except subprocess.TimeoutExpired:
                proc.terminate()
                rc = 124
    elapsed = time.monotonic() - t
    output = (folder / "worker.log").read_bytes().splitlines()
    passed = rc == 0 and b"BENCH_BUILD_OK" in output and b"BENCH_NATIVE_OK" in output
    row = {"case": case["id"], "base": case["base"], "worker_image": E.guest.image_id(case),
           "build": case["build"], "native": E.guest.native_tests(case), "seconds": elapsed,
           "passed": passed, "returncode": rc, "source": "fresh", "log_sha256": E.sha(folder / "worker.log")}
    if case.get("loopback_hosts"):
        row["fixture_sha256"] = fixture_hash(case)
    E.save(folder / "receipt.json", row)
    print(case["id"], round(elapsed), "passed" if passed else "failed", flush=True)
    return passed


def import_previous(case):
    """Reuse a measured cold verification only when source, commands and worker image are identical."""
    if not case.get("legacy") or case.get("loopback_hosts"):
        raise ValueError("old receipts only exist for the known cases")
    original = E.ROOT / "tmp/six-repo-workflow"
    plan = E.read(original / "experiment/plan.json")
    pin = plan["feasibility"][case["id"]]
    path = original / pin["path"]
    record = E.read(path)
    expected = (case["id"], case["base"], E.guest.image_id(case), case["build"], E.guest.native_tests(case))
    if (E.sha(path) != pin["sha256"] or not record["passed"] or
            tuple(record[k] for k in ("case","base","worker_image","build","native")) != expected):
        raise ValueError("cold calibration differs from the freeze")
    folder = E.CACHE / "cold" / case["id"] / str(time.time_ns())
    E.save(folder / "receipt.json", {**record, "source":"verified original cold timing", "original_sha256":E.sha(path)})
    return True


def budget(seconds):
    return max(1200, math.ceil(2 * seconds / 60) * 60)


if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("case", choices=E.CASES)
    ap.add_argument("--reuse-verified-v1", action="store_true")
    a=ap.parse_args()
    E.configure()
    raise SystemExit(0 if (import_previous if a.reuse_verified_v1 else measure)(E.CASES[a.case]) else 2)
