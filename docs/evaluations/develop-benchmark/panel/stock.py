"""Check what a native worker actually loads before releasing a model turn."""
from hashlib import sha256
from pathlib import Path
import subprocess
import tomllib

import environment as E


SYSTEM_SKILLS = {"imagegen", "openai-docs", "review-agent", "skill-creator", "skill-installer"}
FORBIDDEN_INSTRUCTIONS = ("instructions", "developer_instructions", "model_instructions_file",
                          "compact_prompt", "experimental_compact_prompt_file", "personality")


def inventory(server, installed, skills, disabled):
    work = Path(server.work)
    root = subprocess.check_output(["git", "-C", work, "rev-parse", "--show-toplevel"], text=True).strip()
    if Path(root).resolve() != work.resolve():
        raise ValueError("worker must be the root of its own repository")
    if any((server.home / f).exists() for f in ("AGENTS.override.md", "AGENTS.md")):
        raise ValueError("unexpected profile instructions")
    if {s["name"] for s in skills if Path(s["path"]).is_relative_to(server.home / "skills/.system")} != SYSTEM_SKILLS:
        raise ValueError("unexpected stock skill inventory")

    apps = server.rpc("app/list", {})
    servers = server.rpc("mcpServerStatus/list", {})
    if any(result["data"] or result.get("nextCursor") for result in (apps, servers)):
        raise ValueError("worker exposed apps or MCP servers")

    settings = server.rpc("config/read", {"cwd": server.work, "includeLayers": True})
    config = settings["config"]
    if any(config.get(k) for k in FORBIDDEN_INSTRUCTIONS):
        raise ValueError("effective worker configuration injects instructions")
    layers = []
    for layer in settings["layers"]:
        if layer.get("disabledReason"):
            continue
        name = layer["name"]
        kind = name["type"]
        if kind == "project":
            directory = work / ".codex"
            if (name.get("dotCodexFolder") != str(directory) or directory.is_symlink()
                    or not directory.is_dir() or any(directory.iterdir())
                    or layer.get("config") != {} or layer.get("version") != "sha256:" + sha256(b"{}").hexdigest()):
                raise ValueError("unreviewed project configuration layer")
        elif kind not in {"user", "enterpriseManaged", "system"}:
            raise ValueError("unreviewed configuration layer: " + kind)
        layers.append(kind)
    with (server.home / "config.toml").open("rb") as source:
        authored = tomllib.load(source)
    expected = {
        "model": E.PANEL["model"], "model_reasoning_effort": E.PANEL["effort"],
        "web_search": "disabled", "approval_policy": "never", "sandbox_mode": "workspace-write",
        "features": {"apps": False, "memories": False, "remote_plugin": False},
        "plugins": {"_default": {"enabled": False}},
    }
    if installed:
        expected["plugins"][E.host.PLUGIN] = {"enabled": True}
        expected["marketplaces"] = {"law-config": {"source_type": "local", "source": str(server.home.parent / "marketplace")}}
        if E.host.COMPANION:
            expected["plugins"][E.host.COMPANION_ID] = {"enabled": True}
            expected["marketplaces"]["superpowers-local"] = {"source_type":"local", "source":str(Path(E.host.COMPANION_SOURCE).resolve())}
        expected["hooks"] = {"state": {f"{E.host.PLUGIN}:hooks/hooks.json:{event}:0:0":
            {"trusted_hash": "sha256:" + value} for event, value in E.host.HOOKS.items()}}
    if "projects" in authored:
        expected["projects"] = {server.work: {"trust_level": "trusted"}}
    if disabled:
        expected["skills"] = {"config": [{"path": str(p), "enabled": False} for p in disabled]}
    if authored != expected:
        raise ValueError("unexpected authored profile settings: " +
                         str([k for k in authored.keys() | expected.keys() if authored.get(k) != expected.get(k)]))
    names = {"AGENTS.override.md", "AGENTS.md"}
    tracked = subprocess.check_output(["git", "-C", work, "ls-files", "-z"]).split(b"\0")
    docs = {}
    for item in tracked:
        rel = Path(item.decode("utf-8", "surrogateescape"))
        if rel.name in names:
            path = work / rel
            if not path.resolve(strict=True).is_relative_to(work):
                raise ValueError("repository instructions escape the pinned tree")
            docs[rel.as_posix()] = E.sha(path)
    return {"apps": [], "mcp": [], "config_layers": layers, "profile_keys": sorted(authored),
            "repository_instructions_sha256": docs, "global_instructions": [], "stock_skills": sorted(SYSTEM_SKILLS)}
