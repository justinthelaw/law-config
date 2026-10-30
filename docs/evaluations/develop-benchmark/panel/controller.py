"""Qualify actual CLI inventories, restrict native command hooks, and retain usage."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import composite
import environment as E
import stock

STOCK = E.host.Server
STOCK_EXECUTE = E.host.execute


def execution_boundary():
    files=[E.HERE/"controller.py",E.HERE/"stock.py",E.HERE/"environment.py",E.HERE/"platform.json",
           *(E.WORKFLOW/f for f in ("host.py","run.py","guest.py","lab.py"))]
    if E.host.COMPANION:
        files.append(E.HERE/"composite.py")
    return {p.name:E.sha(p) for p in files}


def execute(server, prompt, skill, row, budget):
    server.run_record=row
    server.task_input = [{"type": "text", "text": ("$" + E.host.SKILL + " " if skill else "") + prompt}]
    if skill:
        server.task_input.append({"type": "skill", "name": E.host.SKILL, "path": skill})
    try:
        STOCK_EXECUTE(server,prompt,skill,row,budget)
    finally:
        root=row.get("root")
        row["final"]=server.final_answers.get(root,"")
        row["final_phase"]="final_answer" if root in server.final_answers else None
        if (server.session/"release.json").exists() and "_released" in row:
            with (server.session/"proposal.md").open("x") as out:
                out.write(row.get("final",""))


def select_treatment():
    lock = E.read(Path(os.environ.get("PANEL_TREATMENT_LOCK", E.HERE / "treatment.json")))
    root = Path(os.environ.get("PANEL_PLUGIN_CHECKOUT", E.ROOT)).resolve(strict=True)
    E.host.ROOT = root
    E.host.PACKAGE_SHA256 = lock["package_sha256"]
    E.host.COMPANION = lock.get("companion")
    E.host.COMPANION_SOURCE = os.environ.get("PANEL_COMPANION_SOURCE")
    if E.host.COMPANION and not E.host.COMPANION_SOURCE:
        raise ValueError("set PANEL_COMPANION_SOURCE to the pinned source checkout")
    E.host.PLUGIN_HOOK_HASH = lock["plugin_hook_sha256"]
    E.host.HOOKS = lock["hook_sha256"]
    hooks = E.read(root / "plugins/develop/hooks/hooks.json")["hooks"]
    if set(hooks) != {"PreToolUse", "PostToolUse"}:
        raise ValueError("unreviewed native hook boundary")
    for event, groups in hooks.items():
        if len(groups) != 1 or groups[0]["matcher"] != "*" or len(groups[0]["hooks"]) != 1:
            raise ValueError("unreviewed native hook shape")
        entry = groups[0]["hooks"][0]
        expected = ('python3 -I -B -c "import os,runpy;runpy.run_path(os.path.join('
                    "os.environ['PLUGIN_ROOT'],'hooks','context_guard.py'),run_name='__main__')"
                    f'" --event {event} --max-bytes 20000')
        if entry["type"] != "command" or entry["command"] != expected:
            raise ValueError("review and version the isolated launcher before using changed hook commands")
    return lock


class AuditedServer(STOCK):
    """Only the pinned hook interpreter gets the checkout and plugin, both read-only."""
    def __init__(self, cli, home, work, deadline):
        self.session = home.parent
        if (self.session / "controller-only").is_file() and not (work / ".git").exists():
            E.lab.call("git", "init", "-q", work)
        self.run_record=None
        self.event_seq=0
        self.turn_meters={}
        self.final_answers={}
        self.hook_box = "law-panel-hook-" + uuid.uuid4().hex
        candidate = home / "plugins/cache/law-config/develop"
        versions = list(candidate.glob("*"))
        installed = versions[0] if len(versions) == 1 else None
        if len(versions) > 1:
            raise ValueError("ambiguous installed Develop package")
        self.installed = installed
        command = ["docker","run","-d","--rm","--name",self.hook_box,"--network","none",
                   "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
                   "--user",f"{os.getuid()}:{os.getgid()}","--memory","192m","--pids-limit","64",
                   "--mount",f"type=bind,src={work},dst={work},readonly",
                   "--tmpfs","/tmp:rw,noexec,size=8m","-w",str(work)]
        if installed:
            command += ["--mount",f"type=bind,src={installed},dst={installed},readonly",
                        "-e","PLUGIN_ROOT="+str(installed)]
        E.lab.call(*command,E.PANEL["images"]["python"],"sleep","infinity",capture_output=True)
        bindir = self.session / "hook-dispatch"
        bindir.mkdir()
        counter = self.session / "hook-calls.log"
        counter.touch()
        wrapper = bindir / "python3"
        wrapper.write_text("#!/bin/sh\nif [ \"${PLUGIN_ROOT:-}\" != "+shlex.quote(str(installed or "no-package"))
                           +' ]; then exec /usr/bin/python3 "$@"; fi\n'
                           +"printf '.\\n' >> "+shlex.quote(str(counter))+"\nexec docker exec -i "
                           +self.hook_box+' python3 "$@"\n')
        wrapper.chmod(0o700)
        inherit = {k:os.environ.get(k) for k in ("PATH","BASH_ENV","ZDOTDIR","SHELL")}
        setup = 'export PATH='+shlex.quote(str(bindir))+':"$PATH"\n'
        (bindir/"bash-env").write_text(setup)
        (bindir/".zshenv").write_text(setup)
        try:
            proof = 'import os,sys; assert not os.path.exists(sys.argv[1]); assert set(os.listdir("/sys/class/net")) == {"lo"}; assert not any(x in os.environ for x in ("OPENAI_API_KEY","GITHUB_TOKEN","CODEX_API_KEY")); print("sealed")'
            E.lab.call("docker","exec",self.hook_box,"python3","-c",proof,str(self.session / "profile/config.toml"),
                       capture_output=True, timeout=15)
            os.environ.update(PATH=str(bindir)+os.pathsep+inherit["PATH"],BASH_ENV=str(bindir/"bash-env"),
                              ZDOTDIR=str(bindir),SHELL="/bin/bash")
            super().__init__(cli, home, work, deadline)
        except Exception:
            E.lab.call("docker","stop","-t","1",self.hook_box,capture_output=True)
            raise
        finally:
            for key, value in inherit.items():
                if value is None: os.environ.pop(key,None)
                else: os.environ[key]=value

    def inventory(self, installed):
        # Keep checked-in source and AGENTS.md identical while disabling optional project skills in both arms.
        listed=self.rpc("skills/list",{"cwds":[self.work],"forceReload":True})["data"]
        disabled=[]
        for group in listed:
            for skill in group["skills"]:
                if skill["enabled"] and skill["scope"]=="repo" and Path(skill["path"]).is_relative_to(self.work):
                    change=self.rpc("skills/config/write",{"path":skill["path"],"enabled":False})
                    if change["effectiveEnabled"]:
                        raise ValueError("optional repository skill stayed enabled: "+skill["name"])
                    disabled.append(Path(skill["path"]))
        if disabled:
            self.rpc("skills/list",{"cwds":[self.work],"forceReload":True})
        selected = super().inventory(installed)
        plugins = self.rpc("plugin/list",{"cwds":[self.work],"marketplaceKinds":["local"]})
        active = sorted(p["id"] for m in plugins["marketplaces"] for p in m["plugins"]
                        if p["installed"] and p["enabled"])
        skills = [s for row in self.rpc("skills/list",{"cwds":[self.work]})["data"]
                  for s in row["skills"] if s["enabled"]]
        hooks = [h for row in self.rpc("hooks/list",{"cwds":[self.work]})["data"]
                 for h in row["hooks"] if h["enabled"]]
        expected = composite.expected_plugins("develop" if installed else "control", E.host.COMPANION)
        if E.host.COMPANION:
            paths = {s["name"]:s["path"] for s in skills}
            companion = self.home / "plugins/cache/superpowers-local/superpowers/6.3.0"
            composite.verify_inventory("develop" if installed else "control", active, paths, installed, companion, E.host.COMPANION["skills"])
        E.save(self.session / "inventory.json", {
            "plugins":active,"skills":[s["name"] for s in skills],"disabled_repository_skills":[p.parent.name for p in disabled],
            "stock":stock.inventory(self, installed, skills, disabled),"hooks":[
                {"event":h["eventName"],"plugin":h.get("pluginId"),"trust":h["trustStatus"],
                 "digest":h.get("currentHash"),"source":h.get("sourcePath"),"key":h.get("key")} for h in hooks],
            "mcp":self.rpc("mcpServerStatus/list",{})["data"],"hook_sandbox":"offline read-only workspace and pinned plugin",
            "config_sha256":E.sha(self.home / "config.toml"),"plugin_install_sha256":E.host.PACKAGE_SHA256 if installed else None})
        managed = [h for h in hooks if h.get("pluginId") is None]
        pins = E.read(E.HERE / "platform.json")["managed_hook_sha256"]
        if (active != expected or sorted(h["currentHash"] for h in managed) != sorted(pins)
                or any(h["trustStatus"] != "managed" or h["sourcePath"] != "/<requirements-composition>/requirements.toml" for h in managed)
                or any(h.get("pluginId") not in (None,E.host.PLUGIN) for h in hooks)):
            raise ValueError(f"unexpected plugin or hook inventory: {active} {[(h.get('eventName'),h.get('pluginId'),h.get('sourcePath')) for h in hooks]}")
        return selected

    def send(self, obj):
        method = obj.get("method")
        if self.run_record is not None and method == "thread/start":
            params = obj["params"]
            if set(params) != {"model", "cwd", "approvalPolicy", "sandbox", "ephemeral", "environments"}:
                raise ValueError("unexpected thread-start option")
            self.run_record["thread_start"] = params
        if self.run_record is not None and method == "turn/start":
            params = obj["params"]
            if (set(params) != {"threadId", "input", "effort"} or params["input"] != self.task_input
                    or params["effort"] != E.PANEL["effort"]):
                raise ValueError("unexpected model input")
            E.save(self.session / "turn-input.json", params)
        super().send(obj)

    def next(self):
        msg=super().next()
        self.event_seq+=1
        method=msg.get("method")
        params=msg.get("params",{})
        thread=params.get("threadId")
        turn=params.get("turnId") or (params.get("turn") or {}).get("id")
        if method == "item/completed" and self.run_record is not None:
            item = params["item"]
            if item.get("type") in ("mcpToolCall", "dynamicToolCall", "webSearch"):
                raise ValueError("unexpected external tool call: " + item["type"])
            if self.installed and item.get("type") in ("agentMessage", "subAgentActivity", "collabAgentToolCall"):
                # Private evidence of actual review instructions, dispositions and terminal messages.
                with (self.session / "review-events.jsonl").open("a") as log:
                    log.write(json.dumps({"thread": thread, "turn": turn, "item": item}) + "\n")
        if thread and turn:
            meter=self.turn_meters.setdefault(thread,{}).setdefault(turn,{})
            if method=="thread/tokenUsage/updated":
                meter.update(usage_seq=self.event_seq,total=params["tokenUsage"]["total"])
            elif method=="item/completed" and params["item"].get("type")=="agentMessage":
                meter["message_seq"]=self.event_seq
                if params["item"].get("phase")=="final_answer":
                    self.final_answers[thread]=params["item"]["text"]
            elif method=="turn/completed":
                meter.update(terminal_seq=self.event_seq,status=params["turn"]["status"])
        return msg

    def close(self):
        try:
            if self.run_record is not None:
                # An ordered local RPC drains notifications already queued after the root terminal event.
                self.deadline=time.monotonic()+8
                try:
                    self.rpc("mcpServerStatus/list",{})
                except (TimeoutError,RuntimeError,OSError):
                    pass
                row=self.run_record
                row["turn_meters"]=self.turn_meters
                for thread,turns in self.turn_meters.items():
                    metered=[m for m in turns.values() if "total" in m]
                    if metered:
                        row.setdefault("usage",{})[thread]=max(metered,key=lambda m:m["usage_seq"])["total"]
            super().close()
        finally:
            E.lab.call("docker","stop","-t","1",self.hook_box,capture_output=True,timeout=20)


def activate():
    E.configure()
    select_treatment()
    E.host.Server = AuditedServer
    E.host.execute = execute


def verify_hooks(folder, row, arm):
    if row.get("state") == "blocked" and row.get("error") and not (folder / "inventory.json").exists():
        raise ValueError(row["error"])
    inv = E.read(folder / "inventory.json")
    real = len((folder / "hook-calls.log").read_text().splitlines())
    observed = len(row.get("hooks", []))
    if inv["plugins"] != composite.expected_plugins(arm, E.host.COMPANION) or inv["mcp"]:
        raise ValueError("treatment inventory changed")
    if arm == "control" and (real or observed or any(h["plugin"] for h in inv["hooks"])):
        raise ValueError("control ran a hook")
    if arm == "develop" and (real < observed or (observed == 0 and row.get("commands"))):
        raise ValueError(f"hook dispatch evidence missing ({real} isolated executions, {observed} native receipts)")
    return {"isolated_hook_calls":real,"native_hook_receipts":observed}


def qualification():
    from results import usage
    folder = E.STATE / "qualification" / str(time.time_ns())
    folder.mkdir(parents=True)
    ok = True
    for arm in ("control", "develop"):
        dest = folder / arm
        dest.mkdir()
        row = E.native.probe(arm, dest)
        try:
            row["hook_attestation"] = verify_hooks(dest, row, arm)
            row["token_coverage"]=usage(row)["coverage"]
            if row["token_coverage"]!="complete" or row.get("final_phase")!="final_answer":
                raise ValueError("missing terminal answer or complete per-thread cost receipt")
        except (ValueError,OSError) as e:
            row.update(passed=False,attestation_error=str(e))
        E.save(dest/"probe.json",row)
        ok &= row["passed"]
        print(arm, row["passed"], row.get("error",row.get("attestation_error","")),flush=True)
    evidence={str(path.relative_to(folder)):E.sha(path) for arm in ("control","develop")
              for path in (folder/arm/"probe.json",folder/arm/"inventory.json",folder/arm/"hook-calls.log")
              if path.is_file()}
    E.save(folder/"qualification.json",{"passed":ok,"package_sha256":E.host.PACKAGE_SHA256, **({"treatment_identity":composite.identity(select_treatment())} if E.host.COMPANION else {}),
            "cli":E.host.CLI_SHA256,"controller_sha256":E.sha(E.HERE/"controller.py"),
            "python_worker":E.worker_ids(E.CASES["packaging"]),"execution_boundary":execution_boundary(),
            "evidence":evidence})
    return ok


if __name__ == "__main__":
    activate()
    raise SystemExit(0 if qualification() else 2)
