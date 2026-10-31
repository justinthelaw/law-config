#!/usr/bin/env python3
"""Time the cold build and public tests in a fresh worker before fixing the arm deadline."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guest
import host
import lab


def measure(case):
    lab.prepare(case)
    run = lab.STATE / "feasibility" / case["id"] / str(time.time_ns())
    (run / "profile/skills").mkdir(parents=True)
    work = lab.snapshot(case, case["base"], run)
    cli = Path(os.environ["BENCHMARK_CODEX"]).resolve(strict=True)
    helper = cli.parent.parent / "codex-resources/bwrap"
    if lab.digest(cli) != host.CLI_SHA256 or lab.digest(helper) != host.BWRAP_SHA256:
        raise ValueError("the native worker and its sandbox helper must match qualification")
    image = guest.image_id(case)
    args = guest.args(case, run, work, cli, helper, None, "", verification=True)
    start = time.monotonic()
    log = run / "worker.log"
    with log.open("xb") as output:
        with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT) as proc:
            try:
                code = proc.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                proc.terminate()
                code = 124
    elapsed = time.monotonic() - start
    lines = log.read_bytes().splitlines()
    passed = code == 0 and b"BENCH_BUILD_OK" in lines and b"BENCH_NATIVE_OK" in lines
    receipt = {"case": case["id"], "base": case["base"], "worker_image": image,
               "build": case["build"], "native": guest.native_tests(case), "seconds": elapsed,
               "returncode": code, "passed": passed}
    (run / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=lab.CASES)
    lab.start_state()
    raise SystemExit(0 if measure(lab.CASES[parser.parse_args().case]) else 2)
