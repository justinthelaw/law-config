"""Recompute the headline comparison from the two frozen historical bundles."""
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
from statistics import mean
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tools"))
from records import read_bundle, target_repositories


def functional_score(row):
    if row["proposal"] == "" or row["proposal_observation"] in {"omitted", "incomplete"} or row["patch"] == "":
        return 0
    if any(stage["exit"] not in (None, 0) for stage in row["stages"].values()):
        return 0
    if (row["adjudication"] or {}).get("resolution") == "confirmed":
        return 0
    rotations = {vote["rotation"] for vote in row["quality"]["assessments"]}
    if (row["readiness"] == "ready" and row["executable_pass"] is True and row["proposal"]
            and rotations == {0, 1, 2} and row["quality"]["proposal_points_100"] is not None):
        return row["quality"]["proposal_points_100"]
    raise ValueError(f"Indeterminate functional score for {row['case_id']}/{row['role']}")


def metered_value(row, metric):
    effort = row["effort"]
    if metric == "usd":
        return effort["estimated_usd"] if effort["coverage"] == "complete" else None
    if metric == "tokens":
        return effort["tokens"]["totalTokens"] if effort["pricing"]["token_coverage"] == "complete" else None
    if row["state"] == "completed":
        field = "checkout_to_proposal_seconds" if metric == "checkout_s" else "through_grading_seconds"
        return effort[field]
    return None


def main():
    report = json.loads((HERE / "comparison.json").read_bytes())["current"]
    claimed = report["summary"]
    cases, names = {}, set()
    for batch in report["batches"]:
        path = HERE.parent / batch["manifest"]
        if path.parent.parent != HERE or sha256(path.read_bytes()).hexdigest() != batch["manifest_sha256"]:
            raise ValueError("Unexpected source manifest")
        manifest, rows = read_bundle(path)
        for case in manifest["cases"]:
            key = case["id"]
            if key in cases or case["repo"] in names:
                raise ValueError(f"Duplicate repository {case['repo']}")
            cases[key] = {role: rows[key, role] for role in ("control", "develop", "upstream")}
            names.add(case["repo"])
    if names != set(target_repositories() or []):
        raise ValueError("The two bundles must cover the full historical roster")

    for role in ("control", "develop", "upstream"):
        rows = [case[role] for case in cases.values()]
        score = mean(functional_score(row) for row in rows)
        ready = sum(row["readiness"] == "ready" for row in rows)
        if score != claimed["quality"][role]["functional_mean_100"] or ready != claimed["ready"][role]["ready"]:
            raise ValueError(f"Quality or readiness differs for {role}")
        print(f"{role} functional quality: {score:.4f}/100, {ready}/{len(cases)} ready")
        if role != "upstream":
            seconds = sum(row["effort"]["checkout_to_proposal_seconds"] for row in rows)
            if not isclose(seconds, claimed["elapsed_attempts"][role]["sum_checkout_to_terminal_s"]):
                raise ValueError(f"All-attempt checkout time differs for {role}")

    for metric in ("usd", "tokens", "checkout_s", "through_grading_s"):
        pairs = {}
        for key, case in cases.items():
            values = [metered_value(case[role], metric) for role in ("control", "develop")]
            if None not in values:
                pairs[key] = values
        expected = claimed["paired"][metric]
        stock, develop = map(sum, zip(*pairs.values()))
        if (set(pairs) != set(expected["cases"]) or not isclose(stock, expected["control"])
                or not isclose(develop, expected["develop"]) or not isclose(develop / stock, expected["ratio"])):
            raise ValueError(f"Paired {metric} differs")
        print(f"{metric} across {len(pairs)} pairs: stock {stock:g}, Develop {develop:g}, ratio {develop/stock:.4f}")


if __name__ == "__main__":
    main()
