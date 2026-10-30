"""Operate a named Develop PR benchmark or verify its results offline."""
import argparse
from collections import Counter
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = ROOT / "tmp/pr-quality-panel"
PANEL = HERE / "develop-benchmark/panel"
TOOLS = HERE / "tools"
BUNDLES = HERE / "runs/pr-quality-panel-v2"
sys.path.insert(0, str(TOOLS))
if __name__ == "__main__":
    sys.modules["benchmark"] = sys.modules[__name__]


def read(path):
    return json.loads(path.read_bytes())


def valid_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}", name):
        raise ValueError("use a name of 1–60 letters, digits, underscores, periods or hyphens")
    return name


def command(path, *args, allow_partial=False):
    result = subprocess.run([sys.executable, "-B", str(path), *map(str, args)])
    if result.returncode and not (allow_partial and result.returncode == 2):
        raise RuntimeError(f"{path.name} exited {result.returncode}")
    return result.returncode


def active(lock):
    if not lock.is_file():
        return False
    with lock.open("rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


@contextmanager
def operator(name=None):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "operator.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another operator holds the panel's shared CPU lanes") from None
        for kind in ("launcher", "recovery"):
            for path in (STATE / "runs").glob(f"*/{kind}.lock"):
                if active(path):
                    raise ValueError(f"{path.parent.name} has an active {kind}")
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"name": name, "pid": os.getpid(), "cpu_leases": True}))
        handle.flush()
        yield


def panel_results():
    return sorted(p for root in (BUNDLES, BUNDLES.with_name("pr-quality-confirmation-v1"), BUNDLES.with_name("pr-quality-runner-v3"), BUNDLES.with_name("pr-quality-pytest-entry-v1"))
                  for p in root.glob("*/run.json"))


def published(name):
    matches = [p for p in panel_results() if read(p)["name"] == name]
    if len(matches) > 1:
        raise ValueError(f"published campaign name is ambiguous: {name}")
    return matches[0] if matches else None


def published_summary(name, bundle):
    from records import read_bundle, confirmation_quality_summary
    require_reader()
    manifest, rows = read_bundle(bundle)
    local = STATE / "runs" / name / "plan.json"
    if local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest() != manifest["plan_sha256"]:
        raise ValueError("local plan differs from the published identity")
    producers = [r for r in rows.values() if r["role"] != "upstream"]
    states = Counter(r["state"] for r in producers)
    valid = sum(a["accepted"] for case in manifest["cases"] for a in case["judge_attempts"])
    missing = len(manifest["cases"]) * manifest["runtime"]["executor"]["judge"]["rotations"] - valid
    assessments = {k: n for k, n in (("valid", valid), ("unmeasured", missing)) if n}
    def slots(state):
        return [f"{r['case_id']}/{r['role']}" for r in producers if r["state"] == state]
    partial = missing or states["interrupted"] or states["unreleased"]
    summary = {"name": name, "phase": "published-partial" if partial else "published",
                      "split": (manifest["selection"] or {}).get("split", "all"),
                      "cases": [c["id"] for c in manifest["cases"]], "plan_sha256": manifest["plan_sha256"],
                      "proposal_states": dict(states), "assessments": assessments,
                      "allocated": slots("interrupted"), "unreleased": slots("unreleased"),
                      "pending_assessments": [], "stranded_assessments": [], "unadjudicated": [], "bundle": str(bundle)}
    if manifest["protocol"] == "pr-quality-confirmation-v1":
        summary["strict_confirmation_quality"] = confirmation_quality_summary(manifest["cases"], rows, manifest["runtime"]["treatment"], manifest["runtime"])
    return manifest, summary


def pilot_file(name):
    return BUNDLES.with_name("tuning") / name / "result.json"


