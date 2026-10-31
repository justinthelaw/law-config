"""Count strictly poll-only model responses in sealed participant attempts; no inference.

Usage: python3 -B docs/evaluations/tools/measure_waits.py ATTEMPT_DIR ...
Only explicit calls and native-owned turn/response usage are classified. Mixed work,
input injection, missing ownership and unproven arguments never count as polling.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest

FIELDS = dict(zip(("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                   "output_tokens", "reasoning_output_tokens", "total_tokens"),
                  ("inputTokens", "cachedInputTokens", "cacheWriteInputTokens",
                   "outputTokens", "reasoningOutputTokens", "totalTokens")))
METHOD = re.compile(r"\btools\.([A-Za-z_]\w*)\s*\(")
CHARS = re.compile(r'''["']?chars["']?\s*:\s*(["'])((?:\\.|(?!\1).)*)\1''')
POLL = {"write_stdin", "outer_wait", "sleep"}


def code_mask(source):
    """Hide strings/comments before recognizing tools; templates remain unproven."""
    return re.sub(r'''//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`''',
                  lambda m: " " * len(m.group()), source)


def call_kind(call):
    name = call.get("name", "").split(".")[-1]
    source = call.get("input", call.get("arguments", ""))
    if name in ("wait", "sleep"):
        try:
            args = json.loads(source)
        except (ValueError, TypeError):
            return "unproven"
        if not isinstance(args, dict):
            return "unproven"
        if name == "wait":
            return "outer_wait" if (isinstance(args.get("cell_id"), str)
                and args.get("terminate", False) is False
                and set(args) <= {"cell_id", "yield_time_ms", "max_tokens", "terminate"}) else "unproven"
        return "sleep" if (set(args) == {"duration_ms"}
            and type(args["duration_ms"]) is int and args["duration_ms"] > 0) else "unproven"
    if name == "exec":
        masked = code_mask(source)
        # Regex literals/division need a full JS parser; never prove them by regex.
        if "/" in masked or "`" in source:
            return "unproven"
        methods = METHOD.findall(masked)
        if len(re.findall(r"\btools\b", masked)) != len(methods):
            return "unproven"
        if methods and set(methods) == {"write_stdin"}:
            # Only direct object arguments are proved; variables/spreads/nested objects
            # are conservatively excluded, even when a nearby string says chars:"".
            calls = list(re.finditer(r"\btools\.write_stdin\s*\(\s*\{([^{}]*)\}\s*\)", source))
            mask = code_mask(source)
            calls = [m for m in calls if mask[m.start():].startswith("tools.write_stdin")]
            def empty_input(match):
                arg = match.group(1)
                chars = list(CHARS.finditer(arg))
                keys = re.findall(r'''["']?chars["']?\s*:''', arg)
                return (len(chars) == len(keys) == 1 and not chars[0].group(2)
                        and code_mask(arg)[chars[0].start():].startswith("chars")
                        and "..." not in code_mask(arg))
            if len(calls) == len(methods) and all(map(empty_input, calls)):
                return "write_stdin"
            return "unproven"
    return "work"


def category(calls):
    kinds = {call_kind(c) for c in calls}
    if not kinds:
        return "no_tool_call"
    if kinds <= POLL:
        return next(iter(kinds)) + "_only" if len(kinds) == 1 else "mixed_poll_only"
    return "unproven_or_work"


def scan(events, thread, owned_turns):
    """Task/context boundaries fence inherited fork history before collecting calls."""
    active = None
    pending = []
    seen = set()
    totals = Counter()
    rows = []
    contexts = {}
    ambiguities = 0
    for event in events:
        kind, p = event.get("type"), event.get("payload", {})
        if not isinstance(p, dict):
            continue
        typ = p.get("type")
        if kind == "turn_context" or (kind == "event_msg" and typ == "task_started"):
            turn = p.get("turn_id")
            if turn != active:
                if pending:
                    raise ValueError("owned calls crossed a turn boundary without a usage record")
                active = turn
            if kind == "turn_context" and turn in owned_turns:
                if turn in contexts:
                    raise ValueError("duplicate owned turn context")
                contexts[turn] = {"model": p.get("model"), "effort": p.get("effort")}
        elif kind == "event_msg" and typ == "task_complete":
            if pending:
                raise ValueError("owned calls have no response usage")
            active = None
        elif kind == "response_item" and typ in ("custom_tool_call", "function_call"):
            if active in owned_turns:
                pending.append({k: p[k] for k in ("name", "input", "arguments") if k in p})
        elif kind == "token_usage_record":
            if p.get("thread_id") != thread:
                continue
            turn = p.get("turn_id")
            if turn not in owned_turns or p.get("response_id") in seen:
                raise ValueError("unowned turn or duplicate response meter")
            seen.add(p["response_id"])
            usage = p["usage"]
            if any(type(usage.get(k)) is not int or usage[k] < 0 for k in FIELDS):
                raise ValueError("invalid response counters")
            totals.update({k: usage[k] for k in FIELDS})
            label = category(pending) if active == turn else "ambiguous_ownership"
            ambiguities += active != turn
            rows.append((label, turn, {k: usage[k] for k in FIELDS}))
            pending = []
    if pending:
        raise ValueError("trailing calls without usage")
    return rows, totals, contexts, ambiguities


def load_pricing():
    path = Path(__file__).resolve().parents[1] / "develop-benchmark/panel/pricing.py"
    spec = importlib.util.spec_from_file_location("frozen_wait_pricing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def measure(folder, pricing):
    native_path, result_path = folder / "native.json", folder / "result.json"
    native, result = (json.loads(p.read_text()) for p in (native_path, result_path))
    if native.get("state") != "completed" or result.get("state") != "completed":
        raise ValueError("requires completed sealed attempts; interrupted coverage is unknown")
    for key in ("root", "threads", "children", "usage", "turn_meters", "turn_contexts", "turn_context_receipts"):
        if native.get(key) != result.get(key):
            raise ValueError("sealed/native identity differs: " + key)
    participants = set(native["threads"]) | set(native["children"]) | {native["root"]}
    if set(native["usage"]) != participants or set(native["turn_meters"]) != participants:
        raise ValueError("missing participant meters")
    all_categories = defaultdict(lambda: {"responses": 0, "usd": 0.0})
    threads = []
    for thread in sorted(participants):
        files = list((folder / "profile/sessions").rglob(f"*{thread}*.jsonl"))
        if len(files) != 1:
            raise ValueError("trace missing or ambiguous")
        path = files[0]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if native["turn_context_receipts"][thread] != digest:
            raise ValueError("trace hash differs from native context receipt")
        turns = native["turn_meters"][thread]
        if not pricing.consistent_meter(list(turns.values()), native["usage"][thread], tuple(FIELDS.values())):
            raise ValueError("incomplete or inconsistent terminal meter")
        with path.open() as lines:
            rows, totals, contexts, ambiguity = scan((json.loads(l) for l in lines), thread, set(turns))
        if contexts != native["turn_contexts"][thread]:
            raise ValueError("context/model binding differs")
        if any(totals[k] != native["usage"][thread][v] for k, v in FIELDS.items()):
            raise ValueError("response totals differ from terminal meter")
        cumulative = Counter()
        for turn in sorted(turns, key=lambda t: turns[t]["usage_seq"]):
            for _, row_turn, usage in rows:
                if row_turn == turn:
                    cumulative.update(usage)
            if any(cumulative[k] != turns[turn]["total"][v] for k, v in FIELDS.items()):
                raise ValueError("response/turn cumulative meters differ")
        models = {c["model"] for c in contexts.values()}
        if len(models) != 1:
            raise ValueError("mixed-model cumulative meter cannot be split")
        model = next(iter(models))
        thread_usd = 0.0
        for label, turn, usage in rows:
            value = pricing.model_cost(model, {FIELDS[k]: v for k, v in usage.items()})
            if value is None:
                raise ValueError("unpriced response model")
            all_categories[label]["responses"] += 1
            all_categories[label]["usd"] += value
            thread_usd += value
        expected = pricing.model_cost(model, native["usage"][thread])
        if abs(thread_usd - expected) > 1e-9:
            raise ValueError("response prices differ from terminal price")
        threads.append({"thread_sha256": hashlib.sha256(thread.encode()).hexdigest(),
            "trace_sha256": digest, "model": model, "responses": len(rows), "usd": thread_usd,
            "ambiguous_responses": ambiguity})
    pure = {"write_stdin_only", "outer_wait_only", "sleep_only", "mixed_poll_only"}
    return {"attempt": str(folder), "native_sha256": hashlib.sha256(native_path.read_bytes()).hexdigest(),
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(), "threads": threads,
        "responses": sum(v["responses"] for v in all_categories.values()),
        "usd": sum(v["usd"] for v in all_categories.values()), "categories": dict(all_categories),
        "poll_only_responses": sum(v["responses"] for k, v in all_categories.items() if k in pure),
        "poll_only_usd": sum(v["usd"] for k, v in all_categories.items() if k in pure),
        "ambiguous_responses": sum(t["ambiguous_responses"] for t in threads)}


class Fixtures(unittest.TestCase):
    def test_classification(self):
        def c(s): return {"name": "exec", "input": s}
        self.assertEqual(category([c('await tools.write_stdin({session_id:1,chars:""})')]), "write_stdin_only")
        for s in ('await tools.write_stdin({session_id:1})', 'await tools.write_stdin({chars:"x"})',
                  'await tools.write_stdin({chars:unknown})',
                  'const x=\'chars:""\';await tools.write_stdin(x)',
                  'await tools.write_stdin({other:\'chars:""\'})',
                  'await tools.write_stdin({chars:"",...unknown})',
                  'text(\'tools.write_stdin({chars:""})\')',
                  'const x=/tools.write_stdin({chars:""})/;',
                  'const work=tools;await work.exec_command({cmd:"x"});await tools.write_stdin({chars:""})',
                  'const result=`${await tools.exec_command({cmd:"x"})}`;await tools.write_stdin({chars:""})',
                  'await tools.exec_command({cmd:"x"});await tools.write_stdin({chars:""})'):
            self.assertEqual(category([c(s)]), "unproven_or_work")
        wait = {"name": "wait", "arguments": '{"cell_id":"1","yield_time_ms":300000}'}
        self.assertEqual(category([wait]), "outer_wait_only")
        self.assertEqual(category([wait, {"name": "sleep", "arguments": '{"duration_ms":1000}'}]), "mixed_poll_only")
        self.assertEqual(category([{"name":"wait", "arguments":'{"cell_id":"1","terminate":true}'}]), "unproven_or_work")

    def test_fork_and_new_turn(self):
        def boundary(t): return {"type":"event_msg", "payload":{"type":"task_started","turn_id":t}}
        call = {"type":"response_item", "payload":{"type":"custom_tool_call","name":"exec", "input":'await tools.exec_command({cmd:"work"})'}}
        poll = {"type":"response_item", "payload":{"type":"function_call","name":"wait", "arguments":'{"cell_id":"1"}'}}
        def meter(t, response): return {"type":"token_usage_record", "payload":{"thread_id":"child", "turn_id":t,"response_id":response,"usage":dict.fromkeys(FIELDS,0)}}
        rows, _, _, ambiguity = scan([boundary("parent-turn"),call,boundary("child-turn"),poll,meter("child-turn","r1"),boundary("child-turn2"),meter("child-turn2","r2")], "child", {"child-turn","child-turn2"})
        self.assertEqual([r[0] for r in rows], ["outer_wait_only","no_tool_call"])
        self.assertEqual(ambiguity,0)
        rows, _, _, ambiguity = scan([meter("child-turn","r1")], "child", {"child-turn"})
        self.assertEqual(rows[0][0],"ambiguous_ownership")
        self.assertEqual(ambiguity,1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempts", nargs="*", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=[__file__], exit=True)
    if not args.attempts:
        parser.error("provide sealed attempt directories")
    pricing, pricing_path = load_pricing()
    print(json.dumps({"method":"owned-turn-poll-responses-v1",
        "method_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pricing_sha256":hashlib.sha256(pricing_path.read_bytes()).hexdigest(),
        "rate_card":pricing.MODEL_RATE_CARD,
        "limits":"Tool-only response classification, not avoidable cost. Ambiguous ownership excluded. Fork history fenced by native-owned task/context turn IDs. No reasoning content inspected.",
        "attempts":[measure(p.resolve(), pricing) for p in args.attempts]}, indent=2))
