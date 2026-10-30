"""Capture a completed native campaign as a portable, verified result bundle."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "develop-benchmark/panel"))
import composite
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import records

SUITE = records.ROOT / "develop-benchmark"
sys.path.insert(0, str(SUITE))
import diff_quality as D
import recover_capacity as recovery

C, R, E = recovery.C, D.R, recovery.E
J = R.J


def computation_hash():
    # The trial chooses its treatment independently. Everything else in the
    # frozen implementation and checks must match for a direct comparison.
    h = hashlib.sha256()
    for folder in (E.HERE, E.WORKFLOW, *((E.COHORT.HERE,) if E.COHORT else ())):
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".md" or path == E.HERE / "treatment.json":
                continue
            h.update(str(path.relative_to(folder.parent)).encode() + b"\0" + bytes.fromhex(E.sha(path)))
    return h.hexdigest()


def meter(row, score):
    actual = R.usage(row)
    for key in ("coverage", "tokens", "usd_estimate"):
        if actual[key] != score[key]:
            raise ValueError("reported token record differs from the sealed attempt")
    meters = row.get("usage", {})
    root = row.get("root")
    children = [v for k,v in meters.items() if k != root]
    child_tokens = ({k: sum(x[k] for x in children) if all(type(x.get(k)) is int for x in children) else None
                     for k in R.TOKENS} if children or actual["coverage"] == "complete" else None)
    return {"coverage": actual["coverage"], "tokens": actual["tokens"], "estimated_usd": actual["usd_estimate"],
        "billed_usd": None, "checkout_to_proposal_seconds": row.get("proposal_wall_seconds"),
        "prompt_to_terminal_seconds": row.get("wall_seconds"), "through_grading_seconds": row.get("end_to_end_seconds"),
        "setup_seconds": row.get("setup_seconds"), "grading_seconds": row.get("grading_seconds"),
        "thread_count": len(meters), "child_count": len(set(row.get("children", []))),
        "root_tokens": meters.get(root), "descendant_tokens": child_tokens,
        "observed_commands": len(row.get("commands", [])), "native_hook_receipts": len(row.get("hooks", []))}


def text_hash(content):
    return records.digest(content.encode()) if content is not None else None


def sealed_artifacts(folder, row):
    sealed = (folder / "submission.json").is_file()
    patch = (folder / "candidate.patch").read_bytes().decode("utf-8") if sealed else None
    proposal = (folder / "proposal.md").read_bytes().decode("utf-8") if sealed else None
    if (text_hash(patch), text_hash(proposal)) != (row.get("patch_sha256"), row.get("proposal_sha256")):
        raise ValueError("sealed submission checksum differs")
    return {"patch": patch, "proposal": proposal}


def judge_bindings(root, key, role, judgments, patch, proposal):
    bindings = []
    for j in judgments:
        path = root / "judges" / key / str(j["rotation"]) / "judgment.json"
        sealed = E.read(path)
        mapping = C.verify_receipt(sealed["mapping"])
        C.verify_receipt(sealed["native"])
        packet = C.verify_receipt(sealed["packet"])
        label = j["label"]
        if mapping["labels"].get(label) != role or sealed["scores"]["submissions"][label] != {
                k:v for k,v in j.items() if k not in ("rotation", "label")}:
            raise ValueError("judge score belongs to a different submission")
        values = mapping["raw_inputs"][role]
        if values != {"patch": text_hash(patch or ""), "proposal": text_hash(proposal or "")}:
            raise ValueError("judge input differs from the exact patch or proposal")
        bindings.append({"rotation": j["rotation"], "label": label, "patch_sha256": values["patch"],
                         "proposal_sha256": values["proposal"], "judgment_sha256": E.sha(path),
                         "mapping_sha256": sealed["mapping"]["sha256"], "assessor_sha256": sealed["native"]["sha256"],
                         "packet_sha256": sealed["packet"]["sha256"], "prompt_sha256": packet["prompt_sha256"]})
    return bindings


def submission(name, case, role, plan_sha, reference):
    key = case["case"]
    root = C.run_dir(name)
    score = case[role]
    grade_entry = score.get("grade_receipt")
    grade = C.verified_grade(grade_entry) if grade_entry else {}
    receipts = {"grade": grade_entry["sha256"]} if grade_entry else {}
    if role == "upstream":
        raw = E.upstream(key)
        patch_file = (E.STATE / reference["admission"]["path"]).parent / "upstream.patch"
        patch = patch_file.read_bytes().decode("utf-8")
        if text_hash(patch) != reference["merged_patch_sha256"]:
            raise ValueError("historical diff differs from the frozen reference")
        proposal = raw["title"] + "\n\n" + raw["body"]
        observation = "present" if raw["body_available"] else "unavailable"
        effort, cause = None, None
    else:
        row = C.read_attempt(name, key, role)
        if row["state"] == "unreleased" or row["state"] != score["state"] or (row["state"] == "interrupted" and C.launcher_active(name)):
            raise ValueError(f"cannot publish a nonterminal or stale {key}/{role} record")
        folder = root / "attempts" / key / role
        for file in ("release", "native", "submission", "result", "inventory", *(("turn-input",) if E.COHORT else ())):
            path = folder / (file + ".json")
            if path.is_file():
                receipts[file] = E.sha(path)
        sealed = "submission" in receipts
        artifacts = sealed_artifacts(folder, row)
        patch, proposal = artifacts["patch"], artifacts["proposal"]
        observation = ("present" if C.complete_proposal(proposal or "") else "incomplete" if proposal
                       else "omitted" if sealed and row["state"] == "completed" else "unavailable")
        effort = meter(row, score)
        cause = ("provider_capacity" if "serverOverloaded" in str(row.get("error")) else row["state"]
                 if row["state"] != "completed" else None)
    if grade and grade.get("patch_sha256") != text_hash(patch):
        raise ValueError("grade does not belong to this patch")
    stages = {k: {field: stage.get(field) for field in ("exit","log_sha256","command","reason")}
              for k,stage in grade.get("stages", {}).items()}
    if score["stages"] != {k: v["exit"] for k,v in stages.items()}:
        raise ValueError("reported stage outcome differs from its frozen grade")
    review = score["review"]
    code = D.diff(score)
    return {"format":"law-config.eval-submission/v1","plan_sha256":plan_sha,"case_id":key,"role":role,
            "state":score["state"],"readiness":score["status"],"executable_pass":score["executable_pass"],
            "failure_kind":cause,"stages":stages,"patch":patch,"patch_sha256":text_hash(patch),
            "proposal":proposal,"proposal_sha256":text_hash(proposal),"proposal_observation":observation,
            "bindings":{"grade_patch_sha256":grade.get("patch_sha256"), "judges":judge_bindings(root,key,role,review["judgments"],patch,proposal)},
            "quality":{"axes":review["axes"],"proposal_points_100":review["score"],"diff_points_85":code["points"],
                       "rotation_points_85":{str(k):v for k,v in code["rotations"].items()},"assessments":review["judgments"]},
            "adjudication":score["adjudication"] or None,"effort":effort,"receipt_sha256":receipts}


def export_pilot(name, destination):
    root = E.STATE / "pilots" / name
    paths = sorted(root.glob("result-*.json"))
    if len(paths) != 1:
        raise ValueError("pilot export requires one sealed result")
    source = E.read(paths[0])
    content = json.dumps(source, sort_keys=True).encode()
    registration = C.receipt(root / "registration.json")
    if (paths[0].stem != "result-" + hashlib.sha256(content).hexdigest()[:12]
            or source["registration"] != registration):
        raise ValueError("pilot result differs from its registration or content hash")
    reg = C.verify_receipt(registration)
    plans = {role: C.verify_receipt(entry) for role, entry in reg["plans"].items()}
    raw, key = source["case"], reg["case"]
    if (reg["name"] != name or raw["case"] != key or raw["split"] != "tuning"
            or source["goal_win"] != R.goal_win(raw)):
        raise ValueError("pilot attribution or strict verdict differs")
    plan = plans["candidate"]
    if reg.get("evaluator_protocol", plan["protocol"]) != plan["protocol"]:
        raise ValueError("pilot evaluator protocol differs from its registration")
    ref = plan["references"][key]
    if plan["protocol"] != E.PANEL["protocol"]:
        raise ValueError(f"frozen protocol {plan['protocol']}; set DEVELOP_EVAL_COHORT={plan['protocol']} and report {name}")
    if (plans["prior"]["references"][key] != ref
            or (ref["base"], ref["gold"]) != (E.CASES[key]["base"], E.CASES[key]["gold"])):
        raise ValueError("pilot plans or selected repository task differ")
    rows = {role: submission(plan["name"], raw, role, reg["plans"]["candidate"]["sha256"], ref)
            for role in ("control", "develop", "upstream")}
    prior = C.read_attempt(plans["prior"]["name"], key, "develop")
    prior_grade = C.verified_grade(prior["grade"]) if prior.get("grade") else {}
    exits = {stage: item["exit"] for stage, item in prior_grade.get("stages", {}).items()}
    if (prior.get("grade") != source["prior"]["grade"] or exits != source["prior"]["exits"]
            or prior["state"] != source["prior"]["state"] or prior.get("proposal_wall_seconds") != source["prior"]["wall_seconds"]
            or (prior_grade and prior_grade.get("patch_sha256") != prior.get("patch_sha256"))):
        raise ValueError("prior Develop evidence differs from the recorded outcome")
    profiles, prompt = {}, None
    for role, arm in reg["order"]:
        folder = C.run_dir(plans[role]["name"]) / "attempts" / key / arm
        if (folder / "prompt.txt").is_file():
            prompt = (folder / "prompt.txt").read_text()
            if text_hash(prompt) != ref["prompt_sha256"]:
                raise ValueError("pilot prompt differs from its frozen reference")
        proof = source["attestations"][role + "/" + arm]
        if proof:
            inv = C.verify_receipt(proof["inventory"])
            turn = C.verify_receipt(proof["input"])
            attempt = C.read_attempt(plans[role]["name"], key, arm)
            if (attempt["thread_start"]["ephemeral"] is not False or turn["threadId"] != attempt["root"]
                    or proof["inventory"] != C.receipt(folder / "inventory.json")
                    or proof["input"] != C.receipt(folder / "turn-input.json")):
                raise ValueError("pilot thread mode, input or inventory differs from the stored-profile release")
            proof = {**proof["final_stock"], "plugins": inv["plugins"], "ephemeral": attempt["thread_start"]["ephemeral"],
                     "inventory_sha256": proof["inventory"]["sha256"], "input_sha256": proof["input"]["sha256"],
                     "config_sha256": proof["final_config_sha256"]}
        profiles[role + "/" + arm] = proof
    record = {"format": "law-config.eval-pilot/v1", "name": name, "case": key, "repository": raw["repo"], "pr": raw["pr"],
              **({"evaluator_protocol": reg["evaluator_protocol"]} if "evaluator_protocol" in reg else {}),
              "registration": reg, "registration_sha256": registration["sha256"], "result_sha256": E.sha(paths[0]),
              "treatments": {k: composite.identity(v["runtime"]["treatment"]) for k, v in plans.items()},
              **({"treatment_components": {k: v["runtime"]["treatment"] for k,v in plans.items()}} if any(v["runtime"]["treatment"].get("companion") for v in plans.values()) else {}),
              "base": ref["base"], "merged": ref["gold"], "prompt": prompt, "prompt_sha256": ref["prompt_sha256"],
              "runtime_sha256": plan["runtime"]["source_sha256"], "rubric_sha256": plan["rubric_sha256"],
              "model": E.PANEL["model"], "effort": E.PANEL["effort"], "rates": plan["cost_usd_per_million"],
              "profiles": profiles, "comparisons": raw["pairs"], "goal_win": source["goal_win"], "submissions": rows,
              "route_review": source["route_review"],
              "prior_develop": {"state": prior["state"], "effort": meter(prior, source["prior"]), "stage_exits": exits,
                                "patch_sha256": prior.get("patch_sha256"), "proposal_sha256": prior.get("proposal_sha256"),
                                "full_pr_score": None}, "assessor_costs": raw["evaluator_cost"], "observations": observations(root)}
    records.observation_receipts(record["observations"], pilot_registration=registration["sha256"])
    prior_folder = C.run_dir(plans["prior"]["name"]) / "attempts" / key / "develop"
    artifacts = sealed_artifacts(prior_folder, prior)
    exports = [(destination, record)]
    if destination.is_file() and "patch" not in E.read(destination)["prior_develop"]:
        exports.append((destination.with_name("prior.json"), artifacts))
    else:
        record["prior_develop"].update(artifacts)
    if any(str(Path.home()) + "/" in json.dumps(data) for _, data in exports):
        raise ValueError("pilot export includes a private host path")
    for path, data in exports:
        try:
            E.save(path, data)
        except FileExistsError:
            if E.read(path) != data:
                raise ValueError(f"a different pilot record already exists at {path.name}") from None
    return record


def portable_case(raw, case, ref, plan, layout):
    key = case["id"]
    lane = next(i for i,keys in enumerate(layout["queues"]) if key in keys)
    adm = C.verify_receipt(ref["admission"])
    for rotation in range(plan["judge_rotations"]):
        folder = C.run_dir(plan["name"]) / "judges" / key / str(rotation)
        if not (folder / "judgment.json").is_file() and not records.exhausted_rotation(folder, "recovery" in plan):
            raise ValueError(f"unfinished assessor: {key} rotation {rotation}")
    attempts = []
    totals = []
    for path in sorted((C.run_dir(plan["name"]) / "judges" / key).glob("*/*/native.json")):
        native = E.read(path)
        usage = R.usage(native)
        checksum = E.sha(path)
        judgment = path.parent.parent / "judgment.json"
        seal = E.read(judgment) if judgment.is_file() else None
        accepted = seal is not None and seal["native"]["sha256"] == checksum
        attempts.append(dict(usage, rotation=int(path.parent.parent.name), attempt=int(path.parent.name),
                             native_sha256=checksum, accepted=accepted, state=native["state"],
                             wall_seconds=native.get("wall_seconds"),
                             limitations=seal["scores"]["limitations"] if accepted else []))
        totals.append(json.dumps(usage,sort_keys=True))
    if Counter(totals) != Counter(json.dumps(u,sort_keys=True) for u in raw["evaluator_cost"]):
        raise ValueError(f"{key} assessor usage differs from the native report")
    controls = {"fixture_sha256":adm["fingerprint"],"prompt_sha256":ref["prompt_sha256"],
                "merged_patch_sha256":ref["merged_patch_sha256"],"dependencies_sha256":ref["deps_sha256"],
                "workers":ref["workers"],"deadline_seconds":ref["deadline_seconds"],"arm_order":plan["order"][key],
                "cpu_pair":layout["cpu_pairs"][lane],"build":case["build"],"worker_native":E.guest.native_tests(case),
                "grader_native":case["native"],"independent_check":bool(case.get("independent"))}
    comparisons = dict(raw["pairs"], diff_85={a+"_"+b:D.compare(raw,a,b) for a,b in R.PAIRS})
    if E.COHORT:
        from efficiency_pilot import check_input
        profiles = {}
        for role in ("control", "develop"):
            attempt, proof = check_input(plan["name"], key, role)
            profiles[role] = None if proof is None else {
                **proof["final_stock"], "plugins":E.read(E.STATE / proof["inventory"]["path"])["plugins"],
                "inventory_sha256":proof["inventory"]["sha256"], "turn_sha256":proof["input"]["sha256"],
                "config_sha256":proof["final_config_sha256"], "ephemeral":attempt["thread_start"]["ephemeral"]}
        comparisons["confirmation"] = {"profiles":profiles, "win":all(profiles.values()) and R.goal_win(raw)}
    return {"id":key,"repo":case["repo"],"pr":case["pr"],"base":case["base"],"merged":case["gold"],
            "split":case["split"],"stratum":case["stratum"],"language":case["language"],"domain":case["domain"],
            "complexity":case.get("complexity"),"prompt":case["prompt"],"first_commit":case["first_commit"],
            "authorship":case["authorship"],"base_files":case["base_files"],"base_bytes":case["base_bytes"],
            "pr_delta":case["delta"],"pr_open_to_merge_seconds":raw["pr_open_to_merge_seconds"],"controls":controls,
            "comparison":comparisons,
            "judge_attempts":attempts}


def selection(root, plan, declare=None):
    path = root / "selected-split.json"
    if declare is None and not path.exists():
        return None
    if declare is not None:
        if "recovery" in plan or path.exists() or any((root / d).exists() for d in ("attempts", "judges")):
            raise ValueError("declare the split once on an unused primary plan")
        cases = [key for key in plan["schedule"] if plan["references"][key]["split"] == declare]
        if not cases:
            raise ValueError("the frozen split is empty")
        E.save(path, {"split": declare, "cases": cases, "plan_sha256": E.sha(root / "plan.json"), "declared_unix": time.time()})
    declared = E.read(path)
    expected = [key for key in plan["schedule"] if plan["references"][key]["split"] == declared["split"]]
    if (expected != declared["cases"] or declared["plan_sha256"] != E.sha(root / "plan.json")
            or not expected or "recovery" in plan):
        raise ValueError("declared scope differs from the frozen split")
    for dirname in ("attempts", "judges"):
        if any(p.name not in expected for p in (root / dirname).glob("*")):
            raise ValueError("a release outside the declared split must be reported separately")
    for path_release in (root / "attempts").glob("*/*/release.json"):
        if E.read(path_release)["allocated_unix"] < declared["declared_unix"]:
            raise ValueError("split was declared after proposal release")
    return dict(declared, sha256=E.sha(path))


def export(name, destination):
    root = C.run_dir(name)
    plan = C.plan_for(name)
    plan_sha = E.sha(root / "plan.json")
    result = E.read(root / "report/results.json")
    if result["plan_sha256"] != plan_sha or plan["runtime"]["source_sha256"] != E.version_digest():
        raise ValueError("export requires the exact frozen source and report")
    if set(plan["schedule"]) != {r["case"] for r in result["cases"]}:
        raise ValueError("result report does not cover the frozen cohort")
    scope = selection(root, plan)
    if scope:
        selected = [r for r in result["cases"] if r["case"] in scope["cases"]]
        for group in result["groups"]:
            result["groups"][group] = R.group([r for r in selected if group == "all" or group in (r["split"], r["stratum"])])
        result["cases"] = selected
    layout = E.read(root / "lanes.json")
    qual = C.verify_receipt(plan["qualification"])
    rows, cases = [], []
    for raw in result["cases"]:
        key = raw["case"]
        ref = plan["references"][key]
        cases.append(portable_case(raw,E.CASES[key],ref,plan,layout))
        for role in R.ROLES:
            rows.append(submission(name,raw,role,plan_sha,ref))
    per_role = {(r["case_id"], r["role"]): r for r in rows}
    for group, summary in result["groups"].items():
        ids = [c["id"] for c in cases if group == "all" or group in (c["split"], c["stratum"])]
        summary["code_and_tokens"] = records.code_and_tokens(ids, per_role)
    blob = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",",":")) + "\n" for r in rows).encode()
    parent = plan.get("recovery", {}).get("parent_plan")
    snapshot = ((E.STATE / parent["path"]).parent if parent else root) / "source-snapshot/manifest.json"
    recipe = records.ROOT / "treatments" / plan["runtime"]["package_sha256"][:12] / "recipe.json"
    source = {"original_git_base":None, "treatment_recipe":str(recipe.relative_to(records.ROOT)) if recipe.is_file() else None}
    if snapshot.is_file():
        provenance = E.read(snapshot)
        if provenance["runtime"] != plan["runtime"]: raise ValueError("snapshot has different runtime")
        source.update(original_git_base=provenance["git_base"],source_archive_sha256=provenance["archive_sha256"])
    controller_receipt = root / "recovery-controller.json"
    if controller_receipt.is_file():
        controller = E.read(controller_receipt)
        if (not parent or controller["plan_sha256"] != plan_sha
                or text_hash(controller["source"]) != controller["sha256"]):
            raise ValueError("recovery controller differs from its recorded source or plan")
        source["recovery_controller"] = controller
    runtime = plan["runtime"]
    evaluator = result["evaluator"]
    record = {"format":"law-config.eval-run/v1","protocol":plan["protocol"],"name":name,"plan_sha256":plan_sha,
              "cohort":"capacity-recovery" if parent else "primary","parent_plan_sha256":parent["sha256"] if parent else None,
              "selection":scope,"frozen_unix":plan["frozen_unix"],"runtime":{"source_sha256":runtime["source_sha256"],
                  "implementation_sha256":computation_hash(),"package_sha256":runtime["package_sha256"],
                  "cli_sha256":runtime["cli"],"bwrap_sha256":runtime["bwrap"],"treatment":runtime["treatment"],
                  "model":E.PANEL["model"],"effort":E.PANEL["effort"],"seed":plan["seed"],"rubric_sha256":plan["rubric_sha256"],
                  "rates_usd_per_million":plan["cost_usd_per_million"],"qualifier":plan["qualification"]["sha256"],
                  "executor":{"cpus_per_worker":E.PANEL["cpus"],"memory":E.PANEL["memory"],"lanes":layout["jobs"],
                              "boundary":qual["execution_boundary"],"managed_hooks":E.read(E.HERE/"platform.json"),
                              "judge":{"model":E.PANEL["model"],"effort":E.PANEL["effort"],"rotations":plan["judge_rotations"],
                                       "entrypoint_sha256":E.sha(E.HERE/"judge.py"),"max_attempts_per_rotation":1 if parent else 2}}},
              "cases":cases,"groups":result["groups"],"evaluator":evaluator,
              "campaign_elapsed_seconds":result.get("campaign_elapsed_through_last_measurement_seconds"),
              "submission_span_seconds":result.get("campaign_submission_span_seconds"),
              "observations":observations(root),"submissions":{"path":"submissions.jsonl","rows":len(rows),"sha256":records.digest(blob)},
              "source":source}
    for case in cases:
        if "confirmation" in case["comparison"]:
            case["comparison"]["confirmation"]["strict_quality_win"] = records.confirmation_quality(
                case, per_role, runtime["treatment"], record["runtime"])
    policy = root / "operator-recovery.json"
    if policy.is_file():
        rule = E.read(policy)
        if not parent or rule["plan_sha256"] != plan_sha or rule["on_block"] != "pause":
            raise ValueError("unbound recovery release policy")
        record["runtime"]["executor"]["recovery_release_policy"] = {
            "on_block":rule["on_block"], "prior_releases":rule["prior_releases"]}
    target = destination / plan["protocol"] / (name + "-" + plan_sha[:12])
    output = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    staged = Path(tempfile.mkdtemp(prefix="portable-panel-",dir=E.STATE/"volatile"))
    (staged / "run.json").write_bytes(output)
    (staged / "submissions.jsonl").write_bytes(blob)
    records.read_bundle(staged / "run.json")
    if target.exists():
        if (target/"run.json").read_bytes() != output or (target/"submissions.jsonl").read_bytes() != blob:
            raise ValueError("published run differs; create a versioned correction")
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        staged.rename(target)
    return target


def observations(root):
    results = []
    for path in sorted((root / "sensitivity").glob("*/receipt.json")):
        evidence = E.read(path)
        entry = {"id":path.parent.name,"kind":"post_freeze_probe","primary_scores_changed":False,
                 "receipt_sha256":E.sha(path),"evidence":evidence}
        check = path.parent / "alternative/calibration.json"
        if check.exists():
            entry["alternate_calibration"] = E.read(check)
            fix = path.parent / "alternative/logical-ledger-entries.patch"
            entry["proposed_checker_patch"] = fix.read_text()
        source_name = evidence.get("probe_file", "probe.py")
        if Path(source_name).name != source_name:
            raise ValueError("post-freeze probe must be in its evidence directory")
        probe = path.parent / source_name
        if probe.exists():
            if E.sha(probe) != evidence["probe_sha256"]:
                raise ValueError("post-freeze probe content differs")
            entry["probe"] = probe.read_text()
        results.append(entry)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("name")
    p.add_argument("--declare-split",choices=("tuning","confirmation"),
                   help="seal the case list immediately after freeze and before releasing a model")
    p.add_argument("--destination",type=Path,default=records.ROOT / "runs")
    args = p.parse_args()
    C.controller.activate()
    if args.declare_split:
        print(json.dumps(selection(C.run_dir(args.name), C.plan_for(args.name), args.declare_split), indent=2))
    else:
        print(export(args.name,args.destination))
