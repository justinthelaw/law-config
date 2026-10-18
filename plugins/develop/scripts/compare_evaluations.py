#!/usr/bin/env python3
"""Compare recorded evaluations offline; never execute a task or infer causality."""
import argparse
import copy
import json
from pathlib import Path
import sys

from evaluation import load_json, validate_result


def observation_counts(result):
    """Count recorded channels, not presumed communication quality."""
    counts = dict.fromkeys(("user", "tool", "helper"), 0)
    for attempt in result["attempts"]:
        for observation in attempt["observations"]:
            counts[observation["channel"]] += 1
    return counts


def _outcome(attempt):
    if attempt is None or attempt["state"] != "completed":
        return "incomplete"
    verdicts = [attempt[key]["verdict"] for key in ("functional", "evaluator")]
    if "fail" in verdicts:
        return "fail"
    return "pass" if verdicts == ["pass", "pass"] else "incomplete"


def _costs(result):
    costs = {}
    for name in ("wall_seconds", "tokens", "usd"):
        values = [attempt["cost"][name] for attempt in result["attempts"]]
        known = [value for value in values if value is not None]
        costs[name] = {"known_attempts": len(known), "planned_attempts": len(values),
                       "total": sum(known) if len(known) == len(values) else None}
    return costs


def compare_results(baseline, candidate):
    """Return all attempts and paired outcomes, rejecting incompatible identities.

    Attempt IDs identify predeclared pairs. Extra retries remain unpaired and
    incomplete; neither side's failures can disappear from the denominator.
    """
    for result in (baseline, candidate):
        validate_result(result)
    if baseline["source"]["repository"] != candidate["source"]["repository"]:
        raise ValueError("different source repositories")
    if baseline["host"] != candidate["host"]:
        raise ValueError("different host/model/effort/selection identity")
    if baseline["evidence_kind"] != candidate["evidence_kind"]:
        raise ValueError("different evidence kinds")
    plans = [{row["attempt_id"]: row["fixture"] for row in result["planned_attempts"]}
             for result in (baseline, candidate)]
    attempts = [{row["attempt_id"]: row for row in result["attempts"]}
                for result in (baseline, candidate)]
    pairs = []
    for attempt_id in sorted(plans[0].keys() | plans[1].keys()):
        fixtures = [plan.get(attempt_id) for plan in plans]
        if all(fixtures) and fixtures[0] != fixtures[1]:
            raise ValueError(f"incompatible fixture identity for {attempt_id}")
        pair = {"attempt_id": attempt_id, "fixture": fixtures[0] or fixtures[1]}
        for index, side in enumerate(("baseline", "candidate")):
            attempt = attempts[index].get(attempt_id)
            pair[side] = {"outcome": _outcome(attempt), "attempt": attempt}
        pairs.append(pair)
    incomplete = any(pair[side]["outcome"] == "incomplete"
                     for pair in pairs for side in ("baseline", "candidate"))
    candidate_failed = any(pair["candidate"]["outcome"] == "fail" for pair in pairs)
    costs = {side: _costs(result) for side, result in
             (("baseline", baseline), ("candidate", candidate))}
    paired_plan = plans[0] == plans[1]
    delta = {}
    for name in costs["baseline"]:
        before, after = [costs[side][name]["total"] for side in ("baseline", "candidate")]
        delta[name] = after - before if paired_plan and before is not None and after is not None else None
    return copy.deepcopy({
        "schema_version": 1,
        "status": "incomplete" if incomplete else "candidate_failed" if candidate_failed else "complete",
        "interpretation": "Recorded outcomes only; no causal improvement or native-host certification.",
        "baseline": baseline, "candidate": candidate, "pairs": pairs,
        "counts": {side: {outcome: sum(pair[side]["outcome"] == outcome for pair in pairs)
                          for outcome in ("pass", "fail", "incomplete")}
                   for side in ("baseline", "candidate")},
        "observations": {"baseline": observation_counts(baseline),
                         "candidate": observation_counts(candidate)},
        "agent_cost": costs, "agent_cost_delta": delta,
        "limitations": (["Unverified grader isolation; behavioral conclusions remain unverified."]
                        if any(r["grader_isolation"]["status"] != "verified"
                               for r in (baseline, candidate)) else []),
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args(argv)
    try:
        report = compare_results(load_json(args.baseline), load_json(args.candidate))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return {"complete": 0, "candidate_failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
