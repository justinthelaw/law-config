"""Offline oracle calibration, not an agent trial or application benchmark."""
import importlib.util
from itertools import product
import json
from pathlib import Path
import tempfile
import types
import unittest

from fixture_python import run_fixture_python

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


BAD_FRESH_PUBLISH = GOOD.replace(
    "        self.requests.close()",
    "        self.requests.close()\n"
    "        if not self.requests.transport.jobs:\n"
    "            self.on_value('fabricated')",
)
BAD_REOPEN_AFTER_REJECTION = GOOD.replace(
    "        if self.closed:\n            raise RuntimeError('closed')",
    "        if self.closed:\n"
    "            self.rejected = True\n"
    "            raise RuntimeError('closed')",
).replace(
    "        def receive(value):\n            if self.token is token:",
    "        def receive(value):\n"
    "            if self.closed and getattr(self, 'rejected', False):\n"
    "                self.closed = False\n"
    "                return\n"
    "            if self.token is token:",
)

# Retaining completed references and request counts does not itself violate ownership.
RETAIN_REQUEST_HISTORY = GOOD.replace(
    "        self.closed = False",
    "        self.closed = False\n"
    "        self.sends = 0\n"
    "        self.completed = []",
).replace(
    "        token = object()",
    "        self.sends += 1\n"
    "        token = object()",
).replace(
    "                self.pending = None",
    "                self.completed.append(self.pending)\n"
    "                self.pending = None",
)
BAD_THREE_REQUEST_CLOSE = RETAIN_REQUEST_HISTORY.replace(
    "    def close(self):\n        self.closed = True",
    "    def close(self):\n"
    "        if self.sends == 3 and self.pending is None:\n"
    "            return\n"
    "        self.closed = True",
)
RETAIN_COMPLETED_TOKEN = REGISTER_MIXED_CALLERS.replace(
    "                self.token = None",
    "                self.completed_token = token\n"
    "                self.token = None",
)
BAD_THIRD_CALLER_OWNER = REGISTER_MIXED_CALLERS.replace(
    "        self.peers.append(self)",
    "        self.peers.append(self)\n"
    "        if len(self.peers) == 3:\n"
    "            self.requests = self.peers[0].requests",
)

# Three participants remain the same bounded scenario; registration alone is benign.
def three_caller_position_defect(index, operation):
    target = "        self.requests.close()" if operation == "close" else "        self.requests.send("
    peer_state = "pending is not None" if operation == "close" else "closed is False"
    return REGISTER_MIXED_CALLERS.replace(
        target,
        f"        if len(self.peers) == 3 and self is self.peers[{index}]:\n"
        "            if self.requests.pending is not None:\n"
        f"                peers_live = all(peer.requests.{peer_state} for peer in self.peers)\n"
        "                for peer in self.peers:\n"
        "                    if peers_live and peer is not self and peer.requests.pending is not None:\n"
        "                        peer.requests.pending.cancel()\n" + target,
    )


BAD_NONALTERNATING_OWNER = REGISTER_MIXED_CALLERS.replace(
    "        self.peers.append(self)",
    "        self.peers.append(self)\n"
    "        if len(self.peers) == 3 and type(self.peers[0]) is type(self.peers[1]):\n"
    "            if type(self) is not type(self.peers[0]):\n"
    "                self.requests = self.peers[0].requests",
)
RETAIN_TRANSPORT_COMPLETED = GOOD.replace(
    "                self.pending = None",
    "                self.transport.completed = self.pending\n"
    "                self.pending = None",
)
BAD_COMPLETED_CONSTRUCTION = RETAIN_TRANSPORT_COMPLETED.replace(
    "        self.requests = LatestRequest(transport)",
    "        if hasattr(transport, 'completed'):\n"
    "            transport.completed.cancel()\n"
    "        self.requests = LatestRequest(transport)",
)
BAD_CALLBACK_REPLACES_JOB = GOOD.replace(
    "                self.pending = None",
    "                if sum(job.query == query for job in self.transport.jobs) > 1:\n"
    "                    self.transport.jobs.remove(self.pending)\n"
    "                    self.transport.start(query, lambda value: None)\n"
    "                self.pending = None",
)


# No-start transitions must preserve jobs even when a list edit hides a new start.
BAD_CLOSE_REPLACES_JOB = GOOD.replace(
    "    def close(self):\n        self.closed = True",
    "    def close(self):\n"
    "        if self.pending is None and not self.closed and len(self.transport.jobs) == 1:\n"
    "            self.transport.jobs.pop()\n"
    "            self.transport.start('silent replacement', lambda value: None)\n"
    "        self.closed = True",
)
BAD_REJECT_REPLACES_JOB = GOOD.replace(
    "        if self.closed:\n            raise RuntimeError('closed')",
    "        if self.closed:\n"
    "            if len(self.transport.jobs) == 1 and self.transport.jobs[0].cancel_count == 0:\n"
    "                self.transport.jobs.pop()\n"
    "                self.transport.start('silent replacement', lambda value: None)\n"
    "            raise RuntimeError('closed')",
)
BAD_LATE_RESTORES_PENDING = RETAIN_CLOSED_JOB.replace(
    "        def receive(value):\n            if self.token is token:",
    "        def receive(value):\n"
    "            if self.closed:\n"
    "                self.pending = getattr(self, 'closed_job', None)\n"
    "            if self.token is token:",
)
BAD_REJECT_RESTORES_PENDING = RETAIN_CLOSED_JOB.replace(
    "        if self.closed:\n            raise RuntimeError('closed')",
    "        if self.closed:\n"
    "            self.pending = getattr(self, 'closed_job', None)\n"
    "            raise RuntimeError('closed')",
)
BAD_LATE_PEER_OBSERVER = REGISTER_MIXED_CALLERS.replace(
    "        self.requests = LatestRequest(transport)",
    "        self.requests = LatestRequest(transport)\n"
    "        self.requests.caller = self",
).replace(
    "        def receive(value):\n            if self.token is token:",
    "        def receive(value):\n"
    "            peers = self.caller.peers\n"
    "            if isinstance(self.caller, Autosave) and all(peer.requests.closed for peer in peers):\n"
    "                for peer in peers:\n"
    "                    if isinstance(peer, Screen):\n"
    "                        peer.on_value(value)\n"
    "            if self.token is token:",
)