def pilot_status(name, root):
    from records import control_headroom, pilot_quality_signal, read_pilot
    if pilot_file(name).is_file():
        record = read_pilot(pilot_file(name))
        rows = record["submissions"]
        outcomes = {}
        for role, row in (rows | {"prior_develop": record["prior_develop"]}).items():
            effort = row["effort"] or {}
            quality = row.get("quality", {})
            outcomes[role] = {"readiness": row.get("readiness"),
                              "diff_score_85": quality.get("diff_points_85"),
                              "pr_score_100": quality.get("proposal_points_100", row.get("full_pr_score")),
                              "estimated_usd": effort.get("estimated_usd"), "coverage": effort.get("coverage"),
                              "tokens": (effort.get("tokens") or {}).get("totalTokens"),
                              "proposal_seconds": effort.get("checkout_to_proposal_seconds"),
                              "through_grading_seconds": effort.get("through_grading_seconds")}
        assessors = record.get("assessor_costs") or []
        observed = [a["usd_estimate"] for a in assessors if a.get("usd_estimate") is not None]
        complete_receipts = sum(a.get("coverage") == "complete" and a.get("usd_estimate") is not None
                                for a in assessors)
        # Attempt receipts include retries; they cannot establish completed rotations.
        complete = (len(assessors) >= 3 and complete_receipts == len(assessors)
                    and all({a["rotation"] for a in row["quality"]["assessments"]} == {0, 1, 2}
                            for row in rows.values()))
        return {"name": name, "phase": "published", "case": record["case"], "goal_win": record["goal_win"],
                **({"evaluator_protocol": record["evaluator_protocol"]} if "evaluator_protocol" in record else {}),
                "outcomes": outcomes, "control_headroom": control_headroom(rows["control"]),
                "quality_signal": pilot_quality_signal(record),
                "proposal_states": {"candidate/control": rows["control"]["state"], "candidate/develop": rows["develop"]["state"],
                                    "prior/develop": record["prior_develop"]["state"]},
                "assessor_costs": {"coverage": "complete" if complete else "lower bound" if observed else "unknown",
                                   "estimated_usd": sum(observed) if complete else None,
                                   "observed_usd": sum(observed) if observed else None,
                                   "attempts": len(assessors), "complete_receipts": complete_receipts},
                "assessments": len(rows["develop"]["quality"]["assessments"]), "bundle": str(pilot_file(name))}
    reg = read(root / "registration.json")
    case, states = valid_name(reg["case"]), {}
    if reg["name"] != name or sorted(reg["order"]) != [["candidate", "control"], ["candidate", "develop"], ["prior", "develop"]]:
        raise ValueError("invalid pilot allocation")
    for role, arm in reg["order"]:
        folder = STATE / "runs" / f"{name}-{role}" / "attempts" / case / arm
        result = folder / "result.json"
        states[f"{role}/{arm}"] = (read(result)["state"] if result.is_file() else
                                   "allocated" if (folder / "release.json").is_file() else "unreleased")
    judges = STATE / "runs" / f"{name}-candidate" / "judges" / case
    phase = "proposals" if any(s in ("allocated", "unreleased") for s in states.values()) else "assessments"
    if any(root.glob("result-*.json")):
        phase = "sealed"
    return {"name": name, "phase": phase, "case": case, "proposal_states": states,
            **({"evaluator_protocol": reg["evaluator_protocol"]} if "evaluator_protocol" in reg else {}),
            "assessments": sum((judges / str(i) / "judgment.json").is_file() for i in range(3))}


