"""Provider-native Actions provenance and external check identity regressions."""

import copy
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline_monitor import Watcher
from pipeline_support import WatchError, ensure_read_only
from pipeline_test_support import FakeClock, target
from test_pipeline_checks import CoverageRunner, check
from test_pipeline_revision import MergeRunner


def actions_check(current, *, identifier=101, suite=101, conclusion="success"):
    return {**check(current, identifier=identifier, conclusion=conclusion),
            "app": {"id": 42, "slug": "github-actions"}, "check_suite": {"id": suite}}


def workflow(current, *, suite=101, run=701, workflow_id=7, event="push"):
    return {"id": run, "workflow_id": workflow_id, "check_suite_id": suite,
            "head_sha": current.head, "event": event, "run_attempt": 1,
            "repository": {"full_name": "owner/project"}}


class ActionsRunner(MergeRunner):
    def __init__(self):
        super().__init__()
        self.merge_checks = []
        self.checks = [actions_check(self.current)]
        self.actions = {101: {"total_count": 1, "workflow_runs": [workflow(self.current)]}}

    def __call__(self, argv, cwd=None, optional=False):
        if argv[:2] == ["gh", "api"] and "/actions/runs?check_suite_id=" in argv[2]:
            suite = int(argv[2].split("check_suite_id=")[1].split("&")[0])
            self.overrides[argv[2]] = self.actions[suite]
        return super().__call__(argv, cwd, optional)


class ActionsProvenanceTests(unittest.TestCase):
    def snapshot(self, runner):
        return Watcher([runner.current], runner=runner, emit=lambda event: None).watch(once=True)

    def test_dispatch_only_green_cannot_satisfy_required_pr_check(self):
        runner = ActionsRunner()
        runner.actions[101]["workflow_runs"][0]["event"] = "workflow_dispatch"
        self.assertEqual(self.snapshot(runner), 2)

    def test_documented_pr_events_and_separate_merge_queue(self):
        eligible = {"push", "pull_request", "pull_request_review", "pull_request_target", "deployment", "deployment_status"}
        for event in sorted(eligible | {"workflow_dispatch", "workflow_run", "schedule", "merge_group"}):
            with self.subTest(event=event):
                runner = ActionsRunner()
                runner.actions[101]["workflow_runs"][0]["event"] = event
                self.assertEqual(self.snapshot(runner), 0 if event in eligible else 2)

    def test_missing_or_ambiguous_provenance_cannot_certify_green(self):
        for kind in ("absent", "multiple", "suite", "repo", "head", "run", "workflow", "attempt", "event", "app"):
            with self.subTest(kind=kind):
                runner = ActionsRunner()
                value = runner.actions[101]["workflow_runs"][0]
                if kind == "absent":
                    runner.actions[101] = {"total_count": 0, "workflow_runs": []}
                elif kind == "multiple":
                    runner.actions[101] = {"total_count": 2, "workflow_runs": [value, copy.deepcopy(value)]}
                elif kind == "suite":
                    value["check_suite_id"] = 202
                elif kind == "repo":
                    value["repository"]["full_name"] = "other/project"
                elif kind == "head":
                    value["head_sha"] = "f" * 40
                elif kind in {"run", "workflow"}:
                    value.pop("id" if kind == "run" else "workflow_id")
                elif kind == "attempt":
                    value.pop("run_attempt")
                elif kind == "event":
                    value.pop("event")
                else:
                    runner.checks[0]["app"].pop("slug")
                with self.assertRaises(WatchError):
                    self.snapshot(runner)

    def test_merge_check_can_map_to_its_verified_source_head_workflow(self):
        runner = ActionsRunner()
        runner.merge_checks = [actions_check(runner.merge)]
        runner.checks = []
        self.assertEqual(self.snapshot(runner), 0)

    def test_non_pr_action_does_not_require_pr_event(self):
        runner = ActionsRunner()
        runner.pr = None
        runner.required = [{"context": "build", "app_id": 42}]
        runner.actions[101]["workflow_runs"][0].pop("event")
        self.assertEqual(self.snapshot(runner), 0)

    def test_external_app_does_not_require_actions_provenance(self):
        runner = MergeRunner()
        self.assertEqual(self.snapshot(runner), 0)
        self.assertFalse(any("/actions/runs?" in call[2] for call in runner.calls if call[:2] == ["gh", "api"]))

    def test_ghe_actions_identity_uses_provider_slug_not_public_app_id(self):
        runner = ActionsRunner()
        runner.current = replace(runner.current, repository="ghe.example/owner/project")
        runner.local_target = runner.current
        runner.merge = replace(runner.merge, repository=runner.current.repository)
        self.assertEqual(self.snapshot(runner), 0)
        calls = [call for call in runner.calls if call[:2] == ["gh", "api"] and "/actions/runs?" in call[2]]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-2:], ["--hostname", "ghe.example"])

    def test_many_jobs_in_same_suite_use_one_lookup_and_reuse_it(self):
        runner = ActionsRunner()
        runner.checks.append({**actions_check(runner.current, identifier=102), "name": "other"})
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        monitor.poll_checks()
        calls = [call for call in runner.calls if call[:2] == ["gh", "api"] and "/actions/runs?" in call[2]]
        self.assertEqual(len(calls), 1)

    def test_suite_lookup_allowlist_is_bounded_and_read_only(self):
        endpoint = "repos/owner/project/actions/runs?check_suite_id=101&per_page=2"
        ensure_read_only(["gh", "api", endpoint, "--method", "GET"])
        for command in (["gh", "api", endpoint, "--method", "POST"],
                        ["gh", "api", endpoint + "&page=2", "--method", "GET"],
                        ["gh", "api", endpoint.replace("per_page=2", "per_page=100"), "--method", "GET"]):
            with self.subTest(command=command), self.assertRaises(WatchError):
                ensure_read_only(command)


