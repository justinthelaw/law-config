# Plugins

- Keep each distributable package under `plugins/<name>/` with self-contained `skills/` references. Develop keeps portable source metadata in `plugin-source.json` and generates `.codex-plugin/plugin.json` as its sole runtime manifest; a root `plugin.json` would suppress its native hooks. Regenerate after source metadata changes and validate the shipped artifact without rewriting it.
- Register packages in the repository-root `.agents/plugins/marketplace.json`; source paths are relative to the repository root.
- Keep installation guidance in each package's `INSTALL.md`, agent instructions in scoped `AGENTS.md`, and executable checks with that package.
- Do not store tokens, conversation transcripts, machine-specific paths, or installed plugin caches here. Git updates and installation are separate operations.
- For Develop, follow its [package instructions](develop/AGENTS.md) and the [contribution checks](../docs/CONTRIBUTING.md#validation), including the full plugin test suite.