def status(name):
    from records import exhausted_rotation, resolved_ruling
    pilot = STATE / "pilots" / name
    if (pilot / "registration.json").is_file() or pilot_file(name).is_file():
        return pilot_status(name, pilot)
    root = STATE / "runs" / name
    bundle = published(name)
    if bundle:
        return published_summary(name, bundle)[1]
    lease = STATE / "operator.lock"
    owner = {}
    if active(lease):
        try:
            owner = read(lease)
        except json.JSONDecodeError:
            pass  # The owner is writing its name after taking the resource lock.
    if not (root / "plan.json").is_file():
        frozen = [read(path) for role in ("candidate", "prior")
                  if (path := STATE / "runs" / f"{name}-{role}" / "plan.json").is_file()]
        if frozen:
            if any(p.get("pilot", {}).get("name") != name for p in frozen):
                raise ValueError("pilot name conflicts with frozen experiment")
            return {"name": name, "phase": "frozen-unregistered",
                    "frozen_plans": [{"name": p["name"], "evaluator_protocol": p["protocol"],
                                      "case": p["pilot"]["case"]} for p in frozen]}
        return {"name": name, "phase": "preparing" if owner.get("name") == name else "new"}
    running = (any(active(root / (k + ".lock")) for k in ("launcher", "recovery"))
               or (owner.get("name") == name and owner.get("pid") != os.getpid()))
    plan = read(root / "plan.json")
    selection = root / "selected-split.json"
    split = read(selection) if selection.is_file() else {}
    cases = split.get("cases", plan["schedule"])
    arm_states, judges, flags = {}, {}, set()
    for key in cases:
        for arm in plan["order"][key]:
            folder = root / "attempts" / key / arm
            result = folder / "result.json"
            if result.is_file():
                state = read(result)["state"]
            elif folder.exists():
                state = "allocated" if running else "interrupted"
            else:
                state = "unreleased"
            arm_states.setdefault(state, []).append(f"{key}/{arm}")
        rulings = root / "adjudications" / (key + ".json")
        resolved = read(rulings) if rulings.is_file() else {}
        for rot in range(plan["judge_rotations"]):
            folder = root / "judges" / key / str(rot)
            entry = folder / "judgment.json"
            if entry.is_file():
                state = "valid"
                judgment = read(entry)
                mapping = read(STATE / judgment["mapping"]["path"])["labels"]
                for label, row in judgment["scores"]["submissions"].items():
                    role = mapping[label]
                    if row["flags"] and not resolved_ruling(resolved.get(role)):
                        flags.add(f"{key}/{role}")
            elif exhausted_rotation(folder, "recovery" in plan):
                state = "exhausted"
            elif all((folder / str(i)).exists() for i in range(1 if "recovery" in plan else 2)):
                state = "allocated" if running else "stranded"
            elif folder.exists() and any(child.name in {"0", "1"} for child in folder.iterdir()):
                state = "incomplete"
            else:
                state = "unreleased"
            judges.setdefault(state, []).append(f"{key}/{rot}")
    phase = "running" if running else "proposals" if arm_states.get("unreleased") else "assessments"
    if not running and not arm_states.get("unreleased") and not (judges.keys() - {"valid", "exhausted"}):
        phase = "adjudication" if flags else "partial" if judges.get("exhausted") or arm_states.get("interrupted") else "assessed"
    if not running and judges.get("stranded") and not (arm_states.get("unreleased") or judges.get("unreleased") or judges.get("incomplete")):
        phase = "stranded"
    return {"name": name, "phase": phase, "split": split.get("split", "all"), "cases": cases,
            "plan_sha256": hashlib.sha256((root / "plan.json").read_bytes()).hexdigest(),
            "proposal_states": {s:len(v) for s,v in arm_states.items()}, "assessments": {s:len(v) for s,v in judges.items()},
            "allocated": arm_states.get("allocated", []) + arm_states.get("interrupted", []),
            "unreleased": arm_states.get("unreleased", []),
            "pending_assessments": judges.get("unreleased", []) + judges.get("incomplete", []),
            "stranded_assessments": judges.get("stranded", []),
            "unadjudicated": sorted(flags), "bundle": None}


def require_reader():
    from importlib.metadata import PackageNotFoundError, version
    for requirement in (HERE / "requirements.txt").read_text().splitlines():
        dependency, pinned = requirement.split("==")
        try:
            installed = version(dependency)
        except PackageNotFoundError:
            installed = None
        if installed != pinned:
            raise ValueError(f"{requirement} required. Run {sys.executable} -m pip install -r {HERE / 'requirements.txt'}")