# Existing histories may be retained; submitting must append exactly one new job.
REGISTER_BEFORE_WORK = REGISTER_MIXED_CALLERS.replace(
    "        self.peers.append(self)",
    "        self.peers.append(self)\n"
    "        if len(self.peers) == 2 and not transport.jobs:\n"
    "            transport.preconstructed = True",
)
BAD_SUBMISSION_REPLACES_PREFIX = REGISTER_BEFORE_WORK.replace(
    "        self.pending = self.transport.start(query, receive)",
    "        if getattr(self.transport, 'preconstructed', False) and self.transport.jobs:\n"
    "            self.transport.jobs.pop(0)\n"
    "            self.transport.start('silent extra', lambda value: None)\n"
    "        self.pending = self.transport.start(query, receive)",
)
COUNT_PENDING_REPLACEMENTS = GOOD.replace(
    "        self.closed = False",
    "        self.closed = False\n"
    "        self.pending_replacements = 0",
).replace(
    "        if self.pending is not None:\n            self.pending.cancel()\n        token = object()",
    "        if self.pending is not None:\n"
    "            self.pending_replacements += 1\n"
    "            self.pending.cancel()\n"
    "        token = object()",
)
BAD_BURST_TERMINATES_CALLER = COUNT_PENDING_REPLACEMENTS.replace(
    "                on_value(value)",
    "                on_value(value)\n"
    "                if self.pending_replacements >= 2:\n"
    "                    self.closed = True",
)
BAD_COMPLETED_CONSTRUCTION_CLOSED = RETAIN_TRANSPORT_COMPLETED.replace(
    "        self.requests = LatestRequest(transport)",
    "        self.requests = LatestRequest(transport)\n"
    "        if hasattr(transport, 'completed'):\n"
    "            self.requests.closed = True",
)


# Recording a close on the shared transport must not govern later callers.
RETAIN_TRANSPORT_CLOSED = GOOD.replace(
    "        self.closed = True",
    "        self.transport.had_closed = True\n"
    "        self.closed = True",
)
BAD_CLOSED_CONSTRUCTION_CANCELS_PEER = RETAIN_TRANSPORT_CLOSED.replace(
    "        self.requests = LatestRequest(transport)",
    "        self.requests = LatestRequest(transport)\n"
    "        if getattr(transport, 'had_closed', False):\n"
    "            for job in transport.jobs:\n"
    "                if job.cancel_count == 0:\n"
    "                    job.cancel()",
)


# Metadata may be shared without sharing cancellation or terminal state.
REGISTER_CLOSE_HISTORY = REGISTER_MIXED_CALLERS.replace(
    "        self.requests = LatestRequest(transport)",
    "        self.requests = LatestRequest(transport)\n"
    "        self.born_after_close = getattr(transport, 'had_closed', False)",
).replace(
    "        self.requests.close()",
    "        self.requests.close()\n"
    "        self.requests.transport.had_closed = True",
)
BAD_LATE_CONSTRUCTED_CLOSE = REGISTER_CLOSE_HISTORY.replace(
    "        self.requests.close()",
    "        if self.born_after_close:\n"
    "            for peer in self.peers:\n"
    "                if peer is not self and peer.requests.pending is not None:\n"
    "                    peer.requests.pending.cancel()\n"
    "        self.requests.close()",
)
REGISTER_REQUEST_OWNERS = GOOD.replace(
    "        self.closed = False",
    "        self.closed = False\n"
    "        if not hasattr(transport, 'owners'):\n"
    "            transport.owners = []\n"
    "        transport.owners.append(self)",
)
BAD_PEER_PAYLOAD_OWNERSHIP = REGISTER_REQUEST_OWNERS.replace(
    "        if self.pending is not None:\n            self.pending.cancel()\n        token = object()",
    "        for owner in self.transport.owners:\n"
    "            job = owner.pending\n"
    "            if owner is not self and job is not None and job.query == query:\n"
    "                job.cancel()\n"
    "        if self.pending is not None:\n"
    "            self.pending.cancel()\n"
    "        token = object()",
)
REGISTER_CALLER_USAGE = REGISTER_MIXED_CALLERS.replace(
    "        self.peers.append(self)",
    "        self.peers.append(self)\n"
    "        self.used = False",
).replace(
    "        self.requests.send(",
    "        self.used = True\n"
    "        self.requests.send(",
)
BAD_CLOSE_FRESH_PEER = REGISTER_CALLER_USAGE.replace(
    "        self.requests.close()",
    "        for peer in self.peers:\n"
    "            if peer is not self and not peer.used:\n"
    "                peer.requests.close()\n"
    "        self.requests.close()",
)


BAD_SECOND_PAIR_REPLACEMENT = REGISTER_MIXED_CALLERS.replace(
    "        self.requests.send(",
    "        if len(self.peers) == 2 and self is self.peers[1]:\n"
    "            first = self.peers[0]\n"
    "            if type(first) is type(self) and self.requests.pending is not None:\n"
    "                if first.requests.pending is not None and not first.requests.closed:\n"
    "                    first.requests.pending.cancel()\n"
    "        self.requests.send(",
)
RETAIN_JOB_OWNERS = REGISTER_REQUEST_OWNERS.replace(
    "        self.pending = self.transport.start(query, receive)",
    "        self.pending = self.transport.start(query, receive)\n"
    "        self.pending.owner = self",
)
BAD_RECANCEL_PEER_HISTORY = RETAIN_JOB_OWNERS.replace(
    "    def close(self):\n        self.closed = True",
    "    def close(self):\n"
    "        if not self.closed and len(self.transport.owners) == 2:\n"
    "            for job in self.transport.jobs:\n"
    "                if job.owner is not self and job.cancel_count > 0:\n"
    "                    job.cancel()\n"
    "        self.closed = True",
)
REGISTER_COMPLETED_CALLERS = REGISTER_MIXED_CALLERS.replace(
    "                self.pending = None",
    "                self.completed = self.pending\n"
    "                self.pending = None",
)
BAD_CONSTRUCTOR_CLOSES_COMPLETED = REGISTER_COMPLETED_CALLERS.replace(
    "        self.peers.append(self)",
    "        for peer in self.peers:\n"
    "            if getattr(peer.requests, 'completed', None) is not None:\n"
    "                peer.requests.close()\n"
    "        self.peers.append(self)",
)


