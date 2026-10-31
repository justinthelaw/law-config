"""Run one fresh pair and three assessors per primary case interrupted by provider capacity."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parent / "panel"))
import campaign as C
import judge as J
import results as R

E = C.E


def select(primary, name):
    if primary == name:
        raise ValueError("recovery requires a new campaign name")
    parent = C.run_dir(primary)
    original = C.plan_for(primary)
    layout = E.read(parent / "lanes.json")
    if not (parent / "report/results.json").is_file() or C.launcher_active(primary):
        raise ValueError("wait for the primary campaign and its assessments")
    cases = []
    failures = {}
    last_failure = last_success = 0
    for key in original["schedule"]:
        for arm in original["order"][key]:
            row = C.read_attempt(primary, key, arm)
            if row["state"] in {"interrupted", "unreleased"}:
                raise ValueError("primary slot has no terminal result")
            if row["state"] == "blocked" and "serverOverloaded" in str(row.get("error")):
                if key not in cases:
                    cases.append(key)
                record = parent / "attempts" / key / arm / "result.json"
                failures[f"{key}/{arm}"] = C.receipt(record)
                last_failure = max(last_failure, row["start_unix"] + row["end_to_end_seconds"])
            elif row["state"] == "completed":
                last_success = max(last_success, row["captured_unix"])
    for p in parent.glob("judges/*/*/*/native.json"):
        native = E.read(p)
        if native["state"] == "completed":
            last_success = max(last_success, native["assessment_finished_unix"])
    if not cases:
        raise ValueError("no primary capacity interruptions")
    if last_success <= last_failure:
        raise ValueError("no observed successful model turn after the last capacity stop")
    selection = {"parent_plan": C.receipt(parent / "plan.json"), "cases": cases, "capacity_receipts": failures,
                 "last_capacity_end_unix": last_failure, "subsequent_success_unix": last_success,
                 "proposal_attempts_per_arm": 1, "judge_calls_per_rotation": 1}
    root = C.run_dir(name)
    if (root / "plan.json").is_file():
        plan = C.plan_for(name)
        if plan.get("recovery") != selection or E.read(root / "lanes.json") != layout:
            raise ValueError("recovery selection or CPU layout changed")
    else:
        root.mkdir(parents=True, exist_ok=False)
        E.save(root / "lanes.json", layout)
        E.save(root / "plan.json", dict(original, name=name, schedule=cases, frozen_unix=time.time(), recovery=selection))
    return root, layout, cases


def run(primary, name, *, pause_on_block=False):
    root, layout, cases = select(primary, name)
    with (root / "recovery.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source_path = root / "recovery-controller.json"
        expected = {"plan_sha256":E.sha(root / "plan.json"), "sha256":E.sha(Path(__file__)),
                    "source":Path(__file__).read_text()}
        if not source_path.is_file():
            E.save(source_path, expected)
        elif E.read(source_path) != expected:
            raise ValueError("restore the recorded recovery controller to resume this run")
        policy = root / "operator-recovery.json"
        if pause_on_block and not policy.exists():
            allocated = sorted(str(p.parent.relative_to(root / "attempts")) for p in root.glob("attempts/*/*/release.json"))
            E.save(policy, {"on_block":"pause", "plan_sha256":E.sha(root / "plan.json"), "prior_releases":allocated})
        if policy.exists():
            rule = E.read(policy)
            if rule["on_block"] != "pause" or rule["plan_sha256"] != E.sha(root / "plan.json"):
                raise ValueError("recovery release policy differs from this plan")
        return execute(root, layout, cases, name, pause_on_block=policy.exists())


def execute(root, layout, cases, name, *, pause_on_block=False):
    plan = C.plan_for(name)
    print("Selected fresh pairs:", ", ".join(cases), flush=True)
    stopped = Event()
    def proposals(lane):
        cpus = ",".join(map(str, layout["cpu_pairs"][lane]))
        for key in layout["queues"][lane]:
            if key not in cases:
                continue
            for arm in plan["order"][key]:
                if stopped.is_set():
                    return
                if C.read_attempt(name, key, arm)["state"] != "unreleased":
                    continue
                subprocess.run(["taskset", "-c", cpus, sys.executable, "-B", str(E.HERE / "campaign.py"),
                                "attempt", name, key, arm], env=dict(os.environ, PANEL_CPUSET=cpus), check=True)
                if pause_on_block and C.read_attempt(name, key, arm)["state"] == "blocked":
                    stopped.set()
                    return
    with (root / "launcher.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=layout["jobs"]) as pool:
            list(pool.map(proposals, range(layout["jobs"])))
    if stopped.is_set():
        print("A recovery proposal stopped. Inspect status before resuming the remaining releases.", flush=True)
        return False
    # The frozen assessor normally permits one technical repair. Reserve that slot
    # without releasing a model so this secondary experiment uses at most three calls per case.
    for key in cases:
        for rotation in range(plan["judge_rotations"]):
            repair = root / "judges" / key / str(rotation) / "1"
            repair.mkdir(parents=True, exist_ok=True)
            if not (repair / "call-limit.json").exists():
                E.save(repair / "call-limit.json", {"released": False, "reason": "one assessor call per rotation"})
    subprocess.run([sys.executable, "-B", str(E.HERE / "judge.py"), name, "--jobs", str(layout["jobs"])], check=False)
    for key in cases:
        for rotation in range(plan["judge_rotations"]):
            folder = root / "judges" / key / str(rotation)
            if not (folder / "0").is_dir() or not ((folder / "judgment.json").is_file() or (folder / "0/invalid.json").is_file()):
                raise RuntimeError(f"inspect incomplete recovery assessor: {key} rotation {rotation}")
    write_report(name)
    return True


def write_report(name):
    root = C.run_dir(name)
    plan = C.plan_for(name)
    cases = plan["recovery"]["cases"]
    rows = [R.case_row(name, E.CASES[key]) for key in cases]
    evaluator = [x for row in rows for x in row["evaluator_cost"]]
    arms = [row[arm] for row in rows for arm in ("control", "develop")]
    captures = [(arm["start_unix"], arm["captured_unix"]) for arm in arms
                if arm["start_unix"] is not None and arm["captured_unix"] is not None]
    ends = [arm["start_unix"] + arm["end_to_end_seconds"] for arm in arms
            if arm["start_unix"] is not None and arm["end_to_end_seconds"] is not None]
    ends.extend(a["assessed_unix"] for row in rows for a in row["assessors"])
    ends.extend(E.read(p)["assessment_finished_unix"] for p in root.glob("judges/*/*/*/native.json"))
    report = {"plan_sha256": E.sha(root / "plan.json"), "selection": plan["recovery"],
              "campaign_submission_span_seconds": max(y for x,y in captures) - min(x for x,y in captures) if captures else None,
              "campaign_elapsed_through_last_measurement_seconds": max(ends) - plan["frozen_unix"] if ends else None,
              "groups": {"all": R.group(rows)}, "cases": rows, "evaluator": {
                  "attempts": len(evaluator), "observed_usd": sum(x["usd_estimate"] or 0 for x in evaluator),
                  "complete_receipts": sum(x["coverage"] == "complete" for x in evaluator)}}
    target = root / "report"
    target.mkdir(exist_ok=True)
    (target / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Recovery comparison:", target / "results.json", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("primary")
    parser.add_argument("name")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    C.controller.activate()
    if args.report_only:
        write_report(args.name)
    else:
        raise SystemExit(0 if run(args.primary, args.name) else 3)
