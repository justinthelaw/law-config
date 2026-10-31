"""Replay a published Python caller check from verified proposal patches."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmark as B
from cpu_leases import lease
from native_panel import C, E
from records import digest, read_json, read_pilot

COMMAND = "PYTHONPATH=src:/deps/lib python3 -B /oracle/probe.py"


def replay_paths(source_path, measure, target_path, *, supplement=None, scratch=None):
    source_path, target_path = Path(source_path), Path(target_path)
    archive = read_pilot(source_path)
    observation = supplement or next((o for o in archive["observations"] if o["id"] == measure), None)
    if supplement is not None:
        evidence = supplement.get("evidence", {})
        receipt = digest((json.dumps(evidence, indent=2) + "\n").encode())
        if (supplement.get("id") != measure or supplement.get("source_sha256") != E.sha(source_path)
                or supplement.get("receipt_sha256") != receipt
                or evidence.get("registration_sha256") != archive["registration_sha256"]
                or digest(supplement.get("probe", "").encode()) != evidence.get("probe_sha256")):
            raise ValueError("supplement differs from its source, receipt or probe")
    if not observation or "probe" not in observation:
        raise ValueError("the source pilot does not contain this executable check")
    evidence = observation["evidence"]
    controls = evidence.get("roles", {})
    stages = (controls.get("base") or {}).get("stages", {})
    if evidence.get("case") != archive["case"] or not stages:
        raise ValueError("expected caller calibration for the source case")
    archived_patches = {"base": None, "gold": archive["submissions"]["upstream"]["patch_sha256"],
                        "candidate-control": archive["submissions"]["control"]["patch_sha256"],
                        "candidate-develop": archive["submissions"]["develop"]["patch_sha256"],
                        "prior-develop": archive["prior_develop"]["patch_sha256"]}
    for role, checksum in archived_patches.items():
        if checksum is None and role != "base":
            continue
        saved = controls.get(role) or {}
        if (saved.get("patch_sha256", "") != checksum or set(saved.get("stages", {})) != set(stages)
                or any(row.get("command") != COMMAND for row in saved["stages"].values())):
            raise ValueError(f"{role} caller calibration is missing or differs from its patch")

    path = target_path
    same = source_path.resolve() == target_path.resolve()
    record = archive if same else read_pilot(path)
    if any(record[k] != archive[k] for k in ("case", "repository", "base", "merged", "prompt_sha256")):
        raise ValueError("target pilot must use the same repository, revisions and task")
    case = E.CASES[record["case"]]
    if (case["repo"], case["base"], case["gold"]) != (record["repository"], record["base"], record["merged"]):
        raise ValueError("the configured fixture differs from the published task")
    prior = record["prior_develop"]
    if "patch" not in prior and prior["patch_sha256"] is not None:
        prior = read_json(path.with_name("prior.json").read_bytes())
    arms = record["submissions"]
    if not arms["upstream"]["patch"]:
        raise ValueError("the merged control requires its published patch")
    patches = {"base": None, "gold": arms["upstream"]["patch"], "candidate-control": arms["control"]["patch"],
               "candidate-develop": arms["develop"]["patch"], "prior-develop": prior.get("patch")}

    folder = Path(tempfile.mkdtemp(prefix="caller-replay-", dir=scratch or E.CACHE / "volatile"))
    probe = folder / "probe.py"
    probe.write_text(observation["probe"])
    cpus = sorted(os.sched_getaffinity(0))[:2]
    os.environ["PANEL_CPUSET"] = ",".join(map(str, cpus))
    rows = {}
    with lease(E.STATE, cpus):
        E.prepare(case)
        for role, content in patches.items():
            if content is None and role != "base":
                rows[role] = None
                continue
            patch = folder / (role + ".patch") if content else None
            if patch:
                patch.write_bytes(content.encode())
            checkout = folder / role
            grade = C.grading.grade(case, case["base"], checkout, patch, phases=[], target=case["gold"] if role == "gold" else None)
            if patch and not grade["applied"]:
                raise ValueError(f"{role} patch does not apply to the pinned base")
            work = checkout / "work"
            args, image = E.lab.docker(case, work)
            mount = f"type=bind,src={work},dst=/work"
            if args.count(mount) != 1:
                raise ValueError("expected a single sealed worktree mount")
            args[args.index(mount)] = mount + ",readonly"
            results = {}
            for stage in stages:
                run = subprocess.run([*args, "--mount", f"type=bind,src={probe},dst=/oracle/probe.py,readonly",
                                      "-e", "PANEL_STAGE=" + stage, image, "sh", "-ec", COMMAND],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
                sha = digest(run.stdout)
                if role in ("base", "gold") or same:
                    saved = controls[role]["stages"][stage]
                    if (run.returncode, sha) != (saved["exit"], saved["log_sha256"]):
                        raise ValueError(f"{role}/{stage} differs from its archived calibration")
                results[stage] = {"exit": run.returncode, "log_sha256": sha, "output": run.stdout.decode()}
            rows[role] = {"patch_sha256": digest(content.encode()) if content is not None else None,
                          "stages": results}
    return {"case": case["id"], "source": source_path.parent.name, "measure": measure, "target": target_path.parent.name,
            "source_sha256": E.sha(source_path), "source_receipt_sha256": observation["receipt_sha256"],
            "target_sha256": E.sha(path), "registration_sha256": record["registration_sha256"],
            "probe_sha256": E.sha(probe), "roles": rows}


def replay(source, measure, target):
    return replay_paths(B.pilot_file(source), measure, B.pilot_file(target))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=B.valid_name)
    parser.add_argument("measure", type=B.valid_name)
    parser.add_argument("--run", type=B.valid_name, help="Use another sealed pilot for the same case.")
    args = parser.parse_args()
    B.configure_temp()
    E.configure()
    try:
        print(json.dumps(replay(args.source, args.measure, args.run or args.source), indent=2))
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
