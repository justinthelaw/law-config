# Install Develop

With Codex installed, add the marketplace and plugin:

```sh
codex plugin marketplace add justinthelaw/law-config --ref main
codex plugin add develop@law-config
```

Start a **new local Codex chat**. Open `/hooks`, review the bundled
[context guard](docs/context-guard.md), and trust only the reviewed definitions.
Untrusted or changed hooks are skipped. The hook requires Python 3.10+: `python3`
on Unix or `py -3` on Windows. No runtime is installed automatically.

Invoke Develop with your task:

```text
$develop:develop fix this checkout's failing build; preserve its public API.
```

Select other skills with `/skills`; leave whitespace before task text.

To refresh the marketplace and inspect status:

```sh
codex plugin marketplace upgrade law-config
codex plugin list --marketplace law-config --json
```

Apply updates through Codex's supported flow; check `/skills` and `/hooks` in a
new chat. Install and verify each intended environment separately. The hook
requires local orchestration and execution; cloud orchestration does not run it,
even with local tools. Publication alone does not activate it.

See the [README](README.md) for the skill directory.
