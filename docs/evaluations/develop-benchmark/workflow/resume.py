#!/usr/bin/env python3
"""Preserve a capacity-stopped primary cohort and run only its unreleased slots as a supplement."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab
import report
import run

SUPPLEMENT = lab.STATE / "continuation"


def capacity_stop(row):
    return row["state"] == "blocked" and "'codexErrorInfo': 'serverOverloaded'" in row.get("error", "")


def freeze(root, plan):
    pending, receipts = [], {}
    last = None
    for case in lab.CASES.values():
        for arm in plan["order"][case["id"]]:
            key = f"{case['id']}/{arm}"
            if not (root / key).exists():
                pending.append(key)
                continue
            if pending or (last is not None and capacity_stop(last)):
                raise ValueError("a primary arm was released after a gap or capacity stop")
            last = run.result(plan, case, arm)
            if last["state"] == "blocked" and not capacity_stop(last):
                raise ValueError("only a provider capacity stop permits this supplement")
            receipts[key] = {name: lab.digest(root / key / name) for name in ("release.json", "result.json")}
    if not pending or last is None or not capacity_stop(last):
        raise ValueError("the primary cohort must end at a capacity stop with unreleased slots")
    SUPPLEMENT.mkdir()
    snapshot = SUPPLEMENT / "primary-report.json"
    run.save(snapshot, report.report())
    run.save(SUPPLEMENT / "manifest.json", {"plan_sha256": lab.digest(root / "plan.json"),
        "launcher_sha256": lab.digest(Path(__file__)), "primary_report_sha256": lab.digest(snapshot),
        "primary_receipts": receipts, "supplementary_slots": pending,
        "policy": "Preserve the original stopping point. Continue in the frozen order after a fresh "
                  "model and executor probe. Never repeat a released arm. Pause at the next service failure."})
    print(f"Preserved {len(receipts)} primary slots; {len(pending)} supplementary slots frozen.", flush=True)


def verified_manifest(root, plan):
    manifest = run.read(SUPPLEMENT / "manifest.json")
    if (lab.digest(root / "plan.json") != manifest["plan_sha256"]
            or lab.digest(Path(__file__)) != manifest["launcher_sha256"]
            or lab.digest(SUPPLEMENT / "primary-report.json") != manifest["primary_report_sha256"]):
        raise ValueError("supplement or primary snapshot changed")
    order = [f"{case}/{arm}" for case, arms in plan["order"].items() for arm in arms]
    if list(manifest["primary_receipts"]) + manifest["supplementary_slots"] != order:
        raise ValueError("manifest does not partition the original release order")
    for key, hashes in manifest["primary_receipts"].items():
        case, arm = key.split("/")
        run.result(plan, lab.CASES[case], arm)
        if any(lab.digest(root / key / name) != sha for name, sha in hashes.items()):
            raise ValueError(f"primary receipt changed: {key}")
    return manifest


def classified_report(root, plan):
    manifest = verified_manifest(root, plan)
    summary = report.report()
    summary["primary_snapshot"] = {"path": "continuation/primary-report.json",
        "sha256": manifest["primary_report_sha256"], "released_slots": len(manifest["primary_receipts"])}
    summary["supplementary_slots"] = manifest["supplementary_slots"]
    for pair in summary["pairs"]:
        for arm in run.ARMS:
            key = f"{pair['case']}/{arm}"
            pair[arm]["cohort"] = "primary" if key in manifest["primary_receipts"] else "supplementary"
        if pair["control"]["cohort"] != pair["develop"]["cohort"]:
            pair["develop_minus_control"] = None
    return summary


def resume(root, plan):
    manifest = verified_manifest(root, plan)
    pending = []
    for key in manifest["supplementary_slots"]:
        case, arm = key.split("/")
        if not (root / key).exists():
            pending.append(key)
        else:
            if pending:
                raise ValueError("supplementary release order changed")
            row = run.result(plan, lab.CASES[case], arm)
            if row["state"] == "blocked" and not capacity_stop(row):
                raise ValueError(f"unresolved infrastructure failure: {key}")
    if not pending:
        return
    probe = SUPPLEMENT / "health" / str(time.time_ns())
    probe.mkdir(parents=True)
    observed = run.probe("develop", probe)
    run.save(probe / "probe.json", observed)
    if not observed["passed"]:
        raise ValueError("recovery probe failed; no new slot released")
    for key in pending:
        case, arm = key.split("/")
        current = run.runtime()
        if current != {k: plan[k] for k in current}:
            raise ValueError("frozen runtime changed")
        path = root / key
        path.parent.mkdir(exist_ok=True)
        row = run.trial(lab.CASES[case], arm, path, plan["feasibility"][case]["budget_seconds"])
        if row["state"] == "blocked":
            raise ValueError(f"{key}: {row.get('error')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "report"))
    action = parser.parse_args().action
    os.umask(0o077)
    lab.start_state()
    root, plan = run.start_experiment()
    if action == "report":
        print(json.dumps(classified_report(root, plan), indent=2))
    elif action == "freeze":
        freeze(root, plan)
    else:
        with (SUPPLEMENT / "run.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("a supplementary launcher is already active")
            resume(root, plan)
