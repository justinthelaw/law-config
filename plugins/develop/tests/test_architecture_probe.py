"""Offline oracle calibration, not an agent trial or application benchmark."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parent / "evaluations"

# Evaluator-owned calibration implementations. Never materialize for an agent.
OWNER = '''
class LatestRequest:
    def __init__(self, transport):
        self.transport = transport
        self.pending = None
        self.token = None
        self.closed = False

    def send(self, query, on_value):
        if self.closed:
            raise RuntimeError('closed')
        if self.pending is not None:
            self.pending.cancel()
        token = object()
        self.token = token

        def receive(value):
            if self.token is token:
                self.token = None
                self.pending = None
                on_value(value)

        self.pending = self.transport.start(query, receive)

    def close(self):
        self.closed = True
        self.token = None
        if self.pending is not None:
            self.pending.cancel()
            self.pending = None
'''
CALLERS = '''
class Screen:
    def __init__(self, transport, on_value):
        self.requests = LatestRequest(transport)
        self.on_value = on_value

    def search(self, query):
        self.requests.send(query, self.on_value)

    def close(self):
        self.requests.close()
'''
ADAPTATION = '''
class Autosave:
    def __init__(self, transport, on_value):
        self.requests = LatestRequest(transport)
        self.on_value = on_value

    def submit(self, content):
        self.requests.send(content, self.on_value)

    def close(self):
        self.requests.close()
'''
INITIAL = OWNER + CALLERS
GOOD = INITIAL + ADAPTATION
# A plausible single-caller design: reuse one owner per shared transport.
BAD = GOOD.replace(
    "self.requests = LatestRequest(transport)",
    "if not hasattr(transport, 'requests'):\n"
    "            transport.requests = LatestRequest(transport)\n"
    "        self.requests = transport.requests",
)
# Narrow defects that the original probe accepted. Each changes one lifecycle rule.
BAD_COMPLETED = GOOD.replace("                self.pending = None\n", "")
BAD_COMPLETED_SAVE = (INITIAL + ADAPTATION.replace("LatestRequest", "RetainsCompleted")
                      + OWNER.replace("LatestRequest", "RetainsCompleted")
                      .replace("                self.pending = None\n", ""))
BAD_SAVE_CLOSE = GOOD + '''
original_save_close = Autosave.close
def close_all(self):
    original_save_close(self)
    for job in self.requests.transport.jobs:
        if job.cancel_count == 0:
            job.cancel()
Autosave.close = close_all
'''
BAD_LATE = GOOD.replace(
    "        def receive(value):\n            if self.token is token:",
    "        delivered = False\n"
    "        def receive(value):\n"
    "            nonlocal delivered\n"
    "            if delivered or self.closed:\n"
    "                return\n"
    "            delivered = True\n"
    "            if self.token is token or self.token is None:",
)
BAD_IDLE_CLOSE = GOOD + '''
original_save_close = Autosave.close
def close_only_pending(self):
    if self.requests.pending is not None:
        original_save_close(self)
Autosave.close = close_only_pending
'''
BAD_COMPLETED_CLOSE = BAD_IDLE_CLOSE.replace(
    "if self.requests.pending is not None:",
    "if self.requests.pending is not None or not self.requests.transport.jobs:",
)


def fixture(name):
    return json.loads((ROOT / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def module_from_source(source):
    """Execute trusted local calibration source; this is not an isolation sandbox."""
    module = types.ModuleType("calibration")
    exec(compile(source, "<offline-calibration>", "exec"), module.__dict__)
    return module


def probe_change(case, app, transport_type):
    """Held-out public behavior for an adapted app module; no internal inspection."""
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    screen.search("lookup")
    lookup = transport.jobs[-1]
    save.submit("draft 1")
    old_save = transport.jobs[-1]
    case.assertEqual(lookup.cancel_count, 0, "autosave cancelled another caller")
    save.submit("draft 2")
    new_save = transport.jobs[-1]
    case.assertEqual(old_save.cancel_count, 1)
    case.assertEqual(lookup.cancel_count, 0)
    old_save.deliver("stale save")
    lookup.deliver("found")
    lookup.deliver("duplicate lookup")
    screen.close()
    screen.close()
    case.assertEqual(lookup.cancel_count, 0, "completed screen job was cancelled")
    case.assertEqual(new_save.cancel_count, 0, "screen close cancelled autosave")
    new_save.deliver("saved")
    new_save.deliver("duplicate save")
    case.assertEqual(screen_values, ["found"])
    case.assertEqual(save_values, ["saved"])
    save.submit("draft 3")
    case.assertEqual(new_save.cancel_count, 0, "completed autosave job was cancelled")
    last_save = transport.jobs[-1]
    save.close()
    save.close()
    case.assertEqual(last_save.cancel_count, 1)
    last_save.deliver("late save")
    case.assertEqual(save_values, ["saved"])
    with case.assertRaises(RuntimeError):
        save.submit("closed")
    with case.assertRaises(RuntimeError):
        screen.search("closed")
    case.assertEqual(len(transport.jobs), 4)

    # Autosave close must leave an independently pending screen deliverable.
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    screen.search("pending screen")
    lookup = transport.jobs[-1]
    save.submit("pending save")
    pending_save = transport.jobs[-1]
    save.close()
    save.close()
    case.assertEqual(lookup.cancel_count, 0, "autosave close cancelled screen")
    case.assertEqual(pending_save.cancel_count, 1)
    pending_save.deliver("late save")
    lookup.deliver("screen survives")
    case.assertEqual(screen_values, ["screen survives"])
    case.assertEqual(save_values, [])

    # A cancelled callback's first delivery may follow replacement completion.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        transport, values = transport_type(), []
        caller = caller_type(transport, values.append)
        submit = getattr(caller, method)
        submit("old")
        old = transport.jobs[-1]
        submit("new")
        new = transport.jobs[-1]
        case.assertEqual(old.cancel_count, 1)
        new.deliver("fresh")
        old.deliver("stale")
        case.assertEqual(values, ["fresh"], "stale after replacement was published")

    # Closing fresh and completed callers is terminal even with no pending job.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        for completed in (False, True):
            transport, values = transport_type(), []
            caller = caller_type(transport, values.append)
            submit = getattr(caller, method)
            if completed:
                submit("complete")
                transport.jobs[-1].deliver("done")
            caller.close()
            caller.close()
            with case.assertRaises(RuntimeError):
                submit("closed")
            case.assertEqual(len(transport.jobs), int(completed))
            if completed:
                case.assertEqual(transport.jobs[-1].cancel_count, 0,
                                 "completed job was cancelled on close")
                transport.jobs[-1].deliver("duplicate after close")
                case.assertEqual(values, ["done"])

    # Two instances of the original caller also need independent lifetimes.
    transport = transport_type()
    left_values, right_values = [], []
    left = app.Screen(transport, left_values.append)
    right = app.Screen(transport, right_values.append)
    left.search("left")
    first = transport.jobs[-1]
    right.search("right")
    second = transport.jobs[-1]
    left.close()
    first.deliver("late left")
    second.deliver("right")
    case.assertEqual(first.cancel_count, 1)
    case.assertEqual(second.cancel_count, 0)
    case.assertEqual(left_values, [])
    case.assertEqual(right_values, ["right"])


class ArchitectureProbe(unittest.TestCase):
    def setUp(self):
        self.ownership = fixture("architecture-ownership")
        self.transport = next(item["content"] for item in self.ownership["agent"]["inputs"]
                              if item["path"] == "transport.py")

    def public_result(self, source):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in self.ownership["agent"]["inputs"]:
                (root / item["path"]).write_text(item["content"], encoding="utf-8")
            (root / "app.py").write_text(source, encoding="utf-8")
            return subprocess.run([sys.executable, "-m", "unittest", "-v", "test_public"],
                                  cwd=root, capture_output=True, text=True, timeout=10)

    def test_public_contract_rejects_unimplemented_start(self):
        source = next(item["content"] for item in self.ownership["agent"]["inputs"]
                      if item["path"] == "app.py")
        result = self.public_result(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NotImplementedError", result.stderr)

    def test_good_and_seeded_design_both_pass_initial_contract(self):
        for label, source in (("good", GOOD), ("seeded", BAD)):
            # Freeze the original owner before adding the held-out caller.
            source = source.partition("class Autosave:")[0]
            with self.subTest(source=label):
                result = self.public_result(source)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_good_owner_passes_held_out_change(self):
        probe_change(self, module_from_source(GOOD), module_from_source(self.transport).Transport)

    def test_seeded_global_owner_fails_held_out_change(self):
        with self.assertRaisesRegex(AssertionError, "autosave cancelled another caller"):
            probe_change(self, module_from_source(BAD), module_from_source(self.transport).Transport)

    def test_seeded_lifecycle_defects_fail_held_out_change(self):
        for label, source, message in (
            ("completed screen cancellation", BAD_COMPLETED, "completed screen"),
            ("completed autosave cancellation", BAD_COMPLETED_SAVE, "completed autosave"),
            ("autosave close isolation", BAD_SAVE_CLOSE, "autosave close cancelled screen"),
            ("late first delivery", BAD_LATE, "stale after replacement"),
            ("fresh terminal close", BAD_IDLE_CLOSE, "RuntimeError not raised"),
            ("completed terminal close", BAD_COMPLETED_CLOSE, "RuntimeError not raised"),
        ):
            with self.subTest(defect=label), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_simple_control_needs_only_decided_function_edit(self):
        original = fixture("architecture-simple")["agent"]["inputs"][0]["content"]
        candidate = original.replace('return f"{count} item"',
                                     'return "1 item" if count == 1 else f"{count} items"')
        before, after = module_from_source(original), module_from_source(candidate)
        self.assertNotEqual(before.item_label(2), "2 items")
        for count, label in ((0, "0 items"), (1, "1 item"), (2, "2 items"), (100, "100 items")):
            self.assertEqual(after.item_label(count), label)
        self.assertEqual(len(original.splitlines()), len(candidate.splitlines()))

    def test_public_fixtures_validate_and_materialize_without_graders(self):
        helper_path = ROOT.parents[1] / "scripts" / "evaluation.py"
        # Item 1 supplies this shared helper when the stack is assembled.
        spec = importlib.util.spec_from_file_location("evaluation", helper_path)
        evaluation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluation)
        for name in ("architecture-ownership", "architecture-simple"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                public = fixture(name)
                evaluation.validate_fixture(public)
                hashes = evaluation.materialize(public, Path(directory) / "agent")
                self.assertEqual(set(hashes), {item["path"] for item in public["agent"]["inputs"]})
                self.assertNotIn("held_out_change", public)
                self.assertFalse(any("grader" in path or "probe" in path for path in hashes))


if __name__ == "__main__":
    unittest.main()
