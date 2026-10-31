"""Assessor-only preservation of the declared fresh pytest console entry."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET

NODE = "testing/test_mark_expression.py::test_empty_is_false"
TEST_SHA256 = "6efe7b62b6f0231671c445688fd7cdf721f72005a535591d0820bfcc4d121f20"


def stop(status, code, **details):
    print(json.dumps({"pytest_entry": status, **details}, sort_keys=True), flush=True)
    raise SystemExit(code)


try:
    from pip._vendor.distlib import DistlibException
    from pip._vendor.distlib.scripts import ScriptMaker
    from pip._vendor.distlib.util import get_export_entry
except ImportError as error:
    stop("environment_unavailable", 2, error=str(error))
if "pytest" in sys.modules:
    stop("environment_preloaded", 2)
try:
    entries = tomllib.loads(Path("pyproject.toml").read_text())["project"]["scripts"]
    entries = {name: entries[name] for name in ("pytest", "py.test")}
    for name, value in entries.items():
        if not isinstance(value, str):
            raise ValueError("console mapping must be a string")
        export = get_export_entry(name + " = " + value)
        if not export or not export.prefix or not export.suffix:
            raise ValueError("console mapping must name a callable")
except (OSError, KeyError, ValueError, DistlibException) as error:
    stop("invalid_entry_metadata", 42, error=str(error))
try:
    unchanged = hashlib.sha256(Path(NODE.split("::")[0]).read_bytes()).hexdigest() == TEST_SHA256
except OSError:
    unchanged = False
if not unchanged:
    stop("fixture_unavailable", 2, node=NODE)
with tempfile.TemporaryDirectory(prefix="pytest-entry-") as folder:
    maker = ScriptMaker(None, str(Path(folder) / "bin"))
    maker.variants = {""}
    checked = set()
    for name, value in entries.items():
        if value in checked:
            continue
        checked.add(value)
        maker.make(name + " = " + value)
        launcher = Path(folder) / "bin" / name
        report = Path(folder) / (name + ".xml")
        command = [str(launcher), "--junitxml=" + str(report), NODE]
        try:
            result = subprocess.run(command, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                    capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as error:
            stop("environment_unavailable", 2, error=str(error))
        print(result.stdout + result.stderr, end="", flush=True)
        missing = re.search(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)", result.stderr)
        if missing and missing[1].split(".")[0] not in {"pytest", "_pytest"}:
            stop("dependency_unavailable", 2, module=missing[1])
        if result.returncode in (2, 3, 4) or result.returncode < 0:
            stop("execution_unestablished", 2, returncode=result.returncode)
        if result.returncode:
            stop("selection_failed" if result.returncode == 5 else "behavior_failed", 42,
                 returncode=result.returncode, entry=value, node=NODE)
        try:
            cases = list(ET.parse(report).getroot().iter("testcase"))
            valid = (len(cases) == 1 and cases[0].get("name") == NODE.split("::")[1]
                     and cases[0].get("classname", "").endswith("testing.test_mark_expression")
                     and not any(child.tag in {"failure", "error", "skipped"} for child in cases[0]))
        except (OSError, ET.ParseError):
            valid = False
        if not valid:
            stop("selection_failed", 42, node=NODE)
        stop_record = {"pytest_entry": "passed", "entry": value, "node": NODE,
                       "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
                       "junit": report.read_text()}
        print(json.dumps(stop_record, sort_keys=True), flush=True)
