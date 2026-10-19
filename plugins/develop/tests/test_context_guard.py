"""Behavioral subprocess checks for the native context guard (no host trust edits)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HANDLER = ROOT / "hooks/context_guard.py"


def packaged_command(shell, command, windows=False):
    # Match Codex command_runner.rs build_command: /c uses an outer-quoted
    # raw_arg. CRT argv quoting would instead backslash-escape embedded quotes.
    if windows and any(argument.lower() == "/c" for argument in shell[1:]):
        return subprocess.list2cmdline(shell) + ' "' + command + '"'
    return shell + [command]


class ContextGuard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="develop-context-guard-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def event(self, payload, event="PreToolUse", tool="test_tool", **fields):
        return {
            "hook_event_name": event, "tool_name": tool,
            "tool_input" if event == "PreToolUse" else "tool_response": payload,
            "cwd": str(self.directory), **fields,
        }

    def invoke(self, payload=None, *, raw=None, event="PreToolUse", limit=None,
               args=None, command=None, environment=None):
        argv = command or [sys.executable, "-I", "-B", str(HANDLER)]
        if command is None:
            argv += args if args is not None else ["--event", event]
            if limit is not None:
                argv += ["--max-bytes", str(limit)]
        if raw is None:
            raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        return subprocess.run(argv, input=raw, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, cwd=self.directory,
                              env=environment, timeout=15, check=False)

    def passes(self, result):
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

    def blocked(self, result, event="PreToolUse"):
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stderr, b"")
        self.assertLess(len(result.stdout), 2000)
        output = json.loads(result.stdout)
        if event == "PreToolUse":
            self.assertEqual(set(output), {"hookSpecificOutput"})
            decision = output["hookSpecificOutput"]
            self.assertEqual(decision["hookEventName"], event)
            self.assertEqual(decision["permissionDecision"], "deny")
            reason = decision["permissionDecisionReason"]
        else:
            self.assertEqual(set(output), {"decision", "reason"})
            self.assertEqual(output["decision"], "block")
            reason = output["reason"]
        self.assertIn("rg", reason)
        self.assertIn("pagination", reason)
        return reason

    def test_default_threshold_includes_structure_and_passes_equality(self):
        for event in ("PreToolUse", "PostToolUse"):
            with self.subTest(event=event):
                self.passes(self.invoke(self.event("a" * 19998, event), event=event))
                self.blocked(self.invoke(self.event("a" * 19999, event), event=event), event)

    def test_decoded_utf8_and_json_structure_have_exact_boundaries(self):
        # {"x":"é"} costs braces2 + key3 + colon1 + value4 = 10.
        for event in ("PreToolUse", "PostToolUse"):
            with self.subTest(event=event):
                value = self.event({"x": "é"}, event)
                self.passes(self.invoke(value, event=event, limit=10))
                self.blocked(self.invoke(value, event=event, limit=9), event)
        # Decoding escaped quotes, backslashes and astral codepoints must not
        # charge JSON's transport escaping a second time: 1+1+4+2 = 8.
        value = self.event('"\\😀')
        self.passes(self.invoke(value, limit=8))
        self.blocked(self.invoke(value, limit=7))

    def test_aggregate_keys_values_arrays_and_literals_are_counted(self):
        # [1,true,null,"x"] = 17 bytes including separators and delimiters.
        value = self.event([1, True, None, "x"])
        self.passes(self.invoke(value, limit=17))
        self.blocked(self.invoke(value, limit=16))
        self.blocked(self.invoke(self.event({"k" * 20000: ""})))
        self.blocked(self.invoke(self.event({"a": "a" * 11000, "b": ["b" * 11000]})))
        self.blocked(self.invoke(self.event([0] * 10000)))
        self.blocked(self.invoke(self.event({"nested": [[{"value": "x" * 20000}]]})))

    def test_numeric_tokens_are_not_rounded_or_limited_by_integer_conversion(self):
        for number in (b"1.00000000000000000000", b"1e00000000000000000001", b"7" * 21000):
            with self.subTest(number_bytes=len(number)):
                raw = b'{"hook_event_name":"PreToolUse","tool_name":"test","tool_input":' + number + b'}'
                self.passes(self.invoke(raw=raw, limit=len(number)))
                self.blocked(self.invoke(raw=raw, limit=len(number) - 1))

    def test_post_counts_output_instead_of_input_or_transcript_metadata(self):
        self.passes(self.invoke(self.event("ok", "PostToolUse", tool_input="x" * 100000,
                                           transcript_path="x" * 30000), event="PostToolUse"))
        output = {"content": [{"type": "text", "text": "x" * 21000}], "isError": False}
        self.blocked(self.invoke(self.event(output, "PostToolUse", tool="mcp__test__run"),
                                 event="PostToolUse"), "PostToolUse")

    def test_small_searches_ranges_and_patches_are_quiet(self):
        for tool, value in (("Bash", {"command": "rg -n -m 8 'target' src"}),
                            ("Read", {"file_path": "large.txt", "offset": 0, "limit": 20}),
                            ("apply_patch", {"command": "*** Begin Patch\n*** Update File: large.txt\n@@\n-old\n+new\n*** End Patch"})):
            with self.subTest(tool=tool):
                (self.directory / "large.txt").write_bytes(b"original\n" * 4000)
                self.passes(self.invoke(self.event(value, tool=tool)))
                self.assertEqual((self.directory / "large.txt").read_bytes(), b"original\n" * 4000)

    def test_whole_file_cat_uses_actual_sizes_without_git_or_content_reads(self):
        path = self.directory / "document with spaces.txt"
        path.write_bytes(b"x" * 20001)
        for tool, value in (("Bash", {"command": "cat 'document with spaces.txt'"}),
                            ("Bash", {"cmd": "cat -- 'document with spaces.txt'"}),
                            ("Read", {"file_path": str(path)}),
                            ("read_file", {"path": str(path)}),
                            ("mcp__filesystem__read_file", {"path": str(path)})):
            with self.subTest(tool=tool, value=value):
                self.blocked(self.invoke(self.event(value, tool=tool)))
        self.assertEqual(path.read_bytes(), b"x" * 20001)

    def test_cat_aggregates_files_and_honors_threshold_equality(self):
        (self.directory / "one").write_bytes(b"a" * 10000)
        (self.directory / "two").write_bytes(b"b" * 10000)
        value = self.event({"command": "cat one two"}, tool="Bash")
        self.passes(self.invoke(value))
        (self.directory / "two").write_bytes(b"b" * 10001)
        self.blocked(self.invoke(value))

    def test_cat_resolves_tool_workdir_and_relative_paths(self):
        directory = self.directory / "nested"
        directory.mkdir()
        (directory / "large.txt").write_bytes(b"x" * 20001)
        self.blocked(self.invoke(self.event({"command": "cat large.txt", "workdir": str(directory)}, tool="Bash")))
        self.blocked(self.invoke(self.event({"command": "cat large.txt", "cwd": "nested"}, tool="Bash")))

    def test_dirty_and_unstaged_file_sizes_are_not_taken_from_git_index(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        subprocess.run(["git", "init", "-q", str(self.directory)], check=True)
        path = self.directory / "tracked.txt"
        path.write_text("small", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.directory), "add", "tracked.txt"], check=True)
        path.write_bytes(b"x" * 20001)
        self.blocked(self.invoke(self.event({"command": "cat tracked.txt"}, tool="Bash")))
        (self.directory / "unstaged.txt").write_bytes(b"x" * 20001)
        self.blocked(self.invoke(self.event({"path": "unstaged.txt"}, tool="read_file")))

    def test_complex_shell_and_ranged_reads_defer_to_post_without_execution(self):
        (self.directory / "large.txt").write_bytes(b"x" * 21000)
        for command in ("cat large.txt | head -n 2", "cat large.txt > output.txt",
                        "cat large.txt; touch sentinel", "cat $(touch sentinel)",
                        "cat $DOCUMENT", "cat *.txt", "head -n 2 large.txt",
                        "cat large.txt && touch sentinel", "cat large.txt\ntouch sentinel"):
            with self.subTest(command=command):
                self.passes(self.invoke(self.event({"command": command}, tool="Bash")))
        for arguments in ({"path": "large.txt", "start_line": 1, "end_line": 2},
                          {"file_path": "large.txt", "offset": 0, "limit": 2},
                          {"path": "large.txt", "head": 2}):
            self.passes(self.invoke(self.event(arguments, tool="read_file")))
        self.assertFalse((self.directory / "sentinel").exists())
        self.assertFalse((self.directory / "output.txt").exists())
        self.blocked(self.invoke(self.event("x" * 21000, "PostToolUse"), event="PostToolUse"), "PostToolUse")

    def test_empty_or_zero_bounds_do_not_disguise_a_whole_read(self):
        (self.directory / "large.txt").write_bytes(b"x" * 21000)
        for bound in (None, 0, False, "", [], {}):
            self.blocked(self.invoke(self.event({"path": "large.txt", "limit": bound}, tool="read_file")))

    def test_missing_files_directories_and_non_read_tools_are_not_size_blocked(self):
        (self.directory / "large.txt").write_bytes(b"x" * 21000)
        for tool, value in (("Bash", {"command": "cat missing.txt"}),
                            ("read_file", {"path": str(self.directory)}),
                            ("write_file", {"path": "large.txt", "content": "small"}),
                            ("custom_reader", {"path": "large.txt"})):
            self.passes(self.invoke(self.event(value, tool=tool)))

    @unittest.skipIf(os.name == "nt", "POSIX FIFOs only")
    def test_fifo_is_stat_only_and_never_opened(self):
        os.mkfifo(self.directory / "pipe")
        self.passes(self.invoke(self.event({"command": "cat pipe"}, tool="Bash")))

    def test_native_binary_media_payloads_are_exempt_but_metadata_is_counted(self):
        for kind, mime in (("image", "image/png"), ("audio", "audio/wav"), ("video", "video/mp4")):
            with self.subTest(kind=kind):
                block = {"type": kind, "data": "AAAA" * 10000, "mimeType": mime, "caption": "short"}
                self.passes(self.invoke(self.event({"content": [block]}, "PostToolUse"), event="PostToolUse"))
                block["caption"] = "c" * 21000
                self.blocked(self.invoke(self.event({"content": [block]}, "PostToolUse"), event="PostToolUse"), "PostToolUse")

    def test_recognized_native_data_urls_and_audio_format_payloads(self):
        for block in ({"type": "input_image", "image_url": "data:image/png;base64," + "AAAA" * 10000},
                      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + "AAAA" * 10000, "detail": "auto"}},
                      {"type": "input_audio", "input_audio": {"data": "AAAA" * 10000, "format": "wav"}}):
            self.passes(self.invoke(self.event([block])))

    def test_ordinary_text_svg_unknown_mime_and_malformed_media_are_counted(self):
        for block in ("data:image/png;base64," + "AAAA" * 10000,
                      {"type": "text", "text": "data:image/png;base64," + "AAAA" * 10000},
                      {"type": "image", "data": "AAAA" * 10000},
                      {"type": "image", "data": "AAAA" * 10000, "mimeType": "text/plain"},
                      {"type": "image", "data": "AAAA" * 10000, "mimeType": "image/unknown"},
                      {"type": "image", "data": "AAAA" * 10000, "mimeType": "image/svg+xml"},
                      {"type": "image", "data": "invalid!" * 4000, "mimeType": "image/png"},
                      {"type": "input_image", "image_url": "data:image/svg+xml;base64," + "AAAA" * 10000},
                      {"type": "input_image", "image_url": "data:text/plain;base64," + "AAAA" * 10000},
                      {"data": "AAAA" * 10000, "mimeType": "image/png"},
                      {"type": "image", "data": [1] * 11000, "mimeType": "image/png"}):
            with self.subTest(shape=type(block).__name__):
                self.blocked(self.invoke(self.event(block)))

    def test_nested_media_does_not_exempt_neighbor_text_or_metadata(self):
        image = {"type": "image", "data": "AAAA" * 10000, "mimeType": "image/png"}
        self.passes(self.invoke(self.event({"content": [[image]], "metadata": "small"})))
        self.blocked(self.invoke(self.event({"content": [image], "metadata": "x" * 21000})))
        self.blocked(self.invoke(self.event({"type": "image", "data": "AAAA" * 10000,
                                           "mimeType": "image/png", "extra": "AAAA" * 10000})))

    def test_malformed_duplicate_keys_and_invalid_unicode_fail_closed_privately(self):
        for raw in (b"", b"{", b"[]", b"null", b'{"secret":"PRIVATE_CONTENT"}',
                    b'{"hook_event_name":"PreToolUse","tool_name":"test","tool_input":"\\ud800"}',
                    b'{"hook_event_name":"PreToolUse","tool_name":"test","tool_input":NaN}',
                    b'{"hook_event_name":"PreToolUse","tool_name":"test","tool_input":Infinity}',
                    b'{"hook_event_name":"PreToolUse","tool_name":"test","tool_input":{"secret":"PRIVATE_CONTENT","secret":""}}',
                    b'{"hook_event_name":"PreToolUse","tool_name":"test","tool_input":"\xff"}'):
            for event in ("PreToolUse", "PostToolUse"):
                result = self.invoke(raw=raw, event=event)
                self.blocked(result, event)
                self.assertNotIn(b"PRIVATE_CONTENT", result.stdout + result.stderr)

    def test_event_mismatch_and_missing_fields_use_configured_event_decision(self):
        for event in ("PreToolUse", "PostToolUse"):
            opposite = "PostToolUse" if event == "PreToolUse" else "PreToolUse"
            for value in (self.event("small", opposite), {"hook_event_name": event, "tool_name": "test"},
                          {"hook_event_name": event, "tool_name": 5, "tool_input": "small"},
                          {"hook_event_name": event, "tool_input": "small", "tool_response": "small"}):
                self.blocked(self.invoke(value, event=event), event)

    def test_excessive_nesting_is_bounded_and_private(self):
        raw = b'{"hook_event_name":"PreToolUse","tool_name":"test","tool_input":' + b'[' * 5000 + b'"PRIVATE_CONTENT"' + b']' * 5000 + b'}'
        result = self.invoke(raw=raw)
        self.blocked(result)
        self.assertNotIn(b"PRIVATE_CONTENT", result.stdout + result.stderr)

    def test_raw_cap_is_separate_from_text_limit_and_drains_pipe(self):
        # A permitted 4MiB binary payload does not use the 20KB text budget.
        media = {"type": "image", "mimeType": "image/png", "data": "AAAA" * 1048576}
        self.passes(self.invoke(self.event(media)))
        raw = json.dumps(self.event("PRIVATE_CONTENT")).encode() + b" " * (17 * 1024 * 1024)
        for event in ("PreToolUse", "PostToolUse"):
            result = self.invoke(raw=raw, event=event)
            self.assertIn("raw event", self.blocked(result, event).lower())
            self.assertNotIn(b"PRIVATE_CONTENT", result.stdout + result.stderr)

    def test_configured_limit_and_invalid_cli_values(self):
        self.passes(self.invoke(self.event("x" * 21000), limit=22000))
        for args in ([], ["--event", "Other"], ["--event", "PreToolUse", "--max-bytes", "0"],
                     ["--event", "PreToolUse", "--max-bytes", "-1"],
                     ["--event", "PreToolUse", "--max-bytes", "1.5"],
                     ["--event", "PreToolUse", "--max-bytes", "1048577"]):
            result = self.invoke(self.event("small"), args=args)
            self.assertNotEqual(result.returncode, 0)
            self.assertLess(len(result.stdout + result.stderr), 2000)

    def test_decisions_do_not_echo_payload_paths_or_write_transcripts(self):
        secret = "PRIVATE_CONTENT_DO_NOT_ECHO"
        path = self.directory / (secret + ".txt")
        path.write_text(secret * 1000, encoding="utf-8")
        before = {item.name: item.read_bytes() for item in self.directory.iterdir()}
        for event in ("PreToolUse", "PostToolUse"):
            result = self.invoke(self.event(secret * 1000, event, transcript_path=str(path)), event=event)
            self.blocked(result, event)
            self.assertNotIn(secret.encode(), result.stdout + result.stderr)
        result = self.invoke(self.event({"command": "cat " + path.name}, tool="Bash"))
        self.blocked(result)
        self.assertNotIn(secret.encode(), result.stdout + result.stderr)
        self.assertEqual(before, {item.name: item.read_bytes() for item in self.directory.iterdir()})

    def run_packaged_commands(self, shell, windows=False):
        # Copy the exact shipped hook into a detached hostile-looking path.
        name = "plugin spaces ' $ & ; (test)" if windows else "plugin ' \" $ ` & ; (test)"
        package = self.directory / name
        shutil.copytree(ROOT / "hooks", package / "hooks")
        env = dict(os.environ, PLUGIN_ROOT=str(package))
        commands = json.loads((package / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        for event in ("PreToolUse", "PostToolUse"):
            hook = commands[event][0]["hooks"][0]
            command = hook["commandWindows" if windows else "command"]
            args = packaged_command(shell, command, windows)
            self.passes(self.invoke(self.event("small", event), command=args, environment=env))
            self.blocked(self.invoke(self.event("PRIVATE_CONTENT" * 2000, event), command=args, environment=env), event)
        self.assertFalse(list(package.rglob("__pycache__")))
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), [name])

    def test_cmd_commandline_preserves_nested_quotes_without_crt_escaping(self):
        shell = [r"C:\Program Files\Command\cmd.exe", "/d", "/s", "/C"]
        command = 'py -3 -c "print(123)"'
        self.assertEqual(packaged_command(shell, command, windows=True),
                         r'"C:\Program Files\Command\cmd.exe" /d /s /C "py -3 -c "print(123)""')
        powershell = ["powershell.exe", "-NoProfile", "-Command"]
        self.assertEqual(packaged_command(powershell, command, windows=True), powershell + [command])

    @unittest.skipIf(os.name == "nt", "POSIX packaged command")
    def test_detached_packaged_commands_launch_safely_in_available_posix_shells(self):
        for shell in ("sh", "bash", "zsh"):
            executable = shutil.which(shell)
            if executable:
                with self.subTest(shell=shell):
                    # Each launch must be independent, with no inherited cwd.
                    with tempfile.TemporaryDirectory(prefix="develop-context-launch-") as directory:
                        previous = self.directory
                        try:
                            self.directory = Path(directory)
                            self.run_packaged_commands([executable, "-c"])
                        finally:
                            self.directory = previous

    @unittest.skipUnless(os.name == "nt", "Windows packaged command")
    def test_detached_packaged_commands_launch_safely_in_cmd(self):
        self.run_packaged_commands([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c"], windows=True)

    @unittest.skipUnless(os.name == "nt", "Windows packaged command")
    def test_detached_packaged_commands_launch_safely_in_powershell(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            self.skipTest("PowerShell is not available")
        self.run_packaged_commands([shell, "-NoProfile", "-NonInteractive", "-Command"], windows=True)


if __name__ == "__main__":
    unittest.main()
