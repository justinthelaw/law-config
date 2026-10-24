"""Inventory protocol, local Git integration, and portable CLI regressions."""

from __future__ import annotations

import json
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
        with patch.object(inventory, "worktree_identity", return_value=((), None)):
            result = snapshot(runner, patch=True, paths=["--output=not-an-option", "with\nnewline"])
        self.assertEqual(result["patch"], {"staged": "+change", "unstaged": "+change\n+change"})
        patch_calls = [call for call in runner.calls if call[1] == "diff" and "--numstat" not in call]
        self.assertEqual(len(patch_calls), 3)
        self.assertTrue(any("--cached" in call for call in patch_calls))
        self.assertTrue(any("--cached" not in call for call in patch_calls))
        for call in patch_calls:
            expected_paths = ["--output=not-an-option", "with\nnewline"] if "--cached" in call else [
                "--output=not-an-option" if call == patch_calls[1] else "with\nnewline"
            ]
            self.assertEqual(call[call.index("--") + 1:], [
                *(f":(literal){path}" for path in expected_paths),
                *(f":(exclude,glob){path}/**" for path in expected_paths),
            ])
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

    def test_broad_or_noncanonical_patch_selectors_fail_before_discovery(self) -> None:
        for selected in ("", ".", "..", "./tracked.txt", "one/../tracked.txt", "/tracked.txt",
                         "one/", "one//two"):
            with self.subTest(path=selected), patch.object(inventory, "discover_roots") as discover:
                with self.assertRaisesRegex(WatchError, "file path"):
                    inventory.main(["--patch", "--path", selected])
                discover.assert_not_called()

    def test_overlapping_explicit_paths_fail_before_discovery(self) -> None:
        with patch.object(inventory, "discover_roots") as discover:
            with self.assertRaisesRegex(WatchError, "overlap"):
                inventory.main(["--patch", "--path", "one", "--path", "one/another"])
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

    def configure_tracking(self, root: Path, name: str) -> None:
        if self.git("remote", cwd=root):
            self.git("remote", "remove", "origin", cwd=root)
        self.git("remote", "add", "origin", f"https://github.com/fixture/{name}.git", cwd=root)
        self.git("config", "branch.main.remote", "origin", cwd=root)
        self.git("config", "branch.main.merge", "refs/heads/main", cwd=root)
        self.git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=root)

    def nested_inventory_fixture(self) -> Path:
        self.env["GIT_CEILING_DIRECTORIES"] = str(self.workspace.parent)
        source = self.workspace / "fixtures" / "source"
        source.mkdir(parents=True)
        self.git("init", "--initial-branch=main", cwd=source)
        (source / "tracked.txt").write_text("child baseline\n")
        self.git("add", "--all", cwd=source)
        self.git("commit", "-m", "Child fixture baseline", cwd=source)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "--", str(source), "nested")
        self.git("commit", "-am", "Nested fixture")
        child = self.repo / "nested"
        self.configure_tracking(self.repo, "parent")
        self.configure_tracking(child, "child")
        for root, marker in ((self.repo, "parent"), (child, "child")):
            (root / "tracked.txt").write_text(f"{marker} baseline\n{marker}-private-staged\n")
            self.git("add", "--", "tracked.txt", cwd=root)
            (root / "tracked.txt").write_text(f"{marker} baseline\n{marker}-private-staged\n{marker}-private-unstaged\n")
        return child

    def inventory_cli(self, *arguments: str) -> tuple[subprocess.CompletedProcess, list[dict]]:
        cli = subprocess.run(
            [sys.executable, "-I", str(SCRIPT_DIRECTORY / "repository_inventory.py"), *arguments],
            cwd=self.workspace, env=self.env, capture_output=True, timeout=20,
        )
        return cli, [json.loads(line) for line in cli.stdout.splitlines()]

    def index_files(self, files: dict[str, str]) -> None:
        entries = []
        for name, content in files.items():
            blob = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], input=content.encode(),
                cwd=self.repo, env=self.env, capture_output=True, check=True, timeout=15,
            ).stdout.strip()
            entries.append(b"100644 " + blob + b"\t" + name.encode("utf-8") + b"\0")
        subprocess.run(
            ["git", "update-index", "-z", "--index-info"], input=b"".join(entries),
            cwd=self.repo, env=self.env, capture_output=True, check=True, timeout=15,
        )

    def test_unstaged_names_require_exact_materialized_spelling(self) -> None:
        self.configure_tracking(self.repo, "physical-names")
        pairs = [("caf\u00e9.txt", "cafe\u0301.txt"), ("CASE.txt", "case.txt"),
                 ("DIR/file.txt", "dir/file.txt"), ("caf\u00e9/file.txt", "cafe\u0301/file.txt")]
        for number, pair in enumerate(pairs):
            for actual_number in (0, 1):
                prefix = f"physical-{number}-{actual_number}/"
                names = [prefix + name for name in pair]
                actual, other = names[actual_number], names[1 - actual_number]
                materialized = self.repo / actual
                materialized.parent.mkdir(parents=True)
                materialized.write_text("WORKTREE-OWNER\n")
                self.index_files({name: f"INDEX-{index}\n" for index, name in enumerate(names)})
                other_file = self.repo / other
                aliases = other_file.exists() and other_file.samefile(materialized)
                for selected in names:
                    with self.subTest(actual=actual, selected=selected, aliases=aliases):
                        result = self.read_snapshot(patch=True, paths=[selected])
                        self.assertIn(f"+INDEX-{names.index(selected)}", result["patch"]["staged"])
                        if selected == actual:
                            self.assertIn("+WORKTREE-OWNER", result["patch"]["unstaged"])
                            self.assertNotIn("patch_withheld", result)
                        elif aliases:
                            self.assertNotIn("unstaged", result["patch"])
                            self.assertIn("spelling", result["patch_withheld"]["unstaged"])
                        else:
                            self.assertIn(f"-INDEX-{names.index(selected)}", result["patch"]["unstaged"])
                            self.assertNotIn("WORKTREE-OWNER", result["patch"]["unstaged"])
                        if number == 0 and actual_number == 0:
                            cli, events = self.inventory_cli("--repo", str(self.repo), "--patch", "--path", selected)
                            self.assertEqual(cli.returncode, 0, cli.stderr)
                            native = events[0]["repositories"][0]
                            self.assertEqual(native.get("patch_withheld"), result.get("patch_withheld"))
                            self.assertEqual(native["patch"], result["patch"])
                if not aliases:
                    other_file.parent.mkdir(parents=True, exist_ok=True)
                    other_file.write_text("WORKTREE-INDEPENDENT\n")
                    self.assertFalse(other_file.samefile(materialized))
                    for selected, expected, forbidden in (
                        (actual, "WORKTREE-OWNER", "WORKTREE-INDEPENDENT"),
                        (other, "WORKTREE-INDEPENDENT", "WORKTREE-OWNER"),
                    ):
                        with self.subTest(independent=selected):
                            result = self.read_snapshot(patch=True, paths=[selected])
                            self.assertIn("+" + expected, result["patch"]["unstaged"])
                            self.assertNotIn(forbidden, result["patch"]["unstaged"])
                            self.assertNotIn("patch_withheld", result)

    def test_unstaged_alias_does_not_depend_on_cached_index_membership(self) -> None:
        head = self.git("rev-parse", "HEAD")
        selected_target = Target(self.repo, self.repo, "fixture/project", "main", "main", head, "origin")
        for action in ("add", "remove"):
            selected, other = f"membership-{action}/case.txt", f"membership-{action}/CASE.txt"
            materialized = self.repo / other
            materialized.parent.mkdir()
            materialized.write_text("PRIVATE-SIBLING\n")
            self.index_files({selected: "INDEX-REQUESTED\n", **({other: "INDEX-OTHER\n"} if action == "remove" else {})})
            aliases = (self.repo / selected).exists() and (self.repo / selected).samefile(materialized)
            changed = False

            def interposed(argv, **kwargs):
                nonlocal changed
                output = run_command(argv, **kwargs)
                if argv[1] == "status" and not changed:
                    if action == "add":
                        self.index_files({other: "INDEX-OTHER\n"})
                    else:
                        self.git("update-index", "--force-remove", "--", other)
                    changed = True
                return output

            result = inventory.repository_snapshot(
                selected_target, [selected_target], interposed,
                max_paths=100, patch=True, paths=[selected], max_patch_lines=100, max_patch_chars=10000,
            )
            with self.subTest(action=action, aliases=aliases):
                self.assertTrue(changed)
                self.assertIn("+INDEX-REQUESTED", result["patch"]["staged"])
                self.assertNotIn("PRIVATE-SIBLING", str(result.get("patch", {})))
                if aliases:
                    self.assertIn("spelling", result["patch_withheld"]["unstaged"])

    def test_unstaged_symlink_ancestor_is_withheld_without_reading_target(self) -> None:
        outside = self.workspace / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("PRIVATE-SYMLINK-TARGET\n")
        link = self.repo / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Directory symlinks are unavailable on this host")
        self.index_files({"linked/private.txt": "INDEX-REQUESTED\n"})
        result = self.read_snapshot(patch=True, paths=["linked/private.txt"])
        self.assertIn("+INDEX-REQUESTED", result["patch"]["staged"])
        self.assertNotIn("unstaged", result["patch"])
        self.assertIn("symlink", result["patch_withheld"]["unstaged"])
        self.assertNotIn("PRIVATE-SYMLINK-TARGET", str(result))

    def test_restored_worktree_name_after_capture_does_not_certify_a_raced_patch(self) -> None:
        selected = self.repo / "selected.txt"
        other = self.repo / "SELECTED.txt"
        selected.write_text("INDEX-REQUESTED\n")
        self.git("add", "--", selected.name)
        selected.write_text("OWN-WORKTREE\n")
        sibling = self.repo / "safe.txt"
        sibling.write_text("SAFE-STAGED\n")
        self.git("add", "--", sibling.name)
        sibling.write_text("SAFE-STAGED\nSAFE-WORKTREE\n")
        head = self.git("rev-parse", "HEAD")
        selected_target = Target(self.repo, self.repo, "fixture/project", "main", "main", head, "origin")
        raced = False

        def interposed(argv, **kwargs):
            nonlocal raced
            if argv[1] == "diff" and "--numstat" not in argv and "--cached" not in argv and not raced:
                saved = self.workspace / "saved-requested"
                selected.rename(saved)
                other.write_text("PRIVATE-RACED-SIBLING\n")
                try:
                    output = run_command(argv, **kwargs)
                finally:
                    other.rename(self.workspace / "saved-sibling")
                    saved.rename(selected)
                raced = True
                return output
            return run_command(argv, **kwargs)

        result = inventory.repository_snapshot(
            selected_target, [selected_target], interposed,
            max_paths=100, patch=True, paths=[selected.name, sibling.name], max_patch_lines=100, max_patch_chars=10000,
        )
        self.assertTrue(raced)
        self.assertIn("+INDEX-REQUESTED", result["patch"]["staged"])
        self.assertIn("+SAFE-WORKTREE", result["patch"]["unstaged"])
        self.assertNotIn("+OWN-WORKTREE", result["patch"]["unstaged"])
        self.assertIn("identity changed", result["patch_withheld"]["unstaged"])
        self.assertNotIn("PRIVATE-RACED-SIBLING", str(result))

    def test_ambiguous_unstaged_path_keeps_safe_sibling_summary_and_excerpt_bounds(self) -> None:
        (self.repo / "CASE.txt").write_text("PRIVATE-OTHER-SPELLING\n")
        (self.repo / "safe.txt").write_text("INDEX-SAFE\nWORKTREE-SAFE\n")
        self.index_files({"case.txt": "INDEX-REQUESTED\n", "safe.txt": "INDEX-SAFE\n"})
        result = self.read_snapshot(patch=True, paths=["case.txt", "safe.txt"])
        self.assertIn("+INDEX-REQUESTED", result["patch"]["staged"])
        self.assertIn("+WORKTREE-SAFE", result["patch"]["unstaged"])
        self.assertNotIn("PRIVATE-OTHER-SPELLING", str(result))
        self.assertIn("unstaged", result["diff"])
        self.assertGreater(result["counts"]["unstaged"], 0)
        bounded = self.read_snapshot(patch=True, paths=["case.txt", "safe.txt"], max_patch_lines=2, max_patch_chars=80)
        for text in bounded["patch"].values():
            self.assertLessEqual(len(text), 80)
            self.assertLessEqual(len(text.splitlines()), 2)

    def test_exact_symlink_leaf_reports_only_link_text(self) -> None:
        outside = self.workspace / "outside-links"
        outside.mkdir()
        target = outside / "target.txt"
        target.write_text("PRIVATE-TARGET-CONTENTS\n")
        link = self.repo / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("File symlinks are unavailable on this host")
        self.git("add", "--", link.name)
        link.rename(self.workspace / "saved-link")
        link.symlink_to(outside / "new-target.txt")
        result = self.read_snapshot(patch=True, paths=[link.name])
        self.assertIn("+" + str(outside / "new-target.txt"), result["patch"]["unstaged"])
        self.assertNotIn("PRIVATE-TARGET-CONTENTS", str(result))
        self.assertNotIn("patch_withheld", result)

    def test_cli_filtered_patches_do_not_expand_to_implicit_children(self) -> None:
        child = self.nested_inventory_fixture()
        for arguments in (("--repo", str(self.repo)), ("--cwd", str(self.repo))):
            with self.subTest(arguments=arguments):
                cli, events = self.inventory_cli(*arguments, "--patch", "--path", "tracked.txt")
                self.assertEqual(cli.returncode, 0, cli.stderr)
                snapshots = {item["path"]: item for item in events[0]["repositories"]}
                self.assertIn("parent-private-staged", str(snapshots["."]["patch"]))
                self.assertIn("parent-private-unstaged", str(snapshots["."]["patch"]))
                self.assertEqual(snapshots["nested"]["counts"], {"staged": 1, "unstaged": 1})
                self.assertNotIn("patch", snapshots["nested"])
                self.assertNotIn(b"child-private", cli.stdout)
        cli, events = self.inventory_cli("--repo", str(self.repo), "--patch")
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn(b"child-private", cli.stdout)

    def test_cli_filters_each_explicit_root_and_current_nested_checkout(self) -> None:
        child = self.nested_inventory_fixture()
        (child / "subdirectory").mkdir()
        for arguments in (
            ("--repo", str(self.repo), "--repo", str(child)),
            ("--cwd", str(child)),
            ("--repo", str(child / "subdirectory")),
        ):
            with self.subTest(arguments=arguments):
                cli, events = self.inventory_cli(*arguments, "--patch", "--path", "tracked.txt")
                self.assertEqual(cli.returncode, 0, cli.stderr)
                child_events = [event for event in events if Path(event["root"]) == child]
                self.assertEqual(len(child_events), 1)
                self.assertIn("child-private-staged", str(child_events[0]["repositories"][0]["patch"]))
                for event in events:
                    for item in event["repositories"]:
                        if item["path"] != ".":
                            self.assertNotIn("patch", item)

    def test_cli_sibling_discovery_adds_metadata_without_implicit_patches(self) -> None:
        self.nested_inventory_fixture()
        sibling = self.workspace / "sibling"
        sibling.mkdir()
        self.git("init", "--initial-branch=main", cwd=sibling)
        (sibling / "tracked.txt").write_text("sibling baseline\n")
        self.git("add", "--all", cwd=sibling)
        self.git("commit", "-m", "Sibling fixture", cwd=sibling)
        self.configure_tracking(sibling, "sibling")
        (sibling / "tracked.txt").write_text("sibling-private\n")
        cli, events = self.inventory_cli("--repo", str(self.repo), "--include-siblings", "--patch", "--path", "tracked.txt")
        with self.subTest(mode="implicit sibling"):
            self.assertEqual(cli.returncode, 0, cli.stderr)
            sibling_event = next(event for event in events if Path(event["root"]) == sibling)
            self.assertIn("counts", sibling_event["repositories"][0])
            self.assertNotIn("patch", sibling_event["repositories"][0])
            self.assertNotIn(b"sibling-private", cli.stdout)
        cli, events = self.inventory_cli("--repo", str(self.repo), "--repo", str(sibling),
                                         "--include-siblings", "--patch", "--path", "tracked.txt")
        with self.subTest(mode="explicit sibling"):
            self.assertEqual(cli.returncode, 0, cli.stderr)
            sibling_event = next(event for event in events if Path(event["root"]) == sibling)
            self.assertIn("sibling-private", str(sibling_event["repositories"][0]["patch"]))
        cli, events = self.inventory_cli("--include-siblings", "--patch", "--path", "tracked.txt")
        self.assertEqual(cli.returncode, 2)
        self.assertEqual([event["event"] for event in events], ["blocked"])
        self.assertNotIn(b"private", cli.stdout)

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

    @unittest.skipIf(os.name == "nt", "Windows forbids CR/LF in filenames")
    def test_actual_status_and_json_preserve_byte_distinct_paths(self) -> None:
        names = [b"line\rname.txt", b"line\nname.txt", b"line\r\nname.txt"]
        for name in names:
            (self.repo / os.fsdecode(name)).write_text("baseline\n")
        untracked = self.read_snapshot()
        self.assertEqual({os.fsencode(item["path"]) for item in untracked["changes"]}, set(names))
        self.assertEqual(untracked["counts"], {"untracked": 3})
        self.git("add", "--all")
        self.git("commit", "-m", "Byte distinct paths")
        for name in names:
            path = self.repo / os.fsdecode(name)
            path.write_text("baseline\nstaged\n")
        self.git("add", "--all")
        for name in names:
            (self.repo / os.fsdecode(name)).write_text("baseline\nstaged\nunstaged\n")
        result = self.read_snapshot()
        # JSON must remain printable UTF-8 while callers can recover exact POSIX bytes.
        result = json.loads(json.dumps(result, ensure_ascii=True).encode("utf-8"))
        self.assertEqual({os.fsencode(item["path"]) for item in result["changes"]}, set(names))
        self.assertEqual(result["counts"], {"staged": 3, "unstaged": 3})
        self.assertEqual(result["diff"], {
            category: {"files": 3, "added": 3} for category in ("staged", "unstaged")
        })

    @unittest.skipIf(os.name == "nt", "Windows forbids CR/LF in filenames")
    def test_actual_rename_retains_crlf_source_and_cr_destination(self) -> None:
        original = "old-\r\n.txt"
        destination = "new-\r.txt"
        (self.repo / "tracked.txt").rename(self.repo / original)
        self.git("add", "--all")
        self.git("commit", "-m", "Byte path source")
        (self.repo / original).rename(self.repo / destination)
        self.git("add", "--all")
        result = self.read_snapshot()
        self.assertEqual(result["changes"], [{"path": destination, "status": "R ", "from": original}])

    @unittest.skipIf(os.name == "nt", "Windows filenames must use valid Unicode")
    def test_actual_git_index_and_json_preserve_undecodable_path_bytes(self) -> None:
        # Store byte paths in the actual index even on filesystems (such as APFS)
        # that cannot materialize them. Git still reports their exact staged names.
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], input=b"fixture\n",
            cwd=self.repo, env=self.env, capture_output=True, check=True, timeout=15,
        ).stdout.strip()
        names = [b"invalid-\xff.txt", b"invalid-\xfe.txt", "invalid-\ufffd.txt".encode()]
        index = b"".join(b"100644 " + blob + b"\t" + name + b"\0" for name in names)
        subprocess.run(
            ["git", "update-index", "-z", "--index-info"], input=index,
            cwd=self.repo, env=self.env, capture_output=True, check=True, timeout=15,
        )
        result = self.read_snapshot()
        serialized = json.dumps(result, ensure_ascii=True).encode("utf-8")
        self.assertEqual({os.fsencode(item["path"]) for item in json.loads(serialized)["changes"]}, set(names))
        self.assertEqual(result["counts"], {"staged": 3, "unstaged": 3})
        self.git("remote", "add", "origin", "https://github.com/fixture/project.git")
        self.git("config", "branch.main.remote", "origin")
        self.git("config", "branch.main.merge", "refs/heads/main")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        index_before = (self.repo / ".git/index").read_bytes()
        cli = subprocess.run(
            [sys.executable, "-I", str(SCRIPT_DIRECTORY / "repository_inventory.py"),
             "--repo", str(self.repo)],
            cwd=self.workspace, env=self.env, capture_output=True, check=True, timeout=15,
        )
        self.assertEqual(cli.stderr, b"")
        changes = json.loads(cli.stdout.decode("utf-8"))["repositories"][0]["changes"]
        self.assertEqual({os.fsencode(item["path"]) for item in changes}, set(names))
        selected = next(item["path"] for item in changes if os.fsencode(item["path"]) == b"invalid-\xff.txt")
        cli_patch = subprocess.run(
            [sys.executable, "-I", str(SCRIPT_DIRECTORY / "repository_inventory.py"),
             "--repo", str(self.repo), "--patch", "--path", selected],
            cwd=self.workspace, env=self.env, capture_output=True, check=True, timeout=15,
        )
        excerpt = json.loads(cli_patch.stdout)["repositories"][0]["patch"]["staged"]
        self.assertEqual(excerpt.count("diff --git "), 1)
        self.assertIn("+fixture", excerpt)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index_before)

    def test_cli_preserves_distinct_unicode_index_paths_with_precomposition_enabled(self) -> None:
        self.git("config", "core.precomposeunicode", "true")
        entries = []
        cases = [("caf\u00e9.txt", "NFC-content", "NFD-content"),
                 ("cafe\u0301.txt", "NFD-content", "NFC-content")]
        for name, content, _ in cases:
            blob = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], input=(content + "\n").encode(),
                cwd=self.repo, env=self.env, capture_output=True, check=True, timeout=15,
            ).stdout.strip()
            entries.append(b"100644 " + blob + b"\t" + name.encode("utf-8") + b"\0")
        subprocess.run(
            ["git", "update-index", "-z", "--index-info"], input=b"".join(entries),
            cwd=self.repo, env=self.env, capture_output=True, check=True, timeout=15,
        )
        self.configure_tracking(self.repo, "unicode")
        config_before = (self.repo / ".git/config").read_bytes()
        index_before = (self.repo / ".git/index").read_bytes()
        for selected, expected, forbidden in cases:
            cli, events = self.inventory_cli("--repo", str(self.repo), "--patch", "--path", selected)
            with self.subTest(path=selected):
                self.assertEqual(cli.returncode, 0, cli.stderr)
                patches = events[0]["repositories"][0].get("patch", {})
                for category, sign in (("staged", "+"), ("unstaged", "-")):
                    with self.subTest(category=category):
                        self.assertIn(sign + expected, patches.get(category, ""))
                        self.assertNotIn(forbidden, patches.get(category, ""))
        self.assertEqual((self.repo / ".git/config").read_bytes(), config_before)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index_before)

    def test_actual_selected_patch_does_not_match_pathspec_competitors(self) -> None:
        pairs = [("bracket[1].txt", "bracket1.txt")]
        if os.name != "nt":
            pairs.extend([("star*.txt", "star-other.txt"), (":(glob)*.txt", "magic-other.txt")])
        for selected, competitor in pairs:
            for name in (selected, competitor):
                (self.repo / name).write_text("baseline\n")
        self.git("add", "--all")
        self.git("commit", "-m", "Pathspec competitors")
        for number, pair in enumerate(pairs):
            for role, name in zip(("selected", "competitor"), pair):
                (self.repo / name).write_text(f"baseline\n{role}-{number}-staged\n")
        self.git("add", "--all")
        for number, pair in enumerate(pairs):
            for role, name in zip(("selected", "competitor"), pair):
                (self.repo / name).write_text(f"baseline\n{role}-{number}-staged\n{role}-{number}-unstaged\n")
        for number, (selected, _) in enumerate(pairs):
            with self.subTest(path=selected):
                result = self.read_snapshot(patch=True, paths=[selected])
                for category in ("staged", "unstaged"):
                    excerpt = result.get("patch", {}).get(category, "")
                    self.assertIn(f"+selected-{number}-{category}", excerpt)
                    self.assertNotIn("+competitor-", excerpt)

    def test_actual_patch_paths_ignore_inherited_pathspec_flags(self) -> None:
        selected = "selected[1].txt"
        competitor = "selected1.txt"
        files = [("selected", selected), ("competitor", competitor)]
        (self.repo / selected).write_text("baseline\n")
        # A second case variant can coexist on case-sensitive filesystems.
        if not (self.repo / "Selected[1].txt").exists():
            files.append(("competitor-case", "Selected[1].txt"))
        for _, name in files:
            (self.repo / name).write_text("baseline\n")
        self.git("add", "--all")
        self.git("commit", "-m", "Inherited pathspec fixture")
        for role, name in files:
            (self.repo / name).write_text(f"baseline\n{role}-staged\n")
        self.git("add", "--all")
        for role, name in files:
            (self.repo / name).write_text(f"baseline\n{role}-staged\n{role}-unstaged\n")
        for flag in ("GIT_LITERAL_PATHSPECS", "GIT_ICASE_PATHSPECS",
                     "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS"):
            for requested in (selected, "missing.txt", "SELECTED[1].txt"):
                with self.subTest(flag=flag, requested=requested), patch.dict(os.environ, {flag: "1"}):
                    environment_before = dict(os.environ)
                    result = self.read_snapshot(patch=True, paths=[requested])
                    self.assertEqual(os.environ, environment_before)
                    for category in ("staged", "unstaged"):
                        with self.subTest(category=category):
                            excerpt = result.get("patch", {}).get(category, "")
                            if requested == selected:
                                self.assertIn(f"+selected-{category}", excerpt)
                                self.assertEqual(excerpt.count("diff --git "), 1)
                                self.assertNotIn("+competitor-", excerpt)
                            else:
                                self.assertEqual(excerpt, "")

    def test_exact_patch_excludes_descendants_after_file_to_directory_transition(self) -> None:
        selected = self.repo / "report[1].txt"
        selected.write_text("requested-file\n")
        self.git("add", "--all")
        self.git("commit", "-m", "File before directory transition")
        selected.rename(self.repo / "saved-original")
        selected.mkdir()
        child = selected / "another"
        child.write_text("private-child-staged\n")
        self.git("add", "--", selected.name)
        child.write_text("private-child-staged\nprivate-child-unstaged\n")
        result = self.read_snapshot(patch=True, paths=[selected.name])
        self.assertIn("-requested-file", result.get("patch", {}).get("staged", ""))
        self.assertNotIn("private-child", str(result.get("patch", {})))
        self.assertNotIn("unstaged", result.get("patch", {}))
        broad = self.read_snapshot(patch=True)
        self.assertIn("private-child", str(broad["patch"]))

    def test_exact_patch_excludes_descendants_after_directory_to_file_transition(self) -> None:
        selected = self.repo / "report[1].txt"
        selected.mkdir()
        (selected / "another").write_text("private-child-deleted\n")
        self.git("add", "--all")
        self.git("commit", "-m", "Directory before file transition")
        selected.rename(self.repo / "saved-directory")
        selected.write_text("requested-file-staged\n")
        self.git("add", "--all")
        selected.write_text("requested-file-staged\nrequested-file-unstaged\n")
        result = self.read_snapshot(patch=True, paths=[selected.name])
        for category in ("staged", "unstaged"):
            with self.subTest(category=category):
                excerpt = result.get("patch", {}).get(category, "")
                self.assertIn(f"+requested-file-{category}", excerpt)
                self.assertNotIn("private-child", excerpt)
                self.assertEqual(excerpt.count("diff --git "), 1)

    def test_directory_only_patch_selector_fails_closed(self) -> None:
        directory = self.repo / "directory"
        directory.mkdir()
        (directory / "child").write_text("private-child\n")
        self.git("add", "--all")
        (directory / "child").write_text("private-child\nprivate-unstaged\n")
        with self.assertRaisesRegex(WatchError, "directory"):
            self.read_snapshot(patch=True, paths=[directory.name])

    def test_gitlink_with_directory_transition_fails_closed(self) -> None:
        directory = self.repo / "directory"
        directory.mkdir()
        (directory / "child").write_text("private-child-deleted\n")
        self.git("add", "--all")
        self.git("commit", "-m", "Directory before gitlink transition")
        head = self.git("rev-parse", "HEAD")
        self.git("update-index", "--force-remove", "--", "directory/child")
        self.git("update-index", "--add", "--cacheinfo", f"160000,{head},directory")
        with self.assertRaisesRegex(WatchError, "ambiguous directory transition"):
            self.read_snapshot(patch=True, paths=[directory.name])

    def test_gitlink_to_directory_index_race_never_exposes_children_or_hides_sibling(self) -> None:
        pairs = [("nested[1]", "nested1/keep.txt")]
        if os.name != "nt":
            pairs += [("nested*?", "nested-other/keep.txt"),
                      ("nested\\[?*]", "nested-other-two/keep.txt")]
        head = self.git("rev-parse", "HEAD")
        selected_target = Target(self.repo, self.repo, "fixture/project", "main", "main", head, "origin")
        for phase in ("staged", "unstaged"):
            for selected, sibling in pairs:
                with self.subTest(phase=phase, path=selected):
                    self.git("read-tree", "HEAD")
                    sibling_file = self.repo / sibling
                    sibling_file.parent.mkdir(exist_ok=True)
                    sibling_file.write_text("sibling-staged\n")
                    self.git("add", "--", f":(literal){sibling}")
                    sibling_file.write_text("sibling-staged\nsibling-unstaged\n")
                    self.git("update-index", "--add", "--cacheinfo", f"160000,{head},{selected}")
                    flipped = False

                    def interposed(argv, **kwargs):
                        nonlocal flipped
                        is_patch = argv[1] == "diff" and "--numstat" not in argv
                        if is_patch and ("--cached" in argv) == (phase == "staged") and not flipped:
                            self.git("update-index", "--force-remove", "--", selected)
                            directory = self.repo / selected
                            directory.mkdir(exist_ok=True)
                            private = directory / "private.txt"
                            private.write_text("PRIVATE-STAGED-CHILD\n")
                            self.git("add", "--", f":(literal){selected}/private.txt")
                            private.write_text("PRIVATE-STAGED-CHILD\nPRIVATE-UNSTAGED-CHILD\n")
                            flipped = True
                        return run_command(argv, **kwargs)

                    result = inventory.repository_snapshot(
                        selected_target, [selected_target], interposed,
                        max_paths=100, patch=True, paths=[selected, sibling],
                        max_patch_lines=100, max_patch_chars=10000,
                    )
                    self.assertTrue(flipped)
                    self.assertNotIn("PRIVATE-", str(result.get("patch", {})))
                    for category in ("staged", "unstaged"):
                        self.assertIn(f"+sibling-{category}", result["patch"][category])
                    if phase == "unstaged":
                        self.assertIn("+Subproject commit", result["patch"]["staged"])

    def test_file_to_gitlink_index_race_preserves_exact_pin_patch(self) -> None:
        selected = "file[1].txt"
        (self.repo / selected).write_text("selected file\n")
        self.git("add", "--all")
        head = self.git("rev-parse", "HEAD")
        selected_target = Target(self.repo, self.repo, "fixture/project", "main", "main", head, "origin")

        def interposed(argv, **kwargs):
            if argv[1] == "diff" and "--numstat" not in argv:
                self.git("update-index", "--add", "--cacheinfo", f"160000,{head},{selected}")
            return run_command(argv, **kwargs)

        result = inventory.repository_snapshot(
            selected_target, [selected_target], interposed,
            max_paths=100, patch=True, paths=[selected], max_patch_lines=100, max_patch_chars=10000,
        )
        self.assertIn("+Subproject commit", result.get("patch", {}).get("staged", ""))

    def test_cli_rejects_broad_and_traversing_paths_without_disclosing_patches(self) -> None:
        self.git("remote", "add", "origin", "https://github.com/fixture/project.git")
        self.git("config", "branch.main.remote", "origin")
        self.git("config", "branch.main.merge", "refs/heads/main")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        (self.repo / "tracked.txt").write_text("private-sibling-staged\n")
        self.git("add", "--all")
        (self.repo / "tracked.txt").write_text("private-sibling-staged\nprivate-sibling-unstaged\n")
        for selected in ("", ".", "../repository/tracked.txt", "one/../tracked.txt"):
            with self.subTest(path=selected):
                cli = subprocess.run(
                    [sys.executable, "-I", str(SCRIPT_DIRECTORY / "repository_inventory.py"),
                     "--repo", str(self.repo), "--patch", "--path", selected],
                    cwd=self.workspace, env=self.env, capture_output=True, timeout=15,
                )
                self.assertEqual(cli.returncode, 2)
                event = json.loads(cli.stdout)
                self.assertEqual(event["event"], "blocked")
                self.assertIn("file path", event["reason"])
                self.assertNotIn(b"private-sibling", cli.stdout + cli.stderr)

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
        self.git("config", "diff.submodule", "diff")
        child = self.repo / "component with spaces"
        self.configure_tracking(self.repo, "parent")
        self.configure_tracking(child, "child")
        (child / "child.txt").write_text("child dirty\n")
        (child / "new child.txt").write_text("untracked child\n")
        dirty = self.read_snapshot(patch=True, paths=[child.name])
        self.assertEqual(dirty["changes"], [{"path": child.name, "status": " M", "submodule": "S.MU"}])
        self.assertEqual(dirty["counts"], {"unstaged": 1})
        with self.subTest(mode="unstaged"):
            self.assertIn("-dirty", dirty["patch"]["unstaged"])
            self.assertNotIn("child dirty", str(dirty["patch"]))
            cli, events = self.inventory_cli("--repo", str(self.repo), "--patch", "--path", child.name)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertNotIn(b"child dirty", cli.stdout)
            root = next(item for item in events[0]["repositories"] if item["path"] == ".")
            self.assertIn("-dirty", root["patch"]["unstaged"])
        self.assertIn("child dirty", str(self.read_snapshot(patch=True)["patch"]))
        self.git("add", "--all", cwd=child)
        self.git("commit", "-m", "New child revision", cwd=child)
        self.git("add", "--", child.name)
        staged = self.read_snapshot()
        self.assertEqual(staged["changes"], [{"path": child.name, "status": "M ", "submodule": "S..."}])
        self.assertEqual(staged["counts"], {"staged": 1})
        self.assertEqual(staged["diff"]["staged"], {"files": 1, "added": 1, "removed": 1})
        selected = self.read_snapshot(patch=True, paths=[child.name])
        with self.subTest(mode="staged"):
            self.assertIn("+Subproject commit", selected["patch"]["staged"])
            self.assertNotIn("child dirty", str(selected["patch"]))
            cli, events = self.inventory_cli("--repo", str(self.repo), "--patch", "--path", child.name)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertNotIn(b"child dirty", cli.stdout)
            root = next(item for item in events[0]["repositories"] if item["path"] == ".")
            self.assertIn("+Subproject commit", root["patch"]["staged"])


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
                "pipeline_checks.py", "pipeline_review.py", "command_capture.py", "git_context.py",
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
