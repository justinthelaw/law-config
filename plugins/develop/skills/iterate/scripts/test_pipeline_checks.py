"""Synthetic policy/CI regression tests; never query live repositories."""

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline_checks import CheckPolicy, RequiredCheck, discover_policy, inspect_coverage
from pipeline_monitor import Watcher
from pipeline_support import Target, WatchError, ensure_read_only, github_repository
from pipeline_test_support import FakeClock, default_ci_response, local_metadata_response, run_payload, target


def check(current, name="build", *, app_id=42, conclusion="success", status="completed", identifier=1):
    return {"id": identifier, "name": name, "head_sha": current.head, "app": {"id": app_id, "slug": "external-ci"},
            "status": status, "conclusion": conclusion, "html_url": "https://github.com/example/check"}


class CoverageRunner:
    def __init__(self, current, *, required=(), checks=(), statuses=(), runs=None, rules=(), pr=None):
        self.current = current
        self.local_target = current
        self.required, self.checks, self.statuses = list(required), list(checks), list(statuses)
        self.runs = [run_payload(current)] if runs is None else runs
        self.rules, self.pr = list(rules), pr
        self.calls = []
        self.overrides = {}

    def __call__(self, argv, cwd=None, optional=False):
        ensure_read_only(argv)
        self.calls.append(argv)
        local = local_metadata_response(argv, self.local_target)
        if local is not None:
            return local
        if argv[:3] == ["gh", "auth", "status"]:
            return ""
        if argv[:3] == ["gh", "run", "list"]:
            return json.dumps(self.runs)
        if argv[:3] == ["gh", "pr", "list"]:
            return json.dumps([self.pr] if self.pr else [])
        endpoint = argv[2]
        if endpoint in self.overrides:
            response = self.overrides[endpoint]
            if isinstance(response, Exception):
                raise response
            return json.dumps(response)
        if "/pulls/" in endpoint and self.pr:
            return json.dumps({
                "number": self.pr["number"], "state": "open", "merged": False,
                "head": {"sha": self.current.head, "ref": self.current.upstream_branch,
                         "repo": {"full_name": "/".join(self.current.repository.split("/")[-2:])}},
                "base": {"sha": self.current.head, "ref": self.pr["baseRefName"],
                         "repo": {"full_name": "/".join(self.current.repository.split("/")[-2:])}},
                "merge_commit_sha": None, "mergeable": False,
            })
        if "/rules/branches/" in endpoint:
            return json.dumps(self.rules)
        if "/branches/" in endpoint:
            branch = unquote(endpoint.split("/branches/")[1])
            return json.dumps({"name": branch, "commit": {"sha": self.current.head}, "protected": True,
                               "protection": {"required_status_checks": {"contexts": [value["context"] for value in self.required], "checks": self.required}}})
        if "/check-runs?" in endpoint:
            return json.dumps({"total_count": len(self.checks), "check_runs": self.checks})
        if "/status?" in endpoint:
            return json.dumps({"sha": self.current.head, "total_count": len(self.statuses), "statuses": self.statuses})
        return default_ci_response(argv, self.runs)


