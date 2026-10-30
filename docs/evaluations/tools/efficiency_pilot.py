"""Freeze and run one matched tuning case against pure Codex and the previous package."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "develop-benchmark/panel"))
import composite
import hashlib
import json
import os
import random
import time
import tomllib

import native_panel as N
import results
import stock

B, C, E = N.B, N.C, N.E


def set_treatment(env):
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    C.controller.activate()


def source_for(lock):
    path = lock.resolve(strict=True)
    if path.name != "treatment.json" or path.parent.parent != B.HERE / "treatments":
        raise ValueError("use a versioned treatment lock")
    os.environ.pop("PANEL_PLUGIN_CHECKOUT", None)
    os.environ["PANEL_TREATMENT_LOCK"] = str(path)
    N.preflight()
    return {k: os.environ.get(k) for k in ("PANEL_TREATMENT_LOCK", "PANEL_PLUGIN_CHECKOUT", "PANEL_COMPANION_SOURCE")}


def freeze(args, treatment, role):
    set_treatment(treatment)
    name = B.valid_name(args.name + "-" + role)
    dest = C.run_dir(name) / "plan.json"
    spec = {"name": args.name, "case": args.case, "role": role}
    if dest.exists():
        plan = C.plan_for(name)
    else:
        try:
            plan = C.freeze(name, pilot=spec)
        except ValueError as exc:
            if str(exc).startswith("no qualifying qualification.json") and C.controller.qualification():
                plan = C.freeze(name, pilot=spec)
            else:
                raise
    if plan.get("pilot") != spec:
        raise ValueError("run name already belongs to another protocol")
    return plan, C.receipt(dest)


def registration(args, plans, receipts, cpus):
    candidate, prior = plans["candidate"], plans["prior"]
    for field in ("seed", "references", "rubric_sha256", "cost_usd_per_million", "judge_rotations"):
        if candidate[field] != prior[field]:
            raise ValueError("unmatched pilot plans: " + field)
    for field in ("source_sha256", "cli", "bwrap"):
        if candidate["runtime"][field] != prior["runtime"][field]:
            raise ValueError("unmatched pilot runtime: " + field)
    if composite.component_set(candidate["runtime"]["treatment"]) == composite.component_set(prior["runtime"]["treatment"]):
        raise ValueError("prior and candidate are the same package")
    order = [["candidate", arm] for arm in candidate["order"][args.case]]
    rng = random.Random(f"{candidate['seed']}.{args.case}.prior")
    order.insert(rng.randrange(3), ["prior", "develop"])
    spec = getattr(args, "experiment", {})
    return {"protocol": "develop-efficiency-pilot-v1", "name": args.name, "case": args.case, "plans": receipts,
            "operator_sha256": E.sha(Path(__file__)), "cpus": cpus, "order": order,
            "hypothesis": spec.get("id", "reuse-intent-review-on-stable-scope"),
            "tuning_policy_sha256": E.sha(B.BUNDLES / "tuning.json"),
            **({"hypothesis_sha256": args.hypothesis_sha256} if hasattr(args, "hypothesis_sha256") else {}),
            "falsifier": (spec["falsifier"] + " " if spec else "") + "Reject lost prior verified behavior or required review, failure of either strict prior cost or wall improvement, non-ready candidate, or full-PR loss to pure. Missing measures or unverifiable review leave the comparison unestablished.",
            "quality": "Three blind candidate/pure/merge rotations. Prior Develop soft PR quality is unknown.",
            "goal": "A ready Develop PR strictly wins the full rubric against a terminal pure proposal at complete cost <= pure.",
            "attempts": "One proposal per registered slot. All allocations including technical failures remain in the ledger."}


def check_input(name, key, arm):
    parent = C.run_dir(name) / "attempts" / key / arm
    row = C.read_attempt(name, key, arm)
    if row["state"] != "completed":
        return row, None
    inv = E.read(parent / "inventory.json")
    turn = E.read(parent / "turn-input.json")
    prompt = C.prompt(E.CASES[key])
    role = arm == "develop"
    inputs = turn["input"]
    if (turn["threadId"] != row["root"] or turn["effort"] != E.PANEL["effort"]
            or len(inputs) != 1 + role or inputs[0] != {"type": "text", "text": ("$develop:develop " if role else "") + prompt}
            or (role and (inputs[1].get("type"), inputs[1].get("name")) != ("skill", E.host.SKILL))
            or inv["plugins"] != composite.expected_plugins("develop" if role else "control", E.host.COMPANION) or inv["stock"]["apps"] or inv["stock"]["mcp"]
            ):
        raise ValueError("release no longer matches its stock inventory or paired model input")
    # Trust and the repository configuration can change independently of the
    # authored profile. Check the effective native inventory on every replay.
    home = parent / "profile"
    work = Path(row["thread_start"]["cwd"])
    with (home / "config.toml").open("rb") as source:
        config = tomllib.load(source)
    disabled = [Path(x["path"]) for x in config.get("skills", {}).get("config", [])]
    if (any(not p.is_relative_to(work) for p in disabled) or
            sorted(p.parent.name for p in disabled) != sorted(inv["disabled_repository_skills"])):
        raise ValueError("disabled repository skills differ from pre-release discovery")
    server = C.controller.STOCK(Path(os.environ["BENCHMARK_CODEX"]), home, work, time.monotonic() + 90)
    try:
        installed = Path(inputs[1]["path"]).parents[2] if role else None
        server.inventory(installed)
        listed = server.rpc("skills/list", {"cwds": [str(work)]})["data"]
        skills = [s for group in listed for s in group["skills"] if s["enabled"]]
        terminal = stock.inventory(server, installed, skills, disabled)
        if (sorted(s["name"] for s in skills) != sorted(inv["skills"]) or
                terminal["repository_instructions_sha256"] != inv["stock"]["repository_instructions_sha256"]):
            raise ValueError("final skill catalog or repository instructions differ from release")
        plugins = server.rpc("plugin/list", {"cwds": [str(work)], "marketplaceKinds": ["local"]})
        active = sorted(p["id"] for m in plugins["marketplaces"] for p in m["plugins"] if p["installed"] and p["enabled"])
        if active != inv["plugins"]:
            raise ValueError("active plugins changed after release")
    finally:
        server.close()
    C.controller.verify_hooks(parent, row, arm)
    return row, {"input": C.receipt(parent / "turn-input.json"), "inventory": C.receipt(parent / "inventory.json"),
                 "final_config_sha256": E.sha(home / "config.toml"), "final_stock": terminal}



def run(args):
    if args.case not in E.CASES or E.CASES[args.case]["split"] != "tuning":
        raise ValueError("select a preregistered tuning case")
    if getattr(args, "hypothesis", None):
        policy = {e["id"]: e for e in E.read(B.BUNDLES / "tuning.json")["experiments"]}
        if args.hypothesis in policy:
            args.experiment = policy[args.hypothesis]
        else:
            data = args.candidate.with_name("hypothesis.json").read_bytes()
            args.experiment = json.loads(data)
            if (args.experiment["id"] != args.hypothesis
                    or args.experiment["previous"] != E.read(args.prior)["package_sha256"]):
                raise ValueError("hypothesis does not match the selected treatments")
            args.hypothesis_sha256 = hashlib.sha256(data).hexdigest()
        if args.case not in {row["case"] for row in args.experiment["evidence"]}:
            raise ValueError("case is outside this hypothesis’s registered tuning evidence")
        sys.path.insert(0, str(B.PANEL.parent))
        from confirmation.cohort import AUTHORITY
        C.PROMPT = C.PROMPT.replace("Design and unattended implementation are approved.", AUTHORITY)
    composite.validate_common_component(getattr(args, "experiment", {}), E.read(args.prior), E.read(args.candidate))
    B.valid_name(args.name + "-candidate")
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise ValueError("the pilot needs two available CPUs")
    os.sched_setaffinity(0, cpus)
    os.environ["PANEL_CPUSET"] = ",".join(map(str, cpus))
    sources = {role: source_for(lock) for role, lock in (("prior", args.prior), ("candidate", args.candidate))}
    plans, receipts = {}, {}
    for role, source in sources.items():
        plans[role], receipts[role] = freeze(args, source, role)
    cfg = registration(args, plans, receipts, cpus)
    root = E.STATE / "pilots" / args.name
    path = root / "registration.json"
    if path.exists():
        if E.read(path) != cfg:
            raise ValueError("registration changed; preserve this attempt and use a new name")
    else:
        E.save(path, cfg)
    print("Registered", args.name, E.sha(path), cfg["order"], flush=True)
    attestations = {}
    for role, arm in cfg["order"]:
        set_treatment(sources[role])
        name = plans[role]["name"]
        row = C.read_attempt(name, args.case, arm)
        if row["state"] == "unreleased":
            print("Releasing", role, arm, flush=True)
            C.attempt(name, args.case, arm)
        row, attestation = check_input(name, args.case, arm)
        attestations[f"{role}/{arm}"] = attestation
        if row["state"] in {"blocked", "interrupted"}:
            # Qualify the service before releasing later allocated slots on resume.
            marker = root / f"service-{role}-{arm}.json"
            if not marker.exists():
                if not C.controller.qualification():
                    print("Capacity qualification failed; resume this name.", flush=True)
                    return 3
                E.save(marker, {"passed": True, "plan": receipts[role]})

    set_treatment(sources["candidate"])
    name = plans["candidate"]["name"]
    B.command(E.HERE / "judge.py", name, "--case", args.case, "--jobs", 3, allow_partial=True)
    case = results.case_row(name, E.CASES[args.case])
    set_treatment(sources["prior"])
    prior, _ = check_input(plans["prior"]["name"], args.case, "develop")
    measurements = results.usage(prior)
    prior_grade = C.verified_grade(prior["grade"]) if prior.get("grade") else {}
    output = {"registration": C.receipt(path), "case": case, "goal_win": results.goal_win(case),
              "attestations": attestations, "prior": {**measurements, "state": prior["state"],
              "wall_seconds": prior.get("proposal_wall_seconds"), "grade": prior.get("grade"),
              "exits": {k: v["exit"] for k, v in prior_grade.get("stages", {}).items()},
              "soft_pr_quality": None}, "route_review": "Requires inspection of the recorded independent review events."}
    encoded = json.dumps(output, sort_keys=True).encode()
    output_path = root / ("result-" + hashlib.sha256(encoded).hexdigest()[:12] + ".json")
    if not output_path.exists():
        E.save(output_path, output)
    print(output_path, "strict win:", output["goal_win"], flush=True)
    return 0 if all(a is not None for a in attestations.values()) and len(case["assessors"]) == 3 else 3
