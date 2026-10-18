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
BAD_IDLE_PEER_CLOSE = REGISTER_CALLERS.replace(
    "        self.requests.close()",
    "        if not self.requests.closed and self.requests.pending is None:\n"
    "            for peer in self.peers:\n"
    "                if peer is not self and peer.requests.pending is not None:\n"
    "                    peer.requests.pending.cancel()\n"
    "        self.requests.close()",
)
BAD_COMPLETED_PEER_CLOSE = RETAIN_COMPLETED_PEERS.replace(
    "        self.requests.close()",
    "        for peer in self.peers:\n"
    "            completed = getattr(peer.requests, 'completed', None)\n"
    "            if peer is not self and completed is not None:\n"
    "                completed.cancel()\n"
    "        self.requests.close()",
)
BAD_REJECTED_PEER = REGISTER_CALLERS.replace(
    "        self.requests.send(",
    "        if self.requests.closed:\n"
    "            for peer in self.peers:\n"
    "                if peer is not self and peer.requests.pending is not None:\n"
    "                    peer.requests.pending.cancel()\n"
    "        self.requests.send(",
)
BAD_EXTRA_PEER_JOB = REGISTER_CALLERS.replace(
    "        self.requests.send(",
    "        if len(self.peers) > 1:\n"
    "            self.requests.transport.start('extra', lambda value: None)\n"
    "        self.requests.send(",
)
BAD_REPEATED_STALE = GOOD.replace(
    "        def receive(value):\n            if self.token is token:",
    "        deliveries = 0\n"
    "        succeeded = False\n"
    "        def receive(value):\n"
    "            nonlocal deliveries, succeeded\n"
    "            deliveries += 1\n"
    "            if self.token is token or (not succeeded and deliveries == 2 and not self.closed):\n"
    "                succeeded = True",
)
BAD_REJECTED_COMPLETED_PEER = RETAIN_COMPLETED_PEERS.replace(
    "        self.requests.send(",
    "        if self.requests.closed:\n"
    "            for peer in self.peers:\n"
    "                completed = getattr(peer.requests, 'completed', None)\n"
    "                if peer is not self and completed is not None:\n"
    "                    completed.cancel()\n"
    "        self.requests.send(",
)
REGISTER_MIXED_CALLERS = REGISTER_CALLERS.replace("key = type(self).__name__", "key = 'callers'")
BAD_MIXED_IDLE_CLOSE = REGISTER_MIXED_CALLERS.replace(
    "        self.requests.close()",
    "        if type(self).__name__ == 'Autosave' and not self.requests.closed:\n"
    "            if self.requests.pending is None:\n"
    "                for peer in self.peers:\n"
    "                    if type(peer).__name__ == 'Screen' and peer.requests.pending is not None:\n"
    "                        peer.requests.pending.cancel()\n"
    "        self.requests.close()",
)
BAD_AUTOSAVE_FIRST_OWNER = REGISTER_MIXED_CALLERS.replace(
    "        self.peers.append(self)",
    "        self.peers.append(self)\n"
    "        if type(self).__name__ == 'Screen' and type(self.peers[0]).__name__ == 'Autosave':\n"
    "            self.requests = self.peers[0].requests",
)
BAD_IDLE_CLOSE_JOB = REGISTER_CALLERS.replace(
    "        self.requests.close()",
    "        if len(self.peers) > 1 and not self.requests.closed:\n"
    "            if self.requests.pending is None:\n"
    "                self.requests.transport.start('close job', lambda value: None)\n"
    "        self.requests.close()",
)
BAD_REPEATED_CLOSE_JOB = BAD_IDLE_CLOSE_JOB.replace(
    "len(self.peers) > 1 and not self.requests.closed",
    "len(self.peers) > 1 and self.requests.closed",
)
BAD_IDLE_CALLBACK_JOB = REGISTER_CALLERS.replace(
    "        self.on_value = on_value",
    "        def publish(value):\n"
    "            if any(peer is not self and peer.requests.closed for peer in self.peers):\n"
    "                self.requests.transport.start('callback job', lambda result: None)\n"
    "            on_value(value)\n"
    "        self.on_value = publish",
)
BAD_IDLE_CALLBACK_COMPLETED = RETAIN_COMPLETED_PEERS.replace(
    "        self.on_value = on_value",
    "        def publish(value):\n"
    "            for peer in self.peers:\n"
    "                completed = getattr(peer.requests, 'completed', None)\n"
    "                if peer is not self and peer.requests.closed and completed is not None:\n"
    "                    completed.cancel()\n"
    "            on_value(value)\n"
    "        self.on_value = publish",
)


