"""Compute the registered stopping rule from verified, frozen historical bundles."""
import json
from pathlib import Path
import statistics
import sys

evaluations = Path.cwd() / "docs/evaluations"
sys.path.insert(0, str(evaluations / "runs/pr-quality-pytest-entry-natural-v1"))
from verify import functional_score, metered_value
from records import blinded_proposal_verdict, read_bundle, target_repositories

cases = {}
identities = set()
for path in map(Path, sys.argv[1:]):
    manifest, rows = read_bundle(path)
    if manifest["protocol"] != "pr-quality-pytest-entry-natural-v1":
        raise ValueError("Unexpected evaluator protocol")
    runtime = manifest["runtime"]
    identities.add((runtime["package_sha256"], runtime["source_sha256"], runtime["rubric_sha256"],
                    runtime["cli_sha256"], runtime["model"], runtime["effort"], json.dumps(runtime["treatment"], sort_keys=True)))
    for case in manifest["cases"]:
        key = case["id"]
        if case["repo"] in cases:
            raise ValueError(f"Duplicate repository {case['repo']}")
        cases[case["repo"]] = {role: rows[key, role] for role in ("control", "develop", "upstream")}
if len(identities) != 1 or set(cases) != set(target_repositories()):
    raise ValueError("Expected a single treatment and the full historical repository roster")

def arm_summary(role):
    rows = [case[role] for case in cases.values()]
    result = {"quality": statistics.mean(functional_score(row) for row in rows),
              "ready": sum(row["readiness"] == "ready" for row in rows)}
    if role == "upstream":
        return result
    efforts = [row["effort"] or {} for row in rows]
    times = [e.get("checkout_to_proposal_seconds") for e in efforts]
    prices = [metered_value(row, "usd") if row["effort"] else None for row in rows]
    known = [(e.get("pricing") or {}).get("known_usd_lower_bound") for e in efforts]
    observed = [v for v in known if v is not None]
    result.update(mean_time=statistics.mean(times) if None not in times else None,
                  timed=sum(t is not None for t in times), cost=sum(prices) if None not in prices else None,
                  observed_cost=sum(observed) if observed else None, priced=sum(v is not None for v in prices))
    return result

summary = {role: arm_summary(role) for role in ("control", "develop", "upstream")}
stock, develop = summary["control"], summary["develop"]
quality_ok = develop["quality"] >= 1.10 * stock["quality"]
time_ok = develop["mean_time"] <= 0.90 * stock["mean_time"] if None not in (develop["mean_time"], stock["mean_time"]) else None
cost_ok = None
if develop["cost"] is not None and stock["observed_cost"] is not None and develop["cost"] <= 0.90 * stock["observed_cost"]:
    cost_ok = True
elif stock["cost"] is not None and develop["observed_cost"] is not None and develop["observed_cost"] > 0.90 * stock["cost"]:
    cost_ok = False
paired = {}
for metric in ("usd", "tokens", "checkout_s"):
    pairs = [(metered_value(case["control"], metric), metered_value(case["develop"], metric)) for case in cases.values()
             if all(case[r]["effort"] and case[r]["state"] == "completed" for r in ("control", "develop"))]
    pairs = [p for p in pairs if None not in p]
    paired[metric] = {"pairs":len(pairs), "stock":sum(p[0] for p in pairs), "develop":sum(p[1] for p in pairs)}
per_case = {}
for repo, rows in sorted(cases.items()):
    per_case[repo] = {"quality": {r: functional_score(row) for r, row in rows.items()},
                      "time": {r:(rows[r]["effort"] or {}).get("checkout_to_proposal_seconds") for r in ("control", "develop")},
                      "cost": {r: metered_value(rows[r], "usd") if rows[r]["effort"] else None for r in ("control", "develop")},
                      "blind":blinded_proposal_verdict(rows["develop"], rows["control"], 3)["verdict"]}
criteria = {"quality": quality_ok, "time": time_ok, "cost": cost_ok}
print(json.dumps({"arms": summary, "completed_pairs":paired, "meets_10_percent":criteria,
                  "verified_two_of_three":sum(v is True for v in criteria.values()) >= 2, "repositories":per_case}, indent=2))