def peer_lifecycle_defect(caller_name, peer_name, defect):
    """Scope each seed to one API/peer pairing so every matrix cell is exercised."""
    condition = (
        f"type(self).__name__ == '{caller_name}' and "
        f"any(peer is not self and type(peer).__name__ == '{peer_name}' "
    )
    if defect == "survivor":
        return REGISTER_MIXED_CALLERS.replace(
            "        self.requests.send(",
            f"        if len(self.requests.transport.jobs) >= 5 and {condition}and peer.requests.closed for peer in self.peers):\n"
            "            raise RuntimeError('peer closed')\n"
            "        self.requests.send(",
        )
    if defect == "duplicate":
        return REGISTER_MIXED_CALLERS.replace(
            "        self.requests.send(",
            f"        self.requests.keep_token = lambda peers=tuple(self.peers): ({condition}"
            "and not peer.requests.closed and peer.requests.pending is None for peer in peers))\n"
            "        self.requests.send(",
        ).replace(
            "                self.token = None",
            "                if not getattr(self, 'keep_token', lambda: False)():\n"
            "                    self.token = None",
        )
    raise ValueError(defect)


def fixture(name):
    return json.loads((ROOT / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def module_from_source(source):
    """Execute trusted local calibration source; this is not an isolation sandbox."""
    module = types.ModuleType("calibration")
    exec(compile(source, "<offline-calibration>", "exec"), module.__dict__)
    return module


def expected_cancellations(case, jobs, pending):
    """Only the scenario's known own-pending job may be cancelled once."""
    if pending is not None:
        case.assertTrue(any(job is pending for job in jobs), "pending job must already exist")
        case.assertEqual(pending.cancel_count, 0, "pending job must not already be cancelled")
    return [job.cancel_count + int(job is pending) for job in jobs]


def start_job(case, transport, caller, method, payload, *, pending=None):
    jobs = tuple(transport.jobs)
    expected = expected_cancellations(case, jobs, pending)
    getattr(caller, method)(payload)
    case.assertEqual(len(transport.jobs), len(jobs) + 1, "submission must start exactly one job")
    case.assertEqual(tuple(transport.jobs[:-1]), jobs, "submission replaced existing jobs")
    case.assertEqual([job.cancel_count for job in jobs], expected,
                     "submission changed cancellation counts")
    job = transport.jobs[-1]
    case.assertEqual(job.cancel_count, 0, "submission cancelled its new job")
    case.assertEqual(job.query, payload, "submission payload was changed")
    return job


def deliver_job(case, transport, job, value):
    """Probe observers only append values; delivery must not start or cancel work."""
    jobs = tuple(transport.jobs)
    cancellations = [existing.cancel_count for existing in jobs]
    job.deliver(value)
    case.assertEqual(len(transport.jobs), len(jobs), "callback started a job")
    case.assertEqual(tuple(transport.jobs), jobs, "callback replaced existing jobs")
    case.assertEqual([existing.cancel_count for existing in jobs], cancellations,
                     "callback cancelled existing work")


def close_caller(case, transport, caller, outputs=(), *, pending=None):
    jobs = tuple(transport.jobs)
    expected = expected_cancellations(case, jobs, pending)
    before = [list(output) for output in outputs]
    caller.close()
    case.assertEqual(len(transport.jobs), len(jobs), "close started a job")
    case.assertEqual(tuple(transport.jobs), jobs, "close replaced existing jobs")
    case.assertEqual([job.cancel_count for job in jobs], expected,
                     "close changed cancellation counts")
    case.assertEqual(list(outputs), before, "close changed observer")


def reclose_caller(case, transport, caller, outputs):
    close_caller(case, transport, caller, outputs)


def reject_closed_request(case, transport, caller, method, outputs):
    jobs = tuple(transport.jobs)
    cancellations = [job.cancel_count for job in jobs]
    before = [list(output) for output in outputs]
    with case.assertRaises(RuntimeError):
        getattr(caller, method)("closed")
    case.assertEqual(len(transport.jobs), len(jobs), "rejected request started a job")
    case.assertEqual(tuple(transport.jobs), jobs, "rejected request replaced existing jobs")
    case.assertEqual([job.cancel_count for job in jobs], cancellations,
                     "rejected request cancelled existing work")
    case.assertEqual(list(outputs), before, "rejected request changed observer")
    reclose_caller(case, transport, caller, outputs)


def redeliver_completed(case, transport, jobs, outputs):
    before = [list(output) for output in outputs]
    for job in jobs:
        deliver_job(case, transport, job, "duplicate completed")
        case.assertEqual(list(outputs), before, "completed callback repeated with peers")


def resume_caller(case, transport, caller, method, values, peer_values=()):
    """An open caller can start again without changing completed work or peers."""
    before, peer_before = list(values), list(peer_values)
    new = start_job(case, transport, caller, method, "next request")
    case.assertEqual(values, before, "submission changed observer")
    deliver_job(case, transport, new, "next result")
    deliver_job(case, transport, new, "duplicate next result")
    case.assertEqual(values, before + ["next result"])
    case.assertEqual(list(peer_values), peer_before, "resumed caller changed peer observer")
    return new


def probe_idle_peer_close(case, caller_specs, transport_type, pending_peer=True):
    """Closing an idle caller leaves a fresh or pending peer usable."""
    for closer_index in (0, 1):
        for completed_closer in (False, True):
            transport, values = transport_type(), [[], []]
            callers = [caller_type(transport, output.append)
                       for (caller_type, _), output in zip(caller_specs, values)]
            closer, peer = callers[closer_index], callers[1 - closer_index]
            close_method = caller_specs[closer_index][1]
            peer_method = caller_specs[1 - closer_index][1]
            completed = []
            if pending_peer:
                completed.append(start_job(case, transport, peer, peer_method, "peer complete"))
                deliver_job(case, transport, completed[0], "peer complete")
            if completed_closer:
                completed.append(start_job(case, transport, closer, close_method, "closer complete"))
                deliver_job(case, transport, completed[-1], "closer complete")
            pending = start_job(case, transport, peer, peer_method, "peer pending") if pending_peer else None

            def assert_idle_state(operation):
                case.assertEqual([job.cancel_count for job in completed], [0] * len(completed),
                                 f"{operation} cancelled completed peer work")
                if pending is not None:
                    case.assertEqual(pending.cancel_count, 0, f"{operation} cancelled pending peer")

            close_caller(case, transport, closer, values)
            assert_idle_state("idle close")
            close_caller(case, transport, closer, values)
            assert_idle_state("repeated close")
            reject_closed_request(case, transport, closer, close_method, values)
            assert_idle_state("rejected request")
            if pending is not None:
                deliver_job(case, transport, pending, "peer survives")
                deliver_job(case, transport, pending, "duplicate peer")
            case.assertEqual(values[1 - closer_index], ["peer complete", "peer survives"] if pending_peer else [])
            case.assertEqual(values[closer_index], ["closer complete"] if completed_closer else [])
            resume_caller(case, transport, peer, peer_method,
                          values[1 - closer_index], values[closer_index])
            reject_closed_request(case, transport, closer, close_method, values)


def probe_three_callers(case, caller_specs, active_index, peer_completed, transport_type):
    """Rotate replacement/close through the existing three-caller sequence."""
    transport, values = transport_type(), [[], [], []]
    callers, pending = [], []
    for index, (caller_type, method) in enumerate(caller_specs):
        callers.append(caller_type(transport, values[index].append))
        case.assertEqual([job.cancel_count for job in pending], [0] * len(pending),
                         "construction cancelled pending peer")
        pending.append(start_job(case, transport, callers[-1], method, f"caller {index}"))
        case.assertEqual([job.cancel_count for job in pending], [0] * len(pending),
                         "third caller cancelled peer work")
        case.assertEqual(values, [[], [], []])
    active, method = callers[active_index], caller_specs[active_index][1]
    first_peer, second_peer = [index for index in range(3) if index != active_index]
    expected_cancels, expected_values = [0, 0, 0], [[], [], []]
    replacement = start_job(case, transport, active, method, "active replacement", pending=pending[active_index])
    expected_cancels[active_index] = 1
    case.assertEqual([job.cancel_count for job in pending], expected_cancels,
                     "replacement affected peer work")
    deliver_job(case, transport, pending[active_index], "stale active")
    deliver_job(case, transport, replacement, "active result")
    redeliver_completed(case, transport, (replacement,), values)
    expected_values[active_index] = ["active result"]
    case.assertEqual(values, expected_values, "active callback was misrouted")
    if peer_completed:
        deliver_job(case, transport, pending[first_peer], "first peer result")
    last = start_job(case, transport, active, method, "active pending")
    for own_pending in (last, None):
        close_caller(case, transport, active, values, pending=own_pending)
        case.assertEqual([job.cancel_count for job in transport.jobs], expected_cancels + [0, 1],
                         "close affected peer or completed work")
    if not peer_completed:
        deliver_job(case, transport, pending[first_peer], "first peer result")
    for job in (pending[active_index], last):
        deliver_job(case, transport, job, "late active")
    redeliver_completed(case, transport, (pending[first_peer], replacement), values)
    reject_closed_request(case, transport, active, method, values)
    deliver_job(case, transport, pending[second_peer], "second peer result")
    redeliver_completed(case, transport, (pending[second_peer],), values)
    expected_values[first_peer], expected_values[second_peer] = ["first peer result"], ["second peer result"]
    case.assertEqual(values, expected_values)
    for index, peer_index in ((first_peer, second_peer), (second_peer, first_peer)):
        peer_before = list(values[peer_index])
        resume_caller(case, transport, callers[index], caller_specs[index][1],
                      values[index], values[active_index])
        case.assertEqual(values[peer_index], peer_before, "survivor changed peer observer")
    cancellations = [job.cancel_count for job in transport.jobs]
    for index in (first_peer, second_peer):
        close_caller(case, transport, callers[index], values)
        case.assertEqual([job.cancel_count for job in transport.jobs], cancellations,
                         "close cancelled completed work")
        reject_closed_request(case, transport, callers[index], caller_specs[index][1], values)


def probe_delayed_construction(case, caller_specs, state, transport_type):
    """A new caller preserves existing work and remains independent of a closed peer."""
    (left_type, left_method), (right_type, right_method) = caller_specs
    transport = transport_type()
    left_values, right_values, survivor_values = [], [], []
    left = left_type(transport, left_values.append)
    existing = start_job(case, transport, left, left_method, "before construction")
    if state == "completed":
        deliver_job(case, transport, existing, "survives construction")
    if state == "closed":
        survivor = left_type(transport, survivor_values.append)
        survivor_job = start_job(case, transport, survivor, left_method, "pending survivor")
        close_caller(case, transport, left, (left_values, survivor_values), pending=existing)
        case.assertEqual([existing.cancel_count, survivor_job.cancel_count], [1, 0])
    jobs, before = tuple(transport.jobs), list(left_values)
    cancellations = [1, 0] if state == "closed" else [0]
    right = right_type(transport, right_values.append)
    case.assertEqual(tuple(transport.jobs), jobs, "construction changed jobs")
    case.assertEqual([job.cancel_count for job in jobs], cancellations,
                     f"construction cancelled {state} peer work")
    case.assertEqual((left_values, right_values, survivor_values), (before, [], []),
                     "construction changed observer")
    deliver_job(case, transport, existing, "survives construction")
    deliver_job(case, transport, existing, "duplicate after construction")
    case.assertEqual(left_values, [] if state == "closed" else ["survives construction"])
    case.assertEqual(right_values, [])
    new_job = resume_caller(case, transport, right, right_method, right_values, left_values)
    if state != "closed":
        resume_caller(case, transport, left, left_method, left_values, right_values)
    if state == "closed":
        case.assertEqual(survivor_values, [], "new caller changed pending survivor")
        outputs = (left_values, right_values, survivor_values)
        close_caller(case, transport, right, outputs)
        case.assertEqual([existing.cancel_count, survivor_job.cancel_count, new_job.cancel_count],
                         [1, 0, 0], "new caller close cancelled existing work")
        reclose_caller(case, transport, right, outputs)
        redeliver_completed(case, transport, (new_job,), outputs)
        reject_closed_request(case, transport, right, right_method, outputs)
        deliver_job(case, transport, survivor_job, "survivor result")
        deliver_job(case, transport, survivor_job, "duplicate survivor result")
        case.assertEqual(survivor_values, ["survivor result"])
        case.assertEqual(right_values, ["next result"])
        case.assertEqual(left_values, [])
        reject_closed_request(case, transport, left, left_method,
                              (left_values, right_values, survivor_values))


def probe_change(case, app, transport_type):
    """Held-out public behavior for an adapted app module; no internal inspection."""
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    lookup = start_job(case, transport, screen, "search", "lookup")
    old_save = start_job(case, transport, save, "submit", "draft 1")
    case.assertEqual(lookup.cancel_count, 0, "autosave cancelled another caller")
    new_save = start_job(case, transport, save, "submit", "draft 2", pending=old_save)
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
    close_caller(case, transport, save, pending=last_save)
    close_caller(case, transport, save)
    case.assertEqual(last_save.cancel_count, 1)
    deliver_job(case, transport, last_save, "late save")
    case.assertEqual((screen_values, save_values), (["found"], ["saved"]),
                     "late callback changed closed observers")
    reclose_caller(case, transport, save, (screen_values, save_values))
    reclose_caller(case, transport, screen, (screen_values, save_values))
    reject_closed_request(case, transport, save, "submit", (screen_values, save_values))
    reject_closed_request(case, transport, screen, "search", (screen_values, save_values))
    case.assertEqual(len(transport.jobs), 4)

    # Autosave close must leave an independently pending screen deliverable.
    transport = transport_type()
    screen_values, save_values = [], []
    screen = app.Screen(transport, screen_values.append)
    save = app.Autosave(transport, save_values.append)
    lookup = start_job(case, transport, screen, "search", "pending screen")
    pending_save = start_job(case, transport, save, "submit", "pending save")
    close_caller(case, transport, save, pending=pending_save)
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
    close_caller(case, transport, screen, pending=lookup)
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
        new = start_job(case, transport, caller, method, "new", pending=old)
        case.assertEqual(old.cancel_count, 1)
        deliver_job(case, transport, new, "fresh")
        deliver_job(case, transport, old, "stale")
        deliver_job(case, transport, old, "stale again")
        case.assertEqual(values, ["fresh"], "stale after replacement was published")
        # Starting more work must not cancel the job that already completed.
        next_job = start_job(case, transport, caller, method, "next")
        case.assertEqual(new.cancel_count, 0, "completed job was cancelled on next request")
        case.assertEqual(old.cancel_count, 1, "cancelled job was cancelled again on submit")
        case.assertEqual(len(transport.jobs), 3)
        deliver_job(case, transport, new, "duplicate after successor")
        case.assertEqual(values, ["fresh"], "completed callback repeated after successor started")
        deliver_job(case, transport, next_job, "next value")
        case.assertEqual(values, ["fresh", "next value"])
        for _ in range(2):
            close_caller(case, transport, caller, (values,))
            case.assertEqual([new.cancel_count, next_job.cancel_count], [0, 0],
                             "close cancelled completed work")
            case.assertEqual(old.cancel_count, 1, "cancelled job was cancelled again on close")
        reject_closed_request(case, transport, caller, method, (values,))

    # Replacements cancel exactly once throughout a pending burst, for either API.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        transport, values = transport_type(), []
        caller = caller_type(transport, values.append)
        old = start_job(case, transport, caller, method, "old")
        new = start_job(case, transport, caller, method, "new", pending=old)
        case.assertEqual(old.cancel_count, 1)
        for value in ("stale", "duplicate stale"):
            deliver_job(case, transport, old, value)
            case.assertEqual(values, [], "stale while replacement pending was published")
        latest = start_job(case, transport, caller, method, "latest", pending=new)
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
        resume_caller(case, transport, caller, method, values)

    # Closed callers reject new work without repeating cleanup in any start state.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        for state in ("fresh", "completed", "pending"):
            transport, values = transport_type(), []
            caller = caller_type(transport, values.append)
            if state != "fresh":
                start_job(case, transport, caller, method, "work")
            if state == "completed":
                deliver_job(case, transport, transport.jobs[-1], "done")
            own_pending = transport.jobs[-1] if state == "pending" else None
            close_caller(case, transport, caller, (values,), pending=own_pending)
            close_caller(case, transport, caller, (values,))
            if state == "pending":
                case.assertEqual(transport.jobs[-1].cancel_count, 1)
            reject_closed_request(case, transport, caller, method, (values,))
            case.assertEqual(len(transport.jobs), int(state != "fresh"))
            case.assertEqual(values, ["done"] if state == "completed" else [],
                             "rejected request changed observer")
            if state == "pending":
                case.assertEqual(transport.jobs[-1].cancel_count, 1,
                                 "rejected request cancelled closed work again")
                for value in ("late after rejection", "duplicate after rejection"):
                    deliver_job(case, transport, transport.jobs[-1], value)
                case.assertEqual(values, [], "closed callback was published")
            if state == "completed":
                case.assertEqual(transport.jobs[-1].cancel_count, 0,
                                 "completed job was cancelled on close")
                deliver_job(case, transport, transport.jobs[-1], "duplicate after close")
                case.assertEqual(values, ["done"])
            # Check terminal rejection before re-closing can hide an illicit reopen.
            reject_closed_request(case, transport, caller, method, (values,))

    # The same peer transitions apply to either API in either construction order.
    screen_spec, save_spec = (app.Screen, "search"), (app.Autosave, "submit")
    caller_pairs = ((screen_spec, screen_spec), (save_spec, save_spec),
                    (screen_spec, save_spec), (save_spec, screen_spec))
    for caller_specs in caller_pairs:
        (left_type, left_method), (right_type, right_method) = caller_specs
        for delivery_order, payloads, active_index in product(
            ((0, 1), (1, 0)), (("left", "right"), ("shared", "shared")), (0, 1),
        ):
            transport = transport_type()
            left_values, right_values = [], []
            left = left_type(transport, left_values.append)
            right = right_type(transport, right_values.append)
            first = start_job(case, transport, left, left_method, payloads[0])
            second = start_job(case, transport, right, right_method, payloads[1])
            case.assertEqual(first.cancel_count, 0, "second caller cancelled first")
            completed = (first, second)
            for index in delivery_order:
                deliver_job(case, transport, completed[index], ("left", "right")[index])
            case.assertEqual(left_values, ["left"], "live caller callback was misrouted")
            case.assertEqual(right_values, ["right"], "live caller callback was misrouted")
            redeliver_completed(case, transport, completed, (left_values, right_values))
            # Start another pair to check close isolation while both jobs are pending.
            first = start_job(case, transport, left, left_method, payloads[0] + " pending")
            case.assertEqual([job.cancel_count for job in completed], [0, 0],
                             "submission cancelled completed peer work")
            second = start_job(case, transport, right, right_method, payloads[1] + " pending")
            case.assertEqual([job.cancel_count for job in completed], [0, 0],
                             "submission cancelled completed peer work")
            active, peer = (left, right)[active_index], (left, right)[1 - active_index]
            active_method = (left_method, right_method)[active_index]
            peer_method = (left_method, right_method)[1 - active_index]
            active_values = (left_values, right_values)[active_index]
            peer_values = (left_values, right_values)[1 - active_index]
            old, surviving = (first, second)[active_index], (first, second)[1 - active_index]
            active_before, peer_before = list(active_values), list(peer_values)
            replacement = start_job(case, transport, active, active_method, "replacement", pending=old)
            close_caller(case, transport, active, (left_values, right_values), pending=replacement)
            redeliver_completed(case, transport, completed, (left_values, right_values))
            deliver_job(case, transport, old, "late replaced")
            deliver_job(case, transport, replacement, "late replacement")
            deliver_job(case, transport, surviving, "peer survives")
            case.assertEqual(active_values, active_before)
            case.assertEqual(peer_values, peer_before + ["peer survives"])
            for job in (old, replacement):
                deliver_job(case, transport, job, "duplicate after close")
            case.assertEqual(active_values, active_before, "closed callback was published")
            reject_closed_request(case, transport, active, active_method, (left_values, right_values))
            resume_caller(case, transport, peer, peer_method, peer_values, active_values)

        # Reverse close order with fresh instances: the first stays live.
        transport = transport_type()
        left_values, right_values = [], []
        left = left_type(transport, left_values.append)
        right = right_type(transport, right_values.append)
        first = start_job(case, transport, left, left_method, "left pending")
        second = start_job(case, transport, right, right_method, "right pending")
        close_caller(case, transport, right, pending=second)
        close_caller(case, transport, right)
        case.assertEqual(first.cancel_count, 0, "second caller close cancelled first")
        case.assertEqual(second.cancel_count, 1)
        deliver_job(case, transport, second, "late right")
        deliver_job(case, transport, first, "left survives")
        case.assertEqual(left_values, ["left survives"])
        case.assertEqual(right_values, [])
        deliver_job(case, transport, second, "duplicate after close")
        case.assertEqual(right_values, [], "closed callback was published")
        reject_closed_request(case, transport, right, right_method, (left_values, right_values))
        resume_caller(case, transport, left, left_method, left_values, right_values)
        probe_idle_peer_close(case, caller_specs, transport_type)

        for state in ("pending", "completed"):
            probe_delayed_construction(case, caller_specs, state, transport_type)

    # Reuse one bounded three-participant sequence for each API and active position.
    for caller_specs in product((screen_spec, save_spec), repeat=3):
        for active_index in range(3):
            for peer_completed in (False, True):
                probe_three_callers(case, caller_specs, active_index, peer_completed, transport_type)

    # Equal payloads still represent distinct requests and callback lifetimes.
    for caller_type, method in ((app.Screen, "search"), (app.Autosave, "submit")):
        transport, values = transport_type(), []
        caller = caller_type(transport, values.append)
        payload = "same payload"
        old = start_job(case, transport, caller, method, payload)
        new = start_job(case, transport, caller, method, payload, pending=old)
        case.assertEqual([old.cancel_count, new.cancel_count], [1, 0])
        deliver_job(case, transport, old, "stale")
        case.assertEqual(values, [], "same-payload stale callback was published")
        deliver_job(case, transport, new, "fresh")
        deliver_job(case, transport, old, "duplicate stale")
        deliver_job(case, transport, new, "duplicate fresh")
        case.assertEqual(values, ["fresh"], "same-payload replacement did not publish once")

    for caller_specs in caller_pairs:
        probe_delayed_construction(case, caller_specs, "closed", transport_type)
        probe_idle_peer_close(case, caller_specs, transport_type, pending_peer=False)



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
            return run_fixture_python(root, "-m", "unittest", "-v", "test_public",
                                      timeout=10)

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
        with self.assertRaisesRegex(AssertionError, "submission changed cancellation counts"):
            probe_change(self, module_from_source(BAD), module_from_source(self.transport).Transport)

    def test_seeded_lifecycle_defects_fail_held_out_change(self):
        for label, source, message in (
            ("completed screen cancellation", BAD_COMPLETED, "close changed cancellation counts"),
            ("completed autosave cancellation", BAD_COMPLETED_SAVE, "submission changed cancellation counts"),
            ("autosave close isolation", BAD_SAVE_CLOSE, "close changed cancellation counts"),
            ("late first delivery", BAD_LATE, "stale after replacement"),
            ("fresh terminal close", BAD_IDLE_CLOSE, "RuntimeError not raised"),
            ("completed terminal close", BAD_COMPLETED_CLOSE, "RuntimeError not raised"),
        ):
            with self.subTest(defect=label), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_autosave_payload_and_instance_defects_are_detected(self):
        for source, message in ((BAD_PAYLOAD, "submission payload was changed"),
                                (BAD_SHARED_SAVE, "submission changed cancellation counts")):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_completed_screen_job_is_not_cancelled_on_next_search(self):
        with self.assertRaisesRegex(AssertionError, "submission changed cancellation counts"):
            probe_change(self, module_from_source(BAD_SCREEN_RESUBMIT),
                         module_from_source(self.transport).Transport)

    def test_retained_history_is_benign(self):
        for source in (RETAIN_CANCELLED, RETAIN_CLOSED_JOB, COUNT_DELIVERIES, RETAIN_TRANSPORT_COMPLETED,
                       COUNT_PENDING_REPLACEMENTS, REGISTER_BEFORE_WORK, RETAIN_TRANSPORT_CLOSED,
                       REGISTER_CLOSE_HISTORY, REGISTER_REQUEST_OWNERS, REGISTER_CALLER_USAGE,
                       RETAIN_JOB_OWNERS, REGISTER_COMPLETED_CALLERS):
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
            (BAD_REJECTED_COMPLETED_PEER, "rejected request cancelled existing work"),
            (BAD_MIXED_IDLE_CLOSE, "close changed cancellation counts"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_mixed_construction_order_and_close_job_count_defects(self):
        for source, message in (
            (BAD_AUTOSAVE_FIRST_OWNER, "submission changed cancellation counts"),
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
            (BAD_COMPLETED_PEER_SUBMIT, "submission changed cancellation counts"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_peer_close_rejection_job_count_and_repeated_stale_defects(self):
        for source, message in (
            (BAD_IDLE_PEER_CLOSE, "close changed cancellation counts"),
            (BAD_COMPLETED_PEER_CLOSE, "close changed cancellation counts"),
            (BAD_REJECTED_PEER, "rejected request cancelled existing work"),
            (BAD_EXTRA_PEER_JOB, "submission must start exactly one job"),
            (BAD_REPEATED_STALE, "stale after replacement was published"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_second_caller_close_does_not_cancel_first(self):
        with self.assertRaisesRegex(AssertionError, "close changed cancellation counts"):
            probe_change(self, module_from_source(BAD_SECOND_CLOSE),
                         module_from_source(self.transport).Transport)

    def test_rejected_request_and_completion_do_not_cancel_other_work(self):
        for source, message in (
            (BAD_CLOSED_SUBMIT, "rejected request cancelled existing work"),
            (BAD_SAVE_COMPLETION, "callback cancelled existing work"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_pending_close_duplicate_and_reverse_instance_defects_are_detected(self):
        for source, message in (
            (BAD_PENDING_SCREEN_CLOSE, "close changed cancellation counts"),
            (BAD_DUPLICATE_RESET, "completed callback repeated after successor started"),
            (BAD_FIRST_CALLER, "submission changed cancellation counts"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_recancellation_and_caller_routing_defects_are_detected(self):
        for source, message in (
            (BAD_RECANCEL_SUBMIT, "submission changed cancellation counts"),
            (BAD_RECANCEL_CLOSE, "close changed cancellation counts"),
            (BAD_REVERSE_CALLER, "submission changed cancellation counts"),
            (BAD_SCREEN_CALLBACK, "live caller callback was misrouted"),
            (BAD_SAVE_CALLBACK, "live caller callback was misrouted"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_shared_transition_defects_are_detected(self):
        for source, message in (
            (BAD_REVERSE_PENDING_MIXED, "close changed cancellation counts"),
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
                (BAD_THIRD_PENDING, "submission changed cancellation counts"),
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

    def test_live_peer_duplicates_and_survivor_submissions_for_all_pairings(self):
        for caller_name in ("Screen", "Autosave"):
            for peer_name in ("Screen", "Autosave"):
                for defect, error, message in (
                    ("survivor", RuntimeError, "peer closed"),
                    ("duplicate", AssertionError, "completed callback repeated with peers"),
                ):
                    source = peer_lifecycle_defect(caller_name, peer_name, defect)
                    with self.subTest(caller=caller_name, peer=peer_name, defect=defect):
                        with self.assertRaisesRegex(error, message):
                            probe_change(self, module_from_source(source),
                                         module_from_source(self.transport).Transport)

    def test_fresh_observer_and_late_terminal_close_for_each_api(self):
        for callers in (CALLERS, ADAPTATION):
            for defective, message in (
                (BAD_FRESH_PUBLISH, "close changed observer"),
                (BAD_REOPEN_AFTER_REJECTION, "RuntimeError not raised"),
            ):
                if defective == BAD_FRESH_PUBLISH:
                    replacement = callers.replace(
                        "        self.requests.close()",
                        "        self.requests.close()\n"
                        "        if not self.requests.transport.jobs:\n"
                        "            self.on_value('fabricated')",
                    )
                    source = GOOD.replace(callers, replacement)
                else:
                    source = GOOD.replace(callers, callers.replace("LatestRequest", "DefectiveRequest"))
                    source += defective.partition("class Screen:")[0].replace(
                        "LatestRequest", "DefectiveRequest")
                with self.subTest(api=callers, defect=message), self.assertRaisesRegex(AssertionError, message):
                    probe_change(self, module_from_source(source),
                                 module_from_source(self.transport).Transport)

    def test_three_request_close_defects_for_each_api(self):
        defects = [(BAD_THREE_REQUEST_CLOSE, "RuntimeError not raised")]
        for completed_index in (0, -1):
            defective = RETAIN_REQUEST_HISTORY.replace(
                "    def close(self):\n        self.closed = True",
                "    def close(self):\n"
                "        if self.sends == 3 and self.pending is None and self.completed:\n"
                f"            self.completed[{completed_index}].cancel()\n"
                "        self.closed = True",
            )
            defects.append((defective, "close changed cancellation counts"))
        for callers in (CALLERS, ADAPTATION):
            for defective, message in defects:
                source = GOOD.replace(callers, callers.replace("LatestRequest", "DefectiveRequest"))
                source += defective.partition("class Screen:")[0].replace(
                    "LatestRequest", "DefectiveRequest")
                with self.subTest(api=callers, defect=message), self.assertRaisesRegex(AssertionError, message):
                    probe_change(self, module_from_source(source),
                                 module_from_source(self.transport).Transport)

    def test_completed_peer_callbacks_stay_suppressed_after_close(self):
        for caller_name in ("Screen", "Autosave"):
            for peer_name in ("Screen", "Autosave"):
                source = RETAIN_COMPLETED_TOKEN.replace(
                    "        self.requests.close()",
                    "        self.requests.close()\n"
                    f"        if type(self).__name__ == '{caller_name}' and any(\n"
                    f"            peer is not self and type(peer).__name__ == '{peer_name}'\n"
                    "            for peer in self.peers\n"
                    "        ):\n"
                    "            self.requests.token = getattr(self.requests, 'completed_token', None)",
                )
                with self.subTest(caller=caller_name, peer=peer_name), self.assertRaisesRegex(
                    AssertionError, "completed callback repeated",
                ):
                    probe_change(self, module_from_source(source),
                                 module_from_source(self.transport).Transport)

    def test_third_caller_ownership_defect_is_detected(self):
        for first_name in ("Screen", "Autosave"):
            for second_name in ("Screen", "Autosave"):
                condition = (
                    f"len(self.peers) == 3 and type(self.peers[0]).__name__ == '{first_name}' "
                    f"and type(self.peers[1]).__name__ == '{second_name}'"
                )
                source = BAD_THIRD_CALLER_OWNER.replace("len(self.peers) == 3", condition)
                with self.subTest(first=first_name, second=second_name), self.assertRaisesRegex(
                    AssertionError, "submission changed cancellation counts",
                ):
                    probe_change(self, module_from_source(source),
                                 module_from_source(self.transport).Transport)

    def test_additional_retained_metadata_is_benign(self):
        for source in (RETAIN_REQUEST_HISTORY, RETAIN_COMPLETED_TOKEN):
            with self.subTest(source=source):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_payload_cannot_identify_a_request_for_either_api(self):
        defective_owner = OWNER.replace("token = object()", "token = query")
        for callers in (CALLERS, ADAPTATION):
            source = GOOD.replace(callers, callers.replace("LatestRequest", "DefectiveRequest"))
            source += defective_owner.replace("LatestRequest", "DefectiveRequest")
            with self.subTest(api=callers), self.assertRaisesRegex(
                AssertionError, "same-payload stale callback was published",
            ):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_three_caller_positions_and_transition_snapshots(self):
        controls = [
            (BAD_NONALTERNATING_OWNER, "submission changed cancellation counts"),
            (BAD_COMPLETED_CONSTRUCTION, "construction cancelled completed peer"),
            (BAD_CALLBACK_REPLACES_JOB, "callback replaced existing jobs"),
        ]
        for index in range(3):
            controls.extend((
                (three_caller_position_defect(index, "close"), "close changed cancellation counts"),
                (three_caller_position_defect(index, "replace"), "submission changed cancellation counts"),
            ))
        for source, message in controls:
            with self.subTest(defect=message, source=source), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_closed_transition_defects_are_detected(self):
        for source, message in (
            (BAD_CLOSE_REPLACES_JOB, "close replaced existing jobs"),
            (BAD_REJECT_REPLACES_JOB, "rejected request replaced existing jobs"),
            (BAD_LATE_RESTORES_PENDING, "close changed cancellation counts"),
            (BAD_REJECT_RESTORES_PENDING, "close changed cancellation counts"),
            (BAD_LATE_PEER_OBSERVER, "late callback changed closed observers"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(AssertionError, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_submission_history_and_open_caller_reuse(self):
        for source, error, message in (
            (BAD_SUBMISSION_REPLACES_PREFIX, AssertionError, "submission replaced existing jobs"),
            (BAD_BURST_TERMINATES_CALLER, RuntimeError, "closed"),
            (BAD_COMPLETED_CONSTRUCTION_CLOSED, RuntimeError, "closed"),
        ):
            with self.subTest(source=source), self.assertRaisesRegex(error, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_construction_after_close_preserves_new_and_pending_callers(self):
        for callers in (CALLERS, ADAPTATION):
            source = RETAIN_TRANSPORT_CLOSED.replace(callers, callers.replace(
                "        self.requests = LatestRequest(transport)",
                "        self.requests = LatestRequest(transport)\n"
                "        if getattr(transport, 'had_closed', False):\n"
                "            self.requests.closed = True",
            ))
            with self.subTest(api=callers), self.assertRaisesRegex(RuntimeError, "closed"):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)
        with self.assertRaisesRegex(AssertionError, "construction cancelled closed peer"):
            probe_change(self, module_from_source(BAD_CLOSED_CONSTRUCTION_CANCELS_PEER),
                         module_from_source(self.transport).Transport)

    def test_late_close_equal_payload_and_fresh_peer_isolation(self):
        for source, error, message in (
            (BAD_LATE_CONSTRUCTED_CLOSE, AssertionError, "close changed cancellation counts"),
            (BAD_PEER_PAYLOAD_OWNERSHIP, AssertionError, "submission changed cancellation counts"),
            (BAD_CLOSE_FRESH_PEER, RuntimeError, "closed"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(error, message):
                probe_change(self, module_from_source(source),
                             module_from_source(self.transport).Transport)

    def test_all_job_deltas_pair_positions_and_existing_caller_reuse(self):
        for source, error, message in (
            (BAD_SECOND_PAIR_REPLACEMENT, AssertionError, "submission changed cancellation counts"),
            (BAD_RECANCEL_PEER_HISTORY, AssertionError, "close changed cancellation counts"),
            (BAD_CONSTRUCTOR_CLOSES_COMPLETED, RuntimeError, "closed"),
        ):
            with self.subTest(defect=message), self.assertRaisesRegex(error, message):
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
