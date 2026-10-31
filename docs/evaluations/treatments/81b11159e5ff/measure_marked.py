"""Replay the registered delimiter corpus in a completed Marked tuning trial."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

EVALS = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(EVALS), str(EVALS / "tools")]
import benchmark as B
from cpu_leases import lease
from native_panel import C, E


def observe(entry, probe):
    grade = C.verified_grade(entry)
    work = E.STATE / grade["directory"] / "work"
    args, image = E.lab.docker(E.CASES["marked"], work)
    mount = f"type=bind,src={work},dst=/work"
    if args.count(mount) != 1:
        raise ValueError("expected one sealed workspace mount")
    args[args.index(mount)] = mount + ",readonly"
    output = subprocess.run([*args, "-i", image, "node", "-"], input=probe, capture_output=True, timeout=180)
    if output.returncode:
        raise ValueError(f"reference replay exited {output.returncode}: {output.stderr.decode()[:300]}")
    return {"grade_sha256": entry["sha256"], "patch_sha256": grade.get("patch_sha256"),
            "observations": json.loads(output.stdout)}


def measure(name):
    root = E.STATE / "pilots" / name
    registration = root / "registration.json"
    reg = E.read(registration)
    lock = Path(__file__).with_name("hypothesis.json")
    policy = E.read(lock)
    if (reg["name"] != name or reg["case"] != "marked" or reg["hypothesis"] != policy["id"]
            or E.sha(lock) != reg["hypothesis_sha256"] or E.sha(Path(__file__)) != policy["measurement_program_sha256"]
            or sorted(reg["order"]) != [["candidate", "control"], ["candidate", "develop"], ["prior", "develop"]]):
        raise ValueError("expected the registered Marked treatment and measurement")
    source = EVALS / "runs/pr-quality-panel-v2/marked-delimiter-replay.json"
    archive = E.read(source)
    probe = archive["probe"].encode()
    if E.sha(source) != policy["measurement_source_sha256"] or hashlib.sha256(probe).hexdigest() != archive["probe_sha256"]:
        raise ValueError("registered corpus changed")
    plans = {role: C.verify_receipt(receipt) for role, receipt in reg["plans"].items()}
    candidate = E.read(Path(__file__).with_name("treatment.json"))["package_sha256"]
    for role, pin in (("candidate", candidate), ("prior", policy["previous"])):
        if (plans[role]["pilot"] != {"name": name, "case": "marked", "role": role}
                or plans[role]["runtime"]["package_sha256"] != pin):
            raise ValueError("registered plan belongs to a different treatment or task")
    reference = plans["candidate"]["references"]["marked"]
    if (plans["prior"]["references"]["marked"] != reference or reference["base"] != archive["base"]
            or reference["gold"] != archive["merged"]):
        raise ValueError("registered Marked task differs from the calibration")
    entries = {role: reference[role + "_grade"] for role in ("base", "gold")}
    for role, arm in reg["order"]:
        trial = plans[role]["name"]
        if not (C.run_dir(trial) / "attempts/marked" / arm / "result.json").is_file():
            raise ValueError("wait for all three terminal proposal records")
        entries[f"{role}/{arm}"] = C.read_attempt(trial, "marked", arm).get("grade")
    with lease(E.STATE, os.sched_getaffinity(0)):
        rows = {role: observe(entry, probe) if entry else None for role, entry in entries.items()}
    for role in ("base", "gold"):
        if rows[role]["observations"] != archive["roles"][role]["observations"]:
            raise ValueError(f"{role} reference calibration changed")
    for row in rows.values():
        if row:
            observed = row["observations"]
            if (observed["generated"], observed["reference_disagreements"], observed["official_examples"]) != (3648, 0, 132):
                raise ValueError("reference agreement or corpus coverage changed")
    return {"case": "marked", "registration_sha256": E.sha(registration), "probe_sha256": archive["probe_sha256"],
            "source_sha256": E.sha(source), "measurement_sha256": E.sha(Path(__file__)), "roles": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=B.valid_name)
    args = parser.parse_args()
    B.configure_temp()
    E.configure()
    record = measure(args.run)
    path = E.STATE / "pilots" / args.run / "sensitivity/short-delimiter-runs/receipt.json"
    try:
        E.save(path, record)
    except FileExistsError:
        if E.read(path) != record:
            raise ValueError("a different reference replay already exists") from None
    print(json.dumps(record, indent=2))
