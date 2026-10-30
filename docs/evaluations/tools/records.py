"""Read, validate and compare portable benchmark records without Docker or a model."""
import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "develop-benchmark/panel"))
import composite

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("control", "develop", "upstream")
CODE_WEIGHTS = {"contract": 35, "tests": 25, "design": 25}
MINIMUM_PR_LEAD = 5
STATUS = ("ready", "failed", "pending", "unavailable")
# SHA-256 of the sorted, newline-separated public historical repository identities.
TARGET_REPOSITORIES_SHA256 = "7a8bef9ec30fb7ba617a7bc91f30825d776036b753a14b9b05e26d7dbea586de"
# Frozen native policy for the new strict confirmation claim, not legacy reading.
CONFIRMATION_MODEL = {"model": "gpt-6.1-sol", "effort": "medium"}
CONFIRMATION_RATES = {"uncached_input": 2, "cached_input": 0.1, "output": 10}
CONFIRMATION_NATIVE = {
    "cli_sha256": "c1eecb4b2304cb0e077a673231e30c9d759dec8fea4a6b8818078865e392fa90",
    "bwrap_sha256": "77360cb751ccedc5971391444ac86a8a33c15b04d6b4a6fe45f5d25496e62c4c",
}


def interval(samples, statistic):
    if len(samples) < 2:
        return None
    rng = random.Random(20261028)
    draws = sorted(statistic(rng.choices(samples, k=len(samples))) for _ in range(5000))
    return [draws[125], draws[4874]]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject(value):
        raise ValueError("invalid JSON number " + value)
    return json.loads(text, object_pairs_hook=unique, parse_constant=reject)


def resolved_ruling(value):
    return (isinstance(value, dict) and value.get("resolution") in ("confirmed", "cleared")
            and isinstance(value.get("evidence"), str) and bool(value["evidence"].strip()))


def terminal_assessment(native):
    if not isinstance(native, dict):
        return False
    times = [native.get(k) for k in ("assessment_started_unix", "assessment_finished_unix")]
    return (native.get("state") in ("completed", "blocked", "timeout")
            and all(type(t) in (float, int) and math.isfinite(t) for t in times)
            and 0 < times[0] <= times[1])


def invalid_assessment(trial):
    marker = trial / "invalid.json"
    native = trial / "native.json"
    if not marker.is_file() or not native.is_file():
        return False
    reason, outcome = read_json(marker.read_bytes()), read_json(native.read_bytes())
    return (isinstance(reason, dict) and terminal_assessment(outcome) and reason.get("state") == outcome["state"]
            and isinstance(reason.get("error"), str) and bool(reason["error"].strip()))


def exhausted_rotation(folder, recovery):
    if not invalid_assessment(folder / "0"):
        return False
    if not recovery:
        return invalid_assessment(folder / "1")
    limit = folder / "1/call-limit.json"
    return limit.is_file() and read_json(limit.read_bytes()) == {
        "released": False, "reason": "one assessor call per rotation"}


def code_points(axes):
    if any(axes[axis] is None for axis in CODE_WEIGHTS):
        return None
    return sum(weight * axes[axis] / 4 for axis, weight in CODE_WEIGHTS.items())


def proposal_points(anchors):
    if any(v is None for v in anchors.values()):
        return None
    return code_points(anchors) + 15 * anchors["proposal"] / 4


def proposal_verdict(left, right, required_rotations=2):
    roles = [left["role"], right["role"]]
    statuses = [left["readiness"], right["readiness"]]
    if any(s in ("unavailable", "pending") for s in statuses):
        return {"verdict":"unresolved", "reason":"missing or disputed evidence"}
    if statuses != ["ready", "ready"]:
        return {"verdict":roles[statuses.index("ready")] if "ready" in statuses else "both failed", "reason":"hard gates"}
    return blinded_proposal_verdict(left, right, required_rotations)


def blinded_proposal_verdict(left, right, required_rotations):
    roles = [left["role"], right["role"]]
    if any(row["quality"]["proposal_points_100"] is None for row in (left, right)):
        return {"verdict":"unresolved", "reason":"missing scores"}
    def scores(row):
        return {j["rotation"]: proposal_points(j["scores"]) for j in row["quality"]["assessments"]}
    a, b = scores(left), scores(right)
    deltas = [a[i] - b[i] for i in sorted(a.keys() & b.keys()) if a[i] is not None and b[i] is not None]
    if len(deltas) < required_rotations:
        return {"verdict":"unresolved", "reason":"missing paired rotations"}
    votes = [roles[0] if d > 0 else roles[1] if d < 0 else "tie" for d in deltas]
    median = statistics.median(deltas)
    direction = roles[0] if median >= MINIMUM_PR_LEAD else roles[1] if median <= -MINIMUM_PR_LEAD else "tie"
    support = sum(abs(d) < MINIMUM_PR_LEAD for d in deltas) if direction == "tie" else votes.count(direction)
    return {"verdict":direction if support >= 2 else "unresolved", "reason":"blinded rubric",
            "score_delta":median, "votes":votes, "order_sensitive":len(set(votes)) > 1}


def strict_win(pure, develop, verdict, seats):
    return (set(seats) == {0, 1, 2} and develop["readiness"] == "ready" and verdict == "develop"
            and all(r["state"] == "completed" and r["proposal"] and r["effort"]["coverage"] == "complete"
                    for r in (pure, develop))
            and develop["effort"]["estimated_usd"] <= pure["effort"]["estimated_usd"])


