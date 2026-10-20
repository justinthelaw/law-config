#!/usr/bin/env python3
"""Preserve-first native Codex context guard (see docs/context-guard.md).

Known whole-file reads receive bounded preflight guidance. Oversized received
responses are replaced only after opt-in atomic verified preservation. Unknown
policy and inspection/storage failures warn and leave normal results intact.
The 16 MiB raw-event ceiling bounds parsing, not total process memory.
"""
import argparse
import json
import os
import re
import runpy
import shlex
import stat
import sys


RAW_EVENT_LIMIT = 16 * 1024 * 1024
MAX_CONFIGURED_LIMIT = 1024 * 1024
GUIDANCE = (
    "Use rg with precise paths, terms, headings or symbols; refine noisy matches. "
    "Read only relevant bounded lines/pages or use pagination, and make targeted patches."
)
BINARY_MIMES = {
    "image": {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif",
              "image/bmp", "image/tiff", "image/heic", "image/heif"},
    "audio": {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg",
              "audio/flac", "audio/aac", "audio/mp4", "audio/webm", "audio/pcm"},
    "video": {"video/mp4", "video/webm", "video/mpeg", "video/quicktime", "video/ogg"},
}
READ_TOOLS = {"Read", "read_file", "read_text_file", "mcp__filesystem__read_file",
              "mcp__filesystem__read_text_file"}
RANGE_FIELDS = {"offset", "limit", "start_line", "end_line", "line_start", "line_end",
                "head", "tail", "max_lines", "max_bytes", "page", "pages", "range"}


class InvalidEvent(ValueError):
    """An event cannot safely be inspected; never expose its original content."""


class NumberToken:
    """Keep exact JSON numeric width without integer conversion or rounding."""

    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEvent("duplicate key")
        result[key] = value
    return result


def reject_constant(_value):
    raise InvalidEvent("non-JSON number")


