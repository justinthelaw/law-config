# Develop

Eight portable skills for development, review and maintenance. [Install in Codex](INSTALL.md), then invoke `$develop:develop` with your outcome, or call a skill directly.

The shared Codex context guard requires reviewed, trusted hooks with supported local orchestration and execution. Both hooks use a default budget of **20,000 counted bytes per tool input or result** (UTF-8 text plus JSON structure, not characters or tokens).

| Hook | Registration and implementation | Trigger and behavior |
| --- | --- | --- |
| `PreToolUse` | [Registration](hooks/hooks.json) · [Python handler](hooks/context_guard.py) | Before a supported tool runs, denies oversized arguments and recognizable oversized whole-file reads. |
| `PostToolUse` | [Registration](hooks/hooks.json) · [Python handler](hooks/context_guard.py) | After a supported tool runs, withholds oversized results and replaces them with guidance to narrow searches or reads. **It cannot undo executed side effects.** |

The guard does not save blocked content or provide an artifact path. Narrow a read against an existing source or artifact when available; transient output may not be recoverable. Do not repeat side-effecting calls just to recover output. See [exact accounting, coverage, failure behavior and activation](docs/context-guard.md).

The separate [staged-file size checker](skills/iterate/references/staged-file-size.md) runs only when explicitly requested or required by the repository. It checks Git-index files; it does not install a Git hook or activate the context guard.

[![Develop: one workflow with conditional branches, a review loop and a shared context guard, followed by the eight skills and their logos.](docs/develop-overview.png)](docs/develop-overview.png)

[Full-size image](docs/develop-overview.png) · [HTML source](docs/develop-overview.html) · [Superpowers Codex source](https://github.com/openai/plugins/tree/main/plugins/superpowers) · [Maintainer instructions](AGENTS.md) · [Apache-2.0](LICENSE)
