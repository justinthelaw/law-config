"""Deadline regressions at discovery, subprocess, retry, and completion boundaries."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import watch_pipelines as watcher
from pipeline_monitor import DEFAULT_TIMEOUT, monitor_deadline
from pipeline_test_support import FakeClock, FakeRunner, run_payload, target


class DeadlineTests(unittest.TestCase):
    def test_nonfinite_timings_are_rejected_before_discovery(self) -> None:
        for option in ("interval", "max-interval", "heartbeat", "rediscover", "discovery-grace", "settle", "timeout"):
            for value in ("nan", "inf", "-inf"):
                with self.subTest(option=option, value=value), patch.object(
                    watcher, "discover_roots", return_value=[]
                ) as discover, patch.object(watcher, "discover_targets", return_value=[]), patch.object(watcher, "Watcher"):
                    with self.assertRaises(watcher.WatchError):
                        watcher.main([f"--{option}={value}"])
                    discover.assert_not_called()

    def test_cli_deadline_starts_before_repository_discovery(self) -> None:
        clock = FakeClock()
        calls = []

        def command(argv, **kwargs):
            calls.append(argv)
            clock.sleep(2)
            return subprocess.CompletedProcess(argv, 0, "/fixture\n", "")

        with patch("pipeline_support.time.monotonic", clock.now), patch(
            "pipeline_support.capture_command", side_effect=command
        ), patch.object(watcher, "discover_targets", return_value=[]) as targets, patch.object(watcher, "Watcher"):
            with self.assertRaisesRegex(watcher.WatchError, "timeout"):
                watcher.main(["--timeout", "1", "--repo", "/fixture", "--once"])
        self.assertEqual(len(calls), 1)
        targets.assert_not_called()

    def test_slow_initial_command_stops_later_monitor_operations(self) -> None:
        clock = FakeClock()
        selected = target()
        delegate = FakeRunner([[run_payload(selected)]])
        calls = []

        def runner(argv, **kwargs):
            calls.append(argv)
            clock.sleep(2)
            return delegate(argv, **kwargs)

        events = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append,
                                  clock=clock.now, sleep=clock.sleep, timeout=1)
        self.assertEqual(monitor.watch(once=True), 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(events[-1]["reason"], "monitor timeout")

    def test_cli_discovery_and_monitor_share_one_budget(self) -> None:
        clock = FakeClock()
        selected = target()
        delegate = FakeRunner([[run_payload(selected)]])
        budgets = []

        def command(argv, **kwargs):
            budgets.append(kwargs["timeout"])
            clock.sleep(0.125)
            logical = ["git", *argv[3:]] if argv[:3] == ["git", "-c", "core.fsmonitor="] else argv
            if logical == ["git", "rev-parse", "--show-toplevel"]:
                output = str(selected.path)
            elif logical == ["git", "submodule", "status", "--recursive"]:
                output = ""
            else:
                output = delegate(logical)
            return subprocess.CompletedProcess(argv, 0, output, "")

        events = []
        with patch("pipeline_support.time.monotonic", clock.now), patch(
            "pipeline_support.capture_command", side_effect=command
        ), patch.object(watcher.Watcher, "print_event", events.append):
            self.assertEqual(watcher.main(["--timeout", "1", "--repo", str(selected.path), "--once"]), 2)
        self.assertEqual(budgets, [1, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125])
        self.assertEqual(events[-1]["reason"], "monitor timeout")

    def test_completion_readback_cannot_pass_after_expiry(self) -> None:
        clock = FakeClock()
        selected = target()
        delegate = FakeRunner([[run_payload(selected)]])

        def runner(argv, **kwargs):
            result = delegate(argv, **kwargs)
            if argv[:3] == ["git", "remote", "get-url"]:
                clock.sleep(2)
            return result

        events = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append,
                                  clock=clock.now, sleep=clock.sleep, timeout=1)
        self.assertEqual(monitor.watch(once=True), 2)
        self.assertEqual(events[-1]["reason"], "monitor timeout")
        self.assertFalse(any(event.get("result") == "passed" for event in events))

    def test_default_monitor_runner_bounds_subprocess_timeout(self) -> None:
        clock = FakeClock()
        budgets = []

        def command(argv, **kwargs):
            budgets.append(kwargs["timeout"])
            clock.sleep(kwargs["timeout"])
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        events = []
        monitor = watcher.Watcher([target()], emit=events.append, clock=clock.now,
                                  sleep=clock.sleep, timeout=1)
        with patch("pipeline_support.capture_command", side_effect=command):
            try:
                result = monitor.watch(once=True)
            except watcher.WatchError as error:
                result = str(error)
        self.assertEqual(result, 2)
        self.assertEqual(budgets, [1])
        self.assertEqual(clock.current, 1)

    def test_retry_backoff_stops_at_shared_deadline(self) -> None:
        clock = FakeClock()
        budgets = []

        def command(argv, **kwargs):
            budgets.append(kwargs["timeout"])
            clock.sleep(0.25)
            return subprocess.CompletedProcess(argv, 1, "", "HTTP 503 temporarily unavailable")

        events = []
        monitor = watcher.Watcher([target()], emit=events.append, clock=clock.now,
                                  sleep=clock.sleep, timeout=1)
        with patch("pipeline_support.capture_command", side_effect=command):
            try:
                result = monitor.watch(once=True)
            except watcher.WatchError as error:
                result = str(error)
        self.assertEqual(result, 2)
        self.assertEqual(budgets, [1])
        self.assertEqual(clock.current, 1)

    def test_remaining_budget_shrinks_across_commands(self) -> None:
        clock = FakeClock()
        selected = target()
        delegate = FakeRunner([[run_payload(selected)]])
        budgets = []

        def command(argv, **kwargs):
            budgets.append(kwargs["timeout"])
            clock.sleep(0.25)
            return subprocess.CompletedProcess(argv, 0, delegate(argv), "")

        monitor = watcher.Watcher([selected], emit=lambda event: None, clock=clock.now,
                                  sleep=clock.sleep, timeout=1)
        with patch("pipeline_support.capture_command", side_effect=command):
            self.assertEqual(monitor.watch(once=True), 2)
        self.assertEqual(budgets, [1, 0.75, 0.5, 0.25])


class ResumableBudgetTests(unittest.TestCase):
    def test_library_and_cli_default_to_thirty_minutes(self):
        clock = FakeClock()
        monitor = watcher.Watcher([target()], clock=clock.now, wall_clock=lambda: 1000)
        self.assertEqual(DEFAULT_TIMEOUT, 1800)
        self.assertEqual(watcher.parser().parse_args([]).timeout, 1800)
        self.assertEqual(monitor.deadline.remaining(), 1800)
        self.assertEqual(monitor.deadline.wall_expires_at, 2800)

    def test_indefinite_requires_explicit_zero(self):
        monitor = watcher.Watcher([target()], timeout=0)
        self.assertIsNone(monitor.deadline)
        self.assertEqual(watcher.parser().parse_args(["--timeout", "0"]).timeout, 0)
        events = []
        selected = target()
        monitor = watcher.Watcher([selected], timeout=0, runner=FakeRunner([[run_payload(selected)]]), emit=events.append)
        self.assertEqual(monitor.watch(once=True), 0)
        self.assertEqual(events[0], {"event": "budget", "deadline": None, "indefinite": True})

    def test_absolute_deadline_requires_timezone(self):
        for value in ("not-a-date", "2026-10-21", "2026-10-21T12:00:00"):
            with self.subTest(value=value), patch.object(watcher, "discover_roots") as discover:
                with self.assertRaisesRegex(watcher.WatchError, "ISO 8601.*timezone"):
                    watcher.main(["--deadline", value])
                discover.assert_not_called()

    def test_resume_keeps_original_deadline_and_remaining_budget(self):
        clock = FakeClock()
        first = monitor_deadline(30, clock=clock.now, wall_clock=lambda: 1000)
        from pipeline_monitor import budget_event
        event = budget_event(first)
        clock.sleep(12)
        resumed = monitor_deadline(deadline=event["deadline"], clock=clock.now, wall_clock=lambda: 1012)
        self.assertEqual(resumed.remaining(), 18)
        self.assertEqual(resumed.wall_expires_at, first.wall_expires_at)
        self.assertEqual(budget_event(resumed), event)

    def test_absolute_deadline_overrides_relative_timeout_including_zero(self):
        clock = FakeClock()
        absolute = datetime.fromtimestamp(1030, timezone.utc).isoformat()
        for timeout in (0, 1, 1800):
            with self.subTest(timeout=timeout):
                deadline = monitor_deadline(timeout, absolute, clock=clock.now, wall_clock=lambda: 1000)
                self.assertEqual(deadline.remaining(), 30)

    def test_expired_cli_resume_emits_original_budget_without_provider_reads(self):
        events = []
        absolute = "2000-01-01T00:00:00+00:00"
        with patch.object(watcher, "run_command") as command, patch.object(watcher.Watcher, "print_event", events.append):
            with self.assertRaisesRegex(watcher.WatchTimeout, "monitor timeout"):
                watcher.main(["--deadline", absolute])
        command.assert_not_called()
        self.assertEqual(events, [{"event": "budget", "deadline": absolute, "indefinite": False}])

    def test_expired_library_resume_returns_timeout_before_provider_reads(self):
        events = []
        with patch.object(watcher, "run_command") as command:
            monitor = watcher.Watcher([target()], deadline="2000-01-01T00:00:00Z", runner=command, emit=events.append)
            self.assertEqual(monitor.watch(once=True), 2)
        command.assert_not_called()
        self.assertEqual(events[-1]["reason"], "monitor timeout")

    def test_absolute_budget_uses_monotonic_clock_after_resume(self):
        clock = FakeClock()
        wall = [1000]
        deadline = monitor_deadline(deadline="1970-01-01T00:17:10Z", clock=clock.now, wall_clock=lambda: wall[0])
        wall[0] = 1
        clock.sleep(20)
        self.assertEqual(deadline.remaining(), 10)


if __name__ == "__main__":
    unittest.main()
