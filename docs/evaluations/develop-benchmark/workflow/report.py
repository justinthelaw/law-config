#!/usr/bin/env python3
"""Print the six planned pairs, including unreleased, interrupted and failed attempts."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab import CASES, STATE
from run import frozen_plan, result
from blind import verdicts

STAGES = {"build": 0, "native": 0, "hidden": 0}
TOKENS = ("inputTokens", "cachedInputTokens", "cacheWriteInputTokens",
          "outputTokens", "reasoningOutputTokens", "totalTokens")


def attempt(directory, row=None):
    if not directory.is_dir():
        return {"state": "unreleased"}
    if not (directory / "result.json").exists():
        return {"state": "interrupted", "reference_checks_pass": False}
    if row is None:
        raise ValueError("a released result needs a verified plan")
    usage = row.get("usage", {})
    participants = set(row.get("threads", [])) | set(row.get("children", [])) | {row.get("root")}
    complete = (row["state"] == "completed" and bool(usage) and participants <= usage.keys()
                and all(isinstance(entry.get(key), int) for entry in usage.values() for key in TOKENS))
    observed = {key: sum(entry[key] for entry in usage.values() if isinstance(entry.get(key), int))
                if any(isinstance(entry.get(key), int) for entry in usage.values()) else None for key in TOKENS}
    stages = row.get("grade", {}).get("stages")
    return {"state": row["state"], "stages": stages,
            "reference_checks_pass": row["state"] == "completed" and stages == STAGES,
            "seconds": {k: row.get(k) for k in ("wall_seconds", "setup_seconds", "grading_seconds",
                                                "end_to_end_seconds")},
            "usage_complete": complete, "threads_observed": len(usage),
            "tokens": observed if complete else None, "observed_tokens": observed,
            "token_coverage": "complete" if complete else "lower_bound" if usage else "unknown",
            "diagnostics": row.get("grade", {}).get("diagnostics"),
            "usd": row.get("usd"), "error": row.get("error")}


def differences(control, develop):
    """Positive values mean Develop spent more. Partial or incomplete measurements stay null."""
    if any(a["state"] not in {"completed", "timeout"} for a in (control, develop)):
        return None
    tokens = None
    if control["usage_complete"] and develop["usage_complete"]:
        tokens = {key: develop["tokens"][key] - control["tokens"][key] for key in TOKENS}
        tokens["uncachedInputTokens"] = tokens["inputTokens"] - tokens["cachedInputTokens"]
    return {"reference_pass_delta": int(develop["reference_checks_pass"]) - int(control["reference_checks_pass"]),
            "wall_seconds_delta": develop["seconds"]["wall_seconds"] - control["seconds"]["wall_seconds"],
            "end_to_end_seconds_delta": develop["seconds"]["end_to_end_seconds"] - control["seconds"]["end_to_end_seconds"],
            "tokens_delta": tokens, "usd_delta": None}


def report():
    cases = []
    plan = frozen_plan()
    for key, case in CASES.items():
        folder = STATE / "experiment" / key
        arms = {}
        for name in ("control", "develop"):
            row = result(plan, case, name) if plan and (folder / name / "result.json").exists() else None
            arms[name] = attempt(folder / name, row)
        cases.append({"case": key, "stratum": case.get("stratum", "external"),
                      "reference": f"https://github.com/{case['repo']}/pull/{case['pr']}", **arms,
                      "develop_minus_control": differences(**arms),
                      "blind_quality": verdicts(case, plan) if plan else None})
    return {"planned_pairs": len(CASES), "human_time_seconds": None, "human_cost_usd": None,
            "pairs": cases}


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