def pilot_quality_signal(record):
    """Report the blind PR comparison independently of the frozen readiness-first verdict."""
    develop, control = (record["submissions"][role] for role in ("develop", "control"))
    arms = (develop, control)
    if any(not row["proposal"] for row in arms):
        blind = {"verdict": None, "reason": "missing proposal"}
    elif any({j["rotation"] for j in row["quality"]["assessments"]} != {0, 1, 2} for row in arms):
        blind = {"verdict": None, "reason": "missing paired rotations"}
    else:
        blind = blinded_proposal_verdict(develop, control, 3)
        if blind["reason"] != "blinded rubric":
            blind["verdict"] = None

    at_or_below = None
    if all(row["effort"]["coverage"] == "complete" for row in arms):
        at_or_below = develop["effort"]["estimated_usd"] <= control["effort"]["estimated_usd"]
    joint = None
    if (at_or_below is not None and blind["verdict"] in ("develop", "control", "tie")
            and all(row["state"] == "completed" for row in arms)
            and develop["readiness"] in ("ready", "failed")):
        joint = develop["readiness"] == "ready" and blind["verdict"] == "develop" and at_or_below
    return {"readiness_first_pair": record["comparisons"]["develop_control"], "blinded_full_pr": blind,
            "equal_or_lower_complete_cost": at_or_below, "ready_blind_win_at_no_more_cost": joint}


def _confirmation_profile(row, profile, treatment):
    receipts = row.get("receipt_sha256", {})
    return bool(profile and profile.get("ephemeral") is False
        and profile.get("plugins") == composite.expected_plugins(row["role"], (treatment or {}).get("companion"))
        and all(profile.get(k) == [] for k in ("apps", "mcp", "global_instructions"))
        and receipts.get("inventory") and receipts.get("turn-input")
        and profile.get("inventory_sha256") == receipts["inventory"]
        and profile.get("turn_sha256") == receipts["turn-input"])


def _confirmation_runtime(runtime, treatment):
    if not isinstance(runtime, dict) or any(runtime.get(k) != v for k, v in (CONFIRMATION_MODEL | CONFIRMATION_NATIVE).items()):
        return False
    if runtime.get("rates_usd_per_million") != CONFIRMATION_RATES:
        return False
    lock = runtime.get("treatment")
    judge = runtime.get("executor", {}).get("judge", {})
    if not isinstance(lock, dict):
        return False
    hooks = lock.get("hook_sha256")
    if not isinstance(hooks, dict) or set(hooks) != {"pre_tool_use", "post_tool_use"}:
        return False
    hashes = [lock.get("plugin_hook_sha256"), *hooks.values()]
    if any(not isinstance(h, str) or len(h) != 64 or set(h) - set("0123456789abcdef") for h in hashes):
        return False
    companion = lock.get("companion")
    if "companion" in lock and (not isinstance(companion, dict) or companion.get("source_commit") != composite.COMMIT
                      or companion.get("package_sha256") != composite.PACKAGE_SHA256):
        return False
    return bool(lock and lock.get("package_sha256") == runtime.get("package_sha256")
        and lock.get("package_sha256") and (treatment is None or treatment == lock)
        and all(judge.get(k) == v for k, v in CONFIRMATION_MODEL.items()))


def confirmation_quality(case, rows, treatment=None, runtime=None):
    """Strict blind-quality goal, independent of the historical readiness-first win."""
    decision = case["comparison"].get("confirmation")
    if not _confirmation_runtime(runtime, treatment):
        return None
    treatment = runtime["treatment"]
    if not decision or any(rows.get((case["id"], role)) is None for role in ROLES):
        return None
    pair = {role: rows[case["id"], role] for role in ("control", "develop")}
    if any(not _confirmation_profile(row, decision.get("profiles", {}).get(role), treatment)
           for role, row in pair.items()):
        return None
    return pilot_quality_signal({"submissions": pair, "comparisons": case["comparison"]})[
        "ready_blind_win_at_no_more_cost"]


def target_repositories():
    # Keep historical reading usable if the optional public roster is unavailable.
    try:
        cases = read_json((ROOT / "develop-benchmark/panel/panel.json").read_bytes())["cases"]
        names = [case["repo"] for case in cases]
        if len(names) != 20 or len(set(names)) != 20 or any(not isinstance(name, str) for name in names):
            return None
        if digest("\n".join(sorted(names)).encode()) != TARGET_REPOSITORIES_SHA256:
            return None
        return set(names)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def confirmation_quality_summary(cases, rows, treatment=None, runtime=None):
    def all_won(values):
        if False in values:
            return False
        return True if values and None not in values else None

    selected = [rows.get((case["id"], role)) for case in cases for role in ROLES]
    plans = {row.get("plan_sha256") for row in selected if row}
    one_plan = len(plans) == 1 and None not in plans
    values = [confirmation_quality(case, rows, treatment, runtime) if one_plan else None for case in cases]
    repos = [case.get("repo") for case in cases]
    roster = target_repositories()
    target = [value for repo, value in zip(repos, values) if roster is not None and repo in roster]
    complete = (roster is not None and len(repos) == 20 and set(repos) == roster
                and len({case["id"] for case in cases}) == 20)
    all_20 = all_won(target) if complete or False in target else None
    return {"cases": len(values), "wins": values.count(True), "losses": values.count(False),
            "unknown": values.count(None), "every_observed_case": all_won(values),
            "all_20_repositories": all_20}