# The same operation invariants apply with live peers and either construction order.
BAD_REVERSE_PENDING_MIXED = REGISTER_MIXED_CALLERS.replace(
    "        self.requests.close()",
    "        if isinstance(self, Screen) and isinstance(self.peers[0], Autosave):\n"
    "            if self.requests.pending is not None:\n"
    "                for peer in self.peers:\n"
    "                    if peer is not self and peer.requests.pending is not None:\n"
    "                        peer.requests.pending.cancel()\n"
    "        self.requests.close()",
)
COUNT_DELIVERIES = GOOD.replace(
    "        def receive(value):\n            if self.token is token:",
    "        deliveries, succeeded = 0, False\n"
    "        def receive(value):\n"
    "            nonlocal deliveries, succeeded\n"
    "            deliveries += 1\n"
    "            if self.token is token:\n"
    "                succeeded = True",
)
BAD_DUPLICATE_AFTER_CLOSE = COUNT_DELIVERIES.replace(
    "if self.token is token:",
    "if self.token is token or (self.closed and not succeeded and deliveries == 2):",
)
BAD_LIVE_CALLBACK_JOB = BAD_IDLE_CALLBACK_JOB.replace(
    "any(peer is not self and peer.requests.closed for peer in self.peers)",
    "len(self.peers) > 1 and all(not peer.requests.closed for peer in self.peers)",
)
BAD_PEER_PAYLOAD = REGISTER_CALLERS.replace(
    "self.requests.send(query,", "self.requests.send('changed query' if len(self.peers) > 1 else query,",
).replace(
    "self.requests.send(content,", "self.requests.send('changed content' if len(self.peers) > 1 else content,",
)
BAD_PENDING_CLOSE_JOB = BAD_IDLE_CLOSE_JOB.replace(
    "if self.requests.pending is None:", "if self.requests.pending is not None:",
)
BAD_DUPLICATE_PENDING = COUNT_DELIVERIES.replace(
    "if self.token is token:",
    "if self.token is token or (not succeeded and deliveries == 2 and self.pending is not None):",
)
BAD_THIRD_PENDING = GOOD.replace(
    "        if self.pending is not None:\n            self.pending.cancel()\n        token = object()",
    "        if self.pending is not None and not getattr(self, 'replaced_pending', False):\n"
    "            self.pending.cancel()\n"
    "            self.replaced_pending = True\n"
    "        token = object()",
).replace(
    "                self.pending = None",
    "                self.pending = None\n"
    "                self.replaced_pending = False",
)