class RequiredCheckTests(unittest.TestCase):
    def snapshot(self, runner):
        events = []
        status = Watcher([runner.current], runner=runner, emit=events.append).watch(once=True)
        return status, events

    def test_missing_required_check_blocks_despite_passing_actions(self):
        current = target()
        runner = CoverageRunner(current, required=[{"context": "missing-workflow", "app_id": 42}])
        status, events = self.snapshot(runner)
        self.assertEqual(status, 2)
        self.assertEqual(events[-1]["reason"], "required exact-commit checks are missing")
        self.assertEqual(events[-1]["targets"][0]["missing"], ("missing-workflow (app 42)",))

    def test_external_status_can_satisfy_required_context_without_actions(self):
        current = target()
        runner = CoverageRunner(current, required=[{"context": "external", "app_id": None}], runs=[],
                                statuses=[{"id": 1, "context": "external", "state": "success"}])
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_external_failure_blocks_passing_actions(self):
        current = target()
        runner = CoverageRunner(current, statuses=[{"id": 1, "context": "external", "state": "failure"}])
        self.assertEqual(self.snapshot(runner)[0], 1)

    def test_external_pending_is_pending_not_success(self):
        runner = CoverageRunner(target(), statuses=[{"id": 1, "context": "external", "state": "pending"}])
        self.assertEqual(self.snapshot(runner)[0], 3)

    def test_pinned_app_must_match(self):
        current = target()
        runner = CoverageRunner(current, required=[{"context": "build", "app_id": 42}], checks=[check(current, app_id=7)])
        self.assertEqual(self.snapshot(runner)[0], 2)
        runner.checks = [check(current)]
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_status_without_app_binding_cannot_prove_pinned_app(self):
        runner = CoverageRunner(target(), required=[{"context": "external", "app_id": 42}],
                                statuses=[{"id": 1, "context": "external", "state": "success"}])
        self.assertEqual(self.snapshot(runner)[0], 2)

    def test_ruleset_checks_are_unioned_with_classic_checks(self):
        current = target()
        runner = CoverageRunner(current, required=[{"context": "classic", "app_id": 42}], rules=[
            {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ruleset", "integration_id": 7}]}}
        ])
        policy = discover_policy(current, runner, None)
        self.assertEqual(policy.required, (RequiredCheck("classic", 42), RequiredCheck("ruleset", 7)))

    def test_pr_base_and_publication_branch_policies_are_both_read(self):
        current = target(branch="law/topic")
        runner = CoverageRunner(current)
        runner.pr = {"number": 7, "url": "https://github.com/owner/project/pull/7", "headRefOid": current.head,
                     "headRefName": current.branch, "headRepositoryOwner": {"login": "owner"},
                     "isCrossRepository": False, "baseRefName": "main"}
        self.assertEqual(self.snapshot(runner)[0], 0)
        endpoints = [call[2] for call in runner.calls if call[:2] == ["gh", "api"]]
        self.assertIn("repos/owner/project/branches/law%2Ftopic", endpoints)
        self.assertIn("repos/owner/project/branches/main", endpoints)

    def test_required_workflow_rule_cannot_pass_as_observed_ci(self):
        runner = CoverageRunner(target(), rules=[{"type": "workflows", "parameters": {"workflows": []}}])
        with self.assertRaisesRegex(WatchError, "Unsupported required CI rule workflows"):
            self.snapshot(runner)

    def test_future_required_rule_cannot_be_silently_ignored(self):
        runner = CoverageRunner(target(), rules=[{"type": "future_required_ci"}])
        with self.assertRaisesRegex(WatchError, "Unsupported required CI rule"):
            self.snapshot(runner)

    def test_signing_rule_is_not_a_ci_gate(self):
        runner = CoverageRunner(target(), rules=[{"type": "required_signatures"}])
        self.assertEqual(self.snapshot(runner)[0], 0)

    def test_missing_rules_permission_does_not_mean_no_required_checks(self):
        runner = CoverageRunner(target())
        runner.overrides["repos/owner/project/rules/branches/main?per_page=100&page=1"] = WatchError("HTTP 403")
        with self.assertRaisesRegex(WatchError, "403"):
            self.snapshot(runner)

    def test_incomplete_classic_protection_blocks(self):
        runner = CoverageRunner(target())
        runner.overrides["repos/owner/project/branches/main"] = {"name": "main", "commit": {"sha": runner.current.head}, "protected": True}
        with self.assertRaisesRegex(WatchError, "inaccessible"):
            self.snapshot(runner)

    def test_wrong_sha_check_and_status_rejected(self):
        current = target()
        for kind in ("check", "status"):
            with self.subTest(kind=kind):
                runner = CoverageRunner(current)
                if kind == "check":
                    runner.checks = [{**check(current), "head_sha": "b" * 40}]
                else:
                    runner.overrides[f"repos/owner/project/commits/{current.head}/status?per_page=100&page=1"] = {"sha": "b" * 40, "total_count": 0, "statuses": []}
                with self.assertRaisesRegex(WatchError, "different commit SHA"):
                    self.snapshot(runner)

    def test_changed_remote_head_blocks(self):
        runner = CoverageRunner(target())
        runner.overrides["repos/owner/project/branches/main"] = {"name": "main", "commit": {"sha": "b" * 40}, "protected": False}
        with self.assertRaisesRegex(WatchError, "Published branch head changed"):
            self.snapshot(runner)

    def test_head_race_after_check_polling_is_caught_at_final_readback(self):
        current = target()
        runner = CoverageRunner(current)
        reads = 0
        def run(argv, cwd=None, optional=False):
            nonlocal reads
            if argv[:3] == ["gh", "api", "repos/owner/project/branches/main"]:
                reads += 1
                if reads > 1:
                    return json.dumps({"name": "main", "commit": {"sha": "b" * 40}, "protected": False})
            return runner(argv, cwd, optional)
        with self.assertRaisesRegex(WatchError, "Published branch head changed"):
            Watcher([current], runner=run, emit=lambda event: None).watch(once=True)

    def test_skipped_only_external_checks_do_not_establish_success(self):
        current = target()
        runner = CoverageRunner(current, runs=[], checks=[check(current, conclusion="skipped")])
        self.assertEqual(self.snapshot(runner)[0], 2)

    def test_required_check_appearing_late_is_waited_for(self):
        current = target()
        runner = CoverageRunner(current, required=[{"context": "build", "app_id": 42}])
        clock = FakeClock()
        def sleep(seconds):
            clock.sleep(seconds)
            runner.checks = [check(current)]
        monitor = Watcher([current], runner=runner, emit=lambda event: None, clock=clock.now, sleep=sleep, settle=0)
        self.assertEqual(monitor.watch(), 0)
        self.assertGreater(clock.current, 0)

    def test_missing_check_blocks_after_bounded_grace(self):
        current = target()
        runner = CoverageRunner(current, required=[{"context": "build", "app_id": 42}])
        clock = FakeClock()
        monitor = Watcher([current], runner=runner, emit=lambda event: None, clock=clock.now, sleep=clock.sleep, discovery_grace=10, interval=5)
        self.assertEqual(monitor.watch(), 2)


class PaginationTests(unittest.TestCase):
    def test_check_pagination_fetches_remaining_page(self):
        current = target()
        runner = CoverageRunner(current)
        prefix = f"repos/owner/project/commits/{current.head}/check-runs?filter=latest&per_page=100&page="
        runner.overrides[prefix + "1"] = {"total_count": 101, "check_runs": [check(current, f"job-{i}", identifier=i + 1) for i in range(100)]}
        runner.overrides[prefix + "2"] = {"total_count": 101, "check_runs": [check(current, "last", identifier=101)]}
        coverage = inspect_coverage(current, runner, CheckPolicy(("main",), (RequiredCheck("last"),)))
        self.assertEqual(coverage.observed, 101)
        self.assertEqual(coverage.missing, ())

    def test_short_page_with_larger_total_blocks(self):
        current = target()
        runner = CoverageRunner(current)
        runner.overrides[f"repos/owner/project/commits/{current.head}/check-runs?filter=latest&per_page=100&page=1"] = {"total_count": 2, "check_runs": [check(current)]}
        with self.assertRaisesRegex(WatchError, "Incomplete check_runs pagination"):
            inspect_coverage(current, runner, CheckPolicy((), ()))

    def test_count_race_and_duplicate_pages_block(self):
        current = target()
        for race in (True, False):
            with self.subTest(race=race):
                runner = CoverageRunner(current)
                prefix = f"repos/owner/project/commits/{current.head}/check-runs?filter=latest&per_page=100&page="
                runner.overrides[prefix + "1"] = {"total_count": 101, "check_runs": [check(current, identifier=i + 1) for i in range(100)]}
                runner.overrides[prefix + "2"] = {"total_count": 102 if race else 101, "check_runs": [check(current, identifier=1)]}
                with self.assertRaisesRegex(WatchError, "changed during pagination|Duplicate"):
                    inspect_coverage(current, runner, CheckPolicy((), ()))

    def test_rules_pagination_limit_blocks(self):
        runner = CoverageRunner(target(), rules=[{"type": "required_signatures"}] * 100)
        with self.assertRaisesRegex(WatchError, "bounded inventory coverage"):
            discover_policy(runner.current, runner, None)

    def test_check_suite_api_cap_is_not_silent(self):
        runner = CoverageRunner(target())
        runner.overrides[f"repos/owner/project/commits/{runner.current.head}/check-suites?per_page=1&page=1"] = {"total_count": 1000}
        with self.assertRaisesRegex(WatchError, "1000-suite"):
            inspect_coverage(runner.current, runner, CheckPolicy((), ()))


class IdentityTests(unittest.TestCase):
    def assert_local_drift_blocks(self, *, once):
        current = target()
        changes = (
            {"head": "b" * 40},
            {"branch": "other-local-branch"},
            {"upstream_branch": "release"},
            {"remote": "backup"},
            {"repository": "different/project"},
            {"repository": "unverified.enterprise.example/owner/project"},
            {"branch": ""},
            {"remote": ""},
        )
        for change in changes:
            with self.subTest(once=once, change=change):
                runner = CoverageRunner(current)
                events = []
                clock = FakeClock()

                def run(argv, cwd=None, optional=False):
                    response = runner(argv, cwd, optional)
                    if once and argv[:2] == ["gh", "api"] and "/status?" in argv[2]:
                        runner.local_target = replace(current, **change)
                    return response

                def sleep(seconds):
                    clock.sleep(seconds)
                    runner.local_target = replace(current, **change)

                monitor = Watcher(
                    [current], runner=run, emit=events.append,
                    clock=clock.now, sleep=sleep, interval=1, settle=2,
                )
                with self.assertRaises(WatchError):
                    monitor.watch(once=once)
                self.assertFalse(any(event.get("result") == "passed" for event in events))
                self.assertIn(["git", "branch", "--show-current"], runner.calls)
                self.assertEqual(runner.current, current)
                self.assertEqual(runner.runs, [run_payload(current)])
                if not once:
                    self.assertGreaterEqual(clock.current, 2)

    def test_local_drift_after_check_polling_blocks_terminal_snapshot(self):
        self.assert_local_drift_blocks(once=True)

    def test_local_drift_during_settlement_blocks_completion(self):
        self.assert_local_drift_blocks(once=False)

    def test_local_drift_during_final_network_readback_blocks_completion(self):
        current = target()
        runner = CoverageRunner(current)
        events = []
        reads = 0

        def run(argv, cwd=None, optional=False):
            nonlocal reads
            response = runner(argv, cwd, optional)
            if argv[:3] == ["gh", "pr", "list"]:
                reads += 1
                if reads > 1:
                    runner.local_target = replace(current, head="b" * 40)
            return response

        with self.assertRaisesRegex(WatchError, "Local Git target changed before completion"):
            Watcher([current], runner=run, emit=events.append).watch(once=True)
        self.assertFalse(any(event.get("result") == "passed" for event in events))

    def test_local_readback_preserves_distinct_branch_tracking_and_verified_host(self):
        current = replace(
            target(), branch="law/topic", remote="team/origin",
            repository="verified.enterprise.example/owner/project",
        )
        runner = CoverageRunner(current)
        self.assertEqual(Watcher([current], runner=runner, emit=lambda event: None).watch(once=True), 0)
        self.assertIn(["git", "remote", "get-url", "team/origin"], runner.calls)

    def test_equivalent_repository_transport_and_casing_keep_canonical_identity(self):
        current = target()
        runner = CoverageRunner(current)

        def run(argv, cwd=None, optional=False):
            response = runner(argv, cwd, optional)
            if argv == ["git", "remote", "get-url", "origin"]:
                return "git@github.com:OWNER/Project.git"
            return response

        self.assertEqual(Watcher([current], runner=run, emit=lambda event: None).watch(once=True), 0)

    def test_same_display_name_cannot_share_workflow_coverage(self):
        first = target()
        second = replace(first, path=Path("/other/project"), root=Path("/other/project"), repository="different/project")
        self.assertEqual(first.label, second.label)
        self.assertNotEqual(first.key, second.key)
        monitor = Watcher([first, second], emit=lambda event: None)
        monitor.remember_run(first, run_payload(first))
        self.assertEqual(monitor.missing_targets(), [second.key])
        self.assertEqual(monitor.unsuccessful_targets(), [second.label])

    def test_same_repository_different_refs_and_commits_do_not_share_runs(self):
        first = target()
        second = replace(first, upstream_branch="release", branch="release")
        third = replace(first, head="b" * 40)
        monitor = Watcher([first, second, third], emit=lambda event: None)
        for item in (first, second, third):
            monitor.remember_run(item, run_payload(item, run_id=1))
        self.assertEqual(len(monitor.runs), 3)

    def test_non_github_hosts_are_rejected_unless_explicitly_verified(self):
        for host in ("gitlab.com", "bitbucket.org", "github.enterprise.test"):
            with self.subTest(host=host), self.assertRaisesRegex(WatchError, "not a verified GitHub host"):
                github_repository(f"https://{host}/owner/repo.git")
        self.assertEqual(github_repository("https://github.enterprise.test/owner/repo.git", github_hosts=["github.enterprise.test"]), "github.enterprise.test/owner/repo")

    def test_enterprise_reads_route_explicit_hostname(self):
        current = replace(target(), repository="ghe.example/owner/project")
        runner = CoverageRunner(current)
        discover_policy(current, runner, None)
        self.assertTrue(all(call[-2:] == ["--hostname", "ghe.example"] for call in runner.calls))

    def test_ci_api_allowlist_refuses_mutations_and_arbitrary_reads(self):
        for command in (
            ["gh", "api", "repos/owner/project/actions/runs/7/rerun", "--method", "POST"],
            ["gh", "api", "repos/owner/project/branches/main", "--method", "DELETE"],
            ["gh", "api", "user", "--method", "GET"],
            ["gh", "api", "repos/owner/project/branches/main", "--method", "GET", "-f", "foo=bar"],
        ):
            with self.subTest(command=command), self.assertRaises(WatchError):
                ensure_read_only(command)


if __name__ == "__main__":
    unittest.main()
