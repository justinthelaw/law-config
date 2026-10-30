#!/usr/bin/env python3
"""Prepare a masked reference/control/treatment comparison and seal the assessor's judgments."""
import argparse
import hashlib
from pathlib import Path
import secrets
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab
from run import frozen_plan, read, reference, result, save

AXES = ("correctness", "regression_coverage", "maintainability_scope")
PAIRS = ("AB", "AC", "BC")


def directory(case):
    return lab.STATE / "reviews" / case["id"]


def prepare(case):
    plan = frozen_plan()
    if not plan:
        raise ValueError("no experiment is available")
    folder = directory(case)
    grades, patches = {}, {}
    for arm in ("control", "develop"):
        row = result(plan, case, arm)
        if row["state"] not in {"completed", "timeout"}:
            raise ValueError(f"{arm} has no gradeable submission")
        grades[arm] = row["grade"]
        patches[arm] = (lab.STATE / "experiment" / case["id"] / arm / "candidate.patch").read_bytes()
    grades["reference"] = reference(plan, case)["gold"]
    patches["reference"] = lab.call("git", "--git-dir", lab.objects(case), "diff",
        "--binary", "--no-ext-diff", "--no-textconv", case["base"], case["gold"],
        stdout=subprocess.PIPE).stdout
    arms = list(grades)
    secrets.SystemRandom().shuffle(arms)
    folder.mkdir(parents=True, exist_ok=False)
    packet = folder / "packet"
    packet.mkdir()
    key = dict(zip("ABC", arms))
    save(folder / "private-key.json", key)
    facts = {}
    for label, arm in key.items():
        patch = packet / f"{label}.patch"
        patch.write_bytes(patches[arm])
        facts[label] = {"stages": grades[arm]["stages"], "diagnostics": grades[arm].get("diagnostics"),
                        "patch_sha256": lab.digest(patch)}
    save(packet / "task.json", {"experiment": plan["identity"], "case": case["id"], "prompt": case["prompt"],
        "submissions": facts, "rubric": "Compare each pair on correctness, regression coverage and "
        "maintainability/scope. Inspect weakened native tests. Cite concrete file/behavior evidence. "
        "Judge only what was achievable from the offline base. Ignore provenance, timing, accounts, "
        "release/hosted checks and author hints; report if identity is inferable."})
    template = {"task_sha256": lab.digest(packet / "task.json"), "assessor": "", "limitations": "",
                "pairs": {pair: {**dict.fromkeys(AXES, "unknown"), "evidence": ""} for pair in PAIRS}}
    save(packet / "judgment-template.json", template)
    print(packet)


def validate(case, plan, judgment):
    folder = directory(case)
    task = folder / "packet/task.json"
    facts = read(task)
    if facts["experiment"] != plan["identity"] or facts["case"] != case["id"]:
        raise ValueError("blind task belongs to another experiment")
    if judgment["task_sha256"] != lab.digest(task) or not judgment["assessor"].strip():
        raise ValueError("judgment needs the packet identity and assessor")
    key = read(folder / "private-key.json")
    if set(key) != set("ABC") or set(key.values()) != {"control", "develop", "reference"}:
        raise ValueError("invalid mask key")
    for label, arm in key.items():
        sha = lab.digest(folder / "packet" / f"{label}.patch")
        if sha != facts["submissions"][label]["patch_sha256"]:
            raise ValueError("review packet changed")
        if arm == "reference":
            grade = reference(plan, case)["gold"]
            original = lab.call("git", "--git-dir", lab.objects(case), "diff", "--binary", "--no-ext-diff",
                                "--no-textconv", case["base"], case["gold"], stdout=subprocess.PIPE)
            expected_sha = hashlib.sha256(original.stdout).hexdigest()
        else:
            grade = result(plan, case, arm)["grade"]
            expected_sha = grade["patch_sha256"]
        if (sha != expected_sha or facts["submissions"][label]["stages"] != grade["stages"]
                or facts["submissions"][label]["diagnostics"] != grade.get("diagnostics")):
            raise ValueError("review does not match the graded artifact")
    if set(judgment["pairs"]) != set(PAIRS):
        raise ValueError("all three pairwise comparisons are required")
    for pair, grades in judgment["pairs"].items():
        if not grades["evidence"].strip() or any(grades.get(axis) not in {*pair, "tie", "unknown"} for axis in AXES):
            raise ValueError(f"missing or invalid decision for {pair}")
    return key


def verdicts(case, plan):
    path = directory(case) / "judgment.json"
    if not path.exists():
        return None
    judgment = read(path)
    key = validate(case, plan, judgment)
    rows = []
    for pair, grades in judgment["pairs"].items():
        rows.append({"arms": [key[label] for label in pair],
                     **{axis: key.get(grades[axis], grades[axis]) for axis in AXES},
                     "evidence": grades["evidence"]})
    return {"assessor": judgment["assessor"], "limitations": judgment["limitations"], "pairs": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=lab.CASES)
    parser.add_argument("--judgment", type=Path)
    args = parser.parse_args()
    lab.start_state()
    case = lab.CASES[args.case]
    if args.judgment:
        judgment = read(args.judgment)
        validate(case, frozen_plan(), judgment)
        save(directory(case) / "judgment.json", judgment)
    else:
        prepare(case)
