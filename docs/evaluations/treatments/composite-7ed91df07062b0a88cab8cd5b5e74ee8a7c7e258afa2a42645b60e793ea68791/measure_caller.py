"""Replay a registered trial's five verified grades after grading and before report."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

EVALS = Path(__file__).resolve().parents[2]
if not (EVALS / "benchmark.py").is_file():
    EVALS = Path.cwd() / "docs/evaluations"
sys.path[:0] = [str(EVALS), str(EVALS / "tools")]
import benchmark as B
from native_panel import C, E
from cpu_leases import lease

ID = "observable-red-green-replay"
COMMAND = "PYTHONPATH=src:/deps/lib python3 -B /oracle/probe.py"


def content_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def policy_for(source, registration, plans):
    path = source / "hypothesis.json"
    policy = E.read(path)
    if (registration["hypothesis"] != ID or policy["id"] != ID
            or E.sha(path) != registration.get("hypothesis_sha256")):
        raise ValueError("registered hypothesis differs")
    required = {"measure_caller.py", "calibrate.py", "probes/werkzeug_stream_model.py",
                "probes/expat_literal_model.py", "probes/expat_parameter_entities.py"}
    if not required <= policy["bound_files"].keys():
        raise ValueError("measurement source bindings are incomplete")
    for relative, checksum in policy["bound_files"].items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or E.sha(source / path) != checksum:
            raise ValueError("bound measurement source differs")
    if policy["measurement_program_sha256"] != E.sha(source / "measure_caller.py"):
        raise ValueError("measurement program differs")
    companions = []
    for role, expected in (("prior", policy["previous"]), ("candidate", policy["candidate_package_sha256"])):
        runtime = plans[role]["runtime"]
        treatment = runtime["treatment"]
        companion = treatment.get("companion")
        if (runtime["package_sha256"] != expected or treatment["package_sha256"] != expected
                or content_digest(treatment) != policy["composite_identities"][role]
                or content_digest(companion) != policy["companion_content_sha256"]
                or {key: companion.get(key) for key in policy["common_companion"]} != policy["common_companion"]):
            raise ValueError("registered treatment or companion differs")
        companions.append(companion)
    if companions[0] != companions[1]:
        raise ValueError("companion differs between arms")
    return policy


def measure(name):
    source = Path(__file__).resolve().parent
    path = E.STATE / "pilots" / B.valid_name(name) / "registration.json"
    registration = E.read(path)
    key = registration["case"]
    if (registration["name"] != name or key not in ("werkzeug", "expat")
            or sorted(registration["order"]) != [["candidate", "control"], ["candidate", "develop"], ["prior", "develop"]]):
        raise ValueError("unsupported case or registered allocation")
    plans = {role: C.verify_receipt(entry) for role, entry in registration["plans"].items()}
    policy_for(source, registration, plans)  # Also mandatory before receipt reuse.
    reference = plans["candidate"]["references"][key]
    case = E.CASES[key]
    if ((reference["base"], reference["gold"]) != (case["base"], case["gold"])
            or plans["prior"]["references"][key] != reference):
        raise ValueError("registered fixture differs")
    entries = {"base": reference["base_grade"], "gold": reference["gold_grade"]}
    attempts = {}
    for role, arm in registration["order"]:
        if plans[role]["pilot"] != {"name": name, "case": key, "role": role}:
            raise ValueError("plan belongs to another pilot")
        label = role + "-" + arm
        attempts[label] = C.read_attempt(plans[role]["name"], key, arm)
        entries[label] = attempts[label].get("grade")
    grades = {label: C.verified_grade(entry) if entry else None for label, entry in entries.items()}
    for label, grade in grades.items():
        if grade and ((grade["case"], grade["base"]) != (key, case["base"])
                      or (label in attempts and grade["patch_sha256"] != attempts[label].get("patch_sha256"))):
            raise ValueError("grade belongs to another case or patch")
    names = ["werkzeug_stream_model.py"] if key == "werkzeug" else ["expat_literal_model.py", "expat_parameter_entities.py"]
    probes = source / "probes"
    folder = path.parent / "sensitivity" / ID
    receipt = folder / "receipt.json"
    program_sha = E.sha(source / "measure_caller.py")
    probe_sha = E.sha(probes / names[0])
    inputs = {label: entry["sha256"] if entry else None for label, entry in entries.items()}
    identity = {"registration_sha256": E.sha(path), "measurement_program_sha256": program_sha,
                "bound_files": E.read(source / "hypothesis.json")["bound_files"], "grade_inputs": inputs}
    if receipt.exists():
        old = E.read(receipt)
        if any(old[field] != value for field, value in identity.items()):
            raise ValueError("measurement changed; preserve the original receipt")
        for label, row in old["roles"].items():
            if row.get("stages") and E.sha(folder / (label + ".log")) != row["stages"]["caller"]["log_sha256"]:
                raise ValueError("probe log changed")
        return old
    if B.pilot_file(name).is_file():
        raise ValueError("published pilot has no receipt; refusing new observation")
    folder.mkdir(parents=True, exist_ok=True)
    for index, filename in enumerate(names):
        target = folder / ("probe.py" if index == 0 else filename)
        content = (probes / filename).read_bytes()
        if target.exists() and target.read_bytes() != content:
            raise ValueError("probe source changed")
        target.write_bytes(content)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise ValueError("two available CPUs required")
    os.environ["PANEL_CPUSET"] = ",".join(map(str, cpus))
    run_command = runpy.run_path(str(source / "calibrate.py"))["run_command"]
    rows = {}
    with lease(E.STATE, cpus):
        for label, grade in grades.items():
            if grade is None:
                rows[label] = {"outcome": "unsupported", "gap": "no verified sealed grade",
                               "state": attempts.get(label, {}).get("state", "unknown")}
                continue
            work = E.STATE / grade["directory"] / "work"
            args, image = E.lab.docker(case, work)
            mount = f"type=bind,src={work},dst=/work"
            if args.count(mount) != 1:
                raise ValueError("expected one sealed workspace")
            args[args.index(mount)] = mount + ",readonly"
            box = ID + "-" + name + "-" + label
            args += ["--name", box]
            for index, filename in enumerate(names):
                local = folder / ("probe.py" if index == 0 else filename)
                destination = "/oracle/probe.py" if index == 0 else "/oracle/" + filename
                args += ["--mount", f"type=bind,src={local},dst={destination},readonly"]
            row, stdout, stderr = run_command([*args, image, "sh", "-ec", COMMAND], key)
            if row.get("class") == "timeout":
                subprocess.run(["docker", "stop", "-t", "1", box], capture_output=True, timeout=10)
            log = folder / (label + ".log")
            log.write_bytes(stdout + stderr)
            rows[label] = {**row, "patch_sha256": grade.get("patch_sha256"), "grade_sha256": entries[label]["sha256"],
                           "stages": {"caller": {"command": COMMAND, "exit": row["exit"], "log_sha256": E.sha(log)}}}
    record = {**identity, "case": key, "probe_sha256": probe_sha, "cpus": cpus, "roles": rows,
              "scope": "Post-grade observations only. Unsupported or infrastructure outcomes establish no behavioral pass/red. Original scores and proposal meters remain unchanged."}
    if len(names) > 1:
        record["probe_dependencies"] = {filename: {"sha256": E.sha(probes / filename), "source": (probes / filename).read_text()} for filename in names[1:]}
    E.save(receipt, record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=B.valid_name)
    args = parser.parse_args()
    B.configure_temp()
    E.configure()
    try:
        record = measure(args.run)
        print(json.dumps(record, indent=2))
        outcomes = {row["outcome"] for row in record["roles"].values()}
        raise SystemExit(70 if "infrastructure-error" in outcomes else 3 if "unsupported" in outcomes else 0)
    except (ImportError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"outcome": "infrastructure-error", "class": type(exc).__name__}))
        raise SystemExit(70)