class CheckContinuityTests(unittest.TestCase):
    def test_two_jobs_can_finish_a_staggered_rerun_in_the_same_attempt(self):
        runner = ActionsRunner()
        runner.checks = [actions_check(runner.current, conclusion="failure"),
                         {**actions_check(runner.current, identifier=102, conclusion="failure"), "name": "lint"}]
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.actions[101]["workflow_runs"][0]["run_attempt"] = 2
        runner.checks[0] = actions_check(runner.current, identifier=201)
        monitor.poll_checks()
        self.assertEqual(monitor.check_coverage[runner.current.key].failed, 1)
        runner.checks[1] = {**actions_check(runner.current, identifier=202), "name": "lint"}
        monitor.poll_checks()
        self.assertEqual(monitor.watch(once=True), 0)
        calls = [call for call in runner.calls if call[:2] == ["gh", "api"] and "/actions/runs?" in call[2]]
        self.assertEqual(len(calls), 3)

    def test_starting_mid_rerun_cannot_prove_same_attempt_job_replacement(self):
        runner = ActionsRunner()
        runner.actions[101]["workflow_runs"][0]["run_attempt"] = 2
        runner.checks = [actions_check(runner.current, identifier=201),
                         {**actions_check(runner.current, identifier=102, conclusion="failure"), "name": "lint"}]
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.checks[1] = {**actions_check(runner.current, identifier=202), "name": "lint"}
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def replacement(self, *, same_run=False, same_suite=False, sibling=False):
        runner = ActionsRunner()
        runner.checks = [actions_check(runner.current, conclusion="failure")]
        runner.actions[202] = {"total_count": 1, "workflow_runs": [workflow(
            runner.current, suite=202, run=701 if same_run else 702, workflow_id=7 if same_run else 8,
        )]}
        runner.actions[202]["workflow_runs"][0]["run_attempt"] = 2
        good = CoverageRunner(target("good"))
        reads = 0
        def provider(argv, cwd=None, **kwargs):
            nonlocal reads
            if sibling and cwd == good.current.root:
                return good(argv, cwd, **kwargs)
            if argv[:2] == ["gh", "api"] and f"/commits/{runner.current.head}/check-runs?" in argv[2]:
                reads += 1
                if reads > 1:
                    runner.checks = [actions_check(runner.current, identifier=202, suite=101 if same_suite else 202)]
                    runner.actions[101]["workflow_runs"][0]["run_attempt"] = 2
            return runner(argv, cwd, **kwargs)
        events = []
        monitor = Watcher([runner.current, good.current] if sibling else [runner.current], runner=provider,
                          emit=events.append, settle=0)
        return monitor, runner, events

    def test_other_workflow_same_named_check_does_not_replace_failed_member(self):
        monitor, _, _ = self.replacement()
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.watch()

    def test_substituted_check_blocks_only_its_root(self):
        monitor, _, events = self.replacement(sibling=True)
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["roots_blocked"], 1)
        self.assertEqual(events[-1]["roots_passed"], 1)

    def test_verified_same_workflow_run_rerun_is_allowed_and_suite_cached(self):
        for same_suite in (False, True):
            with self.subTest(same_suite=same_suite):
                monitor, runner, _ = self.replacement(same_run=True, same_suite=same_suite)
                self.assertEqual(monitor.watch(), 0)
                calls = [call for call in runner.calls if call[:2] == ["gh", "api"] and "/actions/runs?" in call[2]]
                self.assertEqual(len(calls), 2)

    def test_external_new_check_id_is_not_assumed_to_be_a_rerun(self):
        runner = MergeRunner()
        runner.merge_checks = [check(runner.merge, conclusion="failure", identifier=101)]
        reads = 0
        def provider(argv, cwd=None, **kwargs):
            nonlocal reads
            if argv[:2] == ["gh", "api"] and f"/commits/{runner.merge.head}/check-runs?" in argv[2]:
                reads += 1
                if reads > 1:
                    runner.merge_checks = [check(runner.merge, identifier=202)]
            return runner(argv, cwd, **kwargs)
        with self.assertRaisesRegex(WatchError, "disappeared"):
            Watcher([runner.current], runner=provider, emit=lambda event: None, settle=0).watch()

    def test_external_same_record_can_update_to_success(self):
        runner = MergeRunner()
        runner.merge_checks = [check(runner.merge, conclusion="failure", identifier=101)]
        reads = 0
        def provider(argv, cwd=None, **kwargs):
            nonlocal reads
            if argv[:2] == ["gh", "api"] and f"/commits/{runner.merge.head}/check-runs?" in argv[2]:
                reads += 1
                if reads > 1:
                    runner.merge_checks[0]["conclusion"] = "success"
            return runner(argv, cwd, **kwargs)
        self.assertEqual(Watcher([runner.current], runner=provider, emit=lambda event: None, settle=0).watch(), 0)

    def test_same_workflow_run_new_job_without_new_attempt_is_unverified(self):
        runner = ActionsRunner()
        runner.checks = [actions_check(runner.current, conclusion="failure")]
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.checks = [actions_check(runner.current, identifier=202)]
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def test_same_name_group_cannot_replace_failed_member_even_with_new_attempt(self):
        runner = ActionsRunner()
        runner.checks = [actions_check(runner.current, conclusion="failure"), actions_check(runner.current, identifier=102)]
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.checks = [actions_check(runner.current, identifier=102), actions_check(runner.current, identifier=103)]
        runner.actions[101]["workflow_runs"][0]["run_attempt"] = 2
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def test_combined_status_updates_by_context_without_creator(self):
        runner = CoverageRunner(target(), runs=[], statuses=[{"id": 1, "context": "external", "state": "pending"}])
        clock = FakeClock()
        reads = 0
        def provider(argv, cwd=None, **kwargs):
            nonlocal reads
            if argv[:2] == ["gh", "api"] and "/status?" in argv[2]:
                reads += 1
                if reads > 1:
                    runner.statuses = [{"id": 2, "context": "external", "state": "success"}]
            return runner(argv, cwd, **kwargs)
        self.assertEqual(Watcher([runner.current], runner=provider, emit=lambda event: None,
                                 clock=clock.now, sleep=clock.sleep, settle=0).watch(), 0)
        self.assertNotIn("creator", runner.statuses[0])


if __name__ == "__main__":
    unittest.main()
