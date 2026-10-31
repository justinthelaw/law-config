"""A fresh native Codex controller; model tools run only in the selected offline executor."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time

import guest
from lab import ROOT, SPEC, call, digest

CLI_SHA256 = "c1eecb4b2304cb0e077a673231e30c9d759dec8fea4a6b8818078865e392fa90"
BWRAP_SHA256 = "77360cb751ccedc5971391444ac86a8a33c15b04d6b4a6fe45f5d25496e62c4c"
PACKAGE_SHA256 = "c619be0cc2668f45fc51c3a8582af64581a83c993b83981e776fa45f90e10fbb"
SKILL = "develop:develop"
PLUGIN = "develop@law-config"
COMPANION = None
COMPANION_SOURCE = None
COMPANION_ID = "superpowers@superpowers-local"
# Reviewed native definition hashes for this exact package. Never trust a newly discovered hash.
HOOKS = {
    "pre_tool_use": "577de816fa43a06f65e002de2a4c9b2a495d03170ba103334b40e9b62bb18368",
    "post_tool_use": "23adcfd4b4d58ca43a6609e83228ecc2822681fd1349ecb31bfc2a0d6d91020c",
}
PLUGIN_HOOK_HASH = "ac6e190ec47b97ea91894054c7ec9b8e5c32d2f6c9caed08a0666ba58d46b2a8"


def package_hash(root, files):
    h = hashlib.sha256()
    for p in sorted(files, key=lambda file: file.relative_to(root).as_posix()):
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + bytes.fromhex(digest(p)))
    return h.hexdigest()


def install(home, cli):
    marketplace = home.parent / "marketplace"
    source = ROOT / "plugins/develop"
    listing = call("git", "-C", ROOT, "ls-files", "-z", "--", "plugins/develop",
                   stdout=subprocess.PIPE).stdout
    files = [ROOT / os.fsdecode(p) for p in listing.split(b"\0") if p]
    if package_hash(source, files) != PACKAGE_SHA256:
        raise ValueError("Develop source changed; version a new experiment")
    for path in [*files, ROOT / ".agents/plugins/marketplace.json"]:
        dst = marketplace / path.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
    env = dict(os.environ, CODEX_HOME=str(home))
    with (home.parent / "plugin-install.log").open("xb") as log:
        for command in (["marketplace", "add", str(marketplace)], ["add", PLUGIN]):
            result = subprocess.run([cli, "plugin", *command, "--json"], env=env, cwd=home,
                                    stdout=subprocess.PIPE, stderr=log, timeout=90)
            if result.returncode:
                log.write(result.stdout)
                result.check_returncode()
    installed = Path(json.loads(result.stdout)["installedPath"])
    if not installed.is_relative_to(home) or package_hash(installed, (p for p in installed.rglob("*")
                                                                      if p.is_file())) != PACKAGE_SHA256:
        raise ValueError("native installation does not match the frozen package")
    with (home / "config.toml").open("a") as config:
        for event, value in HOOKS.items():
            key = f"{PLUGIN}:hooks/hooks.json:{event}:0:0"
            config.write(f'\n[hooks.state."{key}"]\ntrusted_hash = "sha256:{value}"\n')
    if COMPANION:
        import composite
        source = Path(COMPANION_SOURCE).resolve(strict=True)
        if subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip() != composite.COMMIT:
            raise ValueError("companion source commit differs")
        composite.verify_marketplace(source)
        package = source / "plugins/superpowers"
        composite.verify_component(package, COMPANION)
        with (home.parent / "companion-install.log").open("xb") as log:
            for command in (["marketplace", "add", str(source)], ["add", COMPANION_ID]):
                result = subprocess.run([cli, "plugin", *command, "--json"], env=env, cwd=home,
                                        stdout=subprocess.PIPE, stderr=log, timeout=90, check=True)
        companion = Path(json.loads(result.stdout)["installedPath"])
        if not companion.is_relative_to(home):
            raise ValueError("companion install escapes profile")
        composite.verify_component(companion, COMPANION)
    return installed


def profile(case, arm, run, work, canary=""):
    cli = Path(os.environ["BENCHMARK_CODEX"]).resolve(strict=True)
    bwrap = cli.parent.parent / "codex-resources/bwrap"
    if digest(cli) != CLI_SHA256:
        raise ValueError("select the preregistered native CLI binary (not a launcher)")
    if digest(bwrap) != BWRAP_SHA256:
        raise ValueError("the matched Codex Linux sandbox helper is required")
    home = run / "profile"
    home.mkdir(mode=0o700)
    (home / "config.toml").write_text(
        'model = "gpt-6.1-sol"\nmodel_reasoning_effort = "medium"\nweb_search = "disabled"\n'
        'approval_policy = "never"\nsandbox_mode = "workspace-write"\n'
        '[features]\napps = false\nmemories = false\nremote_plugin = false\n'
        '[plugins._default]\nenabled = false\n'
    )
    installed = install(home, cli) if arm == "develop" else None
    (home / "skills").mkdir(exist_ok=True)
    companion = home / "plugins/cache/superpowers-local/superpowers/6.3.0" if installed and COMPANION else None
    args = guest.args(case, run, work, cli, bwrap, installed, canary, companion=companion)
    (home / "environments.toml").write_text(
        'default = "worker"\ninclude_local = false\n[[environments]]\nid = "worker"\n'
        'initialize_timeout_sec = 90\nprogram = "docker"\nargs = ' + json.dumps(args[1:]) + '\n')
    return cli, home, installed


class Server:
    def __init__(self, cli, home, work, deadline):
        self.work = str(work)
        self.home = home
        self.deadline = deadline
        self.messages = queue.Queue()
        self.seq = 0
        self.process = subprocess.Popen([cli, "app-server", "--listen", "stdio://"],
                                       cwd=home, env=dict(os.environ, CODEX_HOME=str(home)),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=(home.parent / "server.log").open("a"), text=True)
        def read():
            try:
                for line in self.process.stdout:
                    self.messages.put(json.loads(line))
            finally:
                self.messages.put(None)
        threading.Thread(target=read, daemon=True).start()
        self.rpc("initialize", {"clientInfo": {"name": "develop-benchmark", "version": "1"},
                                "capabilities": {"experimentalApi": True}})
        self.send({"method": "initialized"})

    def send(self, obj):
        self.process.stdin.write(json.dumps(obj) + "\n")
        self.process.stdin.flush()

    def next(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native controller deadline")
        try:
            msg = self.messages.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("native controller deadline") from exc
        if msg is None:
            raise RuntimeError("native controller exited before the terminal event")
        if "method" in msg and "id" in msg:
            # No live human, escalations, new tools or outside actions in this experiment.
            self.send({"id": msg["id"], "error": {"code": -32601, "message": "Unavailable offline"}})
        return msg

    def rpc(self, method, params):
        self.seq += 1
        self.send({"id": self.seq, "method": method, "params": params})
        while True:
            msg = self.next()
            if msg.get("id") == self.seq and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]

    def inventory(self, installed):
        active = [s for row in self.rpc("skills/list", {"cwds": [self.work]})["data"]
                  for s in row["skills"] if s["enabled"]]
        for s in active:
            path = Path(s["path"])
            if not (path.is_relative_to(self.home / "skills/.system") or
                    (installed and path.is_relative_to(installed / "skills")) or
                    (installed and COMPANION and path.is_relative_to(self.home / "plugins/cache/superpowers-local/superpowers/6.3.0/skills"))):
                raise ValueError(f"unexpected skill in the native profile: {s['name']}")
        skills = [s for s in active if s["name"] == SKILL]
        hooks = [h for row in self.rpc("hooks/list", {"cwds": [self.work]})["data"] for h in row["hooks"]
                 if h.get("pluginId") == PLUGIN]
        if self.rpc("mcpServerStatus/list", {})["data"]:
            raise ValueError("unexpected external MCP server in the trial")
        if installed:
            if len(skills) != 1 or Path(skills[0]["path"]) != installed / "skills/develop/SKILL.md":
                raise ValueError("treatment skill was not discovered")
            if (len(hooks) != 2 or {h["eventName"] for h in hooks} != {"preToolUse", "postToolUse"}
                    or any(not h["enabled"] or h["trustStatus"] != "trusted" for h in hooks)):
                raise ValueError("reviewed treatment hooks are unavailable")
            for h in hooks:
                event = h["key"].split(":")[-3]
                if h["currentHash"] != f"sha256:{HOOKS[event]}/sha256:{PLUGIN_HOOK_HASH}":
                    raise ValueError("treatment hook or package digest changed")
            return skills[0]["path"]
        if skills or hooks:
            raise ValueError("control discovered Develop")
        return None

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)


def execute(server, prompt, skill, record, budget):
    thread = server.rpc("thread/start", {"model": SPEC["model"], "cwd": server.work,
                        "approvalPolicy": "never", "sandbox": "workspace-write", "ephemeral": False,
                        "environments": [{"environmentId": "worker", "cwd": server.work}]})
    root = thread["thread"]["id"]
    if thread["model"] != SPEC["model"]:
        raise ValueError("provider changed the requested model")
    if record.get("pricing_policy") == "natural-sol-v1":
        record["effective_root_model"] = thread["model"]
    inputs = [{"type": "text", "text": ("$" + SKILL + " " if skill else "") + prompt}]
    if skill:
        inputs.append({"type": "skill", "name": SKILL, "path": skill})
    record.update(root=root, threads=[root], usage={}, commands=[], hooks=[], children=[], items={}, final="")
    # The id for the turn is unnecessary. Observe early events including the start response.
    record["_released"] = time.monotonic()
    record["task_start_unix"] = time.time()
    record["budget_seconds"] = budget
    server.deadline = record["_released"] + budget
    server.seq += 1
    server.send({"id": server.seq, "method": "turn/start",
                 "params": {"threadId": root, "input": inputs, "effort": SPEC["effort"]}})
    root_finished = False
    finished_children = set()
    while True:
        msg = server.next()
        method, params = msg.get("method"), msg.get("params", {})
        thread_id = params.get("threadId")
        if msg.get("id") == server.seq and "error" in msg:
            raise RuntimeError(str(msg["error"]))
        if method == "thread/started":
            child = params["thread"]["id"]
            if child not in record["threads"]:
                record["threads"].append(child)
        if thread_id and thread_id not in record["threads"]:
            record["threads"].append(thread_id)
        if method == "thread/tokenUsage/updated":
            record["usage"][thread_id] = params["tokenUsage"]["total"]
        if method == "hook/completed":
            run = params["run"]
            if "plugins/cache/law-config/develop/" in run.get("sourcePath", ""):
                record["hooks"].append([run["eventName"], run["status"]])
                record.setdefault("hook_threads", {}).setdefault(thread_id, []).append(
                    [run["eventName"], run["status"]])
                if run["status"] == "failed":
                    record.setdefault("hook_errors", []).append(str(run["entries"])[:480])
        if method == "item/completed":
            item = params["item"]
            kind = item["type"]
            record["items"][kind] = record["items"].get(kind, 0) + 1
            if item["type"] == "commandExecution":
                record["commands"].append({"thread": thread_id, "command": item.get("command"),
                                           "exit": item.get("exitCode")})
                if record.get("qualifying"):
                    record["commands"][-1]["proofs"] = re.findall(
                        r"BENCH_PROOF ([0-9a-f]{64})", item.get("aggregatedOutput") or "")
            if item["type"] == "collabAgentToolCall":
                for child in item.get("receiverThreadIds", []):
                    if child not in record["children"]:
                        record["children"].append(child)
            if item["type"] in {"subAgentActivity", "collabAgentToolCall"}:
                record.setdefault("review_events", []).append({key: value for key, value in item.items()
                    if key in {"type", "tool", "kind", "model", "reasoningEffort", "agentPath",
                               "agentThreadId", "childThreadId", "receiverThreadIds", "agentsStates"}})
                if record.get("pricing_policy") == "natural-sol-v1":
                    record["review_events"][-1]["parentThreadId"] = thread_id
            if item["type"] == "subAgentActivity" and item.get("kind") == "started":
                child = item.get("agentThreadId") or item.get("childThreadId")
                if child and child not in record["children"]:
                    record["children"].append(child)
            if item["type"] == "subAgentActivity" and item.get("kind") in {"completed", "interrupted"}:
                finished_children.add(item["agentThreadId"])
            if item["type"] == "agentMessage" and thread_id == root:
                record["final"] = item["text"]
        if method == "error" and not params.get("willRetry", False):
            record["error"] = str(params.get("error"))
        if method == "turn/completed" and thread_id == root:
            turn = params["turn"]
            if turn["status"] != "completed":
                raise RuntimeError(str(turn.get("error") or turn["status"]))
            root_finished = True
        if method == "turn/completed" and thread_id != root:
            finished_children.add(thread_id)
        if root_finished and set(record["children"]) <= finished_children:
            return
