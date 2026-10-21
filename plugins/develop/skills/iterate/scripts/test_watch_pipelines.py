"""Deterministic, read-only coverage for the compact GitHub Actions watcher."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if _SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, _SCRIPT_DIRECTORY)

import watch_pipelines as watcher
from pipeline_support import UPSTREAM_FORMAT
from pipeline_monitoring_tests import CompletionTests
from pipeline_test_support import FakeClock, FakeRunner, run_payload, target


class DiscoveryTests(unittest.TestCase):
    def test_github_remote_shapes(self) -> None:
        self.assertEqual(watcher.github_repository("https://github.com/owner/repo.git"), "owner/repo")
        self.assertEqual(watcher.github_repository("git@github.com:owner/repo.git"), "owner/repo")
        self.assertEqual(
            watcher.github_repository("ssh://git@github.enterprise.test/owner/repo.git", github_hosts=["github.enterprise.test"]),
            "github.enterprise.test/owner/repo",
        )

    def test_invalid_remote_is_rejected(self) -> None:
        with self.assertRaises(watcher.WatchError):
            watcher.github_repository("https://github.com/owner")

    def test_initialized_submodule_paths(self) -> None:
        root = Path("/tmp/project")
        for length in (40, 64):
            with self.subTest(length=length):
                status = f" {'a' * length} ui (heads/main)\n {'b' * length} dependencies/router (heads/main)"
                self.assertEqual(
                    watcher.parse_submodules(status, root),
                    [(root / "ui").resolve(), (root / "dependencies/router").resolve()],
                )

    def test_invalid_submodule_object_ids_are_rejected(self) -> None:
        invalid = ["a" * length for length in (0, 39, 41, 52, 63, 65)]
        invalid.extend(("g" * 40, "g" * 64))
        for object_id in invalid:
            with self.subTest(object_id=object_id), self.assertRaisesRegex(watcher.WatchError, "Cannot parse submodule status"):
                watcher.parse_submodules(f" {object_id} ui", Path("/tmp/root"))

    def test_uninitialized_or_mismatched_submodule_blocks(self) -> None:
        for length in (40, 64):
            for marker, error in (("-", "Uninitialized"), ("+", "pinned gitlink"), ("U", "unresolved conflicts")):
                with self.subTest(length=length, marker=marker), self.assertRaisesRegex(watcher.WatchError, error):
                    watcher.parse_submodules(f"{marker}{'a' * length} ui", Path("/tmp/root"))

    def test_discovery_includes_sha1_and_sha256_submodules(self) -> None:
        root = Path("/tmp/project").resolve()
        child = root / "component with spaces"
        for length in (40, 64):
            with self.subTest(length=length):
                heads = {root: "a" * length, child: "b" * length}

                def runner(argv, cwd=None, optional=False):
                    watcher.ensure_read_only(argv)
                    responses = {
                        ("git", "submodule", "status", "--recursive"): f" {heads[child]} {child.name} (heads/main)",
                        ("git", "branch", "--show-current"): "main",
                        ("git", "rev-parse", "HEAD"): heads[cwd],
                        ("git", "for-each-ref", "--count=2", f"--format={UPSTREAM_FORMAT}", "refs/heads/main"):
                            "refs/heads/main\0origin\0refs/heads/main",
                        ("git", "remote", "get-url", "origin"): f"https://github.com/owner/{'project' if cwd == root else 'component'}.git",
                    }
                    return responses[tuple(argv)]

                targets = watcher.discover_targets([root], runner)
                self.assertEqual([(item.path, item.head) for item in targets], list(heads.items()))
                self.assertTrue(all(item.root == root for item in targets))

    def test_current_root_is_default_and_paired_roots_require_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            canonical = workspace / "project"
            secondary = workspace / "project-secondary"
            unrelated = workspace / "unrelated"
            for path in (canonical, secondary, unrelated):
                path.mkdir()
            canonical = canonical.resolve()
            secondary = secondary.resolve()

            def fake_git(argv: list[str], cwd: Path | None = None, optional: bool = False) -> str | None:
                if cwd in (canonical, secondary):
                    return str(cwd)
                return None

            self.assertEqual(
                watcher.discover_roots(canonical, [], fake_git),
                [canonical.resolve()],
            )
            self.assertEqual(
                watcher.discover_roots(canonical, [], fake_git, include_siblings=True),
                [canonical.resolve(), secondary.resolve()],
            )

    def test_cli_requires_explicit_sibling_opt_in(self) -> None:
        self.assertFalse(watcher.parser().parse_args([]).include_siblings)
        self.assertTrue(watcher.parser().parse_args(["--include-siblings"]).include_siblings)

    def test_component_pushes_precede_roots(self) -> None:
        canonical = target()
        ui = target(component="ui")
        router = target(component="dependencies/router")
        secondary = target("project-secondary", branch="main")
        secondary_ui = target("project-secondary", branch="main-secondary", component="ui")
        ordered = watcher.ordered_push_targets([canonical, ui, router, secondary, secondary_ui])
        self.assertEqual(ordered[0], router)
        self.assertTrue(all(item.depth for item in ordered[:3]))
        self.assertTrue(all(not item.depth for item in ordered[3:]))

    def test_upstream_uses_separate_git_remote_and_ref_facts(self) -> None:
        calls = []
        root = Path("/fixture")
        def runner(argv, cwd=None, optional=False):
            watcher.ensure_read_only(argv)
            calls.append(argv)
            if argv == ["git", "branch", "--show-current"]:
                return "topic"
            if argv == ["git", "rev-parse", "HEAD"]:
                return "a" * 40
            if argv == ["git", "for-each-ref", "--count=2", f"--format={UPSTREAM_FORMAT}", "refs/heads/topic"]:
                return "refs/heads/topic\0team/origin\0refs/heads/main"
            if argv == ["git", "remote", "get-url", "team/origin"]:
                return "https://github.com/correct/project.git"
            raise AssertionError(f"Unexpected fallback or remote guess: {argv}")
        selected = watcher.build_target(root, root, runner)
        self.assertEqual((selected.remote, selected.upstream_branch, selected.repository), ("team/origin", "main", "correct/project"))
        self.assertNotIn(["git", "remote"], calls)
        self.assertNotIn(["git", "remote", "get-url", "team"], calls)

    def test_invalid_upstream_facts_never_fall_back_to_another_remote(self) -> None:
        invalid = [
            "", "refs/heads/elsewhere\0origin\0refs/heads/main", "refs/heads/topic\0origin",
            "refs/heads/topic\0origin\0", "refs/heads/topic\0\0refs/heads/main",
            "refs/heads/topic\0.\0refs/heads/main", "refs/heads/topic\0origin\0refs/tags/main",
            "refs/heads/topic\0origin\0refs/heads/", "refs/heads/topic\0-origin\0refs/heads/main",
            "refs/heads/topic\0origin\0refs/heads/main\nrefs/heads/other\0other\0refs/heads/main",
        ]
        for facts in invalid:
            with self.subTest(facts=facts):
                def runner(argv, cwd=None, optional=False):
                    watcher.ensure_read_only(argv)
                    if argv == ["git", "branch", "--show-current"]:
                        return "topic"
                    if argv == ["git", "rev-parse", "HEAD"]:
                        return "a" * 40
                    if argv[1] == "for-each-ref":
                        return facts
                    raise AssertionError(f"Invalid facts must not trigger an alternate lookup: {argv}")
                with self.assertRaises(watcher.WatchError):
                    watcher.build_target(Path("/fixture"), Path("/fixture"), runner)

    def test_absent_upstream_blocks_without_remote_lookup(self) -> None:
        for remotes in ("", "origin", "origin\nbackup"):
            with self.subTest(remotes=remotes):
                calls = []
                def runner(argv, cwd=None, optional=False):
                    watcher.ensure_read_only(argv)
                    calls.append(argv)
                    if argv == ["git", "branch", "--show-current"]:
                        return "topic"
                    if argv == ["git", "rev-parse", "HEAD"]:
                        return "a" * 40
                    if argv[1] == "for-each-ref":
                        return "refs/heads/topic\0\0"
                    if argv == ["git", "remote"]:
                        return remotes
                    if argv == ["git", "remote", "get-url", "origin"]:
                        return "https://github.com/correct/project.git"
                    raise AssertionError(argv)
                with self.assertRaisesRegex(watcher.WatchError, "Missing upstream.*configure tracking"):
                    watcher.build_target(Path("/fixture"), Path("/fixture"), runner)
                self.assertFalse(any(call[:2] == ["git", "remote"] or call[0] == "gh" for call in calls))


class SafetyTests(unittest.TestCase):
    def test_upstream_query_allowlist_is_exact_and_bounded(self) -> None:
        allowed = ["git", "for-each-ref", "--count=2", f"--format={UPSTREAM_FORMAT}", "refs/heads/law/topic"]
        watcher.ensure_read_only(allowed)
        for argv in (
            ["git", "for-each-ref"],
            ["git", "for-each-ref", f"--format={UPSTREAM_FORMAT}", "refs/heads/topic"],
            [*allowed[:-1], "refs/heads/*"],
            [*allowed[:-1], "refs/remotes/origin/main"],
            [*allowed, "refs/heads/other"],
            ["git", "for-each-ref", "--count=2", "--format=%(contents)", "refs/heads/topic"],
        ):
            with self.subTest(argv=argv), self.assertRaises(watcher.WatchError):
                watcher.ensure_read_only(argv)

    def test_read_only_command_allowlist(self) -> None:
        for argv in (
            ["git", "rev-parse", "HEAD"],
            ["git", "branch", "--show-current"],
            ["git", "remote"],
            ["git", "remote", "get-url", "origin"],
            ["git", "submodule", "status", "--recursive"],
            ["gh", "run", "list", "-R", "owner/repo"],
            ["gh", "run", "view", "1", "--log-failed"],
        ):
            with self.subTest(argv=argv):
                watcher.ensure_read_only(argv)

    def test_mutating_commands_are_refused(self) -> None:
        for argv in (
            ["git", "push", "origin", "main"],
            ["git", "commit", "-S"],
            ["git", "branch", "-D", "main"],
            ["git", "remote", "set-url", "origin", "elsewhere"],
            ["git", "submodule", "update", "--init"],
            ["gh", "run", "rerun", "1"],
            ["gh", "run", "cancel", "1"],
        ):
            with self.subTest(argv=argv), self.assertRaises(watcher.WatchError):
                watcher.ensure_read_only(argv)

    def test_failed_log_is_bounded_and_redacted(self) -> None:
        text = "\n".join([f"line {index}" for index in range(10)])
        text += "\nghp_abcdefghijklmnopqrstuvwx"
        bounded = watcher.bounded_log(text, 3)
        self.assertIn("[omitted", bounded)
        self.assertIn("[REDACTED]", bounded)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwx", bounded)
        self.assertNotIn("line 0", bounded)

    def test_transient_github_failure_retries(self) -> None:
        failure = subprocess.CompletedProcess(["gh"], 1, "", "HTTP 503 temporarily unavailable")
        success = subprocess.CompletedProcess(["gh"], 0, "[]", "")
        delays: list[float] = []
        with patch("pipeline_support.capture_command", side_effect=[failure, success]) as invoked:
            self.assertEqual(
                watcher.run_command(["gh", "run", "list"], sleep=delays.append),
                "[]",
            )
        self.assertEqual(invoked.call_count, 2)
        self.assertEqual(delays, [1])

    def test_submodule_status_leading_marker_is_preserved(self) -> None:
        status = f" {'a' * 40} ui (heads/main)\n"
        success = subprocess.CompletedProcess(["git"], 0, status, "")
        with patch("pipeline_support.capture_command", return_value=success):
            output = watcher.run_command(["git", "submodule", "status", "--recursive"])
        self.assertEqual(output, status.rstrip("\n"))


    def test_direct_cli_imports_private_modules_with_python_safe_path(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONSAFEPATH"] = "1"
        result = subprocess.run(
            [sys.executable, str(Path(watcher.__file__).resolve()), "--help"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--repo", result.stdout)


class MonitoringTests(unittest.TestCase):
    def test_exact_commit_and_branch_filtering(self) -> None:
        selected = target()
        valid = run_payload(selected)
        wrong_sha = {**valid, "databaseId": 2, "headSha": "b" * 40}
        wrong_branch = {**valid, "databaseId": 3, "headBranch": "other"}
        runner = FakeRunner([[valid, wrong_sha, wrong_branch]])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append)
        self.assertEqual(monitor.watch(once=True), 0)
        self.assertEqual(len(monitor.runs), 1)
        discovery = next(event for event in events if "workflows" in event)
        self.assertEqual(discovery["workflows"], 1)

    def test_duplicate_run_states_emit_once(self) -> None:
        selected = target()
        active = run_payload(selected, status="in_progress", conclusion="")
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([selected], emit=events.append)
        self.assertTrue(monitor.emit_transition(selected, active))
        self.assertFalse(monitor.emit_transition(selected, active))
        self.assertEqual(len(events), 1)

    def test_heartbeat_is_rate_limited(self) -> None:
        clock = FakeClock()
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([target()], emit=events.append, clock=clock.now, heartbeat=45)
        self.assertFalse(monitor.heartbeat_if_due(44))
        self.assertTrue(monitor.heartbeat_if_due(45))
        self.assertFalse(monitor.heartbeat_if_due(89))
        self.assertTrue(monitor.heartbeat_if_due(90))
        self.assertEqual(len(events), 2)

    def test_terminal_state_classification(self) -> None:
        selected = target()
        cases = {
            ("queued", ""): "active",
            ("in_progress", ""): "active",
            ("completed", "success"): "passed",
            ("completed", "neutral"): "skipped",
            ("completed", "skipped"): "skipped",
            ("completed", "failure"): "failed",
            ("completed", "cancelled"): "failed",
            ("completed", "timed_out"): "failed",
        }
        for (status, conclusion), expected in cases.items():
            with self.subTest(status=status, conclusion=conclusion):
                self.assertEqual(
                    watcher.classify(run_payload(selected, status=status, conclusion=conclusion)),
                    expected,
                )

    def test_failed_job_is_reported_with_bounded_logs(self) -> None:
        selected = target()
        failure = run_payload(selected, conclusion="failure")
        detail = {
            **failure,
            "jobs": [{"databaseId": 17, "name": "e2e", "status": "completed", "conclusion": "failure", "steps": []}],
        }
        runner = FakeRunner([[failure]], [detail])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append, max_log_lines=2)
        self.assertEqual(monitor.watch(once=True), 1)
        evidence = next(event for event in events if event["event"] == "failure")
        self.assertEqual(evidence["job"], "e2e")
        self.assertIn("[REDACTED]", str(evidence["excerpt"]))
        self.assertEqual(events[-1]["result"], "failed")

    def test_missing_exact_commit_is_explicit(self) -> None:
        selected = target()
        runner = FakeRunner([[]])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append)
        self.assertEqual(monitor.watch(once=True), 2)
        self.assertEqual(events[-1]["event"], "blocked")

    def test_failed_workflow_waits_for_other_workflows_to_finish(self) -> None:
        selected = target()
        failure = run_payload(selected, run_id=1, conclusion="failure")
        active = run_payload(selected, run_id=2, status="in_progress", conclusion="")
        failure_detail = {
            **failure,
            "jobs": [{"databaseId": 17, "name": "unit", "status": "completed", "conclusion": "failure", "steps": []}],
        }
        completed = {
            **run_payload(selected, run_id=2),
            "jobs": [{"databaseId": 18, "name": "e2e", "status": "completed", "conclusion": "success", "steps": []}],
        }
        clock = FakeClock()
        runner = FakeRunner([[failure, active]], [failure_detail, active, completed])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher(
            [selected],
            runner=runner,
            emit=events.append,
            clock=clock.now,
            sleep=clock.sleep,
            interval=1,
            settle=0,
        )
        self.assertEqual(monitor.watch(), 1)
        self.assertEqual(events[-1]["result"], "failed")
        self.assertEqual(events[-1]["failed"], 1)
        self.assertEqual(events[-1]["passed"], 1)
        self.assertGreaterEqual(clock.current, 1)

    def test_snapshot_with_failed_and_active_workflows_is_pending(self) -> None:
        selected = target()
        failure = run_payload(selected, run_id=1, conclusion="failure")
        active = run_payload(selected, run_id=2, status="in_progress", conclusion="")
        detail = {
            **failure,
            "jobs": [{"databaseId": 17, "name": "unit", "status": "completed", "conclusion": "failure", "steps": []}],
        }
        runner = FakeRunner([[failure, active]], [detail, active])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append)
        self.assertEqual(monitor.watch(once=True), 3)
        self.assertEqual(events[-1]["result"], "pending")

    def test_late_workflow_after_initial_success_is_discovered(self) -> None:
        selected = target()
        success = run_payload(selected, run_id=1)
        late = run_payload(selected, run_id=2, status="in_progress", conclusion="", workflow="E2E")
        completed = {
            **run_payload(selected, run_id=2, workflow="E2E"),
            "jobs": [{"databaseId": 22, "name": "browser", "status": "completed", "conclusion": "success", "steps": []}],
        }
        runner = FakeRunner([[success], [success, late]], [completed])
        events: list[dict[str, object]] = []
        monitor = watcher.Watcher([selected], runner=runner, emit=events.append, settle=0)
        self.assertEqual(monitor.watch(), 0)
        self.assertEqual(events[-1]["passed"], 2)
        self.assertTrue(any(event["event"] == "discovered" for event in events))


if __name__ == "__main__":
    unittest.main()
