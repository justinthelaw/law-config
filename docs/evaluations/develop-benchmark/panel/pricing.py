"""Frozen Codex Standard proposal estimates in USD per million tokens."""
SOL_RATES = {"uncached_input": 2, "cached_input": 0.1, "output": 10}


def sol_cost(tokens):
    return model_cost("gpt-6.1-sol", tokens)


# Frozen public Codex Standard rates; this estimate excludes agreement-specific
# discounts, speed/regional multipliers and additional feature charges.
MODEL_POLICY = "natural-standard-v2"
MODEL_RATE_CARD = {
    "source": "https://help.openai.com/en/articles/20001415-chatgpt-rate-card-enterprise-token-based-pricing",
    "verified_utc": "2026-10-30T12:41:43Z", "basis": "Codex Standard USD per 1M tokens; estimate, not invoice",
    "rates": {model: dict(zip(("uncached_input", "cached_input", "output"), rates)) for model, rates in (
        ("gpt-6.1-sol", (2, .10, 10)), ("gpt-6.1-terra", (1, .05, 5)),
        ("gpt-6-astra", (10, 1, 50)), ("gpt-6-sol", (2, .20, 10)),
        ("gpt-6-luna", (.10, .01, .50)), ("gpt-5.6-sol", (4, .40, 20)),
        ("gpt-5.6-terra", (2, .20, 12)), ("gpt-5.6-luna", (.20, .02, 1.20)),
        ("gpt-6-astra-law", (12.50, 1.25, 62.50)))}}


def model_cost(model, tokens):
    rates = MODEL_RATE_CARD["rates"].get(model)
    if rates is None:
        return None
    inp, cached, output = (tokens.get(k) for k in ("inputTokens", "cachedInputTokens", "outputTokens"))
    if any(type(v) is not int or v < 0 for v in (inp, cached, output)):
        return None
    if cached > inp:
        raise ValueError("cached input exceeds input")
    return ((inp - cached) * rates["uncached_input"] + cached * rates["cached_input"]
            + output * rates["output"]) / 1e6


def consistent_meter(turns, tokens, keys):
    """Require coherent completed cumulative snapshots before pricing a thread."""
    if (not turns or not isinstance(tokens, dict) or set(tokens) != set(keys)
            or any(type(v) is not int or v < 0 for v in tokens.values())):
        return False
    seqs = ("message_seq", "usage_seq", "terminal_seq")
    if any(not isinstance(t, dict) or t.get("status") != "completed"
           or any(type(t.get(k)) is not int or t[k] <= 0 for k in seqs)
           or t["usage_seq"] < t["message_seq"] or t["terminal_seq"] < t["message_seq"]
           or not isinstance(t.get("total"), dict) or set(t["total"]) != set(keys)
           or any(type(v) is not int or v < 0 for v in t["total"].values())
           or t["total"]["cachedInputTokens"] > t["total"]["inputTokens"]
           or t["total"]["reasoningOutputTokens"] > t["total"]["outputTokens"]
           or t["total"]["totalTokens"] != t["total"]["inputTokens"] + t["total"]["outputTokens"]
           for t in turns) or any(len({t[k] for t in turns}) != len(turns) for k in seqs):
        return False
    ordered = sorted(turns, key=lambda t:t["usage_seq"])
    return (ordered[-1]["total"] == tokens and not any(
        a["total"][k] > b["total"][k] for a,b in zip(ordered,ordered[1:]) for k in keys))


def model_partitions(proof):
    """Reconcile priced thread aggregates; never split a mixed-model meter."""
    partitions = {}
    for thread in proof:
        if not thread["bound"] or not thread["meter_consistent"]:
            continue
        model, tokens = thread["model"], thread["tokens"]
        if model_cost(model, tokens or {}) is None:
            continue
        part = partitions.setdefault(model, {"threads": 0, "tokens": dict.fromkeys(tokens, 0)})
        part["threads"] += 1
        for key, value in tokens.items():
            part["tokens"][key] += value
    return partitions


def partitions_cost(partitions):
    return sum(model_cost(model, part["tokens"]) for model, part in partitions.items()) if partitions else None

NATURAL_PROTOCOLS = frozenset({"pr-quality-pytest-entry-natural-v1", "pr-quality-confirmation-natural-v1"})
CONFIRMATION_PROTOCOLS = frozenset({"pr-quality-confirmation-v1", "pr-quality-confirmation-natural-v1"})


def root_default(start, proof):
    """Tri-state proof that the authenticated first root turn started Sol Medium."""
    if not isinstance(start, dict) or set(start) != {"thread", "requested_model", "effective_model", "requested_effort"}:
        return None
    if any(not isinstance(start.get(k), str) or not start[k] for k in start):
        return None
    if (not isinstance(proof, list) or len(start["thread"]) != 64
            or set(start["thread"]) - set("0123456789abcdef")):
        return None
    roots = [row for row in proof if isinstance(row, dict) and row.get("thread") == start["thread"]]
    if (len(roots) != 1 or not isinstance(roots[0].get("trace_sha256"), str)
            or len(roots[0]["trace_sha256"]) != 64 or set(roots[0]["trace_sha256"]) - set("0123456789abcdef")):
        return None
    turns = roots[0].get("turns")
    if not isinstance(turns, list) or not turns or any(
            not isinstance(t, dict) or type(t.get("message_seq")) is not int or t["message_seq"] <= 0 for t in turns):
        return None
    if len({t["message_seq"] for t in turns}) != len(turns):
        return None
    first = min(turns, key=lambda t: t["message_seq"])
    if not first.get("model") or not first.get("effort"):
        return None
    return (start["requested_model"] == start["effective_model"] == first["model"] == "gpt-6.1-sol"
            and start["requested_effort"] == first["effort"] == "medium")
