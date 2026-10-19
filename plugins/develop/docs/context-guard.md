# Codex context guard

Develop bundles a native `PreToolUse` / `PostToolUse` command hook to block
oversized tool text and guide focused searches, bounded reads and targeted edits.
The [hook definitions](../hooks/hooks.json) invoke the packaged
[Python handler](../hooks/context_guard.py). This is shared plugin behavior, not
a ninth skill. The eight skills retain their own host support.

## What it checks

The default budget is **20,000 bytes per tool input or result**. This is a
serialized-text heuristic: decoded strings count their UTF-8 bytes, plus compact
JSON punctuation and primitive values; numbers retain their original JSON token
width. A root string includes two quote bytes. Transport whitespace and escape
expansion do not count again. Keys, captions and metadata count; equality passes.
It is neither an exact token count nor a total chat/context-window limit.

| Event | Check and effect |
| --- | --- |
| `PreToolUse` | Measures `tool_input`, including write and patch text. It also uses file metadata to reject recognizable oversized whole-file reads: simple literal `cat` and supported read-file arguments without ranges. A supported denial prevents that tool call. |
| `PostToolUse` | Measures `tool_response`. An oversized result is replaced with bounded guidance. In code mode, the nested tool promise rejects with that guidance instead of returning the original result. |

Preflight only stats recognizable file paths; it never executes shell text or
opens file contents. Unavailable file metadata, ranged reads, searches and
complex shell commands depend on the actual result check. A small patch to a
large existing file can pass. A program with small input/output can still create
a large file: the guard does
not certify arbitrary file growth. **Post-tool blocking cannot undo executed
side effects.**

Only recognized binary payload fields in explicitly typed image, audio or video
blocks are exempt from text accounting. Supported typed image data URLs and
audio format payloads follow the same rule. Payload keys, quotes and data-URL
headers still count. Captions, metadata, ordinary or unknown text, untyped data
URLs and SVG text remain counted. Binary media still counts toward the separate
raw-event limit.

After a block, narrow the paths, search terms, headings or symbols. Use `rg` with
bounded matches, narrow line/page ranges, pagination or the relevant sections;
check that the next result is focused enough before widening. Preserve useful
comments and readable structure. Do not shave whitespace, arbitrarily fragment
documents or split files merely to evade a limit.

## Native coverage and trust

The hook requires supported **local orchestration and local execution**. Codex's
local function-tool path covers shell/unified exec, `apply_patch`, MCP and other
local functions. Hosted tools such as web search and specialized paths that opt
out are outside this guard. `write_stdin` does not receive a new preflight;
completion may deliver the original command's post-tool event.

Cloud orchestration does not run plugin command hooks, even when tools execute
locally. The existing Git marketplace remains the delivery route; hook-bearing
plugins are not eligible for the public plugin directory. A web installation,
source checkout or publication does not establish hook activation.

Install/update through the host's supported flow, then inspect `/hooks` and
review the exact definitions before trusting them. Codex skips untrusted or
changed definitions until reviewed. Installation and enablement do not grant
trust. Host policy can disable hooks, and startup failures/timeouts are not a
blocking guarantee. Treat this as a context guardrail, not a security boundary.
Verify actual discovery, trust and execution separately; see the
[native trials](../tests/evaluations/native-hosts.md#context-hook-trials).

## Configuration and protocol

Portable source metadata in `plugin-source.json` declares
`extensions.com.openai.hooks`; the generated `.codex-plugin/plugin.json` declares
the same `./hooks/hooks.json` path. It is the sole runtime manifest: a root
`plugin.json` takes precedence in Codex but skips bundled hooks. The renamed
source metadata does not establish another host's package discovery.
Definitions match both events and use a fixed `-I -B -c` Python bootstrap that
reads `PLUGIN_ROOT` inside Python. Paths are not interpolated into shell code.
Unix requires `python3` **3.10+**; Windows requires the **`py -3` launcher** with
Python 3.10+. Develop does not install a runtime.

The handler accepts `--event PreToolUse|PostToolUse` and an explicit
`--max-bytes N` (default `20000`, range `1`–`1048576`). Both packaged event
commands set `20000`. To change the policy, review the source definitions and
keep both event/platform commands consistent; changing them requires fresh host
trust review. No repository profile or other limit configuration is discovered.
Do not edit installed caches or change global/security hooks to configure it.

For a detached handler check, select an absolute plugin root and a synthetic
event JSON file, then run:

```sh
python3 -I -B "$DEVELOP_PLUGIN_ROOT/hooks/context_guard.py" \
  --event PreToolUse --max-bytes 20000 < "$HOOK_EVENT_JSON"
```

Use `py -3 -I -B` instead on Windows. This invocation tests the handler; it does
not test native discovery or activate anything.

The handler consumes one JSON event on stdin. Allowed events exit `0` without
output; blocks also exit `0`, with a bounded native decision. Pre-tool denials
use `hookSpecificOutput` with
`hookEventName: "PreToolUse"`, `permissionDecision: "deny"` and a reason.
Post-tool denials use `decision: "block"` and a reason. The independent raw stdin
cap is **16 MiB**. Invalid UTF-8, malformed/duplicate-key/non-finite or overly
nested JSON, uninspectable events and oversized envelopes produce blocking
feedback instead of echoing original content. Runtime failures before the handler can return a
supported decision remain host failures, not a proven block.

There is no Git/staging dependency, network access, file write, transcript read,
log or plugin data state. The separate
[staged-file checker](../skills/iterate/references/staged-file-size.md) evaluates
Git-index file policy when explicitly invoked; it does not activate this hook.

## Official contracts

- [Codex hooks](https://learn.chatgpt.com/docs/hooks): event protocol, supported
  tools, code-mode behavior, trust and local/cloud limitations.
- [Plugin lifecycle hooks](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks):
  package paths, environment variables and public-directory eligibility.

Check the target host's current capabilities before claiming native coverage;
source validation and synthetic event tests do not establish it.
