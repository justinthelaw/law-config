# Maintaining Develop

Keep [Develop](skills/develop/SKILL.md) sufficient for routine work. Add an instruction only for an observed failure or a concrete user requirement. Keep deterministic helpers with their owning skill. Follow [skill authoring rules](skills/AGENTS.md) and [artwork ownership](assets/AGENTS.md).

Preserve the five explicit-only maintenance commands, scoped authority, repository checks and recovery data. Review consequential work against actual artifacts. When a test could miss the defect, try a plausible wrong result and a harmless refactor. Use an existing signer as permitted by the user and repository; keep Git security controls intact.

## Verify and release

Run the [contribution checks](../../docs/CONTRIBUTING.md#validation). Exercise changed behavior in fresh sessions, including optional helpers from an unrelated directory. Use [evaluation records](../../docs/evaluations/README.md) for performance claims, with the compared configuration, coverage and limits.

Edit `plugin-source.json` and run `python scripts/generate_codex_manifest.py`. Ship the matching `.codex-plugin/plugin.json` as the sole runtime manifest. A root `plugin.json` suppresses native Codex hooks. Preserve the license, package identity, Git marketplace and [context guard](docs/context-guard.md).

Bump the version for release. Validate source and package before publication. Installation and native hook trust are separate, environment-specific actions. Verify explicit invocation, passive discovery and version in a fresh chat on each requested surface. Never edit installed caches. Move retired sources to recoverable system Trash.
