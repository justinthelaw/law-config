"""Measure root model responses spent collecting terminal output in a sealed tuning trial."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

EVALS = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(EVALS), str(EVALS / "tools")]
import benchmark as B
from native_panel import C, E
import results

FIELDS = dict(zip(("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens",
                   "reasoning_output_tokens", "total_tokens"), results.TOKENS))
METHOD = re.compile(r"\btools\.(\w+)\s*\(")
EMPTY = re.compile(r"""["']?chars["']?\s*:\s*(?:""|'')""")


def readback(call):
    methods = METHOD.findall(call.get("input", ""))
    return (call.get("name") == "exec" and set(methods) == {"write_stdin"}
            and len(EMPTY.findall(call["input"])) == len(methods))


def measure(plan, case, arm):
    folder = C.run_dir(plan["name"]) / "attempts" / case / arm
    if not (folder / "result.json").is_file():
        raise ValueError(f"{plan['name']}/{case}/{arm} has not sealed")
    row = C.read_attempt(plan["name"], case, arm)
    usage = results.usage(row)
    if usage["coverage"] != "complete":
        return {"state": row["state"], "coverage": usage["coverage"], "poll_only_usd": None}
    native = E.read(folder / "native.json")
    if any(row[key] != native[key] for key in ("root", "usage", "turn_meters", "commands", "final")):
        raise ValueError("native meter or trace identity differs from the sealed result")
    root = native["root"]
    trace, = (folder / "profile/sessions").rglob(f"*{root}*.jsonl")
    total, polls, responses, calls = Counter(), Counter(), set(), []
    poll_count = 0
    with trace.open() as lines:
        for line in lines:
            event = json.loads(line)
            item = event["payload"]
            if event["type"] == "response_item" and item.get("type") in ("custom_tool_call", "function_call"):
                calls.append(item)
            if event["type"] != "token_usage_record":
                continue
            if item["thread_id"] != root or item["response_id"] in responses:
                raise ValueError("unexpected thread or duplicate response meter")
            responses.add(item["response_id"])
            total.update(item["usage"])
            if calls and all(map(readback, calls)):
                poll_count += 1
                polls.update(item["usage"])
            calls.clear()
    if calls or any(total[key] != native["usage"][root][field] for key, field in FIELDS.items()):
        raise ValueError("response totals differ from the terminal root meter")
    rates = plan["cost_usd_per_million"]
    def cost(tokens):
        cached = tokens["cached_input_tokens"]
        return ((tokens["input_tokens"] - cached) * rates["uncached_input"]
                + cached * rates["cached_input"] + tokens["output_tokens"] * rates["output"]) / 1e6
    return {"responses": len(responses), "poll_only_responses": poll_count, "poll_only_tokens": polls["total_tokens"],
            "poll_only_usd": cost(polls), "root_tokens": total["total_tokens"], "root_usd": cost(total),
            "proposal_usd": usage["usd_estimate"], "native_sha256": E.sha(folder / "native.json"),
            "root_trace_sha256": E.sha(trace)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=B.valid_name)
    args = parser.parse_args()
    path = E.STATE / "pilots" / args.run / "registration.json"
    reg = E.read(path)
    if reg["name"] != args.run or sorted(reg["order"]) != [["candidate", "control"], ["candidate", "develop"], ["prior", "develop"]]:
        raise ValueError("invalid registered allocation")
    program_sha = E.sha(Path(__file__))
    if reg["hypothesis"] == "await-local-commands":
        hypothesis = Path(__file__).with_name("hypothesis.json")
        if E.sha(hypothesis) != reg["hypothesis_sha256"] or E.read(hypothesis)["measurement_program_sha256"] != program_sha:
            raise ValueError("registered readback measurement differs")
    rows = {}
    for role, arm in reg["order"]:
        plan = C.verify_receipt(reg["plans"][role])
        if plan["pilot"] != {"name": args.run, "case": reg["case"], "role": role}:
            raise ValueError("plan and registered pilot differ")
        rows[f"{role}/{arm}"] = measure(plan, reg["case"], arm)
    print(json.dumps({"case": reg["case"], "registration_sha256": E.sha(path), "measurement_sha256": program_sha,
                      "scope": "Root samples whose only tool collected terminal output. These are measured costs. Some readbacks deliver required output.",
                      "roles": rows}, indent=2))
