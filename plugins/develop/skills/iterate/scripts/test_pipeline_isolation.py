"""Independent roots continue across discovery, runtime and completion failures."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import watch_pipelines as cli
from pipeline_monitor import Watcher
from pipeline_support import WatchError, WatchTimeout
from pipeline_test_support import FakeClock, FakeRunner, run_payload, target


class RootIsolationTests(unittest.TestCase):
    def run_roots(self, stage, *, reverse=False, once=True, all_blocked=False, pending=False):
        bad, good = target("bad"), target("good")
        selected = [good, bad] if reverse else [bad, good]
        clock, events = FakeClock(), []
        runners = {
            item.root: FakeRunner([[run_payload(item, status="in_progress" if stage == "poll" or pending else "completed")]],
                                  [run_payload(item, status="in_progress" if pending and once else "completed")], local_target=item)
            for item in selected
        }
        calls = []

        def runner(argv, cwd=None, **kwargs):
            root = cwd
            calls.append((root, tuple(argv)))
            failing = all_blocked or root == bad.root
            if failing and (
                stage == "auth" and argv[:3] == ["gh", "auth", "status"]
                or stage == "discovery" and argv[:3] == ["gh", "run", "list"]
                or stage == "poll" and argv[:3] == ["gh", "run", "view"]
                or stage == "checks" and argv[:2] == ["gh", "api"] and "/check-runs?" in argv[2]
                or stage == "identity" and argv[:3] == ["git", "remote", "get-url"]
            ):
                raise WatchError(f"{stage} unavailable")
            return runners[root](argv, cwd=cwd, **kwargs)

        monitor = Watcher(selected, runner=runner, emit=events.append, clock=clock.now,
                          sleep=clock.sleep, interval=1, settle=0)
        result = monitor.watch(once=once)
        return result, events, calls, clock

    def test_each_runtime_stage_isolated_in_either_root_order(self):
        for stage in ("auth", "discovery", "poll", "checks", "identity"):
            for reverse in (False, True):
                with self.subTest(stage=stage, reverse=reverse):
                    result, events, _, _ = self.run_roots(stage, reverse=reverse)
                    self.assertEqual(result, 2)
                    self.assertTrue(any(event.get("root") == str(target("good").root)
                                        and event.get("result") == "passed" for event in events))
                    self.assertEqual(events[-1]["result"], "blocked")
                    self.assertEqual(events[-1]["roots_blocked"], 1)
                    self.assertEqual(events[-1]["roots_passed"], 1)

    def test_empty_library_target_selection_cannot_pass(self):
        events = []
        self.assertEqual(Watcher([], emit=events.append).watch(once=True), 2)
        self.assertEqual(events[-1]["reason"], "no monitoring targets")

    def test_all_blocked_has_no_success(self):
        result, events, _, _ = self.run_roots("auth", all_blocked=True)
        self.assertEqual(result, 2)
        self.assertEqual(events[-1]["roots_blocked"], 2)
        self.assertFalse(any(event.get("result") == "passed" for event in events))

    def test_pending_and_blocked_retains_both_outcomes(self):
        result, events, _, _ = self.run_roots("auth", pending=True)
        self.assertEqual(result, 2)
        self.assertEqual(events[-1]["roots_pending"], 1)
        self.assertEqual(events[-1]["roots_blocked"], 1)

    def test_continuous_polling_reaches_healthy_completion_after_block(self):
        result, events, _, _ = self.run_roots("auth", pending=True, once=False)
        self.assertEqual(result, 2)
        self.assertEqual(events[-1]["roots_passed"], 1)
        self.assertEqual(events[-1]["roots_blocked"], 1)

    def test_pending_first_root_does_not_starve_healthy_root(self):
        slow, good = target("slow"), target("good")
        clock, events = FakeClock(), []
        runners = {
            slow.root: FakeRunner([[run_payload(slow, status="in_progress")]],
                                  [run_payload(slow, status="in_progress")], local_target=slow),
            good.root: FakeRunner([[run_payload(good)]], local_target=good),
        }
        result = Watcher([slow, good], runner=lambda argv, cwd=None, **kw: runners[cwd](argv, cwd=cwd, **kw),
                         emit=events.append, clock=clock.now, sleep=clock.sleep,
                         timeout=5, settle=0, interval=1).watch()
        self.assertEqual(result, 2)
        self.assertTrue(any(event.get("root") == str(good.root) and event.get("result") == "passed"
                            for event in events))
        self.assertEqual(events[-1]["reason"], "monitor timeout")
        self.assertEqual(clock.current, 5)

    def test_timeout_is_global_and_does_not_start_next_root(self):
        selected = [target("first"), target("second")]
        events, calls = [], []

        def runner(argv, cwd=None, **kwargs):
            calls.append(cwd)
            raise WatchTimeout("monitor timeout")

        result = Watcher(selected, runner=runner, emit=events.append).watch(once=True)
        self.assertEqual(result, 2)
        self.assertEqual(calls, [selected[0].root])
        self.assertEqual(events[-1]["reason"], "monitor timeout")
        self.assertFalse(any(event.get("result") == "passed" for event in events))

    def test_timeout_during_failure_logs_remains_global(self):
        bad, good = target("bad"), target("good")
        failed = run_payload(bad, conclusion="failure")
        delegate = FakeRunner([[failed]], [failed], local_target=bad)
        events, calls = [], []

        def runner(argv, cwd=None, **kwargs):
            calls.append(cwd)
            if "--log-failed" in argv:
                raise WatchTimeout("monitor timeout")
            return delegate(argv, cwd=cwd, **kwargs)

        result = Watcher([bad, good], runner=runner, emit=events.append).watch(once=True)
        self.assertEqual(result, 2)
        self.assertNotIn(good.root, calls)
        self.assertEqual(events[-1]["reason"], "monitor timeout")
        self.assertFalse(any(event["event"] == "log-error" for event in events))

    def test_submodule_failure_blocks_owning_group_only(self):
        parent, child, good = target("parent"), target("parent", component="child"), target("good")
        runners = {item.path: FakeRunner([[run_payload(item)]], local_target=item) for item in (parent, child, good)}
        events = []

        def runner(argv, cwd=None, **kwargs):
            if cwd == child.path and argv[:3] == ["gh", "run", "list"]:
                raise WatchError("submodule inaccessible")
            return runners[cwd](argv, cwd=cwd, **kwargs)

        result = Watcher([parent, child, good], runner=runner, emit=events.append).watch(once=True)
        self.assertEqual(result, 2)
        self.assertFalse(any(event.get("root") == str(parent.root) and event.get("result") == "passed"
                             for event in events))
        self.assertEqual(events[-1]["roots_passed"], 1)

    def test_same_remote_in_separate_checkouts_does_not_share_completion(self):
        good = target("good")
        bad = replace(target("bad"), repository=good.repository)
        events = []
        delegates = {item.root: FakeRunner([[run_payload(item)]], local_target=item) for item in (bad, good)}

        def runner(argv, cwd=None, **kwargs):
            if cwd == bad.path and argv[:3] == ["git", "remote", "get-url"]:
                raise WatchError("checkout changed")
            return delegates[cwd](argv, cwd=cwd, **kwargs)

        self.assertEqual(Watcher([bad, good], runner=runner, emit=events.append).watch(once=True), 2)
        self.assertEqual(events[-1]["roots_passed"], 1)
        self.assertEqual(events[-1]["roots_blocked"], 1)

    def test_cli_discovery_and_construction_failures_do_not_skip_healthy_root(self):
        for stage in ("root", "submodules", "metadata"):
            for reverse in (False, True):
                with self.subTest(stage=stage, reverse=reverse):
                    bad, good = target("bad"), target("good")
                    events = []
                    delegate = FakeRunner([[run_payload(good)]], local_target=good)

                    def runner(argv, cwd=None, **kwargs):
                        if cwd == bad.path.resolve():
                            if stage == "root" or stage == "submodules" and argv[1] == "submodule" or stage == "metadata" and argv[1] == "branch":
                                raise WatchError(f"{stage} unavailable")
                        if argv == ["git", "rev-parse", "--show-toplevel"]:
                            return str(cwd)
                        if argv == ["git", "submodule", "status", "--recursive"]:
                            return ""
                        return delegate(argv, cwd=cwd)

                    roots = [good, bad] if reverse else [bad, good]
                    with patch.object(cli, "run_command", side_effect=runner), patch.object(Watcher, "print_event", events.append):
                        result = cli.main(["--once", *[value for item in roots for value in ("--repo", str(item.path))]])
                    self.assertEqual(result, 2)
                    self.assertEqual(events[-1]["roots_passed"], 1)
                    self.assertEqual(events[-1]["roots_blocked"], 1)


class AggregateReadinessTests(unittest.TestCase):
    def changed_after_early_pass(self, change, *, once=False):
        early, late = target("early"), target("late")
        clock, events = FakeClock(), []
        early_passed, changed = False, False
        delegates = {
            early.root: FakeRunner([[run_payload(early)]], local_target=early),
            late.root: FakeRunner([[run_payload(late, status="completed" if once else "in_progress")]],
                                 [run_payload(late, status="in_progress"), run_payload(late)], local_target=late),
        }

        def emit(event):
            nonlocal early_passed
            events.append(event)
            if event.get("root") == str(early.root) and event.get("result") == "passed":
                early_passed = True

        def runner(argv, cwd=None, **kwargs):
            nonlocal changed
            if cwd == late.root and early_passed and (clock.current > 0 or once) and not changed:
                changed = True
                if change == "head":
                    delegates[early.root].local_target = replace(early, head="b" * 40)
                elif change == "remote":
                    delegates[early.root].local_target = replace(early, repository="owner/moved")
                elif change in ("rerun", "late_workflow", "endless_pending"):
                    late_work = change != "rerun"
                    fresh = run_payload(early, run_id=2 if late_work else 1,
                                        attempt=1 if late_work else 2,
                                        status="in_progress" if late_work else "completed",
                                        conclusion="" if late_work else "failure")
                    delegates[early.root].lists = [[run_payload(early), fresh]] if late_work else [[fresh]]
                    delegates[early.root].views = [fresh, run_payload(early, run_id=2)] if change == "late_workflow" else [fresh]
            if cwd == early.root and changed:
                if change == "access" and argv[:3] == ["gh", "run", "list"]:
                    raise WatchError("readback access lost")
                if change == "timeout" and argv[:3] == ["gh", "run", "list"]:
                    raise WatchTimeout("monitor timeout")
                if change == "checks" and argv[:2] == ["gh", "api"] and "/status?" in argv[2]:
                    return json.dumps({"sha": early.head, "total_count": 1,
                                       "statuses": [{"id": 1, "context": "external", "state": "failure"}]})
            return delegates[cwd](argv, cwd=cwd, **kwargs)

        result = Watcher([early, late], runner=runner, emit=emit, clock=clock.now,
                         sleep=clock.sleep, interval=1, settle=0, timeout=30).watch(once=once)
        self.assertTrue(early_passed)
        self.assertTrue(changed)
        if change == "endless_pending":
            self.assertEqual(clock.current, 30)
        return result, events, delegates

    def test_early_root_identity_is_revalidated_before_aggregate_success(self):
        for change in ("head", "remote"):
            with self.subTest(change=change):
                result, events, _ = self.changed_after_early_pass(change)
                self.assertEqual(result, 2)
                self.assertEqual(events[-1]["result"], "blocked")
                self.assertEqual(events[-1]["roots_blocked"], 1)
                self.assertEqual(events[-1]["roots_passed"], 1)

    def test_early_root_late_workflows_reruns_and_checks_invalidate_old_pass(self):
        for change, expected in (("rerun", 1), ("checks", 1)):
            with self.subTest(change=change):
                result, events, _ = self.changed_after_early_pass(change)
                self.assertEqual(result, expected)
                self.assertNotEqual(events[-1].get("result"), "passed")

    def test_continuous_final_revalidation_resumes_only_new_pending_work(self):
        result, events, delegates = self.changed_after_early_pass("late_workflow")
        self.assertEqual(result, 0)
        self.assertTrue(any(event["event"] == "root-reopened" and event["root"] == str(target("early").root)
                            for event in events))
        self.assertEqual(events[-1]["result"], "passed")
        self.assertEqual(events[-1]["roots_passed"], 2)
        late_auth = [call for call in delegates[target("late").root].calls if call[:3] == ("gh", "auth", "status")]
        self.assertEqual(len(late_auth), 3)  # Initial monitor and two final snapshots; no resumed polling.

    def test_once_final_revalidation_reports_new_pending_work(self):
        result, events, _ = self.changed_after_early_pass("late_workflow", once=True)
        self.assertEqual(result, 3)
        self.assertEqual(events[-1]["result"], "pending")
        self.assertTrue(any(event["event"] == "root-reopened" for event in events))

    def test_reopened_work_keeps_original_global_deadline(self):
        result, events, _ = self.changed_after_early_pass("endless_pending")
        self.assertEqual(result, 2)
        self.assertEqual(events[-1]["reason"], "monitor timeout")
        self.assertTrue(any(event["event"] == "root-reopened" for event in events))

    def test_unchanged_roots_get_only_one_final_snapshot(self):
        result, events, delegates = self.changed_after_early_pass("unchanged")
        self.assertEqual(result, 0)
        for delegate in delegates.values():
            self.assertEqual(sum(call[:3] == ("gh", "auth", "status") for call in delegate.calls), 2)
        self.assertFalse(any(event["event"] == "root-reopened" for event in events))

    def test_final_revalidation_access_failure_is_root_local(self):
        result, events, delegates = self.changed_after_early_pass("access")
        self.assertEqual(result, 2)
        self.assertEqual(events[-1]["roots_blocked"], 1)
        self.assertEqual(events[-1]["roots_passed"], 1)
        self.assertTrue(any("readback access lost" in event.get("reason", "") for event in events))

    def test_final_revalidation_timeout_remains_global(self):
        result, events, _ = self.changed_after_early_pass("timeout")
        self.assertEqual(result, 2)
        self.assertEqual(events[-1]["reason"], "monitor timeout")


if __name__ == "__main__":
    unittest.main()
