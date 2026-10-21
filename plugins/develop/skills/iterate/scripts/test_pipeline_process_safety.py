"""Real-process boundaries for read-only pipeline inspection."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest
from unittest.mock import patch


_SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if _SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, _SCRIPT_DIRECTORY)

import pipeline_support as support
from command_capture import CapturedCommand, capture_command


class LogBoundsTests(unittest.TestCase):
    def test_character_truncation_preserves_one_line_limit(self):
        result = support.bounded_log("x" * 200, 1, 80)
        self.assertLessEqual(len(result.splitlines()), 1)
        self.assertLessEqual(len(result), 80)
        self.assertIn("omitted", result)

    def test_both_limits_hold_for_small_budgets(self):
        original = "\n".join(f"line {number} " + "x" * 100 for number in range(10))
        for lines in (1, 2, 3, 10):
            for chars in (1, 8, 9, 23, 24, 25, 80, 500):
                with self.subTest(lines=lines, chars=chars):
                    result = support.bounded_log(original, lines, chars)
                    self.assertLessEqual(len(result.splitlines()), lines)
                    self.assertLessEqual(len(result), chars)
                    self.assertTrue("omitted" in result or "…" in result)

    def test_complete_log_is_unchanged(self):
        self.assertEqual(support.bounded_log("one\ntwo\n", 2, 20), "one\ntwo")


class RunnerOutputTests(unittest.TestCase):
    def test_oversized_structured_stdout_blocks_optional_result(self):
        command = [sys.executable, "-I", "-c", "print('x' * (2 * 1024 * 1024))"]
        with patch.object(support, "ensure_read_only"), self.assertRaisesRegex(
            support.WatchError, "output.*limit"
        ):
            support.run_command(command, optional=True)

    def test_oversized_stderr_blocks_optional_success_and_failure(self):
        for status in (0, 2):
            command = [sys.executable, "-I", "-c",
                       f"import sys; sys.stderr.write('x' * (2 * 1024 * 1024)); sys.exit({status})"]
            with self.subTest(status=status), patch.object(support, "ensure_read_only"), self.assertRaisesRegex(
                support.WatchError, "output.*limit"
            ):
                support.run_command(command, optional=True)

    def test_truncated_valid_json_suffix_never_reaches_the_caller(self):
        result = CapturedCommand(["gh"], 0, "[]", "", stdout_overflow=True)
        with patch.object(support, "capture_command", return_value=result), self.assertRaisesRegex(
            support.WatchError, "output.*limit"
        ):
            support.run_command(["gh", "run", "list"], optional=True)

    def test_log_tail_discards_partial_credentials_and_redacts_complete_lines(self):
        token = "ghp_" + "a" * 100
        script = "import sys; sys.stdout.write(" + repr(token + "\n" + token + "\nlast line\n") + ")"
        actual_capture = capture_command

        def fixture_capture(command, **kwargs):
            return actual_capture([sys.executable, "-I", "-c", script],
                                  **kwargs, max_bytes=150)

        with patch.object(support, "capture_command", side_effect=fixture_capture):
            output = support.run_command(["gh", "run", "view", "1", "--log-failed"])
        self.assertIn("capture limit exceeded", output)
        self.assertIn("[REDACTED]", output)
        self.assertTrue(output.endswith("last line"))
        self.assertNotIn("aaa", output)

    def test_truncated_single_line_emits_only_the_omission_marker(self):
        result = CapturedCommand(["gh"], 0, "credential-suffix", "", stdout_overflow=True)
        with patch.object(support, "capture_command", return_value=result):
            output = support.run_command(["gh", "run", "view", "1", "--log"])
        self.assertIn("omitted", output)
        self.assertNotIn("credential-suffix", output)

    def test_nonzero_log_tail_does_not_expose_partial_credentials(self):
        result = CapturedCommand(["gh"], 2, "credential-suffix\nlast line", "", stdout_overflow=True)
        with patch.object(support, "capture_command", return_value=result), self.assertRaises(
            support.WatchError
        ) as caught:
            support.run_command(["gh", "run", "view", "1", "--log"])
        self.assertIn("omitted", str(caught.exception))
        self.assertNotIn("credential-suffix", str(caught.exception))

    def test_log_secret_crossing_a_read_chunk_is_redacted(self):
        script = "print('x' * 65534 + 'ghp_abcdefghijklmnopqrstuvwx')"
        actual_capture = capture_command

        def fixture_capture(command, **kwargs):
            return actual_capture([sys.executable, "-I", "-c", script], **kwargs)

        with patch.object(support, "capture_command", side_effect=fixture_capture):
            output = support.run_command(["gh", "run", "view", "1", "--log"])
        self.assertIn("[REDACTED]", output)
        self.assertNotIn("abcdefghijkl", output)

    def test_nonzero_failure_redacts_both_streams(self):
        for stream in ("stdout", "stderr"):
            script = f"import sys; sys.{stream}.write('ghp_abcdefghijklmnopqrstuvwx'); sys.exit(2)"
            with self.subTest(stream=stream), patch.object(support, "ensure_read_only"), self.assertRaises(
                support.WatchError
            ) as caught:
                support.run_command([sys.executable, "-I", "-c", script])
            self.assertIn("[REDACTED]", str(caught.exception))
            self.assertNotIn("abcdefghijkl", str(caught.exception))


class CaptureTests(unittest.TestCase):
    def capture(self, script, **kwargs):
        return capture_command([sys.executable, "-I", "-c", script], **kwargs)

    def test_simultaneous_streams_complete_without_deadlock(self):
        script = (
            "import os, threading\n"
            "def write(fd, data):\n"
            " for _ in range(128): os.write(fd, data * 1024)\n"
            "worker = threading.Thread(target=write, args=(2, b'e'))\n"
            "worker.start()\nwrite(1, b'o')\nworker.join()\n"
        )
        result = self.capture(script, max_bytes=256 * 1024, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "o" * (128 * 1024))
        self.assertEqual(result.stderr, "e" * (128 * 1024))
        self.assertFalse(result.stdout_overflow or result.stderr_overflow)

    def test_large_streams_retain_bounded_memory_and_report_overflow(self):
        script = (
            "import os, threading\n"
            "def write(fd, data):\n"
            " for _ in range(512): os.write(fd, data * 65536)\n"
            "worker = threading.Thread(target=write, args=(2, b'e'))\n"
            "worker.start()\nwrite(1, b'o')\nworker.join()\n"
        )
        tracemalloc.start()
        try:
            result = self.capture(script, max_bytes=4096, timeout=10)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result.stdout, "o" * 4096)
        self.assertEqual(result.stderr, "e" * 4096)
        self.assertTrue(result.stdout_overflow and result.stderr_overflow)
        self.assertLess(peak, 2 * 1024 * 1024)

    def test_tail_keeps_latest_bytes_and_exact_limit_is_complete(self):
        exact = self.capture("print('abcdefgh', end='')", max_bytes=8, tail=True)
        self.assertEqual(exact.stdout, "abcdefgh")
        self.assertFalse(exact.stdout_overflow)
        tail = self.capture("print('abcdefghijk', end='')", max_bytes=8, tail=True)
        self.assertEqual(tail.stdout, "defghijk")
        self.assertTrue(tail.stdout_overflow)

    def test_nonzero_exit_keeps_both_complete_streams(self):
        result = self.capture("import sys; print('out'); sys.stderr.write('err'); sys.exit(7)")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (7, "out\n", "err"))
        with self.assertRaises(subprocess.CalledProcessError):
            result.check_returncode()

    def test_binary_crlf_and_bare_cr_normalize_on_both_streams(self):
        payload = b"one\r\ntwo\rthree\nfour\r\r\n"
        script = (f"import sys; sys.stdout.buffer.write({payload!r}); "
                  f"sys.stderr.buffer.write({payload!r})")
        result = self.capture(script, max_bytes=len(payload))
        self.assertEqual((result.stdout, result.stderr),
                         ("one\ntwo\nthree\nfour\n\n", "one\ntwo\nthree\nfour\n\n"))
        self.assertFalse(result.stdout_overflow or result.stderr_overflow)

    def test_newline_normalization_does_not_expand_the_byte_budget(self):
        payload = b"\r\n" * 8
        script = (f"import sys; sys.stdout.buffer.write({payload!r}); "
                  f"sys.stderr.buffer.write({payload!r})")
        result = self.capture(script, max_bytes=12)
        self.assertEqual((result.stdout, result.stderr), ("\n" * 6, "\n" * 6))
        self.assertTrue(result.stdout_overflow and result.stderr_overflow)

    def test_timeout_terminates_the_child_and_returns_promptly(self):
        processes = []
        actual_popen = subprocess.Popen

        def spawn(*args, **kwargs):
            process = actual_popen(*args, **kwargs)
            processes.append(process)
            return process

        started = time.monotonic()
        with patch("command_capture.subprocess.Popen", side_effect=spawn), self.assertRaises(subprocess.TimeoutExpired):
            self.capture("import time; print('started', flush=True); time.sleep(30)", timeout=0.1)
        self.assertLess(time.monotonic() - started, 3)
        self.assertIsNotNone(processes[0].poll())


class GitSelectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="develop-git-selectors-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith("GIT_")}
        self.environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                                GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
        self.selected = self.workspace / "selected"
        self.foreign = self.workspace / "foreign"
        for root in (self.selected, self.foreign):
            root.mkdir()
            self.git(root, "init", "-q")

    def git(self, root, *arguments):
        return subprocess.run(["git", *arguments], cwd=root, env=self.environment,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              check=True, timeout=10).stdout.decode().strip()

    def test_foreign_selectors_cannot_redirect_discovery_even_when_optional(self):
        overrides = [
            {"GIT_DIR": str(self.foreign / ".git"), "GIT_WORK_TREE": str(self.foreign)},
            {"GIT_DIR": str(self.foreign / ".git")},
            {"GIT_WORK_TREE": str(self.foreign)},
            {"GIT_COMMON_DIR": str(self.foreign / ".git")},
        ]
        for override in overrides:
            with self.subTest(override=override), patch.dict(
                os.environ, {**self.environment, **override}, clear=True
            ), self.assertRaisesRegex(support.WatchError, "selectors conflict"):
                support.git_root(self.selected, support.run_command, optional=True)

    def test_matching_relative_selectors_preserve_environment_and_current_directory(self):
        environment = {**self.environment, "GIT_DIR": ".git", "GIT_WORK_TREE": ".",
                       "GIT_COMMON_DIR": ".git", "GIT_INDEX_FILE": ".git/next-index"}
        before_cwd = Path.cwd()
        with patch.dict(os.environ, environment, clear=True):
            before_environment = dict(os.environ)
            self.assertEqual(support.git_root(self.selected, support.run_command), self.selected)
            self.assertEqual(os.environ, before_environment)
            self.assertEqual(Path.cwd(), before_cwd)

    def test_linked_worktree_selectors_and_temporary_index_match(self):
        self.git(self.selected, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "Fixture")
        linked = self.workspace / "linked"
        self.git(self.selected, "worktree", "add", "--detach", str(linked), "HEAD")
        git_dir = self.git(linked, "rev-parse", "--absolute-git-dir")
        common_dir = self.git(linked, "rev-parse", "--git-common-dir")
        environment = {**self.environment, "GIT_DIR": git_dir, "GIT_WORK_TREE": str(linked),
                       "GIT_COMMON_DIR": common_dir,
                       "GIT_INDEX_FILE": str(Path(git_dir) / "next-index")}
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(support.git_root(linked, support.run_command), linked)

    def test_selected_hook_index_is_used_without_changing_the_index(self):
        (self.selected / "small.txt").write_text("small", encoding="utf-8")
        self.git(self.selected, "add", "small.txt")
        original = (self.selected / ".git/index").read_bytes()
        alternate = self.selected / ".git/hook-index"
        alternate.write_bytes(original)
        environment = {**self.environment, "GIT_INDEX_FILE": str(alternate),
                       "GIT_DIR": str(self.selected / ".git"), "GIT_WORK_TREE": str(self.selected)}
        with patch.dict(os.environ, environment, clear=True):
            output = support.run_command(
                ["git", "diff", "--cached", "--numstat", "-z", "--no-renames",
                 "--no-ext-diff", "--no-textconv", "--"], cwd=self.selected,
            )
        self.assertIn("small.txt", output)
        self.assertEqual(alternate.read_bytes(), original)
        self.assertEqual((self.selected / ".git/index").read_bytes(), original)

    def test_foreign_index_alone_cannot_supply_staged_data(self):
        (self.foreign / "foreign.txt").write_text("foreign", encoding="utf-8")
        self.git(self.foreign, "add", "foreign.txt")
        environment = {**self.environment, "GIT_INDEX_FILE": str(self.foreign / ".git/index")}
        with patch.dict(os.environ, environment, clear=True), self.assertRaisesRegex(
            support.WatchError, "index inside its Git directory"
        ):
            support.run_command(
                ["git", "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"],
                cwd=self.selected,
            )


if __name__ == "__main__":
    unittest.main()
