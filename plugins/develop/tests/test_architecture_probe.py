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
BAD_PAYLOAD = INITIAL + ADAPTATION.replace(
    "self.requests.send(content, self.on_value)",
    "self.requests.send('discarded content', self.on_value)",
)
BAD_SHARED_SAVE = INITIAL + ADAPTATION.replace(
    "self.requests = LatestRequest(transport)",
    "if not hasattr(transport, 'autosave_requests'):\n"
    "            transport.autosave_requests = LatestRequest(transport)\n"
    "        self.requests = transport.autosave_requests",
)
# Narrow defects that the original probe accepted. Each changes one lifecycle rule.
BAD_COMPLETED = GOOD.replace("                self.pending = None\n", "")
BAD_COMPLETED_SAVE = (INITIAL + ADAPTATION.replace("LatestRequest", "RetainsCompleted")
                      + OWNER.replace("LatestRequest", "RetainsCompleted")
                      .replace("                self.pending = None\n", ""))
# Screen retains completed jobs until close, so only its next search is defective.
BAD_SCREEN_RESUBMIT = (
    OWNER + CALLERS.replace("LatestRequest", "RetainsUntilClose") + ADAPTATION
    + OWNER.replace("LatestRequest", "RetainsUntilClose")
    .replace("                self.pending = None\n", "")
    .replace("    def close(self):\n",
             "    def close(self):\n"
             "        if self.token is None:\n"
             "            self.pending = None\n")
)
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
# Retaining cancelled job history is benign; cancelling that history again is not.
RETAIN_CANCELLED = GOOD + '''
class RetainsCancelled(LatestRequest):
    def __init__(self, transport):
        super().__init__(transport)
        self.cancelled = []

    def send(self, query, on_value):
        previous = self.pending
        super().send(query, on_value)
        if previous is not None:
            self.cancelled.append(previous)

    def close(self):
        super().close()

LatestRequest = RetainsCancelled
'''
BAD_RECANCEL_SUBMIT = RETAIN_CANCELLED.replace(
    "        previous = self.pending",
    "        for job in self.cancelled:\n"
    "            job.cancel()\n"
    "        previous = self.pending",
)
BAD_RECANCEL_CLOSE = RETAIN_CANCELLED.replace(
    "        super().close()",
    "        for job in self.cancelled:\n"
    "            job.cancel()\n"
    "        super().close()",
)
BAD_REVERSE_CALLER = (
    OWNER + CALLERS.replace(
        "    def search(self, query):",
        "    def search(self, query):\n"
        "        save = getattr(self.requests.transport, 'save_requests', None)\n"
        "        if save is not None and save.pending is not None:\n"
        "            save.pending.cancel()",
    ) + ADAPTATION.replace(
        "        self.requests = LatestRequest(transport)",
        "        self.requests = LatestRequest(transport)\n"
        "        transport.save_requests = self.requests",
    )
)
BAD_SCREEN_CALLBACK = OWNER + CALLERS.replace(
    "self.on_value = on_value", "type(self).on_value = staticmethod(on_value)",
) + ADAPTATION
BAD_SAVE_CALLBACK = INITIAL + ADAPTATION.replace(
    "self.on_value = on_value", "type(self).on_value = staticmethod(on_value)",
)
BAD_PENDING_SCREEN_CLOSE = (
    OWNER + CALLERS.replace(
        "    def close(self):",
        "    def close(self):\n"
        "        save = getattr(self.requests.transport, 'save_requests', None)\n"
        "        if self.requests.pending is not None and save is not None:\n"
        "            if save.pending is not None:\n"
        "                save.pending.cancel()",
    ) + ADAPTATION.replace(
        "        self.requests = LatestRequest(transport)",
        "        self.requests = LatestRequest(transport)\n"
        "        transport.save_requests = self.requests",
    )
)
BAD_DUPLICATE_RESET = GOOD.replace(
    "        def receive(value):\n            if self.token is token:",
    "        self.delivered = False\n"
    "        succeeded = False\n"
    "        def receive(value):\n"
    "            nonlocal succeeded\n"
    "            if self.closed:\n"
    "                return\n"
    "            if self.token is token or (succeeded and not self.delivered):\n"
    "                succeeded = self.delivered = True",
)
# Registration alone is benign; cancelling a later instance's work is the defect.
REGISTER_CALLERS = GOOD.replace(
    "        self.on_value = on_value",
    "        self.on_value = on_value\n"
    "        key = type(self).__name__\n"
    "        if not hasattr(transport, key):\n"
    "            setattr(transport, key, [])\n"
    "        self.peers = getattr(transport, key)\n"
    "        self.peers.append(self)",
)
BAD_FIRST_CALLER = REGISTER_CALLERS.replace(
    "        self.requests.send(",
    "        if self is self.peers[0]:\n"
    "            for peer in self.peers[1:]:\n"
    "                if peer.requests.pending is not None:\n"
    "                    peer.requests.pending.cancel()\n"
    "        self.requests.send(",
)
BAD_SECOND_CLOSE = REGISTER_CALLERS.replace(
    "        self.requests.close()",
    "        first = self.peers[0]\n"
    "        if self is not first and first.requests.pending is not None:\n"
    "            first.requests.pending.cancel()\n"
    "        self.requests.close()",
)
RETAIN_CLOSED_JOB = GOOD.replace(
    "        self.closed = True\n",
    "        if self.pending is not None:\n"
    "            self.closed_job = self.pending\n"
    "        self.closed = True\n",
)
BAD_CLOSED_SUBMIT = RETAIN_CLOSED_JOB.replace(
    "        if self.closed:\n            raise RuntimeError('closed')",
    "        if self.closed:\n"
    "            if hasattr(self, 'closed_job'):\n"
    "                self.closed_job.cancel()\n"
    "            raise RuntimeError('closed')",
)
BAD_SAVE_COMPLETION = OWNER + CALLERS.replace(
    "        self.requests = LatestRequest(transport)",
    "        self.requests = LatestRequest(transport)\n"
    "        transport.screen_requests = self.requests",
) + ADAPTATION.replace(
    "        self.requests.send(content, self.on_value)",
    "        def publish(value):\n"
    "            screen = getattr(self.requests.transport, 'screen_requests', None)\n"
    "            if screen is not None and screen.pending is not None:\n"
    "                screen.pending.cancel()\n"
    "            self.on_value(value)\n"
    "        self.requests.send(content, publish)",
)
BAD_PEER_COMPLETION = REGISTER_CALLERS.replace(
    "        self.on_value = on_value",
    "        def publish(value):\n"
    "            for peer in self.peers:\n"
    "                if peer is not self:\n"
    "                    if peer.requests.pending is not None:\n"
    "                        peer.requests.pending.cancel()\n"
    "            on_value(value)\n"
    "        self.on_value = publish",
)
BAD_REVERSE_PEER_COMPLETION = BAD_PEER_COMPLETION.replace(
    "if peer is not self:", "if peer is not self and self is self.peers[-1]:",
)
# Keeping a completed-job reference is benign; cancelling a peer's reference is not.
RETAIN_COMPLETED_PEERS = REGISTER_CALLERS.replace(
    "                self.pending = None",
    "                self.completed = self.pending\n"
    "                self.pending = None",
)
BAD_COMPLETED_PEER_SUBMIT = RETAIN_COMPLETED_PEERS.replace(
    "        self.requests.send(",
    "        for peer in self.peers:\n"
    "            completed = getattr(peer.requests, 'completed', None)\n"
    "            if peer is not self and completed is not None:\n"
    "                completed.cancel()\n"
    "        self.requests.send(",
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
    case.assertEqual(old_save.query, "draft 1", "autosave payload was changed")
    case.assertEqual(lookup.cancel_count, 0, "autosave cancelled another caller")
    save.submit("draft 2")
    new_save = transport.jobs[-1]
    case.assertEqual(new_save.query, "draft 2", "autosave payload was changed")
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
    case.assertEqual(last_save.query, "draft 3", "autosave payload was changed")
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

    # Autosave success must leave an independently pending Screen untouched.
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    screen.search("pending screen")
    lookup = transport.jobs[-1]
    save.submit("successful save")
    transport.jobs[-1].deliver("saved")
    case.assertEqual(lookup.cancel_count, 0, "autosave completion cancelled pending screen")
    lookup.deliver("found")
    case.assertEqual(save_values, ["saved"])
    case.assertEqual(screen_values, ["found"])

    # Starting Screen after Autosave must also preserve the other caller's work.
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    save.submit("pending save")
    pending_save = transport.jobs[-1]
    screen.search("later screen")
    lookup = transport.jobs[-1]
    case.assertEqual(pending_save.cancel_count, 0, "screen cancelled pending autosave")
    screen.close()
    screen.close()
    case.assertEqual(lookup.cancel_count, 1)
    case.assertEqual(pending_save.cancel_count, 0, "pending screen close cancelled autosave")
    pending_save.deliver("save survives")
    lookup.deliver("late screen")
    case.assertEqual(save_values, ["save survives"])
    case.assertEqual(screen_values, [])

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
        # Starting more work must not cancel the job that already completed.
        submit("next")
        case.assertEqual(new.cancel_count, 0, "completed job was cancelled on next request")
        case.assertEqual(old.cancel_count, 1, "cancelled job was cancelled again on submit")
        case.assertEqual(len(transport.jobs), 3)
        new.deliver("duplicate after successor")
        case.assertEqual(values, ["fresh"], "completed callback repeated after successor started")
        transport.jobs[-1].deliver("next value")
        case.assertEqual(values, ["fresh", "next value"])
        caller.close()
        caller.close()
        case.assertEqual(old.cancel_count, 1, "cancelled job was cancelled again on close")

    # Closed callers reject new work without repeating cleanup in any start state.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        for state in ("fresh", "completed", "pending"):
            transport, values = transport_type(), []
            caller = caller_type(transport, values.append)
            submit = getattr(caller, method)
            if state != "fresh":
                submit("work")
            if state == "completed":
                transport.jobs[-1].deliver("done")
            caller.close()
            caller.close()
            if state == "pending":
                case.assertEqual(transport.jobs[-1].cancel_count, 1)
            with case.assertRaises(RuntimeError):
                submit("closed")
            case.assertEqual(len(transport.jobs), int(state != "fresh"))
            if state == "pending":
                case.assertEqual(transport.jobs[-1].cancel_count, 1,
                                 "rejected request cancelled closed work again")
                transport.jobs[-1].deliver("late after rejection")
                case.assertEqual(values, [])
            if state == "completed":
                case.assertEqual(transport.jobs[-1].cancel_count, 0,
                                 "completed job was cancelled on close")
                transport.jobs[-1].deliver("duplicate after close")
                case.assertEqual(values, ["done"])

    # Each caller type needs independent lifetimes between its own instances.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        for delivery_order in ((0, 1), (1, 0)):
            transport = transport_type()
            left_values, right_values = [], []
            left = caller_type(transport, left_values.append)
            right = caller_type(transport, right_values.append)
            getattr(left, method)("left")
            first = transport.jobs[-1]
            getattr(right, method)("right")
            second = transport.jobs[-1]
            case.assertEqual(first.cancel_count, 0, "second caller cancelled first")
            completed = (first, second)
            for index in delivery_order:
                completed[index].deliver(("left", "right")[index])
                case.assertEqual([job.cancel_count for job in completed], [0, 0],
                                 "callback cancelled peer work")
            case.assertEqual(left_values, ["left"], "live caller callback was misrouted")
            case.assertEqual(right_values, ["right"], "live caller callback was misrouted")
            # Start another pair to check close isolation while both jobs are pending.
            getattr(left, method)("left pending")
            case.assertEqual([job.cancel_count for job in completed], [0, 0],
                             "submission cancelled completed peer work")
            first = transport.jobs[-1]
            getattr(right, method)("right pending")
            case.assertEqual([job.cancel_count for job in completed], [0, 0],
                             "submission cancelled completed peer work")
            second = transport.jobs[-1]
            getattr(left, method)("left replacement")
            replacement = transport.jobs[-1]
            case.assertEqual(first.cancel_count, 1)
            case.assertEqual(second.cancel_count, 0, "first caller cancelled second")
            left.close()
            first.deliver("late left")
            replacement.deliver("late replacement")
            second.deliver("right survives")
            case.assertEqual(first.cancel_count, 1)
            case.assertEqual(replacement.cancel_count, 1)
            case.assertEqual(second.cancel_count, 0)
            case.assertEqual(left_values, ["left"])
            case.assertEqual(right_values, ["right", "right survives"])

        # Reverse close order with fresh instances: the first stays live.
        transport = transport_type()
        left_values, right_values = [], []
        left = caller_type(transport, left_values.append)
        right = caller_type(transport, right_values.append)
        getattr(left, method)("left pending")
        first = transport.jobs[-1]
        getattr(right, method)("right pending")
        second = transport.jobs[-1]
        right.close()
        right.close()
        case.assertEqual(first.cancel_count, 0, "second caller close cancelled first")
        case.assertEqual(second.cancel_count, 1)
        second.deliver("late right")
        first.deliver("left survives")
        case.assertEqual(left_values, ["left survives"])
        case.assertEqual(right_values, [])



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

    def test_autosave_payload_and_instance_defects_are_detected(self):
        for source, message in ((BAD_PAYLOAD, "autosave payload"),
                                (BAD_SHARED_SAVE, "second caller cancelled first")):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_completed_screen_job_is_not_cancelled_on_next_search(self):
        with self.assertRaisesRegex(AssertionError, "completed job was cancelled on next request"):
            probe_change(self, module_from_source(BAD_SCREEN_RESUBMIT),
                         module_from_source(self.transport).Transport)

    def test_retained_history_is_benign(self):
        for source in (RETAIN_CANCELLED, RETAIN_CLOSED_JOB):
            with self.subTest(source=source):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_caller_registration_is_benign(self):
        for source in (REGISTER_CALLERS, RETAIN_COMPLETED_PEERS):
            with self.subTest(source=source):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_peer_jobs_survive_completion_and_later_submissions(self):
        for source, message in (
            (BAD_PEER_COMPLETION, "callback cancelled peer work"),
            (BAD_REVERSE_PEER_COMPLETION, "callback cancelled peer work"),
            (BAD_COMPLETED_PEER_SUBMIT, "submission cancelled completed peer work"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_second_caller_close_does_not_cancel_first(self):
        with self.assertRaisesRegex(AssertionError, "second caller close cancelled first"):
            probe_change(self, module_from_source(BAD_SECOND_CLOSE),
                         module_from_source(self.transport).Transport)

    def test_rejected_request_and_completion_do_not_cancel_other_work(self):
        for source, message in (
            (BAD_CLOSED_SUBMIT, "rejected request cancelled closed work again"),
            (BAD_SAVE_COMPLETION, "autosave completion cancelled pending screen"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_pending_close_duplicate_and_reverse_instance_defects_are_detected(self):
        for source, message in (
            (BAD_PENDING_SCREEN_CLOSE, "pending screen close cancelled autosave"),
            (BAD_DUPLICATE_RESET, "completed callback repeated after successor started"),
            (BAD_FIRST_CALLER, "first caller cancelled second"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_recancellation_and_caller_routing_defects_are_detected(self):
        for source, message in (
            (BAD_RECANCEL_SUBMIT, "cancelled job was cancelled again on submit"),
            (BAD_RECANCEL_CLOSE, "cancelled job was cancelled again on close"),
            (BAD_REVERSE_CALLER, "screen cancelled pending autosave"),
            (BAD_SCREEN_CALLBACK, "live caller callback was misrouted"),
            (BAD_SAVE_CALLBACK, "live caller callback was misrouted"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
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
