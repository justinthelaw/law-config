# Codex sweep coverage

Read official evidence per inspected surface, not entire manuals. No external skill, connector or account-wide source is required; report unavailable evidence and continue independent checks.

## Baseline

- Pin selected client executable/bundle, platform, channel, observed/target version. Query only verified executables; inspect supplied target schemas/source without installing. Shared files need supported intersection or proposed separation, never silent client selection.
- Trace selected config layers/profiles: CLI/environment, user/project, agent overrides, managed defaults and enforced requirements. Verify type-specific merge/precedence. Qualify effective-state claims when an influential layer is inaccessible/unselected.
- Prefer target-release official schemas, tagged source, release notes and native inspection APIs. For independently released hosts/services use current official evidence with surface/date. No retroactive application of current fields when historical evidence is absent. Separate schema support, maturity, host support, account access and enablement.

## Inventory

Start with names/documented discovery locations inside selected roots, including hidden/nested definitions, installed/source duplicates and declared references. Deduplicate physical files while retaining consumers/precedence. Do not follow links/references outside scope. Record missing references/access failures; selectively parse sensitive configuration without exposing values.

| Primitive | Checks |
| --- | --- |
| Configuration | `config.toml`, seeds, profiles, managed defaults, `requirements.toml`, catalogs/fragments: field/type validity, removed/renamed settings, defaults, precedence, ignored overrides, maturity, paths/trust. |
| Models/providers | IDs/routing, reasoning/plan effort, context/compaction, modalities/capabilities; authorized catalogs/compatibility. Valid strings do not prove access. Preserve pins/channels. |
| Instructions | Applicable `AGENTS.md`, overrides, fallback names/references: discovery/order, size limits, commands/paths, conflicts, duplication/ownership. Preserve unique requirements; unsupported length preferences are optional. |
| Agents | Roles, descriptions/instructions, model/provider overrides, permission inheritance, gates/concurrency; loaded files and inherited defaults. |
| Skills | Every `SKILL.md`, frontmatter, folder/name, invocation policy, `agents/openai.yaml`, dependencies/prompts/scripts/references/assets; required/optional fields, paths, invocation support. Label disabled/shadowed copies; presence is not discovery. |
| Plugins/marketplaces | Source/host manifests, catalogs, versions/identity/layout/ref paths, skill/MCP/app/hook mappings, enablement/dependencies and image pointers/schema. Separate maintained source, generated metadata, cache and published listing; repair the owner. |
| Hooks/rules | Events/matchers, commands/timeouts, approvals, enablement/trust, syntax/precedence/policy support. Inspect without execution; evidence ignored/unenforced controls. |
| MCP/apps | Transport, arguments, environment names, auth method, filters/capabilities/host support. Check references without server startup/token reads; runtime connectivity/access need separately scoped checks. |
| Environments/workflows | Worktrees, setup/launchers, prompt/command templates, SDK/app-server consumers, automations/memory settings: interfaces/options/paths/consumer versions. No session/memory bodies or schedule creation. |
| Additional surfaces | Discover unfamiliar/new primitive types from versioned schemas/source; record owner/evidence or coverage gap. |

Ledger per item: identity/path, type, owner, consumer/target, active/shadowed/disabled state, evidence, checks/status. Coverage is `Checked`, `Not applicable`, `Excluded` or `Unverified`; absent categories need reasons. Count checked/total actual items and list discovery gaps separately; incomplete denominators never imply full coverage.

## Findings and validation

Keep the smallest source locator establishing applicability. Classify `Required` only for proven incompatibility, broken reference or necessary behavior; `Deprecated` for documented supported retirement/migration; `Optional` for supported improvements; `Unverified` for missing evidence/state/version applicability.

For authorized repairs validate parse/schema, local references/package, then documented consumer checks within scope. Use fixtures/isolated configuration instead of changing live state. Repeat the affected operation on fictional inputs with the selected client/effective config; observe results and restrictions. Capture changes, for example, need small and oversized results with expected recovery/passthrough. Missing trust/access/execution means unverified with prerequisite identified. Separate static validation, live loading, installation and publication. Failed checks roll back only task-owned changes; preserve unrelated work/recoverable originals.

Official starting points (resolve current destinations; select revision evidence):

- [Configuration](https://learn.chatgpt.com/docs/config-file/config-reference), [managed configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration).
- [Customization](https://learn.chatgpt.com/docs/customization/overview), [AGENTS](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
- [Skill metadata/invocation](https://learn.chatgpt.com/docs/build-skills#optional-metadata), [plugins/marketplaces](https://learn.chatgpt.com/docs/enterprise/plugin-management#supported-formats).
- [Codex source/releases](https://github.com/openai/codex): matching tag/commit, never an unversioned branch as historical proof.
