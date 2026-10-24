"""Provider fixtures for fresh merge checks and independent workflow identities."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline_monitor import Watcher
from pipeline_support import WatchError
from pipeline_test_support import FakeRunner, run_payload, target
from test_pipeline_checks import CoverageRunner, check


class MergeRunner(CoverageRunner):
    def __init__(self):
        current = target(branch="topic")
        super().__init__(current, runs=[])
        self.pr = {"number": 7, "url": "https://github.com/owner/project/pull/7",
                   "headRefOid": current.head, "headRefName": "topic",
                   "headRepositoryOwner": {"login": "owner"}, "isCrossRepository": False,
                   "baseRefName": "main"}
        self.merge = replace(current, head="c" * 40)
        self.pull = {"number": 7, "state": "open", "merged": False, "mergeable": True,
                     "head": {"sha": current.head, "ref": "topic", "repo": {"full_name": "owner/project"}},
                     "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "owner/project"}},
                     "merge_commit_sha": self.merge.head}
        self.commit = {"sha": self.merge.head, "parents": [{"sha": "b" * 40}, {"sha": current.head}]}
        self.merge_checks = [check(self.merge)]
        self.merge_statuses = []
        self.overrides["repos/owner/project/branches/main"] = {
            "name": "main", "commit": {"sha": "b" * 40}, "protected": True,
            "protection": {"required_status_checks": {
                "contexts": ["build"], "checks": [{"context": "build", "app_id": 42}],
            }},
        }

    def __call__(self, argv, cwd=None, optional=False):
        if argv[:2] == ["gh", "api"]:
            endpoint = argv[2]
            if endpoint.endswith("/pulls/7"):
                self.overrides[endpoint] = self.pull
            if endpoint.endswith("/git/commits/" + self.merge.head):
                self.overrides[endpoint] = self.commit
            if "/commits/" + self.merge.head + "/check-runs?" in endpoint:
                self.overrides[endpoint] = {"total_count": len(self.merge_checks), "check_runs": self.merge_checks}
            if "/commits/" + self.merge.head + "/status?" in endpoint:
                self.overrides[endpoint] = {"sha": self.merge.head, "total_count": len(self.merge_statuses), "statuses": self.merge_statuses}
        return super().__call__(argv, cwd, optional)


class MergeRevisionTests(unittest.TestCase):
    def snapshot(self, runner):
        events = []
        result = Watcher([runner.current], runner=runner, emit=events.append).watch(once=True)
        return result, events

    def test_malformed_native_enums_block_only_the_affected_root(self):
        for field in ("status", "conclusion", "state"):
            for malformed in ([], {}):
                with self.subTest(field=field, malformed=malformed):
                    bad = MergeRunner()
                    if field == "state":
                        bad.merge_statuses = [{"id": 8, "context": "external", "state": malformed}]
                    else:
                        bad.merge_checks[0][field] = malformed
                    good = CoverageRunner(target("good"))
                    def provider(argv, cwd=None, **kwargs):
                        return (good if cwd == good.current.root else bad)(argv, cwd, **kwargs)
                    events = []
                    monitor = Watcher([bad.current, good.current], runner=provider,
                                      emit=events.append, settle=0)
                    self.assertEqual(monitor.watch(), 2)
                    self.assertTrue(any(event["event"] == "root-blocked"
                                        and event["root"] == str(bad.current.root) for event in events))
                    self.assertTrue(any(event["event"] == "root-summary" and event.get("result") == "passed"
                                        and event["root"] == str(good.current.root) for event in events))
                    self.assertEqual(events[-1]["roots_blocked"], 1)
                    self.assertEqual(events[-1]["roots_passed"], 1)

    def test_required_merge_check_satisfies_missing_head_check(self):
        runner = MergeRunner()
        result, events = self.snapshot(runner)
        self.assertEqual(result, 0)
        coverage = next(event for event in events if event["event"] == "check-coverage")
        self.assertEqual(coverage["sha"], runner.merge.head)
        self.assertEqual(coverage["head_sha"], runner.current.head)
        self.assertFalse(any("/commits/" + runner.current.head + "/" in call[2]
                             for call in runner.calls if call[:2] == ["gh", "api"]))

    def test_merge_failure_cannot_borrow_head_success(self):
        runner = MergeRunner()
        runner.checks = [check(runner.current)]
        runner.merge_checks = [check(runner.merge, conclusion="failure")]
        self.assertEqual(self.snapshot(runner)[0], 1)

    def test_empty_merge_coverage_falls_back_to_head(self):
        runner = MergeRunner()
        runner.merge_checks = []
        runner.checks = [check(runner.current)]
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_merge_commit_status_is_evaluated_without_head_fallback(self):
        runner = MergeRunner()
        runner.overrides["repos/owner/project/branches/main"]["protection"]["required_status_checks"]["checks"][0]["app_id"] = None
        runner.merge_checks = []
        runner.merge_statuses = [{"id": 8, "context": "build", "state": "success"}]
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_unrelated_merge_check_does_not_borrow_required_head_check(self):
        runner = MergeRunner()
        runner.merge_checks = [check(runner.merge, name="other")]
        runner.checks = [check(runner.current)]
        self.assertEqual(self.snapshot(runner)[0], 2)

    def test_explicit_absent_merge_falls_back_to_head(self):
        runner = MergeRunner()
        runner.pull["merge_commit_sha"] = None
        runner.pull["mergeable"] = False
        runner.checks = [check(runner.current)]
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_partial_sha256_is_rejected_before_use(self):
        runner = MergeRunner()
        runner.pull["merge_commit_sha"] = "a" * 48
        with self.assertRaisesRegex(WatchError, "invalid pull-request test-merge SHA"):
            self.snapshot(runner)
        self.assertFalse(any("/git/commits/" in call[2] for call in runner.calls
                             if call[:2] == ["gh", "api"]))

    def test_missing_merge_identity_is_unverified(self):
        runner = MergeRunner()
        runner.pull.pop("merge_commit_sha")
        runner.checks = [check(runner.current)]
        with self.assertRaisesRegex(WatchError, "test-merge identity is unavailable"):
            self.snapshot(runner)

    def test_unknown_merge_calculation_does_not_fall_back_to_green_head(self):
        runner = MergeRunner()
        runner.pull["mergeable"] = None
        runner.pull["merge_commit_sha"] = None
        runner.checks = [check(runner.current)]
        with self.assertRaisesRegex(WatchError, "test-merge calculation is incomplete"):
            self.snapshot(runner)

    def test_unreadable_merge_coverage_never_falls_back(self):
        runner = MergeRunner()
        runner.checks = [check(runner.current)]
        runner.overrides[f"repos/owner/project/commits/{runner.merge.head}/check-suites?per_page=1&page=1"] = WatchError("HTTP 403")
        with self.assertRaisesRegex(WatchError, "403"):
            self.snapshot(runner)

    def test_stale_or_unrelated_merge_is_rejected(self):
        for change in ("head", "base", "number", "repository", "closed", "parents"):
            with self.subTest(change=change):
                runner = MergeRunner()
                if change in {"head", "base"}:
                    runner.pull[change]["sha"] = "d" * 40
                elif change == "number":
                    runner.pull["number"] = 9
                elif change == "repository":
                    runner.pull["head"]["repo"]["full_name"] = "other/project"
                elif change == "closed":
                    runner.pull["state"] = "closed"
                else:
                    runner.commit["parents"][1]["sha"] = "d" * 40
                with self.assertRaises(WatchError):
                    self.snapshot(runner)

    def test_base_change_after_poll_prevents_success(self):
        runner = MergeRunner()
        def run(argv, cwd=None, **kwargs):
            response = runner(argv, cwd, **kwargs)
            if argv[:2] == ["gh", "api"] and "/status?" in argv[2]:
                runner.pull["base"]["sha"] = "d" * 40
            return response
        with self.assertRaises(WatchError):
            Watcher([runner.current], runner=run, emit=lambda event: None).watch(once=True)

    def test_stale_pr_base_metadata_cannot_certify_changed_base_branch(self):
        runner = MergeRunner()
        runner.overrides["repos/owner/project/branches/main"]["commit"]["sha"] = "d" * 40
        with self.assertRaisesRegex(WatchError, "base branch changed"):
            self.snapshot(runner)

    def test_merge_parent_read_is_cached_only_for_same_context(self):
        runner = MergeRunner()
        monitor = Watcher([runner.current], runner=runner, emit=lambda event: None)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        monitor.poll_checks()
        self.assertEqual(sum("/git/commits/" in call[2] for call in runner.calls
                             if call[:2] == ["gh", "api"]), 1)
        runner.pull["base"]["sha"] = "d" * 40
        with self.assertRaisesRegex(WatchError, "current PR head and base"):
            monitor.poll_checks()

    def test_non_pr_target_adds_no_merge_lookup(self):
        runner = CoverageRunner(target())
        self.assertEqual(self.snapshot(runner)[0], 0)
        self.assertFalse(any("/pulls/" in call[2] or "/git/commits/" in call[2]
                             for call in runner.calls if call[:2] == ["gh", "api"]))


class WorkflowIdentityTests(unittest.TestCase):
    def test_malformed_workflow_enums_block_only_the_affected_root(self):
        for source in ("list", "view"):
            for field in ("status", "conclusion"):
                for malformed in (["invalid"], {"invalid": True}):
                    with self.subTest(source=source, field=field, malformed=malformed):
                        bad, good = target("bad"), target("good")
                        invalid = run_payload(bad)
                        invalid[field] = malformed
                        initial = invalid if source == "list" else run_payload(bad, status="queued", conclusion="")
                        runners = {bad.root: FakeRunner([[initial]], [invalid], local_target=bad),
                                   good.root: FakeRunner([[run_payload(good)]], local_target=good)}
                        events = []
                        monitor = Watcher([bad, good],
                                          runner=lambda argv, cwd=None, **kw: runners[cwd](argv, cwd=cwd, **kw),
                                          emit=events.append, settle=0)
                        self.assertEqual(monitor.watch(once=True), 2)
                        self.assertEqual(events[-1]["roots_blocked"], 1)
                        self.assertEqual(events[-1]["roots_passed"], 1)
                        self.assertTrue(any(event["event"] == "root-blocked"
                                            and event["root"] == str(bad.root) for event in events))
                        self.assertTrue(any(event["event"] == "root-summary" and event.get("result") == "passed"
                                            and event["root"] == str(good.root) for event in events))
                        if source == "list":
                            self.assertNotIn((bad.key, 1), monitor.runs)
                        else:
                            self.assertEqual(monitor.runs[(bad.key, 1)][1], initial)

    def test_disappeared_sole_success_cannot_pass_final_rediscovery(self):
        current = target()
        run = run_payload(current)
        runner = FakeRunner([[run], []])
        monitor = Watcher([current], runner=runner, emit=lambda event: None, settle=0)
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.watch()
        self.assertEqual(monitor.runs[(current.key, 1)][1], run)

    def test_disappeared_run_keeps_healthy_sibling_independent(self):
        bad, good = target("bad"), target("good")
        runners = {bad.root: FakeRunner([[run_payload(bad)], []], local_target=bad),
                   good.root: FakeRunner([[run_payload(good)]], local_target=good)}
        events = []
        monitor = Watcher([bad, good], runner=lambda argv, cwd=None, **kw: runners[cwd](argv, cwd=cwd, **kw),
                          emit=events.append, settle=0)
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["roots_passed"], 1)
        self.assertEqual(events[-1]["roots_blocked"], 1)
        self.assertIn((bad.key, 1), monitor.runs)

    def test_duplicate_run_identity_is_unverified(self):
        current = target()
        runner = FakeRunner([[run_payload(current), run_payload(current)]])
        with self.assertRaisesRegex(WatchError, "Duplicate workflow"):
            Watcher([current], runner=runner, emit=lambda event: None).watch(once=True)

    def test_invalid_run_ids_block_only_their_root(self):
        for identifier in (None, "bad", "1", True, -1, 0, 1.5):
            for reverse in (False, True):
                with self.subTest(identifier=identifier, reverse=reverse):
                    bad, good = target("bad"), target("good")
                    malformed = run_payload(bad)
                    if identifier is None:
                        malformed.pop("databaseId")
                    else:
                        malformed["databaseId"] = identifier
                    runners = {bad.root: FakeRunner([[malformed]], local_target=bad),
                               good.root: FakeRunner([[run_payload(good)]], local_target=good)}
                    events = []
                    monitor = Watcher([good, bad] if reverse else [bad, good],
                                      runner=lambda argv, cwd=None, **kw: runners[cwd](argv, cwd=cwd, **kw),
                                      emit=events.append)
                    self.assertEqual(monitor.watch(once=True), 2)
                    self.assertEqual(events[-1]["roots_passed"], 1)
                    self.assertEqual(events[-1]["roots_blocked"], 1)


class BoundPolicyTests(unittest.TestCase):
    @staticmethod
    def policies(runner, topic=(), base=()):
        for branch, sha, names in (("topic", runner.current.head, topic), ("main", "b" * 40, base)):
            runner.overrides[f"repos/owner/project/branches/{branch}"] = {
                "name": branch, "commit": {"sha": sha}, "protected": True,
                "protection": {"required_status_checks": {
                    "contexts": list(names), "checks": [{"context": name, "app_id": None} for name in names],
                }},
            }

    def snapshot(self, runner):
        return Watcher([runner.current], runner=runner, emit=lambda event: None).watch(once=True)

    def test_publication_failure_cannot_borrow_merge_success(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["merge-only"])
        runner.statuses = [{"id": 1, "context": "topic-only", "state": "failure"}]
        runner.merge_checks = [check(runner.merge, "topic-only"), check(runner.merge, "merge-only", identifier=2)]
        self.assertEqual(self.snapshot(runner), 1)

    def test_missing_publication_check_cannot_borrow_merge_result(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["merge-only"])
        runner.merge_checks = [check(runner.merge, "topic-only"), check(runner.merge, "merge-only", identifier=2)]
        self.assertEqual(self.snapshot(runner), 2)

    def test_publication_failure_keeps_healthy_root_independent(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["build"])
        runner.statuses = [{"id": 1, "context": "topic-only", "state": "failure"}]
        good = CoverageRunner(target("good"))
        events = []
        result = Watcher([runner.current, good.current], emit=events.append, runner=lambda argv, cwd=None, **kw:
                         (good if cwd == good.current.root else runner)(argv, cwd, **kw)).watch(once=True)
        self.assertEqual(result, 1)
        self.assertEqual(events[-1]["roots_failed"], 1)
        self.assertEqual(events[-1]["roots_passed"], 1)

    def test_ruleset_context_keeps_its_publication_branch_binding(self):
        runner = MergeRunner()
        self.policies(runner, (), ["build"])
        runner.overrides["repos/owner/project/rules/branches/topic?per_page=100&page=1"] = [{
            "type": "required_status_checks", "parameters": {
                "required_status_checks": [{"context": "topic-rule", "integration_id": 42}],
            },
        }]
        runner.checks = [check(runner.current, "topic-rule", conclusion="failure")]
        runner.merge_checks.append(check(runner.merge, "topic-rule", identifier=2))
        self.assertEqual(self.snapshot(runner), 1)

    def test_same_required_context_check_and_status_both_must_pass(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["build"])
        runner.overrides["repos/owner/project/branches/topic"]["protection"]["required_status_checks"]["checks"][0]["app_id"] = 42
        runner.checks = [check(runner.current, "topic-only")]
        runner.statuses = [{"id": 8, "context": "topic-only", "state": "failure"}]
        self.assertEqual(self.snapshot(runner), 1)

    def test_distinct_requirements_pass_on_their_own_revisions(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["merge-only"])
        runner.statuses = [{"id": 1, "context": "topic-only", "state": "success"}]
        runner.merge_checks = [check(runner.merge, "merge-only")]
        self.assertEqual(self.snapshot(runner), 0)

    def test_overlapping_requirement_must_pass_both_revisions(self):
        for head_state, merge_conclusion, expected in (("failure", "success", 1), ("success", "failure", 1), ("success", "success", 0)):
            with self.subTest(head=head_state, merge=merge_conclusion):
                runner = MergeRunner()
                self.policies(runner, ["build"], ["build"])
                runner.statuses = [{"id": 1, "context": "build", "state": head_state}]
                runner.merge_checks = [check(runner.merge, conclusion=merge_conclusion)]
                self.assertEqual(self.snapshot(runner), expected)

    def test_base_only_required_check_uses_merge_even_when_head_copy_failed(self):
        runner = MergeRunner()
        self.policies(runner, (), ["build"])
        runner.checks = [check(runner.current, conclusion="failure")]
        self.assertEqual(self.snapshot(runner), 0)

    def test_optional_head_copy_of_base_check_does_not_override_merge(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["build"])
        runner.checks = [check(runner.current, "topic-only"), check(runner.current, "build", conclusion="failure", identifier=2)]
        self.assertEqual(self.snapshot(runner), 0)

    def test_no_requirements_still_observes_failure_on_effective_revision(self):
        runner = MergeRunner()
        self.policies(runner)
        runner.merge_checks = [check(runner.merge, conclusion="failure")]
        self.assertEqual(self.snapshot(runner), 1)

    def test_no_requirements_remain_empty_on_both_branches(self):
        runner = MergeRunner()
        self.policies(runner)
        runner.checks = [check(runner.current, conclusion="failure")]
        self.assertEqual(self.snapshot(runner), 0)

    def test_optional_effective_merge_failure_still_blocks_required_success(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["build"])
        runner.checks = [check(runner.current, "topic-only")]
        runner.merge_checks.append(check(runner.merge, "optional", conclusion="failure", identifier=2))
        self.assertEqual(self.snapshot(runner), 1)

    def test_empty_merge_checks_apply_both_policies_to_one_head_snapshot(self):
        runner = MergeRunner()
        self.policies(runner, ["topic-only"], ["merge-only"])
        runner.merge_checks = []
        runner.checks = [check(runner.current, "topic-only"), check(runner.current, "merge-only", identifier=2)]
        self.assertEqual(self.snapshot(runner), 0)
        reads = [call for call in runner.calls if call[:2] == ["gh", "api"]
                 and f"/commits/{runner.current.head}/check-runs?" in call[2]]
        self.assertEqual(len(reads), 1)


class VanishedCoverageTests(unittest.TestCase):
    def monitor(self, runner):
        return Watcher([runner.current], runner=runner, emit=lambda event: None, settle=0)

    def test_merge_checks_disappearing_cannot_switch_back_to_green_head(self):
        runner = MergeRunner()
        runner.checks = [check(runner.current)]
        monitor = self.monitor(runner)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.merge_checks = []
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def test_individual_success_disappearing_is_unverified_with_other_results_present(self):
        for source in ("check", "status"):
            with self.subTest(source=source):
                runner = MergeRunner()
                runner.merge_checks.append(check(runner.merge, "other", identifier=2))
                runner.merge_statuses = [{"id": 3, "context": "external", "state": "success"}]
                monitor = self.monitor(runner)
                monitor.discover_runs(initial=True)
                monitor.poll_checks()
                if source == "check":
                    runner.merge_checks.pop()
                else:
                    runner.merge_statuses = []
                with self.assertRaisesRegex(WatchError, "disappeared"):
                    monitor.poll_checks()

    def test_replacement_external_check_id_is_unverified(self):
        runner = MergeRunner()
        monitor = self.monitor(runner)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.merge_checks[0]["id"] = 99
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def test_disappeared_same_named_check_is_detected_by_multiplicity(self):
        runner = MergeRunner()
        runner.merge_checks.append(check(runner.merge, identifier=2))
        monitor = self.monitor(runner)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.merge_checks.pop()
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def test_head_individual_status_disappearance_is_unverified(self):
        runner = CoverageRunner(target(), statuses=[{"id": 1, "context": "external", "state": "success"}])
        monitor = self.monitor(runner)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.statuses = []
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def test_new_merge_revision_does_not_inherit_old_missing_checks(self):
        runner = MergeRunner()
        monitor = self.monitor(runner)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.merge = replace(runner.merge, head="d" * 40)
        runner.pull["merge_commit_sha"] = runner.merge.head
        runner.commit["sha"] = runner.merge.head
        runner.merge_checks = []
        runner.checks = [check(runner.current)]
        monitor.poll_checks()
        self.assertEqual(monitor.check_coverage[runner.current.key].sha, runner.current.head)
        runner.merge = replace(runner.merge, head="c" * 40)
        runner.pull["merge_commit_sha"] = runner.merge.head
        runner.commit["sha"] = runner.merge.head
        with self.assertRaisesRegex(WatchError, "disappeared"):
            monitor.poll_checks()

    def test_revision_history_is_bounded(self):
        runner = MergeRunner()
        monitor = self.monitor(runner)
        monitor.discover_runs(initial=True)
        monitor.poll_checks()
        runner.merge = replace(runner.merge, head="d" * 40)
        runner.pull["merge_commit_sha"] = runner.merge.head
        runner.commit["sha"] = runner.merge.head
        runner.merge_checks = [check(runner.merge)]
        with patch("pipeline_monitor.MAX_CHECK_SNAPSHOTS", 1), self.assertRaisesRegex(WatchError, "bounded revision coverage"):
            monitor.poll_checks()

    def test_final_settlement_blocks_vanished_merge_but_finishes_healthy_root(self):
        runner = MergeRunner()
        runner.checks = [check(runner.current)]
        good = CoverageRunner(target("good"))
        reads = 0
        def provider(argv, cwd=None, **kwargs):
            nonlocal reads
            if cwd == good.current.root:
                return good(argv, cwd, **kwargs)
            if argv[:2] == ["gh", "api"] and f"/commits/{runner.merge.head}/check-runs?" in argv[2]:
                reads += 1
                if reads > 1:
                    runner.merge_checks = []
            return runner(argv, cwd, **kwargs)
        events = []
        monitor = Watcher([runner.current, good.current], runner=provider, emit=events.append, settle=0)
        self.assertEqual(monitor.watch(), 2)
        self.assertEqual(events[-1]["roots_blocked"], 1)
        self.assertEqual(events[-1]["roots_passed"], 1)


class PublicationTransitionTests(unittest.TestCase):
    def transition(self, *, reverse=False, sibling=False, disappear=True, required=True):
        runner = MergeRunner()
        BoundPolicyTests.policies(runner, ["build"] if required else (), ["build"])
        runner.checks = [check(runner.current)]
        runner.statuses = [{"id": 3, "context": "build", "state": "failure"}]
        if not reverse:
            runner.merge_checks = []
        good = CoverageRunner(target("good"))
        reads = 0
        def provider(argv, cwd=None, **kwargs):
            nonlocal reads
            if sibling and cwd == good.current.root:
                return good(argv, cwd, **kwargs)
            if argv[:2] == ["gh", "api"] and argv[2].endswith("/pulls/7"):
                reads += 1
                if reads == 2:
                    if reverse:
                        # A new valid merge with no checks selects head fallback.
                        # The publication head itself has not changed.
                        runner.merge = replace(runner.merge, head="d" * 40)
                        runner.pull["merge_commit_sha"] = runner.merge.head
                        runner.commit["sha"] = runner.merge.head
                        runner.merge_checks = []
                    else:
                        runner.merge_checks = [check(runner.merge)]
                    if disappear:
                        runner.statuses = []
                    else:
                        runner.statuses[0]["state"] = "success"
            return runner(argv, cwd, **kwargs)
        events = []
        monitor = Watcher([runner.current, good.current] if sibling else [runner.current],
                          runner=provider, emit=events.append, settle=0)
        return monitor, events

    def test_required_head_status_disappearance_blocks_both_mode_transitions(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                monitor, events = self.transition(reverse=reverse)
                with self.assertRaisesRegex(WatchError, "publication.*disappeared"):
                    monitor.watch()
                self.assertFalse(any(event.get("result") == "passed" for event in events))

    def test_healthy_sibling_finishes_when_publication_status_disappears(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                monitor, events = self.transition(reverse=reverse, sibling=True)
                self.assertEqual(monitor.watch(), 2)
                self.assertEqual(events[-1]["roots_blocked"], 1)
                self.assertEqual(events[-1]["roots_passed"], 1)

    def test_required_status_becoming_success_is_not_disappearance(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                monitor, _ = self.transition(reverse=reverse, disappear=False)
                self.assertEqual(monitor.watch(), 0)
                publication = [coverage for key, coverage in monitor.check_snapshots.items() if key[1] == "publication"]
                self.assertEqual(len(publication), 1)
                self.assertEqual(len(publication[0].results), 2)
                self.assertTrue(all(coverage.results for coverage in monitor.check_snapshots.values()))

    def test_optional_head_copy_can_stop_applying_when_merge_checks_appear(self):
        monitor, _ = self.transition(required=False)
        self.assertEqual(monitor.watch(), 0)


if __name__ == "__main__":
    unittest.main()
