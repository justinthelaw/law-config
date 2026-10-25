# Develop

Eight portable skills for development, review and maintenance. [Install in Codex](INSTALL.md), then invoke `$develop:develop` with your outcome, or call a skill directly.

Supply your development standards in the prompt, an attached `AGENTS.md` or a named connector source. Develop applies them within the selected scope and existing authority, using a shared [standards, presentation and unattended-continuation contract](skills/develop/references/contract.md). Reports use concise prose, tables or supported visuals according to the task; unattended work retains its budget and pending human decisions across handoffs.

The shared Codex context guard requires reviewed, trusted hooks and supported local orchestration and execution. Its default threshold is **20,000 counted bytes** (UTF-8 text plus JSON structure, not tokens).

| Hook | Source | Behavior |
| --- | --- | --- |
| `PreToolUse` | [Registration](hooks/hooks.json) · [Handler](hooks/context_guard.py) | Denies recognizable oversized whole-file reads; allows large edits and never rewrites commands. |
| `PostToolUse` | [Registration](hooks/hooks.json) · [Handler](hooks/context_guard.py) | With explicit session authorization, saves and verifies an oversized received response before returning a path/size/hash receipt. Otherwise warns and passes through. **Executed side effects remain.** |

Preservation is opt-in, POSIX-only and best-effort, with private storage, fixed quotas and explicit retention. No sandbox autodetection or upstream-truncation recovery is claimed. Never blindly repeat side-effecting calls. See [setup, recovery and native/code-mode limitations](docs/context-guard.md).

The separate [staged-file size checker](skills/iterate/references/staged-file-size.md) runs only when explicitly requested or required by the repository. It checks Git-index files; it does not install a Git hook or activate the context guard.

[![A user asks in chat why a CI job failed. Develop routes the question to Iterate, which reads the failed job log and replies with the cause or the missing evidence. The map also shows the other skills, the shared context guard, and Engineering Design and Interface Design linked to Iterate and included in the skill list.](docs/develop-overview.png)](docs/develop-overview.png)

The diagram and skill list include eight available skills plus Engineering Design and Interface Design as planned additions. Their dashed links show design guidance and handoff with Iterate; runnable entrypoints are not implemented yet.

[Full-size image](docs/develop-overview.png) · [Responsive HTML source](docs/develop-overview.html) · [Superpowers Codex source](https://github.com/openai/plugins/tree/main/plugins/superpowers) · [Maintainer instructions](AGENTS.md) · [Apache-2.0](LICENSE)
