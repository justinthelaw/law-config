# Install Develop

In a terminal with Codex installed, add the marketplace and plugin:

```sh
codex plugin marketplace add justinthelaw/law-config --ref main
codex plugin add develop@law-config
```

Start a **new Codex chat**, then invoke Develop with your task:

```text
$develop:develop fix this checkout's failing build; preserve its public API.
```

You can also select a skill with `/skills`. Put a space after the skill name.

To refresh the marketplace and inspect available plugin status:

```sh
codex plugin marketplace upgrade law-config
codex plugin list --marketplace law-config --json
```

Use Codex's supported update flow to apply an available update, then check
`/skills` in a new chat. Install separately on each intended environment.

See the [README](README.md) for the visual guide and all eight skills.