def control_headroom(row):
    votes = {j["rotation"]: proposal_points(j["scores"]) for j in row["quality"]["assessments"]}
    scores = [votes.get(i) for i in range(3)]
    gain = 100 - statistics.median(scores) if None not in scores else None
    complete = row["state"] == "completed" and bool(row["proposal"]) and row["effort"]["coverage"] == "complete"
    route = "unresolved"
    if complete and set(votes) == {0, 1, 2}:
        if row["readiness"] == "failed":
            route = "hard gates"
        elif row["readiness"] == "ready" and gain is not None:
            route = "soft margin" if gain >= MINIMUM_PR_LEAD else "score ceiling"
    return {"case": row["case_id"], "control_readiness": row["readiness"], "complete_control": complete,
            "rotation_scores_100": scores, "maximum_median_lead": gain, "strict_win_route": route}


def verify_confirmation(case, rows, seats, treatment=None, runtime=None):
    decision = case["comparison"]["confirmation"]
    pair = [rows[case["id"], role] for role in ("control", "develop")]
    for row in pair:
        role = row["role"]
        profile = decision["profiles"][role]
        if row["state"] != "completed" and profile is None:
            continue
        if not _confirmation_profile(row, profile, treatment):
            raise ValueError(f"{case['id']}/{role} stock profile differs from the sealed arm")
    win = strict_win(*pair, case["comparison"]["develop_control"]["verdict"], seats)
    if decision["win"] is not win:
        raise ValueError(f"{case['id']} confirmation outcome differs from quality and cost evidence")
    if "strict_quality_win" in decision and decision["strict_quality_win"] is not confirmation_quality(case, rows, treatment, runtime):
        raise ValueError(f"{case['id']} strict confirmation outcome differs from blind quality and cost evidence")


def within_panel_diff(left, right):
    a, b = (row["quality"] for row in (left, right))
    if (any(row["state"] not in ("completed", "merged") for row in (left, right))
            or a["diff_points_85"] is None or b["diff_points_85"] is None):
        return None
    deltas = [a["rotation_points_85"][str(i)] - b["rotation_points_85"][str(i)] for i in range(3)]
    return {"delta": statistics.median(deltas), "reversal": min(deltas) < 0 < max(deltas)}


def code_and_tokens(ids, rows):
    code = {}
    for left, right in (("develop","control"), ("develop","upstream"), ("control","upstream")):
        pairs = [p for k in ids if (p := within_panel_diff(rows[k,left], rows[k,right])) is not None]
        values = [p["delta"] for p in pairs]
        code[left + "_" + right] = {"pairs": len(pairs), "mean_delta_85": statistics.mean(values) if pairs else None,
                                    "interval": interval(values, statistics.mean), "higher": sum(d > 0 for d in values),
                                    "equal": values.count(0), "lower": sum(d < 0 for d in values),
                                    "reversals": sum(p["reversal"] for p in pairs)}
    tokens = []
    for k in ids:
        a, b = (rows[k, role]["effort"] for role in ROLES[:2])
        if a["coverage"] == b["coverage"] == "complete":
            tokens.append((a["tokens"]["totalTokens"], b["tokens"]["totalTokens"]))
    pure, develop = (sum(pair[i] for pair in tokens) for i in (0, 1))
    ratio = lambda p: sum(y for x,y in p) / sum(x for x,y in p)
    return {"diff_85": code, "complete_pair_tokens": {"pairs":len(tokens), "pure_sum":pure, "develop_sum":develop,
            "ratio":develop/pure if pure else None, "interval":interval(tokens, ratio) if all(x for x,y in tokens) else None}}


