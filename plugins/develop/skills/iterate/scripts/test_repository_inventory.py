"""Inventory protocol, local Git integration, and portable CLI regressions."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import repository_inventory as inventory
from pipeline_support import Target, WatchError, build_target, ensure_read_only, run_command


HEAD = "a" * 40


def target(path: Path = Path("/inventory-fixture"), *, root: Path | None = None) -> Target:
    return Target(path, root or path, "fixture/project", "main", "main", HEAD, "origin")


def headers(*, head: str = HEAD, branch: str = "main") -> str:
    return f"# branch.oid {head}\0# branch.head {branch}\0"


def ordinary(path: str, status: str = "M.", submodule: str = "N...") -> str:
    mode = "160000" if submodule != "N..." else "100644"
    return f"1 {status} {submodule} {mode} {mode} {mode} {HEAD} {HEAD} {path}\0"


def renamed(destination: str, source: str) -> str:
    return f"2 R. N... 100644 100644 100644 {HEAD} {HEAD} R100 {destination}\0{source}\0"


def conflicted(path: str) -> str:
    return f"u UU N... 100644 100644 100644 100644 {HEAD} {HEAD} {HEAD} {path}\0"


class SnapshotRunner:
    def __init__(self, status: str, *, numstat: str = "1\t0\tchanged\0", diff: str = "") -> None:
        self.status = status
        self.numstat = numstat
        self.diff = diff
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: Path | None = None) -> str:
        ensure_read_only(argv)
        self.calls.append(list(argv))
        if argv[1] == "status":
            return self.status
        if argv[1] == "diff":
            return self.numstat if "--numstat" in argv else self.diff
        raise AssertionError(f"Unexpected inventory command: {argv}")


def snapshot(runner: SnapshotRunner, **options: object) -> dict:
    defaults = dict(max_paths=30, patch=False, paths=[], max_patch_lines=40, max_patch_chars=4000)
    defaults.update(options)
    selected = target()
    return inventory.repository_snapshot(selected, [selected], runner, **defaults)


def isolated_environment(home: Path) -> dict[str, str]:
    """Keep fixture Git independent of user configuration, hooks, and repositories."""
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("GIT_", "PYTHON"))
    }
    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_AUTHOR_NAME": "Inventory Fixture",
        "GIT_AUTHOR_EMAIL": "inventory@example.invalid",
        "GIT_COMMITTER_NAME": "Inventory Fixture",
        "GIT_COMMITTER_EMAIL": "inventory@example.invalid",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


class PorcelainTests(unittest.TestCase):
    def test_nul_rename_retains_original_and_new_names_with_spaces_and_newlines(self) -> None:
        source = "old directory/original name\nwith newline.txt"
        destination = "new directory/new name\nwith newline.txt"
        metadata, changes = inventory.parse_status(
            headers() + "# branch.upstream origin/main\0# branch.ab +3 -2\0"
            + renamed(destination, source) + "? another file\n.txt\0"
        )
        self.assertEqual(metadata, {
            "oid": HEAD, "head": "main", "upstream": "origin/main", "ahead": 3, "behind": 2,
        })
        self.assertEqual(changes, [
            {"path": "another file\n.txt", "status": "??"},
            {"path": destination, "status": "R ", "from": source},
        ])

    def test_conflict_and_staged_unstaged_counts_are_not_deduplicated(self) -> None:
        _, changes = inventory.parse_status(
            ordinary("same path", "MM") + conflicted("conflicted\nfile") + "? new file\0"
        )
        self.assertEqual(inventory.change_counts(changes), {
            "staged": 2, "unstaged": 2, "untracked": 1, "conflicts": 1,
        })
        conflict = next(item for item in changes if item["path"] == "conflicted\nfile")
        self.assertTrue(conflict["conflict"])
        self.assertEqual(conflict["status"], "UU")

    def test_dirty_submodule_and_changed_gitlink_are_preserved(self) -> None:
        _, changes = inventory.parse_status(
            ordinary("dirty component", ".M", "S.MU")
            + ordinary("changed gitlink", "MM", "SCM.")
        )
        self.assertEqual(changes, [
            {"path": "changed gitlink", "status": "MM", "submodule": "SCM."},
            {"path": "dirty component", "status": " M", "submodule": "S.MU"},
        ])
        self.assertEqual(inventory.change_counts(changes), {"staged": 1, "unstaged": 2})

    def test_rename_without_original_path_is_rejected(self) -> None:
        incomplete = renamed("destination", "source").split("\0", 1)[0]
        for record in (incomplete, incomplete + "\0"):
            with self.subTest(record=repr(record)), self.assertRaises(WatchError):
                inventory.parse_status(record)

    def test_malformed_or_unsupported_records_are_rejected(self) -> None:
        for record in ("1 M. too short\0", "u UU too short\0", "! ignored\0"):
            with self.subTest(record=record), self.assertRaises(WatchError):
                inventory.parse_status(record)


class SnapshotTests(unittest.TestCase):
    def test_truncated_paths_still_report_complete_counts_and_diffs(self) -> None:
        runner = SnapshotRunner(
            headers() + ordinary("z staged", "M.") + ordinary("b both", "MM")
            + conflicted("c conflict") + "? a untracked\0",
            numstat="3\t2\tname with\nnewline\0-\t-\tbinary\0",
        )
        result = snapshot(runner, max_paths=2)
        self.assertEqual([item["path"] for item in result["changes"]], ["a untracked", "b both"])
        self.assertEqual(result["omitted_paths"], 2)
        self.assertEqual(result["counts"], {"staged": 3, "unstaged": 2, "untracked": 1, "conflicts": 1})
        self.assertEqual(result["diff"], {
            category: {"files": 2, "added": 3, "removed": 2, "binary": 1}
            for category in ("staged", "unstaged")
        })
        self.assertEqual(len(runner.calls), 3)
        self.assertNotIn("patch", result)

    def test_clean_snapshot_does_not_fetch_a_diff(self) -> None:
        runner = SnapshotRunner(headers())
        result = snapshot(runner, patch=True)
        self.assertEqual(result["changes"], [])
        self.assertNotIn("counts", result)
        self.assertNotIn("omitted_paths", result)
        self.assertEqual(len(runner.calls), 1)

    def test_head_race_blocks_before_reading_diffs(self) -> None:
        runner = SnapshotRunner(headers(head="b" * 40) + ordinary("changed"))
        with self.assertRaisesRegex(WatchError, "HEAD changed"):
            snapshot(runner)
        self.assertEqual(len(runner.calls), 1)

    def test_branch_race_blocks_even_when_commit_matches(self) -> None:
        runner = SnapshotRunner(headers(branch="other-branch") + ordinary("changed"))
        with self.assertRaisesRegex(WatchError, "branch changed"):
            snapshot(runner)
        self.assertEqual(len(runner.calls), 1)

    def test_patch_path_stays_after_option_boundary_for_both_diff_categories(self) -> None:
        runner = SnapshotRunner(headers() + ordinary("--output=not-an-option", "MM"), diff="+change")
        result = snapshot(runner, patch=True, paths=["--output=not-an-option", "with\nnewline"])
        self.assertEqual(result["patch"], {"staged": "+change", "unstaged": "+change"})
        patch_calls = [call for call in runner.calls if call[1] == "diff" and "--numstat" not in call]
        self.assertEqual(len(patch_calls), 2)
        self.assertTrue(any("--cached" in call for call in patch_calls))
        self.assertTrue(any("--cached" not in call for call in patch_calls))
        for call in patch_calls:
            self.assertEqual(call[call.index("--") + 1:], ["--output=not-an-option", "with\nnewline"])
            self.assertIn("--no-ext-diff", call)
            self.assertIn("--no-textconv", call)

    def test_nested_repository_records_nearest_parent(self) -> None:
        root = target()
        parent = target(root.path / "component", root=root.path)
        child = target(parent.path / "nested", root=root.path)
        result = inventory.repository_snapshot(
            child, [root, child, parent], SnapshotRunner(headers()),
            max_paths=30, patch=False, paths=[], max_patch_lines=40, max_patch_chars=4000,
        )
        self.assertEqual(result["path"], "component/nested")
        self.assertEqual(result["parent"], "component")

    def test_invalid_limits_fail_before_discovery(self) -> None:
        for flag in ("--max-paths", "--max-patch-lines", "--max-patch-chars"):
            with self.subTest(flag=flag), patch.object(inventory, "discover_roots") as discover:
                with self.assertRaisesRegex(WatchError, "positive"):
                    inventory.main([flag, "0"])
                discover.assert_not_called()

    def test_path_without_patch_fails_before_discovery(self) -> None:
        with patch.object(inventory, "discover_roots") as discover:
            with self.assertRaisesRegex(WatchError, "requires --patch"):
                inventory.main(["--path", "selected file"])
            discover.assert_not_called()


class PatchBoundsTests(unittest.TestCase):
    def test_patch_redacts_credentials_before_returning_excerpt(self) -> None:
        secrets = [
            "ghp_abcdefghijklmnopqrstuvwx", "github_pat_abcdefghijklmnopqrstuvwx",
            "Bearer abcdefghijklmnopqrstuvwx", "AKIA1234567890ABCDEF", "sk-abcdefghijklmnopqrstuvwx",
        ]
        result = inventory.bounded_patch("\n".join("+" + secret for secret in secrets), 20, 1000)
        self.assertEqual(result.count("[REDACTED]"), len(secrets))
        for secret in secrets:
            self.assertNotIn(secret, result)

    def test_line_limit_retains_context_and_omission_notice(self) -> None:
        text = "\n".join(f"line {index}" for index in range(30))
        result = inventory.bounded_patch(text, 6, 4000)
        self.assertLessEqual(len(result.splitlines()), 6)
        self.assertIn("line 0", result)
        self.assertIn("line 29", result)
        self.assertIn("[omitted", result)

    def test_line_and_character_limits_hold_together(self) -> None:
        text = "\n".join(f"line {index} " + "x" * 200 for index in range(20))
        for line_limit in (1, 2, 3, 6):
            for char_limit in (1, 17, 28, 60, 90):
                with self.subTest(lines=line_limit, chars=char_limit):
                    result = inventory.bounded_patch(text, line_limit, char_limit)
                    self.assertLessEqual(len(result), char_limit)
                    self.assertLessEqual(len(result.splitlines()), line_limit)

    def test_character_truncation_does_not_expose_a_partial_secret(self) -> None:
        text = "+prefix ghp_abcdefghijklmnopqrstuvwx suffix " + "x" * 100
        result = inventory.bounded_patch(text, 10, 80)
        self.assertNotIn("abcdefghijkl", result)
        self.assertNotIn("mnopqrstuvwx", result)
        self.assertLessEqual(len(result), 80)


class LocalGitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="inventory-test-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.repo = self.workspace / "repository"
        self.repo.mkdir()
        self.env = isolated_environment(self.workspace)
        self.environment_patch = patch.dict(os.environ, self.env, clear=True)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.git("init", "--initial-branch=main")
        (self.repo / "tracked.txt").write_text("original\n")
        self.git("add", "--all")
        self.git("commit", "-m", "Fixture baseline")

    def git(self, *args: str, cwd: Path | None = None, expected: int = 0) -> str:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "commit.gpgsign=false", *args],
            cwd=cwd or self.repo, env=self.env, text=True, capture_output=True,
            stdin=subprocess.DEVNULL, timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return result.stdout.rstrip("\r\n")

    def read_snapshot(self, **options: object) -> dict:
        selected = Target(
            self.repo, self.repo, "fixture/project", self.git("branch", "--show-current"),
            "main", self.git("rev-parse", "HEAD"), "origin",
        )
        defaults = dict(max_paths=30, patch=False, paths=[], max_patch_lines=40, max_patch_chars=4000)
        defaults.update(options)
        index_before = (self.repo / ".git" / "index").read_bytes()
        result = inventory.repository_snapshot(selected, [selected], run_command, **defaults)
        self.assertEqual((self.repo / ".git" / "index").read_bytes(), index_before)
        return result

    def test_slash_named_remote_is_not_confused_with_its_prefix_remote(self) -> None:
        self.git("remote", "add", "team", "https://github.com/wrong/project.git")
        # Modern `remote add` rejects overlapping names, but existing/handwritten
        # configurations can contain them and Git resolves their upstream facts.
        self.git("config", "remote.team/origin.url", "https://github.com/correct/project.git")
        self.git("config", "remote.team/origin.fetch", "+refs/heads/*:refs/remotes/team/origin/*")
        self.git("config", "branch.main.remote", "team/origin")
        self.git("config", "branch.main.merge", "refs/heads/main")
        self.git("update-ref", "refs/remotes/team/origin/main", "HEAD")
        selected = build_target(self.repo, self.repo, run_command)
        self.assertEqual(selected.remote, "team/origin")
        self.assertEqual(selected.repository, "correct/project")
        self.assertEqual(selected.upstream_branch, "main")

    def test_slash_named_upstream_branch_is_preserved_from_git_facts(self) -> None:
        self.git("remote", "add", "team/origin", "https://github.com/correct/project.git")
        self.git("config", "branch.main.remote", "team/origin")
        self.git("config", "branch.main.merge", "refs/heads/release/next")
        self.git("update-ref", "refs/remotes/team/origin/release/next", "HEAD")
        selected = build_target(self.repo, self.repo, run_command)
        self.assertEqual((selected.remote, selected.upstream_branch), ("team/origin", "release/next"))

    def test_single_remote_does_not_supply_missing_or_partial_tracking(self) -> None:
        self.git("remote", "add", "origin", "https://github.com/fixture/project.git")
        for branch, facts in (
            ("no-tracking", {}),
            ("remote-only", {"remote": "origin"}),
            ("ref-only", {"merge": "refs/heads/published-name"}),
        ):
            with self.subTest(branch=branch):
                self.git("checkout", "-b", branch)
                for key, value in facts.items():
                    self.git("config", f"branch.{branch}.{key}", value)
                config_before = (self.repo / ".git" / "config").read_bytes()
                calls = []
                def runner(argv, **kwargs):
                    calls.append(argv)
                    return run_command(argv, **kwargs)
                with self.assertRaisesRegex(WatchError, "upstream"):
                    build_target(self.repo, self.repo, runner)
                self.assertFalse(any(call[:2] == ["git", "remote"] or call[0] == "gh" for call in calls))
                self.assertEqual((self.repo / ".git" / "config").read_bytes(), config_before)

    def test_actual_git_rename_preserves_both_unusual_paths(self) -> None:
        # Windows forbids control characters in filenames. Synthetic protocol
        # tests retain newline coverage on every platform.
        separator = " " if os.name == "nt" else "\n"
        original = f"old name{separator}original.txt"
        renamed_path = f"new name{separator}renamed.txt"
        (self.repo / "tracked.txt").rename(self.repo / original)
        self.git("add", "--all")
        self.git("commit", "-m", "Unusual original path")
        (self.repo / original).rename(self.repo / renamed_path)
        self.git("add", "--all")
        result = self.read_snapshot()
        self.assertEqual(result["changes"], [{"path": renamed_path, "status": "R ", "from": original}])
        self.assertEqual(result["counts"], {"staged": 1})

    def test_actual_staged_and_unstaged_change_to_same_path(self) -> None:
        path = self.repo / "tracked.txt"
        path.write_text("original\nstaged\n")
        self.git("add", "--", path.name)
        path.write_text("original\nstaged\nunstaged\n")
        result = self.read_snapshot(patch=True)
        self.assertEqual(result["changes"], [{"path": path.name, "status": "MM"}])
        self.assertEqual(result["counts"], {"staged": 1, "unstaged": 1})
        self.assertEqual(result["diff"], {category: {"files": 1, "added": 1} for category in ("staged", "unstaged")})
        self.assertIn("+staged", result["patch"]["staged"])
        self.assertIn("+unstaged", result["patch"]["unstaged"])

    def test_actual_merge_conflict_is_marked(self) -> None:
        self.git("checkout", "-b", "other")
        (self.repo / "tracked.txt").write_text("other\n")
        self.git("commit", "-am", "Other fixture change")
        self.git("checkout", "main")
        (self.repo / "tracked.txt").write_text("main\n")
        self.git("commit", "-am", "Main fixture change")
        self.git("merge", "--no-edit", "other", expected=1)
        result = self.read_snapshot()
        self.assertEqual(result["changes"], [{"path": "tracked.txt", "status": "UU", "conflict": True}])
        self.assertEqual(result["counts"], {"staged": 1, "unstaged": 1, "conflicts": 1})

    def test_patch_does_not_execute_configured_diff_or_textconv_commands(self) -> None:
        marker = self.workspace / "unexpected-converter-invocation"
        converter = self.workspace / "fixture converter.py"
        converter.write_text(
            "from pathlib import Path\n"
            + f"Path({str(marker)!r}).write_text('invoked')\n"
        )
        command = shlex.join([sys.executable, str(converter)])
        (self.repo / ".gitattributes").write_text("tracked.txt diff=fixture\n")
        self.git("add", "--all")
        self.git("commit", "-m", "Fixture diff attributes")
        self.git("config", "diff.fixture.textconv", command)
        self.git("config", "diff.external", command)
        (self.repo / "tracked.txt").write_text("changed\n")
        result = self.read_snapshot(patch=True)
        self.assertFalse(marker.exists(), "Inventory executed a configured external diff converter")
        self.assertIn("+changed", result["patch"]["unstaged"])

    def test_inventory_suppresses_fsmonitor_without_changing_config(self) -> None:
        marker = self.workspace / "unexpected-fsmonitor-invocation"
        hook = self.workspace / "fixture fsmonitor.py"
        hook.write_text(
            "from pathlib import Path\n"
            + f"Path({str(marker)!r}).write_text('invoked')\n"
        )
        self.git("config", "core.fsmonitor", shlex.join([sys.executable, str(hook)]))
        config_before = (self.repo / ".git" / "config").read_bytes()
        (self.repo / "tracked.txt").write_text("changed\n")
        result = self.read_snapshot(patch=True)
        self.assertFalse(marker.exists(), "Inventory executed the configured fsmonitor hook")
        self.assertEqual(result["changes"], [{"path": "tracked.txt", "status": " M"}])
        self.assertIn("+changed", result["patch"]["unstaged"])
        self.assertEqual((self.repo / ".git" / "config").read_bytes(), config_before)

    def test_actual_dirty_submodule_and_staged_gitlink(self) -> None:
        source = self.workspace / "submodule-source"
        source.mkdir()
        self.git("init", "--initial-branch=main", cwd=source)
        (source / "child.txt").write_text("child baseline\n")
        self.git("add", "--all", cwd=source)
        self.git("commit", "-m", "Child fixture baseline", cwd=source)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "--", str(source), "component with spaces")
        self.git("commit", "-am", "Fixture submodule")
        child = self.repo / "component with spaces"
        (child / "child.txt").write_text("child dirty\n")
        (child / "new child.txt").write_text("untracked child\n")
        dirty = self.read_snapshot()
        self.assertEqual(dirty["changes"], [{"path": child.name, "status": " M", "submodule": "S.MU"}])
        self.assertEqual(dirty["counts"], {"unstaged": 1})
        self.git("add", "--all", cwd=child)
        self.git("commit", "-m", "New child revision", cwd=child)
        self.git("add", "--", child.name)
        staged = self.read_snapshot()
        self.assertEqual(staged["changes"], [{"path": child.name, "status": "M ", "submodule": "S..."}])
        self.assertEqual(staged["counts"], {"staged": 1})
        self.assertEqual(staged["diff"]["staged"], {"files": 1, "added": 1, "removed": 1})


class PortableCLITests(unittest.TestCase):
    def test_both_copied_clis_support_help_from_unrelated_safe_path_cwd(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inventory-portable-test-") as temporary:
            workspace = Path(temporary)
            copied = workspace / "installed scripts"
            unrelated = workspace / "unrelated cwd"
            copied.mkdir()
            unrelated.mkdir()
            for name in (
                "repository_inventory.py", "watch_pipelines.py", "pipeline_support.py",
                "pipeline_monitor.py", "pipeline_run_state.py", "pipeline_failure_reporting.py",
                "pipeline_checks.py", "pipeline_review.py",
            ):
                shutil.copyfile(SCRIPT_DIRECTORY / name, copied / name)
            (unrelated / "pipeline_support.py").write_text("raise RuntimeError('cwd module imported')\n")
            for cli in ("repository_inventory.py", "watch_pipelines.py"):
                for safe_flag in ((False, True) if sys.version_info >= (3, 11) else (False,)):
                    with self.subTest(cli=cli, safe_flag=safe_flag):
                        env = isolated_environment(workspace)
                        env["PATH"] = str(unrelated)
                        env["PYTHONSAFEPATH"] = "1"
                        env.pop("PYTHONDONTWRITEBYTECODE")
                        argv = [sys.executable, *(["-P"] if safe_flag else []), str(copied / cli), "--help"]
                        result = subprocess.run(argv, cwd=unrelated, env=env, capture_output=True, text=True, timeout=15)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn("usage:", result.stdout)
                        self.assertIn("--repo", result.stdout)
                        self.assertEqual(result.stderr, "")
                        self.assertFalse((copied / "__pycache__").exists())
                        self.assertFalse((unrelated / "__pycache__").exists())


if __name__ == "__main__":
    unittest.main()
