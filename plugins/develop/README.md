# Develop

Eight portable skills for development, review and maintenance. [Install in Codex](INSTALL.md), then invoke `$develop:develop` with your outcome, or call a skill directly.

The shared Codex context guard requires reviewed, trusted hooks and supported local orchestration and execution. Its default threshold is **20,000 counted bytes** (UTF-8 text plus JSON structure, not tokens).

| Hook | Source | Behavior |
| --- | --- | --- |
| `PreToolUse` | [Registration](hooks/hooks.json) · [Handler](hooks/context_guard.py) | Denies recognizable oversized whole-file reads; allows large edits and never rewrites commands. |
| `PostToolUse` | [Registration](hooks/hooks.json) · [Handler](hooks/context_guard.py) | With explicit session authorization, saves and verifies an oversized received response before returning a path/size/hash receipt. Otherwise warns and passes through. **Executed side effects remain.** |

Preservation is opt-in, POSIX-only and best-effort, with private storage, fixed quotas and explicit retention. No sandbox autodetection or upstream-truncation recovery is claimed. Never blindly repeat side-effecting calls. See [setup, recovery and native/code-mode limitations](docs/context-guard.md).

The separate [staged-file size checker](skills/iterate/references/staged-file-size.md) runs only when explicitly requested or required by the repository. It checks Git-index files; it does not install a Git hook or activate the context guard.

[![Develop: one workflow with conditional branches, a review loop and a shared context guard, followed by the eight skills and their logos.](docs/develop-overview.png)](docs/develop-overview.png)

[Full-size image](docs/develop-overview.png) · [HTML source](docs/develop-overview.html) · [Superpowers Codex source](https://github.com/openai/plugins/tree/main/plugins/superpowers) · [Maintainer instructions](AGENTS.md) · [Apache-2.0](LICENSE)