def verify_summary(name, group, cases, rows):
    ids = [c["id"] for c in cases if name == "all" or name in (c["split"], c["stratum"])]
    if group["n"] != len(ids):
        raise ValueError(f"wrong {name} denominator")
    if group["code_and_tokens"] != code_and_tokens(ids, rows):
        raise ValueError(f"{name} paired code or token aggregate differs")
    for role in ROLES:
        observed = [rows[k, role] for k in ids]
        counts = {s:sum(row["readiness"] == s for row in observed) for s in STATUS}
        if group["status_counts"][role] != counts:
            raise ValueError(f"{name}/{role} readiness count differs")
        if role != "upstream":
            efforts = [r["effort"] for r in observed]
            seen = group["observed_by_arm"][role]
            if (seen["complete"] != sum(e["coverage"] == "complete" for e in efforts)
                    or seen["usd_observations"] != sum(e["estimated_usd"] is not None for e in efforts)
                    or not math.isclose(seen["usd_estimate"],sum(e["estimated_usd"] or 0 for e in efforts),abs_tol=1e-12)
                    or seen["timed_attempts"] != sum(e["checkout_to_proposal_seconds"] is not None for e in efforts)
                    or not math.isclose(seen["observed_proposal_wall_seconds"],sum(e["checkout_to_proposal_seconds"] or 0 for e in efforts),abs_tol=1e-9)
                    or any(seen["tokens"][k] != sum(e["tokens"][k] or 0 for e in efforts) for k in seen["tokens"])):
                raise ValueError(f"{name}/{role} observed effort totals differ")
    fields = {"usd_estimate":"estimated_usd","proposal_wall_seconds":"checkout_to_proposal_seconds",
              "wall_seconds":"prompt_to_terminal_seconds","end_to_end_seconds":"through_grading_seconds"}
    for metric, field in fields.items():
        pairs = []
        for key in ids:
            pair = [rows[key, role] for role in ROLES[:2]]
            if all(row["effort"][field] is not None and (row["effort"]["coverage"] == "complete"
                    if metric == "usd_estimate" else row["state"] == "completed") for row in pair):
                pairs.append([row["effort"][field] for row in pair])
        report = group["paired"].get(metric)
        if not pairs and report is None:
            continue
        if not pairs or not report or report["pairs"] != len(pairs):
            raise ValueError(f"{name}/{metric} eligible pair count differs")
        pure, develop = (sum(pair[i] for pair in pairs) for i in (0, 1))
        if not all(math.isclose(value, report[k], abs_tol=1e-12) for k, value in
                   (("pure_sum",pure),("develop_sum",develop),("ratio",develop/pure),
                    ("median_pair_ratio",statistics.median(y/x for x,y in pairs if x)))):
            raise ValueError(f"{name}/{metric} paired aggregate differs")
        limits = interval(pairs, lambda p:sum(y for x,y in p)/sum(x for x,y in p))
        if limits != report["ratio_interval"]:
            raise ValueError(f"{name}/{metric} paired interval differs")
    pairs = []
    for key in ids:
        a,b = (rows[key,role]["quality"] for role in ROLES[:2])
        if len(a["assessments"]) == len(b["assessments"]) == 3 and None not in (a["proposal_points_100"], b["proposal_points_100"]):
            pairs.append((a["proposal_points_100"], b["proposal_points_100"]))
    delta = lambda p:statistics.mean(y-x for x,y in p)
    expected = {"pairs":len(pairs),"mean":delta(pairs),"interval":interval(pairs,delta)} if pairs else None
    if group["paired"].get("quality_delta") != expected:
        raise ValueError(f"{name} proposal score aggregate differs")
    selected = [c for c in cases if c["id"] in ids]
    for pair, counts in group["preferences"].items():
        if any(v != sum(c["comparison"][pair]["verdict"] == verdict for c in selected) for verdict,v in counts.items()):
            raise ValueError(f"{name}/{pair} preference count differs")
    simultaneous = []
    for case in selected:
        key=case["id"]
        a,b = (rows[key,role]["effort"] for role in ROLES[:2])
        if (a["coverage"] == b["coverage"] == "complete" and rows[key,"develop"]["readiness"] == "ready"
                and case["comparison"]["develop_control"]["verdict"] in ("tie","develop")
                and b["estimated_usd"] < a["estimated_usd"]
                and b["checkout_to_proposal_seconds"] < a["checkout_to_proposal_seconds"]):
            simultaneous.append(key)
    if simultaneous != group["simultaneous"]:
        raise ValueError(f"{name} simultaneous win list differs")


def verify_cost(key, effort, rates):
    if effort and effort["coverage"] == "complete":
        t = effort["tokens"]
        root, children = effort["root_tokens"], effort["descendant_tokens"]
        if not isinstance(root, dict) or not isinstance(children, dict):
            raise ValueError(f"{key} missing complete thread counters")
        for field, value in t.items():
            lead, rest = root.get(field), children.get(field, 0 if not effort["child_count"] else None)
            if type(lead) is not int or type(rest) is not int or min(lead, rest) < 0 or value != lead + rest:
                raise ValueError(f"{key} {field} differs from root and descendant counters")
        if t["totalTokens"] != t["inputTokens"] + t["outputTokens"]:
            raise ValueError(f"{key} total tokens differ from input and output counters")
        cost = ((t["inputTokens"] - t["cachedInputTokens"]) * rates["uncached_input"] +
                t["cachedInputTokens"] * rates["cached_input"] + t["outputTokens"] * rates["output"]) / 1e6
        if not math.isclose(cost, effort["estimated_usd"], abs_tol=1e-10):
            raise ValueError(f"{key} estimated cost differs from complete token counters")


def verify_artifacts(key, row, artifacts):
    for field in ("patch", "proposal"):
        if field not in artifacts or not isinstance(artifacts[field], (str, type(None))):
            raise ValueError(f"{key} invalid {field} artifact")
        content = artifacts[field]
        expected = digest(content.encode()) if content is not None else None
        if row[field + "_sha256"] != expected:
            raise ValueError(f"{key} {field} digest differs")


