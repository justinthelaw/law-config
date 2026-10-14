"""Deadline regressions at discovery, subprocess, retry, and completion boundaries."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import watch_pipelines as watcher
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
            "pipeline_support.subprocess.run", side_effect=command
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
            "pipeline_support.subprocess.run", side_effect=command
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
        with patch("pipeline_support.subprocess.run", side_effect=command):
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
        with patch("pipeline_support.subprocess.run", side_effect=command):
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
        with patch("pipeline_support.subprocess.run", side_effect=command):
            self.assertEqual(monitor.watch(once=True), 2)
        self.assertEqual(budgets, [1, 0.75, 0.5, 0.25])


if __name__ == "__main__":
    unittest.main()