def check():
    from records import read_pilot
    require_reader()
    command(TOOLS / "check_layout.py")
    command(PANEL / "test_panel.py")
    subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", HERE / "tests"], check=True)
    command(TOOLS / "records.py", "validate", *panel_results())
    for path in sorted(BUNDLES.with_name("tuning").glob("*/result.json")):
        print(f"{read_pilot(path)['name']}: verified pilot")


def configure_temp():
    if (subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", STATE / "probe"]).returncode or
            subprocess.check_output(["git", "-C", ROOT, "ls-files", "--", STATE])):
        raise ValueError("the task directory must be Git-ignored and untracked")
    scratch = STATE / "volatile"
    scratch.mkdir(parents=True, exist_ok=True)
    for k in ("TMPDIR", "TMP", "TEMP"):
        os.environ[k] = str(scratch)
    os.environ.update(PYTHONDONTWRITEBYTECODE="1", OAIPKG_DISABLE_META_MISSING="1")
    import tempfile
    tempfile.tempdir = str(scratch)


def dispatch(args):
    if args.action == "status":
        print(json.dumps(status(args.name), indent=2))
        return 0
    if args.action == "report":
        registration = STATE / "pilots" / args.name / "registration.json"
        destination = pilot_file(args.name)
        if registration.is_file() or destination.is_file():
            require_reader()
            from records import read_pilot
            if registration.is_file():
                configure_temp()
                from export_panel import export_pilot
                export_pilot(args.name, destination)
            read_pilot(destination)
            print(f"Verified {destination}")
            return 0
    configure_temp()
    if args.action == "preflight":
        import native_panel
        os.environ["PANEL_TREATMENT_LOCK"] = str(args.treatment.resolve(strict=True))
        native_panel.preflight()
        print("Native preflight passed")
        return 0
    if args.action == "compose-treatment":
        sys.path.insert(0, str(PANEL))
        import composite
        base_path = args.develop.resolve(strict=True)
        if base_path.name != "treatment.json" or not base_path.is_relative_to(HERE / "treatments"):
            raise ValueError("select a versioned Develop treatment")
        base = read(base_path)
        if base.get("companion"):
            raise ValueError("select a single-package Develop treatment")
        source = composite.prepare_source(STATE / "cache/superpowers-6.3.0.git", STATE / "volatile")
        lock = dict(base, label=args.label, companion=composite.component_pin(source / "plugins/superpowers"))
        target = HERE / "treatments" / ("composite-" + composite.identity(lock)) / "treatment.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if read(target) != lock:
                raise ValueError("composite identity already exists with different metadata")
        else:
            target.write_text(json.dumps(lock, indent=2) + "\n")
        hypothesis = base_path.with_name("hypothesis.json")
        if hypothesis.is_file():
            destination = target.with_name("hypothesis.json")
            if destination.exists() and destination.read_bytes() != hypothesis.read_bytes():
                raise ValueError("composite hypothesis already exists with different bytes")
            if not destination.exists():
                destination.write_bytes(hypothesis.read_bytes())
        print(target)
        return 0
    if args.action == "capture-treatment":
        from capture_treatment import capture
        return capture(args)
    if args.action in ("restore-treatment", "restore-six"):
        import shutil
        from native_panel import RECIPE, restore_source
        clone = restore_source(RECIPE if args.action == "restore-six" else args.recipe)
        if args.action == "restore-treatment":
            print(f"Verified package checkout: {clone}")
            return 0
        target = clone / PANEL.parent.relative_to(ROOT) / "workflow"
        shutil.copytree(PANEL.parent / "workflow", target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        with (clone / ".git/info/exclude").open("a") as out:
            out.write("\n/tmp/six-repo-workflow/\n")
        print(f"Six-repository checkout: {target}")
        return 0
    if args.action == "check":
        check()
        return 0
    if args.action == "pilot":
        with operator(args.name):
            require_reader()
            import efficiency_pilot
            efficiency_pilot.load_hypothesis(args)
            from cpu_leases import lease
            cpus = sorted(os.sched_getaffinity(0))[:2]
            with lease(STATE, cpus):
                case = efficiency_pilot.E.CASES.get(args.case)
                plans = [efficiency_pilot.C.run_dir(args.name + "-" + role) / "plan.json" for role in ("candidate", "prior")]
                if case and case["split"] == "tuning" and not any(p.is_file() for p in plans):
                    os.sched_setaffinity(0, cpus)
                    os.environ["PANEL_CPUSET"] = ",".join(map(str, cpus))
                    efficiency_pilot.N.setup([case])
                return efficiency_pilot.run(args)
    bundle = published(args.name)
    if bundle:
        manifest, summary = published_summary(args.name, bundle)
        scope = (manifest.get("selection") or {}).get("split", "all")
        if getattr(args, "split", None) not in (None, scope):
            raise ValueError("published selection differs")
        parent = getattr(args, "parent", None)
        if parent:
            parent_bundle = published(parent)
            if not parent_bundle or manifest["parent_plan_sha256"] != read(parent_bundle)["plan_sha256"]:
                raise ValueError("published recovery belongs to a different parent")
        elif args.action == "run" and manifest["cohort"] != "primary":
            raise ValueError("use recover PARENT NAME for a recovery campaign")
        jobs = getattr(args, "jobs", None)
        if jobs is not None and jobs != manifest["runtime"]["executor"]["lanes"]:
            raise ValueError("published concurrency differs")
        print(f"Verified {bundle}")
        return 3 if summary["phase"] == "published-partial" else 0
    with operator(args.name):
        require_reader()
        import native_panel
        if args.action == "report":
            return native_panel.operate(args)
        from cpu_leases import lease
        with lease(STATE, os.sched_getaffinity(0)):
            return native_panel.operate(args)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("check", help="test the environment and validate published records offline")
    restore = sub.add_parser("restore-treatment", help="restore and verify a versioned package without a model call")
    restore.add_argument("recipe", type=Path)
    preflight = sub.add_parser("preflight", help="verify a treatment without model calls")
    preflight.add_argument("--treatment", type=Path, required=True)
    compose = sub.add_parser("compose-treatment", help="pin Develop with official Superpowers")
    compose.add_argument("--develop", type=Path, required=True)
    compose.add_argument("--label", required=True, type=valid_name)
    capture = sub.add_parser("capture-treatment", help="freeze and replay the current Develop package")
    capture.add_argument("--source", type=Path, default=ROOT, help="Git checkout root containing the candidate package")
    capture.add_argument("--previous", type=Path, required=True, help="previous versioned recipe")
    capture.add_argument("--label", required=True, type=valid_name)
    pilot = sub.add_parser("pilot", help="freeze one tuning case, two Develop packages and one pure control")
    pilot.add_argument("name", type=valid_name)
    pilot.add_argument("--case", required=True)
    pilot.add_argument("--hypothesis", help="test a registered tuning or treatment hypothesis with interactive plan review waived")
    pilot.add_argument("--candidate", type=Path, required=True)
    pilot.add_argument("--prior", type=Path, required=True)
    sub.add_parser("restore-six", help="restore the historical package and six-repository runner in a private checkout")
    for action in ("run", "status", "report", "recover"):
        p = sub.add_parser(action)
        if action == "recover":
            p.add_argument("parent", type=valid_name)
        p.add_argument("name", type=valid_name)
        if action == "run":
            p.add_argument("--jobs", type=int, help="two CPUs per lane, default 3")
            p.add_argument("--split", choices=["all", "tuning", "confirmation"])
    try:
        return dispatch(parser.parse_args(argv))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError, ImportError) as exc:
        print(f"Benchmark stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
