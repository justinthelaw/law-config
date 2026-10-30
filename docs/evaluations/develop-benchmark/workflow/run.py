#!/usr/bin/env python3
"""Qualify the native controller, run the fixed cohort, or inspect its append-only receipts."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

# Import the trusted script siblings even when Python's safe-path mode is enabled.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import guest
import host
import lab

ARMS = ("control", "develop")


def read(path):
    return json.loads(path.read_bytes())


def save(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def identity():
    files = [lab.HERE / name for name in ("cases.json", "host.py", "run.py", "lab.py", "guest.py", "report.py", "blind.py", "feasibility.py")]
    files += sorted((lab.HERE / "checks").iterdir()) + sorted((lab.HERE / "vm").iterdir())
    return hashlib.sha256(b"".join(bytes.fromhex(lab.digest(f)) for f in files if f.is_file())).hexdigest()


def runtime():
    return {"identity": identity(), "cli_sha256": host.CLI_SHA256,
            "package_sha256": host.PACKAGE_SHA256,
            "worker_images": {family: guest.image_id(next(c for c in lab.CASES.values()
                              if c["image"] == family)) for family in lab.SPEC["images"]}}


def verify_grade(grade):
    folder = (lab.STATE / grade["directory"]).resolve(strict=True)
    if folder.parent != (lab.STATE / "volatile").resolve() or read(folder / "grade.json") != grade:
        raise ValueError("grade differs from its independent grader receipt")


def admission(case):
    folder = lab.STATE / "calibration" / case["id"]
    latest = max(folder.glob("*.json"), default=None)
    if latest is None:
        raise ValueError(f"{case['id']}: no reference calibration")
    row = read(latest)
    for key, hidden in (("base", 42), ("gold", 0)):
        ref = row[key]
        verify_grade(ref)
        if (not row["admitted"] or ref["revision"] != case[key] or ref["case"] != case["id"]
                or ref["fixture_sha256"] != lab.fingerprint(case)
                or ref["image"] != lab.SPEC["images"][case["image"]]
                or ref["stages"] != {"build": 0, "native": 0, "hidden": hidden}):
            raise ValueError(f"{case['id']}: invalid or stale {key} calibration")
    return latest


def native(case, arm, run, work, prompt, nonce="", *, budget=300, capture=None):
    start = time.monotonic()
    row = {"arm": arm, "model": lab.SPEC["model"], "effort": lab.SPEC["effort"], "usd": None, "qualifying": bool(nonce)}
    server = None
    try:
        cli, home, installed = host.profile(case, arm, run, work, nonce)
        server = host.Server(cli, home, work, time.monotonic() + 120)
        skill = server.inventory(installed)
        row["skill"] = host.SKILL if skill else None
        host.execute(server, prompt, skill, row, budget)
        if arm == "develop" and row["commands"]:
            events = {event for event, status in row["hooks"] if status == "completed"}
            if row.get("hook_errors") or events != {"preToolUse", "postToolUse"}:
                raise ValueError("treatment command hooks did not complete")
        if any(item.get("kind") == "started" and
               (item.get("model"), item.get("reasoningEffort")) != (lab.SPEC["model"], lab.SPEC["effort"])
               for item in row.get("review_events", [])):
            raise ValueError("descendant model or effort changed")
        row["state"] = "completed"
    except TimeoutError as exc:
        row.update(state="timeout" if "_released" in row else "blocked", error=str(exc))
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        row.update(state="blocked", error=str(exc))
    finally:
        ended = time.monotonic()
        release = row.pop("_released", None)
        row["setup_seconds"] = (release or ended) - start
        row["wall_seconds"] = ended - release if release is not None else None
        try:
            if capture and release is not None:
                with guest.frozen(run):
                    row["snapshot_unix"] = time.time()
                    capture()
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            row.update(state="blocked", error=f"submission capture: {exc}")
        finally:
            if server:
                server.close()
    return row


def inherited_context(run, parent, child):
    logs = list((run / "profile/sessions").rglob(f"rollout-*-{child}.jsonl"))
    if len(logs) != 1:
        return False
    with logs[0].open() as stream:
        return any(event["type"] == "session_meta" and event["payload"].get("id") == parent
                   for event in map(json.loads, stream))


def probe(arm, run):
    case = lab.CASES["packaging"]
    lab.prepare(case)
    work = run / "work"
    work.mkdir()
    nonce = secrets.token_hex(16)
    (run / "controller-only").write_text(secrets.token_hex(16))
    prompt = (
        "Qualify this disposable offline executor. From your own thread run exactly "
        "`python3 -I /setup/prove.py root`. Ask a fresh subagent to inherit this entire conversation (fork_turns=all) on this same "
        "model and effort to run exactly `python3 -I /setup/prove.py child` in its own shell. "
        "Wait for it. The read-only program checks the isolated filesystem and network and writes "
        "one proof into the current checkout. Do not pass a proof to the child. Design approved."
    )
    row = native(case, arm, run, work, prompt, nonce)
    digests = {role: hashlib.sha256((nonce + role).encode()).hexdigest() for role in ("root", "child")}
    def proved(role, actors):
        path = work / (role + "-proof")
        return (path.is_file() and not path.is_symlink() and path.read_text() == digests[role]
                and any(cmd["thread"] in actors and cmd["exit"] == 0 and digests[role] in cmd.get("proofs", [])
                        for cmd in row.get("commands", [])))
    root = row.get("root")
    children = set(row.get("children", []))
    actors = children | {root}
    usage = row.get("usage", {})
    events = row.get("hook_threads", {})
    inheriting = {child for child in children if inherited_context(run, root, child)}
    row["inherited_children"] = sorted(inheriting)
    row["proofs_match"] = proved("root", {root}) and proved("child", inheriting)
    row["passed"] = bool(row["state"] == "completed" and row["proofs_match"] and children
                         and all(usage.get(actor, {}).get("totalTokens", 0) > 0 for actor in actors)
                         and (arm == "control" or all({event for event, state in events.get(actor, [])
                              if state == "completed"} == {"preToolUse", "postToolUse"} for actor in actors)))
    return row


def qualify():
    pinned = runtime()
    parent = lab.STATE / "qualification" / str(time.time_ns())
    parent.mkdir(parents=True)
    rows = {}
    for arm in ARMS:
        run = parent / arm
        run.mkdir()
        rows[arm] = probe(arm, run)
        save(run / "probe.json", rows[arm])
        print(arm, "qualified" if rows[arm]["passed"] else rows[arm].get("error", "probe failed"), flush=True)
    result = {**pinned, "passed": pinned == runtime() and all(row["passed"] for row in rows.values())}
    save(parent / "qualification.json", result)
    return result["passed"]


def start_experiment():
    qualification = max((lab.STATE / "qualification").glob("*/qualification.json"), default=None)
    if not qualification or read(qualification) != {**runtime(), "passed": True}:
        raise ValueError("native qualification is missing or stale")
    refs = {}
    for case in lab.CASES.values():
        source = admission(case)
        refs[case["id"]] = {"path": str(source.relative_to(lab.STATE)), "sha256": lab.digest(source),
                            "base": case["base"], "gold": case["gold"]}
    feasibility = {}
    for case in lab.CASES.values():
        path = max((lab.STATE / "feasibility" / case["id"]).glob("*/receipt.json"), default=None)
        if not path:
            raise ValueError(f"{case['id']}: missing cold worker verification")
        measured = read(path)
        if not measured["passed"] or any(measured[k] != case[k] for k in ("base", "build")) or (
                measured["native"] != guest.native_tests(case)) or (
                measured["worker_image"] != guest.image_id(case)):
            raise ValueError(f"{case['id']}: failed or stale cold worker verification")
        feasibility[case["id"]] = {"path": str(path.relative_to(lab.STATE)), "sha256": lab.digest(path),
            "budget_seconds": max(lab.SPEC["seconds_per_arm"], 60 * math.ceil(2 * measured["seconds"] / 60))}
    path = lab.STATE / "experiment"
    plan = {**runtime(), "qualifier": str(qualification.relative_to(lab.STATE)),
            "references": refs, "feasibility": feasibility, "order": {k: list(ARMS if i % 2 == 0 else reversed(ARMS))
                                         for i, k in enumerate(lab.CASES)}}
    if not path.exists():
        path.mkdir()
        save(path / "plan.json", plan)
    if read(path / "plan.json") != plan:
        raise ValueError("the frozen experiment or calibration changed")
    return path, plan


def frozen_plan():
    path = lab.STATE / "experiment/plan.json"
    if not path.exists():
        return None
    plan = read(path)
    if plan["identity"] != identity():
        raise ValueError("local benchmark sources differ from the frozen experiment")
    return plan


def reference(plan, case):
    pin = plan["references"][case["id"]]
    receipt = lab.STATE / pin["path"]
    if (pin["base"], pin["gold"]) != (case["base"], case["gold"]) or lab.digest(receipt) != pin["sha256"]:
        raise ValueError("reference receipt does not match the frozen experiment")
    return read(receipt)


def result(plan, case, arm):
    run = lab.STATE / "experiment" / case["id"] / arm
    release = read(run / "release.json")
    expected = dict(case=case["id"], arm=arm, identity=plan["identity"], base=case["base"], gold=case["gold"])
    expected["plan_sha256"] = lab.digest(lab.STATE / "experiment/plan.json")
    if any(release.get(k) != v for k, v in expected.items()):
        raise ValueError("release does not match the frozen experiment")
    row = read(run / "result.json")
    if (row.get("case"), row.get("arm")) != (case["id"], arm):
        raise ValueError("attempt attribution changed")
    native_path = run / "native.json"
    if native_path.exists():
        observed = read(native_path)
        for k, v in observed.items():
            if k not in {"state", "error"} and row.get(k) != v:
                raise ValueError("result differs from its native observation")
        if row["state"] != "blocked" and (row["state"], row.get("error")) != (observed["state"], observed.get("error")):
            raise ValueError("attempt status differs from its native observation")
    elif row["state"] != "blocked":
        raise ValueError("missing native observation")
    grade = row.get("grade")
    if not grade and row["state"] in {"completed", "timeout"}:
        raise ValueError("missing submission grade")
    if grade:
        patch = run / "candidate.patch"
        sha = lab.digest(patch)
        if sha != grade.get("patch_sha256"):
            raise ValueError("candidate patch differs from the graded submission")
        if patch.stat().st_size:
            verify_grade(grade)
            ref = reference(plan, case)["base"]
            if (grade["case"], grade["revision"], grade["fixture_sha256"], grade["image"]) != (
                    case["id"], case["base"], ref["fixture_sha256"], ref["image"]):
                raise ValueError("candidate used a different grader or base")
        elif grade != empty_grade(sha):
            raise ValueError("empty submission has an invalid grade")
    return row


def empty_grade(sha):
    return {"stages": dict.fromkeys(("build", "native", "hidden")), "reason": "empty submission",
            "patch_sha256": sha}


def collect_patch(case, run, work, start_commit):
    # Candidate Git hooks/config must never execute in the controller. Use the offline worker.
    args, image = lab.docker(case, work)
    script = ("git -c core.hooksPath=/dev/null add -A -- . && "
              f"git --no-pager diff --cached --no-ext-diff --no-textconv --binary {start_commit} -- .")
    with (run / "candidate.patch").open("xb") as f:
        lab.call(*args, image, "sh", "-ec", script, stdout=f, timeout=120)


def trial(case, arm, run, budget):
    run.mkdir()  # Interrupted directories are evidence. Never overwrite or repeat an arm.
    save(run / "release.json", {"case": case["id"], "arm": arm, "identity": identity(),
                                "allocated_unix": time.time(), "base": case["base"], "gold": case["gold"],
                                "plan_sha256": lab.digest(lab.STATE / "experiment/plan.json")})
    start = time.monotonic()
    row = {"case": case["id"], "arm": arm, "state": "blocked"}
    try:
        location = Path(tempfile.mkdtemp(prefix="worker-"))
        work = lab.snapshot(case, case["base"], location)
        row["workspace"] = str(work.relative_to(lab.STATE))
        start_commit = lab.call("git", "-C", work, "rev-parse", "HEAD", capture_output=True,
                                text=True).stdout.strip()
        prompt = (lab.COMMON_PROMPT + case["prompt"] + "\n\nAvailable offline verification commands:\n"
                  + case["build"] + "\n" + guest.native_tests(case))
        observed = native(case, arm, run, work, prompt, budget=budget,
                          capture=lambda: collect_patch(case, run, work, start_commit))
        save(run / "native.json", observed)
        row.update(observed)
        grading_start = time.monotonic()
        patch = run / "candidate.patch"
        if not patch.exists():
            raise ValueError(row.get("error") or "no submission was captured")
        if not patch.stat().st_size:
            row["grade"] = empty_grade(lab.digest(patch))
        else:
            row["grade"] = lab.grade(case, case["base"], patch)
        row["grading_seconds"] = time.monotonic() - grading_start
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        row.update(state="blocked", error=str(exc))
    row["end_to_end_seconds"] = time.monotonic() - start
    save(run / "result.json", row)
    print(case["id"], arm, row["state"], row.get("grade", {}).get("stages"), flush=True)
    return row


def run_cases():
    root, plan = start_experiment()
    for case in lab.CASES.values():
        for arm in plan["order"][case["id"]]:
            current = runtime()
            if current != {k: plan[k] for k in current}:
                raise ValueError("frozen runtime changed before release")
            run = root / case["id"] / arm
            run.parent.mkdir(exist_ok=True)
            if run.exists() and not (run / "result.json").exists():
                raise ValueError(f"interrupted release at {run}; retain it and stop")
            row = result(plan, case, arm) if run.exists() else trial(case, arm, run,
                plan["feasibility"][case["id"]]["budget_seconds"])
            if row["state"] == "blocked":
                raise ValueError(f"{case['id']} {arm}: infrastructure or service stop: {row.get('error')}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build-workers", "qualify", "run"))
    args = parser.parse_args()
    os.umask(0o077)
    lab.start_state()
    if args.action == "build-workers":
        for family in lab.SPEC["images"]:
            guest.build(next(case for case in lab.CASES.values() if case["image"] == family))
        raise SystemExit(0)
    raise SystemExit(0 if (qualify() if args.action == "qualify" else run_cases()) else 2)
