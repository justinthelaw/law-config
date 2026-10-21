"""Workflow completion, delayed discovery, and timeout regression tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import watch_pipelines as watcher
from pipeline_test_support import FakeClock, FakeRunner, run_payload, target, default_ci_response, local_metadata_response


class CompletionTests(unittest.TestCase):
    def test_delayed_dependent_workflow_restarts_the_settlement_window(self) -> None:
        selected = target()
        success = run_payload(selected, run_id=1)
        late = run_payload(selected, run_id=2, status="in_progress", conclusion="", workflow="E2E")
        completed = {
            **run_payload(selected, run_id=2, workflow="E2E"),
            "jobs": [{"databaseId": 22, "name": "browser", "status": "completed", "conclusion": "success", "steps": []}],
        }
        clock = FakeClock()
        runner = FakeRunner([[success], [success], [success, late]], [completed])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher(
            [selected],
            runner=runner,
            emit=events.append,
            clock=clock.now,
            sleep=clock.sleep,
            interval=20,
            rediscover=60,
            settle=120,
        )
        self.assertEqual(monitor.watch(), 0)
        self.assertEqual(events[-1]["passed"], 2)
        self.assertGreaterEqual(clock.current, 240)

    def test_timeout_cannot_be_skipped_by_terminal_settlement(self) -> None:
        selected = target()
        clock = FakeClock()
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher(
            [selected],
            runner=FakeRunner([[run_payload(selected)]]),
            emit=events.append,
            clock=clock.now,
            sleep=clock.sleep,
            interval=20,
            settle=20,
            timeout=1,
        )
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["reason"], "monitor timeout")
        self.assertEqual(clock.current, 1)

    def test_timeout_cannot_be_bypassed_by_new_terminal_workflows(self) -> None:
        selected = target()
        clock = FakeClock()
        events: list[dict[str, object]] = []

        class GrowingRunner:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, argv: list[str], cwd: Path | None = None, optional: bool = False) -> str:
                if argv[:3] == ["gh", "auth", "status"]:
                    return ""
                if argv[:3] == ["gh", "run", "list"]:
                    self.calls += 1
                    clock.current += 1
                    return json.dumps([run_payload(selected, run_id=self.calls)])
                return default_ci_response(argv, [run_payload(selected)])

        monitor = watcher.Watcher(
            [selected],
            runner=GrowingRunner(),
            emit=events.append,
            clock=clock.now,
            sleep=clock.sleep,
            settle=0,
            timeout=2,
        )
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["reason"], "monitor timeout")

    def test_timeout_is_checked_after_slow_final_rediscovery(self) -> None:
        selected = target()
        clock = FakeClock()
        events: list[dict[str, object]] = []

        class SlowFinalRunner:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, argv: list[str], cwd: Path | None = None, optional: bool = False) -> str:
                if argv[:3] == ["gh", "auth", "status"]:
                    return ""
                if argv[:3] == ["gh", "run", "list"]:
                    self.calls += 1
                    if self.calls > 1:
                        clock.current += 2
                    return json.dumps([run_payload(selected)])
                return default_ci_response(argv, [run_payload(selected)])

        monitor = watcher.Watcher(
            [selected],
            runner=SlowFinalRunner(),
            emit=events.append,
            clock=clock.now,
            sleep=clock.sleep,
            settle=0,
            timeout=1,
        )
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["reason"], "monitor timeout")

    def test_skipped_only_workflows_block_completion(self) -> None:
        selected = target()
        skipped = run_payload(selected, conclusion="skipped")
        runner = FakeRunner([[skipped]])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append, settle=0)
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["reason"], "no successful exact-commit workflows")
        self.assertEqual(events[-1]["targets"], [selected.label])

    def test_each_target_requires_a_successful_workflow(self) -> None:
        passing = target()
        skipped = target("other")
        passing_run = run_payload(passing)
        skipped_run = run_payload(skipped, conclusion="neutral")

        def runner(argv: list[str], cwd: Path | None = None, optional: bool = False) -> str:
            local = local_metadata_response(argv, passing if cwd == passing.path else skipped)
            if local is not None:
                return local
            if argv[:3] == ["gh", "auth", "status"]:
                return ""
            if argv[:3] == ["gh", "run", "list"]:
                current = argv[argv.index("-R") + 1]
                return json.dumps([passing_run] if current == passing.qualified_repository else [skipped_run])
            return default_ci_response(argv, [passing_run])

        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([passing, skipped], runner=runner, emit=events.append)
        self.assertEqual(monitor.watch(once=True), 2)
        self.assertTrue(any(event.get("targets") == [skipped.label] for event in events))
        self.assertEqual(events[-1]["result"], "blocked")
        self.assertEqual(events[-1]["roots_passed"], 1)
        self.assertEqual(events[-1]["roots_blocked"], 1)

    def test_optional_skipped_workflow_with_success_can_pass(self) -> None:
        selected = target()
        runs = [run_payload(selected, run_id=1), run_payload(selected, run_id=2, conclusion="skipped")]
        monitor = watcher.Watcher([selected], runner=FakeRunner([runs]), emit=lambda event: None)
        self.assertEqual(monitor.watch(once=True), 0)

    def test_saturated_workflow_listing_is_rejected(self) -> None:
        selected = target()
        runs = [run_payload(selected, run_id=1), run_payload(selected, run_id=2)]
        monitor = watcher.Watcher([selected], runner=FakeRunner([runs]), max_runs=2)
        with self.assertRaisesRegex(watcher.WatchError, "2-run limit"):
            monitor.watch(once=True)

    def test_new_monitor_uses_newly_published_commit(self) -> None:
        previous = target(head="a" * 40)
        published = target(head="b" * 40)
        old_run = run_payload(previous, run_id=1)
        new_run = run_payload(published, run_id=2)
        runner = FakeRunner([[old_run, new_run]], local_target=published)
        monitor = watcher.Watcher([published], runner=runner, emit=lambda event: None)
        self.assertEqual(monitor.watch(once=True), 0)
        self.assertEqual(set(monitor.runs), {(published.key, 2)})

    def test_late_workflow_is_discovered(self) -> None:
        selected = target()
        success = run_payload(selected)
        clock = FakeClock()
        runner = FakeRunner([[], [success]])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher(
            [selected],
            runner=runner,
            emit=events.append,
            clock=clock.now,
            sleep=clock.sleep,
            interval=5,
            rediscover=60,
            discovery_grace=30,
        )
        self.assertEqual(monitor.watch(), 0)
        self.assertTrue(any(event["event"] == "discovered" for event in events))

    def test_active_workflow_reaches_terminal_success(self) -> None:
        selected = target()
        active = run_payload(selected, status="in_progress", conclusion="")
        completed = {
            **run_payload(selected),
            "jobs": [{"databaseId": 22, "name": "unit", "status": "completed", "conclusion": "success", "steps": []}],
        }
        runner = FakeRunner([[active]], [completed])
        events: list[dict[str, object]] = []
        clock = FakeClock()
        monitor = watcher.Watcher(
            [selected],
            runner=runner,
            emit=events.append,
            clock=clock.now,
            sleep=clock.sleep,
            settle=0,
        )
        self.assertEqual(monitor.watch(), 0)
        self.assertEqual(events[-1]["result"], "passed")
