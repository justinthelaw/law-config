"""Retire only the named run's completed, disposable offline workers."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import threading
import time

import campaign as C
import composite
from records import invalid_assessment, terminal_assessment

E = C.E


def terminals(root):
    for record in root.glob("attempts/*/*/result.json"):
        yield record.parent, record.parent.parent.name, record, record
    for native in root.glob("judges/*/*/*/native.json"):
        folder = native.parent
        judgment = folder.parent / "judgment.json"
        if terminal_assessment(E.read(native)) and judgment.is_file() and E.read(judgment)["native"] == C.receipt(native):
            yield folder, folder.parent.parent.name, native, judgment
        elif invalid_assessment(folder):
            yield folder, folder.parent.parent.name, native, folder / "invalid.json"


def expected_mounts(folder, key, record):
    if record.name == "result.json":
        row = C.read_attempt(folder.parents[2].name, key, folder.name)
        if row["state"] in ("interrupted", "unreleased") or not row.get("workspace"):
            return None
        work = E.STATE / row["workspace"]
    else:
        work = E.STATE / E.read(folder / "packet.json")["workspace"]
    if not work.is_relative_to(E.CACHE / "volatile") or work.resolve() != work:
        raise ValueError("unexpected worker workspace")
    cli = Path(os.environ["BENCHMARK_CODEX"]).resolve(strict=True)
    mounts = {"/work": (str(work), True), "/deps": (str(E.dependencies(E.CASES[key])), False),
              "/setup": (str(folder / "guest-setup"), False), "/skills": (str(folder / "profile/skills"), False),
              "/guest/opt/codex/codex": (str(cli), False),
              "/guest/opt/codex/codex-resources/bwrap": (str(cli.parent.parent / "codex-resources/bwrap"), False)}
    if folder.name == "develop" and record.name == "result.json":
        installed, = (folder / "profile/plugins/cache/law-config/develop").iterdir()
        mounts["/plugin"] = (str(installed), False)
        plan = E.read(folder.parents[2] / "plan.json")
        companion = plan["runtime"]["treatment"].get("companion")
        if companion:
            path = folder / "profile/plugins/cache/superpowers-local/superpowers/6.3.0"
            composite.verify_component(path, companion)
            mounts["/companion"] = (str(path), False)
    return mounts


def verify_worker(data, cid, label, image, expected):
    config = data["HostConfig"]
    mounts = data["Mounts"]
    observed = {m["Destination"]: (m["Source"], m["RW"]) for m in mounts}
    if (data["Id"] != cid or data["Config"]["Labels"].get("law-native-trial") != label
            or data["Image"] != image or not config["AutoRemove"] or config["NetworkMode"] != "none"
            or not config["ReadonlyRootfs"] or config.get("Privileged") or config.get("Devices")
            or any(m["Type"] != "bind" for m in mounts) or len(observed) != len(mounts) or observed != expected):
        raise ValueError("worker identity, limits or mounts differ; leaving the worker running")


def retire(name):
    root = C.run_dir(name)
    if not (root / "plan.json").is_file():
        return
    plan = E.read(root / "plan.json")
    terminal = {E.guest.label(row[0]).split("=", 1)[1]: row for row in terminals(root)}
    if not terminal:
        return
    rows = subprocess.check_output(["docker", "ps", "--no-trunc", "--filter", "label=law-native-trial",
                                   "--format", '{{.ID}} {{.Label "law-native-trial"}}'], text=True)
    for line in rows.splitlines():
        cid, label = line.split()
        if label not in terminal:
            continue
        folder, key, record, marker = terminal[label]
        expected = expected_mounts(folder, key, record)
        if expected is None:
            continue
        raw = subprocess.run(["docker", "inspect", cid], capture_output=True)
        if raw.returncode:
            continue
        data, = json.loads(raw.stdout)
        verify_worker(data, cid, label, plan["references"][key]["workers"]["worker"], expected)
        digest, marker_digest = E.sha(record), E.sha(marker)
        stopped = subprocess.run(["docker", "stop", "--time", "5", cid], capture_output=True)
        if stopped.returncode:
            if subprocess.run(["docker", "inspect", cid], capture_output=True).returncode:
                continue
            raise RuntimeError(stopped.stderr.decode(errors="replace"))
        if (E.sha(record), E.sha(marker)) != (digest, marker_digest):
            raise ValueError("terminal receipt changed")
        E.save(root / "retirements" / (cid + ".json"), {"worker_id": cid, "trial": str(folder.relative_to(root)),
               "worker_image": data["Image"], "record_sha256": digest, "terminal_marker_sha256": marker_digest,
               "stopped_unix": time.time()})


@contextmanager
def manage(name):
    stop = threading.Event()
    errors = []
    def watch():
        while not stop.wait(120):
            try:
                retire(name)
            except (ValueError, OSError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
                errors.append(exc)
                return
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        if errors:
            raise errors[0]
        retire(name)