def verify_submission(row, rates, independent, observations, *, allow_open_flags=False):
    key = row["case_id"], row["role"]
    verify_artifacts(key, row, row)
    if (row["effort"] is None) != (key[1] == "upstream"):
        raise ValueError(f"{key} incorrect measurement attribution")
    flagged = any(j["flags"] for j in row["quality"]["assessments"])
    if ((flagged and not allow_open_flags) or row["adjudication"] is not None) and not resolved_ruling(row["adjudication"]):
        raise ValueError(f"{key} has no substantiated adjudication")
    if row["adjudication"]:
        for probe, checksum in row["adjudication"].get("probe_receipts_sha256", {}).items():
            if observations.get(probe) != checksum:
                raise ValueError(f"{key} adjudication links to a different probe receipt")
    verify_cost(key, row["effort"], rates)
    if row["state"] in ("interrupted", "unreleased", "blocked"):
        readiness = "unavailable"
    elif not row["executable_pass"] or (row["adjudication"] or {}).get("resolution") == "confirmed":
        readiness = "failed"
    elif len(row["quality"]["assessments"]) < 3 or (flagged and not row["adjudication"]):
        readiness = "pending"
    else:
        readiness = "ready"
    if row["readiness"] != readiness:
        raise ValueError(f"{key} readiness contradicts the executable, assessor or adjudication evidence")
    if row["executable_pass"]:
        required = {"build", "native", "contract", "preserve"}
        if independent:
            required.add("independent")
        if (row["state"] not in ("completed", "merged") or not required <= row["stages"].keys()
                or any(s["exit"] != 0 for s in row["stages"].values())):
            raise ValueError(f"{key} executable pass contradicts required stages or terminal state")
    binding = row["bindings"]
    if "grade" in row["receipt_sha256"] and binding["grade_patch_sha256"] != row["patch_sha256"]:
        raise ValueError(f"{key} grade is bound to a different patch")
    quality = row["quality"]
    rotations = {str(j["rotation"]): code_points(j["scores"]) for j in quality["assessments"]}
    labels = {j["rotation"]:j["label"] for j in quality["assessments"]}
    if len(binding["judges"]) != len(labels) or {j["rotation"] for j in binding["judges"]} != set(labels):
        raise ValueError(f"{key} judge binding count differs")
    for j in binding["judges"]:
        if j["label"] != labels[j["rotation"]] or any(
                j[field + "_sha256"] != digest((row[field] or "").encode()) for field in ("patch","proposal")):
            raise ValueError(f"{key} judge is bound to a different submission")
    for axis, anchor in quality["axes"].items():
        observed = [j["scores"][axis] for j in quality["assessments"] if j["scores"][axis] is not None]
        if anchor != (statistics.median(observed) if len(observed) >= 2 else None):
            raise ValueError(f"{key} axis differs from judge observations")
    anchors = quality["axes"]
    full_pr = proposal_points(anchors)
    if full_pr != quality["proposal_points_100"]:
        raise ValueError(f"{key} complete proposal score differs")
    if len(rotations) != len(quality["assessments"]) or rotations != quality["rotation_points_85"]:
        raise ValueError(f"{key} invalid or duplicate judge rotation")
    complete = set(rotations) == {"0", "1", "2"} and all(v is not None for v in rotations.values())
    if quality["diff_points_85"] != (code_points(quality["axes"]) if complete else None):
        raise ValueError(f"{key} diff score inconsistent with observed axes")


def observation_receipts(items, *, pilot_registration=None):
    receipts = {}
    for item in items:
        if item["id"] in receipts:
            raise ValueError("duplicate post-freeze observation")
        evidence = item["evidence"]
        if "probe" in item and digest(item["probe"].encode()) != evidence.get("probe_sha256"):
            raise ValueError("post-freeze probe checksum differs")
        if pilot_registration is not None:
            if evidence.get("registration_sha256") != pilot_registration:
                raise ValueError("post-freeze evidence belongs to a different pilot registration")
            if digest((json.dumps(evidence, indent=2) + "\n").encode()) != item["receipt_sha256"]:
                raise ValueError("post-freeze evidence differs from its receipt")
        receipts[item["id"]] = item["receipt_sha256"]
    return receipts


def read_pilot(path):
    record = read_json(path.read_bytes())
    reg, rows = record["registration"], record["submissions"]
    if record.get("evaluator_protocol") != reg.get("evaluator_protocol"):
        raise ValueError("published pilot evaluator protocol differs")
    components = record.get("treatment_components", {})
    if components:
        if set(components) != {"candidate", "prior"} or any(composite.identity(lock) != record["treatments"][role] for role,lock in components.items()):
            raise ValueError("published pilot treatment identity differs")
    if (record["format"] != "law-config.eval-pilot/v1" or record["name"] != path.parent.name
            or (reg["name"], reg["case"]) != (record["name"], record["case"]) or set(rows) != set(ROLES)
            or digest((json.dumps(reg, indent=2) + "\n").encode()) != record["registration_sha256"]):
        raise ValueError("published pilot registration or identity differs")
    if record["prompt"] is not None and digest(record["prompt"].encode()) != record["prompt_sha256"]:
        raise ValueError("published pilot task differs")
    observations = observation_receipts(record["observations"], pilot_registration=record["registration_sha256"])
    independent = "independent" in rows["upstream"]["stages"]
    for role, row in rows.items():
        if (row["role"] != role or row["case_id"] != reg["case"]
                or row["plan_sha256"] != reg["plans"]["candidate"]["sha256"]):
            raise ValueError("published pilot contains a submission from another case or plan")
        verify_submission(row, record["rates"], independent, observations, allow_open_flags=True)
    prior = record["prior_develop"]
    if "patch" in prior or "proposal" in prior:
        verify_artifacts("prior Develop", prior, prior)
    elif path.with_name("prior.json").is_file():
        verify_artifacts("prior Develop", prior, read_json(path.with_name("prior.json").read_bytes()))
    verify_cost("prior Develop", prior["effort"], record["rates"])
    for role, arm in reg["order"]:
        attempt = prior if role == "prior" else rows[arm]
        profile = record["profiles"][f"{role}/{arm}"]
        if attempt["state"] != "completed" and profile is None:
            continue
        if (not profile or profile["ephemeral"] is not False or profile["plugins"] != composite.expected_plugins(arm, components.get(role, {}).get("companion"))
                or any(profile[k] for k in ("apps", "mcp", "global_instructions"))
                or (role == "candidate" and profile["inventory_sha256"] != attempt["receipt_sha256"]["inventory"])):
            raise ValueError("published pilot stock profile differs from its release")
    for a, b in (("develop", "control"), ("develop", "upstream"), ("control", "upstream")):
        if proposal_verdict(rows[a], rows[b], 3) != record["comparisons"][a + "_" + b]:
            raise ValueError("published pilot verdict differs from its paired judgments")
    seats = set.intersection(*({j["rotation"] for j in row["quality"]["assessments"]} for row in rows.values()))
    win = strict_win(rows["control"], rows["develop"], record["comparisons"]["develop_control"]["verdict"], seats)
    if record["goal_win"] is not win:
        raise ValueError("published pilot outcome differs from quality and cost evidence")
    return record