def fixture(name):
    return json.loads((ROOT / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def module_from_source(source):
    """Execute trusted local calibration source; this is not an isolation sandbox."""
    module = types.ModuleType("calibration")
    exec(compile(source, "<offline-calibration>", "exec"), module.__dict__)
    return module


def start_job(case, transport, caller, method, payload):
    count = len(transport.jobs)
    getattr(caller, method)(payload)
    case.assertEqual(len(transport.jobs), count + 1, "submission must start exactly one job")
    job = transport.jobs[-1]
    case.assertEqual(job.query, payload, "submission payload was changed")
    return job


def deliver_job(case, transport, job, value):
    """Probe observers only append values; delivery must not start or cancel work."""
    jobs = tuple(transport.jobs)
    cancellations = [existing.cancel_count for existing in jobs]
    job.deliver(value)
    case.assertEqual(len(transport.jobs), len(jobs), "callback started a job")
    case.assertEqual([existing.cancel_count for existing in jobs], cancellations,
                     "callback cancelled existing work")


def close_caller(case, transport, caller):
    count = len(transport.jobs)
    caller.close()
    case.assertEqual(len(transport.jobs), count, "close started a job")


def probe_idle_peer_close(case, caller_specs, transport_type):
    """Either caller can close fresh/completed without affecting its pending peer."""
    for closer_index in (0, 1):
        for completed_closer in (False, True):
            transport, values = transport_type(), [[], []]
            callers = [caller_type(transport, output.append)
                       for (caller_type, _), output in zip(caller_specs, values)]
            closer, peer = callers[closer_index], callers[1 - closer_index]
            close_method = caller_specs[closer_index][1]
            peer_method = caller_specs[1 - closer_index][1]
            completed = [start_job(case, transport, peer, peer_method, "peer complete")]
            deliver_job(case, transport, completed[0], "peer complete")
            if completed_closer:
                completed.append(start_job(case, transport, closer, close_method, "closer complete"))
                deliver_job(case, transport, completed[-1], "closer complete")
            pending = start_job(case, transport, peer, peer_method, "peer pending")

            def assert_idle_state(operation):
                case.assertEqual([job.cancel_count for job in completed], [0] * len(completed),
                                 f"{operation} cancelled completed peer work")
                case.assertEqual(pending.cancel_count, 0, f"{operation} cancelled pending peer")

            close_caller(case, transport, closer)
            assert_idle_state("idle close")
            close_caller(case, transport, closer)
            assert_idle_state("repeated close")
            count = len(transport.jobs)
            with case.assertRaises(RuntimeError):
                getattr(closer, close_method)("closed")
            case.assertEqual(len(transport.jobs), count, "rejected request started a job")
            assert_idle_state("rejected request")
            deliver_job(case, transport, pending, "peer survives")
            deliver_job(case, transport, pending, "duplicate peer")
            case.assertEqual(values[1 - closer_index], ["peer complete", "peer survives"])
            case.assertEqual(values[closer_index], ["closer complete"] if completed_closer else [])


def probe_change(case, app, transport_type):
    """Held-out public behavior for an adapted app module; no internal inspection."""
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    lookup = start_job(case, transport, screen, "search", "lookup")
    old_save = start_job(case, transport, save, "submit", "draft 1")
    case.assertEqual(lookup.cancel_count, 0, "autosave cancelled another caller")
    new_save = start_job(case, transport, save, "submit", "draft 2")
    case.assertEqual(old_save.cancel_count, 1)
    case.assertEqual(lookup.cancel_count, 0)
    deliver_job(case, transport, old_save, "stale save")
    deliver_job(case, transport, lookup, "found")
    deliver_job(case, transport, lookup, "duplicate lookup")
    close_caller(case, transport, screen)
    close_caller(case, transport, screen)
    case.assertEqual(lookup.cancel_count, 0, "completed screen job was cancelled")
    case.assertEqual(new_save.cancel_count, 0, "screen close cancelled autosave")
    deliver_job(case, transport, new_save, "saved")
    deliver_job(case, transport, new_save, "duplicate save")
    case.assertEqual(screen_values, ["found"])
    case.assertEqual(save_values, ["saved"])
    last_save = start_job(case, transport, save, "submit", "draft 3")
    case.assertEqual(new_save.cancel_count, 0, "completed autosave job was cancelled")
    close_caller(case, transport, save)
    close_caller(case, transport, save)
    case.assertEqual(last_save.cancel_count, 1)
    deliver_job(case, transport, last_save, "late save")
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
    lookup = start_job(case, transport, screen, "search", "pending screen")
    pending_save = start_job(case, transport, save, "submit", "pending save")
    close_caller(case, transport, save)
    close_caller(case, transport, save)
    case.assertEqual(lookup.cancel_count, 0, "autosave close cancelled screen")
    case.assertEqual(pending_save.cancel_count, 1)
    deliver_job(case, transport, pending_save, "late save")
    deliver_job(case, transport, lookup, "screen survives")
    case.assertEqual(screen_values, ["screen survives"])
    case.assertEqual(save_values, [])

    # Autosave success must leave an independently pending Screen untouched.
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    lookup = start_job(case, transport, screen, "search", "pending screen")
    start_job(case, transport, save, "submit", "successful save")
    deliver_job(case, transport, transport.jobs[-1], "saved")
    case.assertEqual(lookup.cancel_count, 0, "autosave completion cancelled pending screen")
    deliver_job(case, transport, lookup, "found")
    case.assertEqual(save_values, ["saved"])
    case.assertEqual(screen_values, ["found"])

    # Starting Screen after Autosave must also preserve the other caller's work.
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    pending_save = start_job(case, transport, save, "submit", "pending save")
    lookup = start_job(case, transport, screen, "search", "later screen")
    case.assertEqual(pending_save.cancel_count, 0, "screen cancelled pending autosave")
    close_caller(case, transport, screen)
    close_caller(case, transport, screen)
    case.assertEqual(lookup.cancel_count, 1)
    case.assertEqual(pending_save.cancel_count, 0, "pending screen close cancelled autosave")
    deliver_job(case, transport, pending_save, "save survives")
    deliver_job(case, transport, lookup, "late screen")
    case.assertEqual(save_values, ["save survives"])
    case.assertEqual(screen_values, [])

    # A cancelled callback's first delivery may follow replacement completion.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        transport, values = transport_type(), []
        caller = caller_type(transport, values.append)
        old = start_job(case, transport, caller, method, "old")
        new = start_job(case, transport, caller, method, "new")
        case.assertEqual(old.cancel_count, 1)
        deliver_job(case, transport, new, "fresh")
        deliver_job(case, transport, old, "stale")
        deliver_job(case, transport, old, "stale again")
        case.assertEqual(values, ["fresh"], "stale after replacement was published")
        # Starting more work must not cancel the job that already completed.
        start_job(case, transport, caller, method, "next")
        case.assertEqual(new.cancel_count, 0, "completed job was cancelled on next request")
        case.assertEqual(old.cancel_count, 1, "cancelled job was cancelled again on submit")
        case.assertEqual(len(transport.jobs), 3)
        deliver_job(case, transport, new, "duplicate after successor")
        case.assertEqual(values, ["fresh"], "completed callback repeated after successor started")
        deliver_job(case, transport, transport.jobs[-1], "next value")
        case.assertEqual(values, ["fresh", "next value"])
        close_caller(case, transport, caller)
        close_caller(case, transport, caller)
        case.assertEqual(old.cancel_count, 1, "cancelled job was cancelled again on close")

    # Replacements cancel exactly once throughout a pending burst, for either API.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        transport, values = transport_type(), []
        caller = caller_type(transport, values.append)
        old = start_job(case, transport, caller, method, "old")
        new = start_job(case, transport, caller, method, "new")
        case.assertEqual(old.cancel_count, 1)
        for value in ("stale", "duplicate stale"):
            deliver_job(case, transport, old, value)
            case.assertEqual(values, [], "stale while replacement pending was published")
        latest = start_job(case, transport, caller, method, "latest")
        case.assertEqual(new.cancel_count, 1, "replacement was not cancelled exactly once")
        case.assertEqual(old.cancel_count, 1, "cancelled job was cancelled again on submit")
        case.assertEqual(latest.cancel_count, 0)
        for job in (old, new):
            for value in ("older", "duplicate older"):
                deliver_job(case, transport, job, value)
                case.assertEqual(values, [], "older callback in pending burst was published")
        deliver_job(case, transport, latest, "latest value")
        deliver_job(case, transport, latest, "duplicate latest")
        case.assertEqual(values, ["latest value"])

    # Closed callers reject new work without repeating cleanup in any start state.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        for state in ("fresh", "completed", "pending"):
            transport, values = transport_type(), []
            caller = caller_type(transport, values.append)
            if state != "fresh":
                start_job(case, transport, caller, method, "work")
            if state == "completed":
                deliver_job(case, transport, transport.jobs[-1], "done")
            close_caller(case, transport, caller)
            close_caller(case, transport, caller)
            if state == "pending":
                case.assertEqual(transport.jobs[-1].cancel_count, 1)
            with case.assertRaises(RuntimeError):
                getattr(caller, method)("closed")
            case.assertEqual(len(transport.jobs), int(state != "fresh"))
            if state == "pending":
                case.assertEqual(transport.jobs[-1].cancel_count, 1,
                                 "rejected request cancelled closed work again")
                deliver_job(case, transport, transport.jobs[-1], "late after rejection")
                deliver_job(case, transport, transport.jobs[-1], "duplicate after rejection")
                case.assertEqual(values, [], "closed callback was published")
            if state == "completed":
                case.assertEqual(transport.jobs[-1].cancel_count, 0,
                                 "completed job was cancelled on close")
                deliver_job(case, transport, transport.jobs[-1], "duplicate after close")
                case.assertEqual(values, ["done"])

    # The same peer transitions apply to either API in either construction order.
    screen_spec, save_spec = (app.Screen, "search"), (app.Autosave, "submit")
    for caller_specs in ((screen_spec, screen_spec), (save_spec, save_spec),
                         (screen_spec, save_spec), (save_spec, screen_spec)):
        (left_type, left_method), (right_type, right_method) = caller_specs
        for delivery_order in ((0, 1), (1, 0)):
            transport = transport_type()
            left_values, right_values = [], []
            left = left_type(transport, left_values.append)
            right = right_type(transport, right_values.append)
            first = start_job(case, transport, left, left_method, "left")
            second = start_job(case, transport, right, right_method, "right")
            case.assertEqual(first.cancel_count, 0, "second caller cancelled first")
            completed = (first, second)
            for index in delivery_order:
                deliver_job(case, transport, completed[index], ("left", "right")[index])
            case.assertEqual(left_values, ["left"], "live caller callback was misrouted")
            case.assertEqual(right_values, ["right"], "live caller callback was misrouted")
            # Start another pair to check close isolation while both jobs are pending.
            first = start_job(case, transport, left, left_method, "left pending")
            case.assertEqual([job.cancel_count for job in completed], [0, 0],
                             "submission cancelled completed peer work")
            second = start_job(case, transport, right, right_method, "right pending")
            case.assertEqual([job.cancel_count for job in completed], [0, 0],
                             "submission cancelled completed peer work")
            replacement = start_job(case, transport, left, left_method, "left replacement")
            case.assertEqual(first.cancel_count, 1)
            case.assertEqual(second.cancel_count, 0, "first caller cancelled second")
            close_caller(case, transport, left)
            case.assertEqual([job.cancel_count for job in completed], [0, 0],
                             "close cancelled completed peer work")
            deliver_job(case, transport, first, "late left")
            deliver_job(case, transport, replacement, "late replacement")
            deliver_job(case, transport, second, "right survives")
            case.assertEqual(first.cancel_count, 1)
            case.assertEqual(replacement.cancel_count, 1)
            case.assertEqual(second.cancel_count, 0)
            case.assertEqual(left_values, ["left"])
            case.assertEqual(right_values, ["right", "right survives"])

        # Reverse close order with fresh instances: the first stays live.
        transport = transport_type()
        left_values, right_values = [], []
        left = left_type(transport, left_values.append)
        right = right_type(transport, right_values.append)
        first = start_job(case, transport, left, left_method, "left pending")
        second = start_job(case, transport, right, right_method, "right pending")
        close_caller(case, transport, right)
        close_caller(case, transport, right)
        case.assertEqual(first.cancel_count, 0, "second caller close cancelled first")
        case.assertEqual(second.cancel_count, 1)
        deliver_job(case, transport, second, "late right")
        deliver_job(case, transport, first, "left survives")
        case.assertEqual(left_values, ["left survives"])
        case.assertEqual(right_values, [])
        probe_idle_peer_close(case, caller_specs, transport_type)

        # A later constructor must preserve work already pending on this transport.
        transport = transport_type()
        left_values, right_values = [], []
        left = left_type(transport, left_values.append)
        pending = start_job(case, transport, left, left_method, "pending before construction")
        right = right_type(transport, right_values.append)
        case.assertEqual(len(transport.jobs), 1, "construction started a job")
        case.assertEqual(pending.cancel_count, 0, "construction cancelled pending peer")
        deliver_job(case, transport, pending, "survives construction")
        deliver_job(case, transport, pending, "duplicate after construction")
        case.assertEqual(left_values, ["survives construction"])
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
        for source, message in ((BAD_PAYLOAD, "submission payload was changed"),
                                (BAD_SHARED_SAVE, "second caller cancelled first")):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_completed_screen_job_is_not_cancelled_on_next_search(self):
        with self.assertRaisesRegex(AssertionError, "completed job was cancelled on next request"):
            probe_change(self, module_from_source(BAD_SCREEN_RESUBMIT),
                         module_from_source(self.transport).Transport)

    def test_retained_history_is_benign(self):
        for source in (RETAIN_CANCELLED, RETAIN_CLOSED_JOB, COUNT_DELIVERIES):
            with self.subTest(source=source):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_caller_registration_is_benign(self):
        for source in (REGISTER_CALLERS, RETAIN_COMPLETED_PEERS, REGISTER_MIXED_CALLERS):
            with self.subTest(source=source):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_rejected_completed_peer_and_mixed_idle_close_defects(self):
        for source, message in (
            (BAD_REJECTED_COMPLETED_PEER, "rejected request cancelled completed peer work"),
            (BAD_MIXED_IDLE_CLOSE, "idle close cancelled pending peer"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_mixed_construction_order_and_close_job_count_defects(self):
        for source, message in (
            (BAD_AUTOSAVE_FIRST_OWNER, "second caller cancelled first"),
            (BAD_IDLE_CLOSE_JOB, "close started a job"),
            (BAD_REPEATED_CLOSE_JOB, "close started a job"),
            (BAD_IDLE_CALLBACK_JOB, "callback started a job"),
            (BAD_IDLE_CALLBACK_COMPLETED, "callback cancelled existing work"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_peer_jobs_survive_completion_and_later_submissions(self):
        for source, message in (
            (BAD_PEER_COMPLETION, "callback cancelled existing work"),
            (BAD_REVERSE_PEER_COMPLETION, "callback cancelled existing work"),
            (BAD_COMPLETED_PEER_SUBMIT, "submission cancelled completed peer work"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_peer_close_rejection_job_count_and_repeated_stale_defects(self):
        for source, message in (
            (BAD_IDLE_PEER_CLOSE, "idle close cancelled pending peer"),
            (BAD_COMPLETED_PEER_CLOSE, "close cancelled completed peer work"),
            (BAD_REJECTED_PEER, "rejected request cancelled pending peer"),
            (BAD_EXTRA_PEER_JOB, "submission must start exactly one job"),
            (BAD_REPEATED_STALE, "stale after replacement was published"),
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
            (BAD_SAVE_COMPLETION, "callback cancelled existing work"),
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

    def test_shared_transition_defects_are_detected(self):
        for source, message in (
            (BAD_REVERSE_PENDING_MIXED, "second caller close cancelled first"),
            (BAD_DUPLICATE_AFTER_CLOSE, "closed callback was published"),
            (BAD_LIVE_CALLBACK_JOB, "callback started a job"),
            (BAD_PEER_PAYLOAD, "payload was changed"),
            (BAD_PENDING_CLOSE_JOB, "close started a job"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_pending_burst_defects_are_detected_for_each_api(self):
        for callers in (CALLERS, ADAPTATION):
            for defective, message in (
                (BAD_DUPLICATE_PENDING, "stale while replacement pending was published"),
                (BAD_THIRD_PENDING, "replacement was not cancelled exactly once"),
            ):
                # Restrict the defective lifecycle owner to one API at a time.
                source = GOOD.replace(callers, callers.replace("LatestRequest", "DefectiveRequest"))
                source += defective.partition("class Screen:")[0].replace(
                    "LatestRequest", "DefectiveRequest")
                with self.subTest(api=callers, defect=message), self.assertRaisesRegex(AssertionError, message):
                    probe_change(self, module_from_source(source),
                                 module_from_source(self.transport).Transport)

    def test_pending_peer_construction_defects_are_detected(self):
        for existing in ("Screen", "Autosave"):
            for constructed in ("Screen", "Autosave"):
                source = REGISTER_MIXED_CALLERS.replace(
                    "        self.peers.append(self)",
                    f"        if type(self).__name__ == '{constructed}':\n"
                    "            for peer in self.peers:\n"
                    f"                if type(peer).__name__ == '{existing}' and peer.requests.pending is not None:\n"
                    "                    peer.requests.pending.cancel()\n"
                    "        self.peers.append(self)",
                )
                with self.subTest(existing=existing, constructed=constructed), self.assertRaisesRegex(
                    AssertionError, "construction cancelled pending peer",
                ):
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
