"""Behavior tests use private fixtures only; no host cleanup or application access."""

import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "inventory", Path(__file__).resolve().parents[1] / "scripts" / "inventory.py"
)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def file(self, path, value=b"payload"):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        return target

    def scan(self, **kwargs):
        output = io.StringIO()
        scanner = inventory.Inventory(self.root, output, **kwargs)
        result = scanner.run()
        return result, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_hidden_source_dependencies_and_codex_are_included_without_body_reads(self):
        names = [".hidden/a", ".git/objects/a", "node_modules/pkg/a", "Documents/work.txt",
                 ".codex/archived_sessions/old.jsonl", ".codex/worktrees/abc/repo/a",
                 ".codex/plugins/cache/market/plugin/1.0/main.py"]
        for name in names:
            self.file(name)
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("file body read")), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("file body read")), \
             mock.patch.object(os, "rename", side_effect=AssertionError("mutation")), \
             mock.patch.object(os, "unlink", side_effect=AssertionError("mutation")):
            summary, records = self.scan()
        found = {r["path"] for r in records if r["type"] == "node"}
        self.assertTrue(all(str(self.root / name) in found for name in names))
        self.assertTrue(summary["exhaustive"])
        self.assertEqual(summary["file_totals"]["unique_files"], len(names))
        self.assertEqual(summary["cleanup_actions"], 0)
        self.assertIn("codex-archived-sessions", {r.get("category") for r in records})

    @unittest.skipIf(os.name == "nt", "symlink privilege varies on Windows")
    def test_links_cycles_and_dangling_links_are_not_followed(self):
        self.file("real/a")
        (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        (self.root / "dangling").symlink_to(self.root / "missing")
        summary, records = self.scan()
        self.assertEqual(summary["gaps"]["symlink"], 2)
        self.assertEqual(summary["file_totals"]["unique_files"], 1)
        self.assertFalse(summary["exhaustive"])
        self.assertTrue(summary["complete_within_boundaries"])

    def test_hardlinks_are_counted_once_but_every_path_is_recorded(self):
        original = self.file("a", b"12345")
        try:
            os.link(original, self.root / "b")
        except OSError:
            self.skipTest("hardlinks unsupported on fixture filesystem")
        summary, records = self.scan()
        self.assertEqual(summary["file_totals"]["files"], 2)
        self.assertEqual(summary["file_totals"]["unique_files"], 1)
        self.assertEqual(summary["file_totals"]["logical_bytes"], 5)

    def test_sparse_file_preserves_logical_and_allocated_sizes(self):
        path = self.root / "sparse"
        with path.open("wb") as stream:
            stream.seek(8_000_000)
            stream.write(b"x")
        summary, records = self.scan()
        row = next(r for r in records if r.get("kind") == "file")
        self.assertEqual(row["logical_bytes"], 8_000_001)
        expected = getattr(path.stat(), "st_blocks", None)
        self.assertEqual(row["allocated_bytes"], expected * 512 if expected is not None else None)

    def test_mount_cloud_and_explicit_exclusions_have_coverage_gaps(self):
        for name in ("mount/a", "OneDrive - Org/a", "CloudStorage/a", "excluded/a", "keep/a"):
            self.file(name)
        summary, records = self.scan(mounts={inventory.path_key(self.root / "mount")},
                                     excludes=[self.root / "excluded"])
        self.assertEqual(summary["file_totals"]["files"], 1)
        self.assertEqual(summary["gaps"]["mount_boundary"], 1)
        self.assertEqual(summary["gaps"]["cloud_or_backup_tree"], 2)
        self.assertEqual(summary["gaps"]["explicit_exclusion"], 1)

    def test_permission_failure_is_not_an_empty_directory(self):
        self.file("denied/a")
        actual = os.scandir

        def denied(handle):
            info = os.fstat(handle) if isinstance(handle, int) else os.stat(handle)
            if info.st_ino == (self.root / "denied").stat().st_ino:
                raise PermissionError(13, "fixture denied")
            return actual(handle)

        with mock.patch.object(inventory.os, "scandir", side_effect=denied):
            summary, records = self.scan()
        self.assertFalse(summary["complete_within_boundaries"])
        self.assertEqual(summary["gaps"]["directory_error"], 1)

    def test_node_budget_marks_wide_directory_incomplete(self):
        for i in range(30):
            self.file(f"file-{i:02}")
        summary, records = self.scan(max_nodes=6)
        self.assertEqual(summary["nodes"], 6)
        self.assertFalse(summary["complete_within_boundaries"])
        self.assertIn("budget", summary["gaps"])
        self.assertEqual(records[-1]["type"], "summary")

    def test_time_budget_marks_scan_incomplete(self):
        self.file("a")
        tick = iter(range(1000))
        summary, records = self.scan(max_seconds=1, clock=lambda: next(tick))
        self.assertFalse(summary["exhaustive"])
        self.assertIn("budget", summary["gaps"])

    def test_order_is_stable_and_names_round_trip(self):
        for name in ("z", "A", "a", "newline\nname", "é"):
            self.file(name)
        _, first = self.scan()
        _, second = self.scan()
        paths = lambda records: [r["path"] for r in records if r["type"] == "node"]
        self.assertEqual(paths(first), paths(second))
        self.assertIn(str(self.root / "newline\nname"), paths(first))

    @unittest.skipIf(os.name == "nt", "native Windows long-path support depends on host policy")
    def test_deep_tree_does_not_use_python_recursion(self):
        import sys
        current = self.root
        directories = []
        for _ in range(140):
            current /= "d"
            current.mkdir()
            directories.append(current)
        (current / "leaf").write_bytes(b"x")
        previous = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(100)
            summary, records = self.scan()
        finally:
            sys.setrecursionlimit(previous)
        self.assertTrue(summary["exhaustive"])
        self.assertEqual(summary["file_totals"]["files"], 1)

    def test_cli_exclusive_output_and_report_exclusion(self):
        self.file("a")
        report = self.root / "report.jsonl"
        args = ["--root", str(self.root), "--output", str(report)]
        with mock.patch.object(inventory, "mounted_filesystems", return_value=[]):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(inventory.main(args), 0)
            before = report.read_bytes()
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(inventory.main(args), 2)
            self.assertEqual(report.read_bytes(), before)
        summary = json.loads(before.splitlines()[-1])
        self.assertEqual(summary["file_totals"]["files"], 1)
        self.assertEqual(summary["gaps"]["explicit_exclusion"], 1)

    @unittest.skipIf(os.name == "nt", "Windows root reparse points are intentionally rejected")
    def test_cli_exclusions_are_rebased_through_root_alias(self):
        self.file("target/excluded/a")
        self.file("target/keep/a")
        alias = self.root / "alias"
        alias.symlink_to(self.root / "target", target_is_directory=True)
        report = self.root / "report.jsonl"
        with mock.patch.object(inventory, "mounted_filesystems", return_value=[]), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            result = inventory.main(["--root", str(alias), "--output", str(report),
                                     "--exclude", str(alias / "excluded")])
        self.assertEqual(result, 0)
        summary = json.loads(report.read_text().splitlines()[-1])
        self.assertEqual(summary["file_totals"]["files"], 1)
        self.assertEqual(summary["gaps"]["explicit_exclusion"], 1)

    @unittest.skipUnless(hasattr(os, "getuid"), "POSIX ownership evidence")
    def test_foreign_owned_root_and_children_are_readable_but_not_cleanup_eligible(self):
        self.file("system-owned/metadata", b"abc")
        with mock.patch.object(inventory.os, "getuid", return_value=os.getuid() + 1):
            summary, records = self.scan()
        self.assertTrue(summary["exhaustive"])
        self.assertEqual(summary["file_totals"]["logical_bytes"], 3)
        nodes = [r for r in records if r["type"] == "node"]
        self.assertTrue(all(r["ownership_matches_current_user"] is False for r in nodes))
        self.assertTrue(all(r["cleanup_eligibility"] == "unverified" for r in nodes))
        self.assertEqual(summary["cleanup_actions"], 0)

    def test_cli_reports_local_and_network_mount_coverage_without_entering(self):
        self.file("local-volume/a")
        self.file("network-volume/a")
        volumes = [
            {"path": str(self.root / "local-volume"), "filesystem": "ext4", "verified_local": True},
            {"path": str(self.root / "network-volume"), "filesystem": "nfs", "verified_local": False},
        ]
        report = self.root / "volumes.jsonl"
        with mock.patch.object(inventory, "mounted_filesystems", return_value=volumes), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            result = inventory.main(["--root", str(self.root), "--output", str(report)])
        self.assertEqual(result, 0)
        records = [json.loads(line) for line in report.read_text().splitlines()]
        self.assertEqual(records[0]["mounted_filesystems"], volumes)
        self.assertEqual(records[-1]["gaps"]["mount_boundary"], 2)
        self.assertEqual(records[-1]["file_totals"]["files"], 0)
        self.assertFalse(records[-1]["exhaustive"])

    def test_placeholder_root_is_never_opened(self):
        scanner = inventory.Inventory(self.root, io.StringIO())
        scanner.root_info = SimpleNamespace(st_flags=inventory.MAC_DATALESS, st_mode=stat.S_IFDIR,
                                            st_dev=1, st_ino=1, st_mtime_ns=1, st_uid=0)
        with mock.patch.object(inventory.os, "open", side_effect=AssertionError("placeholder opened")):
            with self.assertRaises(ValueError):
                scanner.run()

    def test_replaced_directory_is_rejected_before_enumeration(self):
        scanner = inventory.Inventory(self.root, io.StringIO())
        with self.assertRaises(OSError):
            with scanner.directory((), (-1, -1)):
                self.fail("replaced directory accepted")

    def test_unknown_allocation_and_identity_are_reported(self):
        scanner = inventory.Inventory(self.root, io.StringIO())
        info = SimpleNamespace(st_mode=stat.S_IFREG, st_dev=scanner.root_info.st_dev,
                               st_ino=0, st_size=100, st_mtime_ns=1, st_uid=0)
        scanner.node(self.root / "file", info)
        self.assertEqual(scanner.totals["allocation_unknown_files"], 1)
        self.assertEqual(scanner.identity_unknown_files, 1)

    @unittest.skipIf(os.name == "nt", "Windows filenames use Unicode")
    def test_undecodable_filename_survives_jsonl(self):
        raw = os.fsencode(self.root) + b"/bad-\xff"
        output = io.StringIO()
        scanner = inventory.Inventory(self.root, output)
        info = self.file("metadata-fixture").stat()
        # Some host filesystems reject invalid UTF-8; exercise serialization in memory
        scanner.node(Path(os.fsdecode(raw)), info)
        found = json.loads(output.getvalue().splitlines()[0])
        self.assertEqual(os.fsencode(found["path"]), raw)


class PortableRulesTests(unittest.TestCase):
    def test_windows_reparse_and_recall_flags(self):
        for flag in (0x400, 0x1000, 0x40000, 0x400000):
            info = SimpleNamespace(st_file_attributes=flag, st_mode=stat.S_IFDIR)
            self.assertEqual(inventory.skip_attributes(info), "reparse_or_offline_placeholder")

    def test_macos_dataless_flag(self):
        info = SimpleNamespace(st_flags=0x40000000, st_mode=stat.S_IFREG)
        self.assertEqual(inventory.skip_attributes(info), "dataless_placeholder")

    def test_linux_same_device_bind_mount_and_escaped_names(self):
        mounts = inventory.linux_mounts(
            '1 0 8:1 / / rw - ext4 /dev/sda1 rw\n'
            '2 1 8:1 /source /home/u/bind\\040mount rw - ext4 /dev/sda1 rw\n'
        )
        self.assertEqual(str(mounts[1][0]), "/home/u/bind mount")
        with mock.patch.object(inventory.sys, "platform", "linux"), \
             mock.patch.object(Path, "read_text", return_value=
                               '1 0 8:1 / / rw - ext4 /dev/sda1 rw\n'
                               '2 1 8:1 /source /home/u/bind rw - ext4 /dev/sda1 rw\n'):
            self.assertIn(inventory.path_key("/home/u/bind"), inventory.boundaries(Path("/home/u")))

    def test_custom_codex_home_and_plugin_version_group(self):
        home = Path("/custom/agent-home")
        kind, group = inventory.category(home / "plugins/cache/market/plugin/local/main.py", [home])
        self.assertEqual(kind, "codex-plugin-installations")
        self.assertEqual(group, str(home / "plugins/cache/market/plugin/local"))


if __name__ == "__main__":
    unittest.main()