def read_bundle(path):
    from jsonschema import Draft202012Validator
    schema = read_json((ROOT / "schemas/panel-v1.json").read_bytes())
    manifest = read_json(path.read_bytes())
    def validate(validator, data):
        error = next(validator.iter_errors(data), None)
        if error is not None:
            raise ValueError(f"invalid {path.name} bundle at {error.json_path}: {error.message[:240]}")
    validate(Draft202012Validator(schema), manifest)
    validator = Draft202012Validator(dict(schema, **{"$ref": "#/$defs/submission"}))
    payload = (path.parent / manifest["submissions"]["path"]).read_bytes()
    if digest(payload) != manifest["submissions"]["sha256"]:
        raise ValueError("submission file checksum differs")
    cases = {c["id"]: c for c in manifest["cases"]}
    if len(cases) != len(manifest["cases"]) or not cases:
        raise ValueError("empty or duplicate case identity")
    if (manifest["parent_plan_sha256"] is None) != (manifest["cohort"] == "primary"):
        raise ValueError("invalid parent identity for cohort")
    judge = manifest["runtime"]["executor"]["judge"]
    cap = 1 if manifest["cohort"] == "capacity-recovery" else 2
    if judge["rotations"] != 3 or judge["max_attempts_per_rotation"] != cap:
        raise ValueError("assessor policy differs from the cohort's frozen limits")
    source = manifest["source"].get("recovery_controller")
    if source and (manifest["cohort"] != "capacity-recovery" or source["plan_sha256"] != manifest["plan_sha256"]
                   or digest(source["source"].encode()) != source["sha256"]):
        raise ValueError("recorded recovery controller does not match its source or plan")
    observations = observation_receipts(manifest["observations"])
    scope = manifest["selection"]
    if scope and (manifest["cohort"] != "primary" or scope["plan_sha256"] != manifest["plan_sha256"]
                  or set(scope["cases"]) != cases.keys() or any(c["split"] != scope["split"] for c in cases.values())
                  or scope["declared_unix"] < manifest["frozen_unix"]):
        raise ValueError("bundle differs from its preregistered selection")
    rows = {}
    for line in payload.splitlines():
        row = read_json(line)
        validate(validator, row)
        key = row["case_id"], row["role"]
        if key in rows or key[0] not in cases or row["plan_sha256"] != manifest["plan_sha256"]:
            raise ValueError(f"wrong run, case or duplicate role: {key}")
        if key[1] == "upstream" and row["patch_sha256"] != cases[key[0]]["controls"]["merged_patch_sha256"]:
            raise ValueError(f"{key} upstream patch differs from the frozen merged reference")
        verify_submission(row, manifest["runtime"]["rates_usd_per_million"],
                          cases[key[0]]["controls"]["independent_check"], observations)
        rows[key] = row
    if set(rows) != {(case, role) for case in cases for role in ROLES} or len(rows) != manifest["submissions"]["rows"]:
        raise ValueError("expected exactly one record for each case and producer")
    for case in cases.values():
        seats = {}
        for role in ROLES:
            judges = rows[case["id"], role]["bindings"]["judges"]
            if len({j["label"] for j in judges}) != len(judges):
                raise ValueError(f"{case['id']}/{role} repeated judge position")
            for judge in judges:
                seats.setdefault(judge["rotation"], []).append(judge)
        for rotation, judges in seats.items():
            if {j["label"] for j in judges} != {"A", "B", "C"} or any(
                    len({j[k] for j in judges}) != 1 for k in
                    ("judgment_sha256", "mapping_sha256", "assessor_sha256", "packet_sha256", "prompt_sha256")):
                raise ValueError(f"{case['id']} rotation {rotation} does not identify one shared assessment")
        meters = case["judge_attempts"]
        if any(a["rotation"] not in range(3) or a["attempt"] not in range(cap)
               or (a["accepted"] and a["state"] != "completed") for a in meters):
            raise ValueError(f"{case['id']} assessor attempt violates its cohort limit or terminal state")
        if len({(a["rotation"], a["attempt"]) for a in meters}) != len(meters):
            raise ValueError(f"{case['id']} duplicate assessor attempt")
        accepted = [(a["rotation"], a["native_sha256"]) for a in meters if a["accepted"]]
        if sorted(accepted) != sorted((rotation, judges[0]["assessor_sha256"]) for rotation, judges in seats.items()):
            raise ValueError(f"{case['id']} scored assessor differs from its metering entry")
        confirmation = manifest["protocol"] == "pr-quality-confirmation-v1"
        for a,b in (("develop","control"),("develop","upstream"),("control","upstream")):
            if case["comparison"][a+"_"+b] != proposal_verdict(rows[case["id"],a], rows[case["id"],b], 3 if confirmation else 2):
                raise ValueError(f"{case['id']} full proposal verdict differs from its paired votes and gates")
            if case["comparison"]["diff_85"][a+"_"+b] != within_panel_diff(rows[case["id"],a],rows[case["id"],b]):
                raise ValueError(f"{case['id']} within-panel paired diff score differs")
        if confirmation:
            verify_confirmation(case, rows, seats, manifest["runtime"]["treatment"], manifest["runtime"])
    attempts = [attempt for case in cases.values() for attempt in case["judge_attempts"]]
    assessor = manifest["evaluator"]
    if (assessor["attempts"] != len(attempts) or assessor["complete_receipts"] != sum(a["coverage"] == "complete" for a in attempts)
            or not math.isclose(assessor["observed_usd"], sum(a["usd_estimate"] or 0 for a in attempts), abs_tol=1e-10)):
        raise ValueError("assessor totals differ from case receipts")
    if "all" not in manifest["groups"]:
        raise ValueError("missing all-case denominator")
    for name, group in manifest["groups"].items():
        verify_summary(name, group, manifest["cases"], rows)
    return manifest, rows


