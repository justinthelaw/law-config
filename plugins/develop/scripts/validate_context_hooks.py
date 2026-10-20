"""Offline checks for the one bundled context guard; never import its code."""
import ast
from pathlib import Path
import stat

from generate_codex_manifest import load_json

HOOK_PATH = "./hooks/hooks.json"
MAX_CONFIG_BYTES = 64 * 1024
MAX_HANDLER_BYTES = 256 * 1024
EVENTS = ("PreToolUse", "PostToolUse")
BOOTSTRAP = ("import os,runpy;runpy.run_path(os.path.join(os.environ['PLUGIN_ROOT'],"
             "'hooks','context_guard.py'),run_name='__main__')")
# A closed, reviewed Python 3.10 stdlib import set establishes this handler's
# self-contained import closure. Adding a module requires updating this check.
HANDLER_IMPORTS = {"__future__", "argparse", "json", "os", "re", "shlex", "stat", "sys", "runpy",
                   "hashlib", "pathlib", "time", "uuid", "fcntl"}


def packaged_text(root, relative, limit):
    """Reject links/special files before reading, then bound the bytes read.

    This is static artifact validation, not protection against concurrent
    malicious filesystem replacement after validation.
    """
    path = root / relative
    current = root
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("source or parent is a symlink")
        expected = stat.S_ISREG if index == len(parts) - 1 else stat.S_ISDIR
        if not expected(mode):
            raise ValueError("require regular source files and directory parents")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("source escapes its package")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"source exceeds {limit} bytes")
    return data.decode("utf-8")


def expected_group(event):
    suffix = f' -I -B -c "{BOOTSTRAP}" --event {event} --max-bytes 20000'
    return {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": "python3" + suffix,
            "commandWindows": "py -3" + suffix,
            "timeout": 5,
            "statusMessage": "Checking tool context size",
        }],
    }


def validate_config(config):
    if not isinstance(config, dict) or set(config) != {"description", "hooks"}:
        raise ValueError("require only description and hooks; no bypass or trust settings")
    if not isinstance(config["description"], str) or not 0 < len(config["description"]) <= 256:
        raise ValueError("require a short description string")
    events = config["hooks"]
    if not isinstance(events, dict) or set(events) != set(EVENTS):
        raise ValueError("require exactly PreToolUse and PostToolUse")
    for event in EVENTS:
        groups = events[event]
        if groups != [expected_group(event)]:
            raise ValueError(f"{event}: require one synchronous fixed context guard command on each platform")
        # JSON equality treats 5.0 like 5; the schema requires integer seconds.
        if type(groups[0]["hooks"][0]["timeout"]) is not int:
            raise ValueError(f"{event}: require integer timeout 5")


def validate_handler(text, filename):
    tree = ast.parse(text, filename=filename, feature_version=(3, 10))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ValueError("handler must be self-contained; relative imports are unsupported")
            names = [node.module]
        else:
            names = []
        if any(name not in HANDLER_IMPORTS for name in names):
            raise ValueError("handler imports must use the reviewed Python 3.10 stdlib set; no local dependencies")
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in {"__import__", "eval", "exec", "compile"}):
            raise ValueError("dynamic code/imports prevent static handler import validation")


def validate_context_hooks(root):
    errors = []
    for relative, limit in (("hooks/hooks.json", MAX_CONFIG_BYTES),
                            ("hooks/context_guard.py", MAX_HANDLER_BYTES),
                            ("hooks/response_store.py", MAX_HANDLER_BYTES)):
        try:
            text = packaged_text(root, relative, limit)
            if relative.endswith(".json"):
                validate_config(load_json(text))
            else:
                validate_handler(text, str(root / relative))
        except (OSError, ValueError, RuntimeError, SyntaxError, RecursionError) as exc:
            errors.append(f"{relative}: {exc}")
    return errors