def read_event():
    retained = bytearray()
    size = 0
    while True:
        chunk = sys.stdin.buffer.read(64 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size <= RAW_EVENT_LIMIT:
            retained.extend(chunk)
        else:
            retained.clear()
    if size > RAW_EVENT_LIMIT:
        raise InvalidEvent("raw event exceeds the 16 MiB inspection limit")
    raw = retained.decode("utf-8")
    return raw, json.loads(raw, object_pairs_hook=unique_object,
                      parse_int=NumberToken, parse_float=NumberToken,
                      parse_constant=reject_constant)


def is_base64(value):
    return (len(value) % 4 == 0
            and re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", value) is not None)


def string_cost(value, media=None):
    if media == "base64" and is_base64(value):
        return 2
    if media in BINARY_MIMES and value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        if (separator and header.startswith("data:") and header.endswith(";base64")
                and header[5:-7] in BINARY_MIMES[media] and is_base64(encoded)):
            return len(header.encode("utf-8")) + 3  # Prefix, comma and quotes.
    return len(value.encode("utf-8")) + 2


def media_children(value, context):
    """Recognize explicit native block shapes, never similarly named loose data."""
    result = {}
    kind = value.get("type")
    if type(kind) is str and kind in BINARY_MIMES:
        mime = value.get("mimeType", value.get("mime_type"))
        if type(mime) is str and mime in BINARY_MIMES[kind]:
            result["data"] = "base64"
    if kind in ("input_image", "image_url"):
        result["image_url"] = "image"
    if kind == "input_audio":
        result["input_audio"] = "input_audio"
    if context == "image":
        result["url"] = "image"
    if context == "input_audio" and value.get("format") in ("wav", "mp3"):
        result["data"] = "base64"
    return result


def text_size(value, limit):
    total = 0
    pending = [(value, None, 0)]
    while pending:
        item, media, depth = pending.pop()
        if depth > 256:
            raise InvalidEvent("nesting limit")
        if isinstance(item, str):
            total += string_cost(item, media)
        elif isinstance(item, NumberToken):
            total += len(item.text)
        elif isinstance(item, dict):
            total += 2 + max(0, len(item) - 1) + len(item)
            if total > limit:
                return total
            contexts = media_children(item, media)
            for key, child in item.items():
                total += string_cost(key)
                if total > limit:
                    return total
                pending.append((child, contexts.get(key), depth + 1))
        elif isinstance(item, list):
            total += 2 + max(0, len(item) - 1)
            if total > limit:
                return total
            pending.extend((child, None, depth + 1) for child in item)
        elif item is None:
            total += 4
        elif isinstance(item, bool):
            total += 4 if item else 5
        else:
            raise InvalidEvent("uninspectable value")
        if total > limit:
            return total
    return total


def has_range(arguments):
    for key in RANGE_FIELDS.intersection(arguments):
        value = arguments[key]
        if isinstance(value, NumberToken):
            if re.fullmatch(r"[1-9][0-9]*", value.text):
                return True
        elif type(value) is str and value.strip():
            return True
        elif isinstance(value, (list, dict)) and value:
            return True
    return False


def literal_cat_paths(command):
    if not isinstance(command, str) or any(char in command for char in "$`<>|;&\n\r()~*?[]{}!"):
        return []
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        return []
    if not words or words[0] not in ("cat", "/bin/cat", "/usr/bin/cat"):
        return []
    paths = words[1:]
    if paths and paths[0] == "--":
        paths = paths[1:]
    if not paths or any(path.startswith("-") for path in paths):
        return []
    return paths


def oversized_whole_read(event, limit):
    arguments = event["tool_input"]
    if not isinstance(arguments, dict):
        return False
    tool = event["tool_name"]
    if tool in ("Bash", "exec_command"):
        paths = literal_cat_paths(arguments.get("command", arguments.get("cmd")))
    elif tool in READ_TOOLS and not has_range(arguments):
        path = arguments.get("file_path", arguments.get("path"))
        paths = [path] if type(path) is str else []
    else:
        return False
    directory = event.get("cwd", os.getcwd())
    working = arguments.get("workdir", arguments.get("cwd"))
    if type(working) is str:
        directory = os.path.join(directory, working)
    total = 0
    for path in paths:
        try:
            info = os.stat(os.path.join(directory, path))
        except (OSError, ValueError):
            continue
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > limit:
                return True
    return False


def deny_read(reason):
    output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
              "permissionDecision": "deny", "permissionDecisionReason": reason + " " + GUIDANCE}}
    print(json.dumps(output, ensure_ascii=True, separators=(",", ":")))


def positive_limit(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer from 1 through 1048576") from None
    if not 1 <= number <= MAX_CONFIGURED_LIMIT:
        raise argparse.ArgumentTypeError("must be an integer from 1 through 1048576")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, choices=("PreToolUse", "PostToolUse"))
    parser.add_argument("--max-bytes", type=positive_limit, default=20000)
    arguments = parser.parse_args()
    try:
        raw, event = read_event()
        field = "tool_input" if arguments.event == "PreToolUse" else "tool_response"
        if (not isinstance(event, dict) or event.get("hook_event_name") != arguments.event
                or type(event.get("tool_name")) is not str or not event["tool_name"]
                or field not in event
                or ("cwd" in event and type(event["cwd"]) is not str)):
            raise InvalidEvent("invalid event envelope")
        text_size(event, sys.maxsize)  # Validate depth/Unicode without denying large edits.
        if arguments.event == "PreToolUse":
            if oversized_whole_read(event, arguments.max_bytes):
                deny_read(f"Whole-file read exceeds the {arguments.max_bytes}-byte context text limit.")
        elif text_size(event[field], arguments.max_bytes) > arguments.max_bytes:
            helper = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                "response_store.py"))
            receipt = helper["preserve"](raw, event.get("session_id"))
            print(json.dumps({"continue": False, "stopReason": receipt}, ensure_ascii=True))
    except (ValueError, TypeError, RecursionError, OSError, OverflowError, RuntimeError, ImportError):
        # No parser, path, payload, or exception text is promoted to instructions.
        print(json.dumps({"systemMessage": "Context guard: inspection or preservation unavailable; "
                          "normal result passthrough. Use bounded reads; capture non-repeatable "
                          "output at the producer. Never blindly retry side effects."}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