def compare(previous, candidate, split, role):
    old, old_rows = read_bundle(previous)
    new, new_rows = read_bundle(candidate)
    if old["cohort"] != new["cohort"] or old["protocol"] != new["protocol"]:
        raise ValueError("compare only the same cohort and protocol")
    global_differences = [k for k in ("model", "effort", "implementation_sha256", "cli_sha256", "bwrap_sha256",
                                      "rubric_sha256", "seed", "rates_usd_per_million", "executor")
                          if old["runtime"][k] != new["runtime"][k]]
    cases = [{c["id"]: c for c in run["cases"] if split == "all" or c["split"] == split} for run in (old, new)]
    changes, excluded = [], {}
    for key in sorted(cases[0].keys() | cases[1].keys()):
        if not all(key in cohort for cohort in cases):
            excluded[key] = ["case absent from one selected split"]
            continue
        a, b = (cohort[key] for cohort in cases)
        mismatches = [k for k in ("repo", "pr", "base", "merged", "split", "controls") if a[k] != b[k]]
        if "controls" in mismatches:
            mismatches.remove("controls")
            mismatches.extend("controls." + k for k in sorted(a["controls"].keys() | b["controls"].keys())
                              if a["controls"].get(k) != b["controls"].get(k))
        if mismatches or global_differences:
            excluded[key] = global_differences + mismatches
            continue
        left, right = (table[key, role] for table in (old_rows, new_rows))
        def delta(a, b):
            return b - a if a is not None and b is not None else None
        complete = left["state"] == right["state"] == "completed"
        priced = complete and left["effort"]["coverage"] == right["effort"]["coverage"] == "complete"
        changes.append({"case": key, "status": [left["readiness"], right["readiness"]],
                        "between_version_display_delta_85": delta(left["quality"]["diff_points_85"], right["quality"]["diff_points_85"]) if complete else None,
                        "total_tokens_delta": delta(left["effort"]["tokens"]["totalTokens"], right["effort"]["tokens"]["totalTokens"]) if priced else None,
                        "estimated_usd_delta": delta(left["effort"]["estimated_usd"], right["effort"]["estimated_usd"]) if priced else None,
                        "proposal_seconds_delta": delta(left["effort"]["checkout_to_proposal_seconds"], right["effort"]["checkout_to_proposal_seconds"]) if complete else None})
    stats = {}
    for field in ("between_version_display_delta_85", "total_tokens_delta", "estimated_usd_delta", "proposal_seconds_delta"):
        values = [row[field] for row in changes if row[field] is not None]
        stats[field] = {"matched": len(values), "mean": statistics.mean(values) if values else None}
    return {"previous": old["plan_sha256"], "candidate": new["plan_sha256"], "role": role, "split": split,
            "package_sha256": [run["runtime"]["package_sha256"] for run in (old,new)],
            **({"treatment_identity": [composite.identity(run["runtime"]["treatment"]) for run in (old,new)]}
               if any(run["runtime"]["treatment"].get("companion") for run in (old,new)) else {}),
            "excluded": excluded, "cases": changes, "aggregate": stats}


def tuning_summary(pilots):
    """Describe repeated exposed pilots within exact recorded evaluation contexts."""
    groups = {}
    for pilot in pilots:
        context = {"evaluator_protocol": pilot["registration"].get("evaluator_protocol"),
                   **{key: pilot.get(key) for key in ("runtime_sha256", "rubric_sha256", "model", "effort", "rates")}}
        # An absent protocol stays unknown. Its exact runtime hash still prevents
        # mixing different legacy evaluators or the explicitly selected v3.
        if any(context[key] is None for key in context if key != "evaluator_protocol"):
            context["unverified_context_run"] = pilot["name"]
        key = json.dumps(context, sort_keys=True)
        group = groups.setdefault(key, {"context": context, "runs": []})
        arms = [pilot["submissions"][role] for role in ("develop", "control")]
        exclusions = [f"{arm['role']}: {field}={value}" for arm in arms
                      for field, value, expected in (("readiness", arm["readiness"], "ready"),
                                                     ("state", arm["state"], "completed"),
                                                     ("coverage", arm["effort"]["coverage"], "complete"))
                      if value != expected]
        signal = pilot_quality_signal(pilot)
        group["runs"].append({"name": pilot["name"], "case": pilot["case"], "treatments": pilot["treatments"],
                              "included_ready_complete": not exclusions, "exclusions": exclusions,
                              "blind_full_pr": signal["blinded_full_pr"],
                              "full_pr_points_100": {role: row["quality"]["proposal_points_100"]
                                                     for role, row in pilot["submissions"].items()},
                              "blind_full_pr_vs_merged": {arm["role"]: blinded_proposal_verdict(
                                  arm, pilot["submissions"]["upstream"], 3) for arm in arms},
                              "merged_readiness": pilot["submissions"]["upstream"]["readiness"],
                              "develop_merged_readiness_first": pilot["comparisons"]["develop_upstream"],
                              "strict_joint_win": signal["ready_blind_win_at_no_more_cost"],
                              "effort": {arm["role"]: {key: arm["effort"].get(key) for key in
                                         ("coverage", "estimated_usd", "checkout_to_proposal_seconds", "through_grading_seconds")}
                                         | {"total_tokens": arm["effort"]["tokens"].get("totalTokens")} for arm in arms}})

    def metric(rows, field):
        values = [[row["effort"][role].get(field) for role in ("develop", "control")] for row in rows]
        pairs = [pair for pair in values if all(type(v) in (int, float) and math.isfinite(v) for v in pair)]
        totals = [sum(pair[i] for pair in pairs) for i in range(2)] if pairs else [None, None]
        return {"pairs": len(pairs), "develop": totals[0], "control": totals[1]}

    for group in groups.values():
        rows = group["runs"]
        ready = [row for row in rows if row["included_ready_complete"]]
        scored = [row for row in ready if row["blind_full_pr"].get("score_delta") is not None]
        joint = [row["strict_joint_win"] for row in rows if row["strict_joint_win"] is not None]
        group["denominators"] = {"records": len(rows), "ready_complete_pairs": len(ready),
                                 "excluded": len(rows)-len(ready), "cases": len({row["case"] for row in rows})}
        group["quality"] = {"pairs": len(scored),
                            "verdicts": {v: sum(row["blind_full_pr"]["verdict"] == v for row in scored)
                                         for v in ("develop", "tie", "control", "unresolved")},
                            "mean_paired_delta_100": statistics.mean(row["blind_full_pr"]["score_delta"] for row in scored) if scored else None}
        group["strict_joint"] = {"pairs": len(joint), "wins": sum(joint) if joint else None}
        group["ready_complete_totals"] = {"estimated_usd": metric(ready, "estimated_usd"),
                                          "total_tokens": metric(ready, "total_tokens"),
                                          "proposal_seconds": metric(ready, "checkout_to_proposal_seconds"),
                                          "through_grading_seconds": metric(ready, "through_grading_seconds")}
    return {"records": len(pilots),
            "scope": "Repeated exposed tasks and different treatments are diagnostic; no cross-context metric totals.",
            "quality_measure": "Develop versus stock uses the mean of paired median rotation differences (/100). blind_full_pr_vs_merged uses the blind rotations. develop_merged_readiness_first gives hard gates precedence.",
            "joint_measure": "Published ready_blind_win_at_no_more_cost helper across all records, independently of the ready/ready table.",
            "measurement_scope": "Complete root+descendant estimates; wall totals sum proposal durations, not campaign elapsed. Each metric has a paired denominator.",
            "protocol_note": "Unknown protocol stays null; runtime hash also partitions.",
            "groups": list(groups.values())}


def tuning(directory):
    return tuning_summary([read_pilot(path) for path in sorted(directory.glob("*/result.json"))])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    rollup = sub.add_parser("tuning", help="describe all portable tuning pilots by recorded evaluation context")
    rollup.add_argument("directory", type=Path, nargs="?", default=ROOT / "runs/tuning")
    check = sub.add_parser("validate")
    check.add_argument("manifest", type=Path, nargs="+")
    ceiling = sub.add_parser("headroom", help="show the largest possible quality lead against each recorded control")
    ceiling.add_argument("record", type=Path)
    match = sub.add_parser("compare")
    match.add_argument("previous", type=Path)
    match.add_argument("candidate", type=Path)
    match.add_argument("--role", choices=ROLES[:2], default="develop")
    match.add_argument("--split", choices=("tuning", "confirmation", "all"), default="tuning")
    args = parser.parse_args()
    if args.action == "tuning":
        print(json.dumps(tuning(args.directory), indent=2))
    elif args.action == "validate":
        for path in args.manifest:
            record, rows = read_bundle(path)
            print(f"{record['name']}: {len(record['cases'])} cases, {len(rows)} verified submissions")
    elif args.action == "headroom":
        if args.record.name == "result.json":
            controls = [read_pilot(args.record)["submissions"]["control"]]
        else:
            _, rows = read_bundle(args.record)
            controls = [row for (_, role), row in rows.items() if role == "control"]
        print(json.dumps([control_headroom(row) for row in controls], indent=2))
    else:
        print(json.dumps(compare(args.previous, args.candidate, args.split, args.role), indent=2))
