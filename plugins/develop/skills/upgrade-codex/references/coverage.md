# Codex sweep coverage

Use this inventory for every sweep. Read the applicable official references as each surface is inspected; do not preload entire manuals or preserve a hardcoded version catalog here.

## Resolve the baseline

Record each selected client's executable or bundle identity, platform, release channel, observed version and target version. Use a documented version query only for a verified executable. For a supplied target, inspect its published schema/source without installing it. If the same files serve multiple clients, assess their supported intersection or propose separate configuration; do not silently choose one client.

Trace the selected configuration layers and active profiles, including declared command-line/environment overrides, user/project settings, agent overrides, managed defaults and enforced requirements. Verify merge and precedence rules for the target; tables, scalars and policy fields may compose differently. If an unselected or inaccessible layer affects the result, record that dependency and qualify effective-state claims.

Prefer the target release's official schemas, tagged source, release notes and documented native inspection APIs. Use current official guidance for independently released host/service contracts, naming the applicable surface and evidence date. When historical evidence is unavailable, report uncertainty rather than applying today's fields retroactively. Distinguish schema support, experimental maturity, host support, account availability and local enablement.

## Inventory and checks

| Primitive | Inspect |
| --- | --- |
| Configuration | Selected `config.toml`, seeds, profiles, managed defaults and `requirements.toml`; schema-valid fields/types, removed or renamed settings, defaults, precedence, ignored overrides, feature maturity, paths and trust. Include referenced catalogs and configuration fragments. |
| Models and providers | Model IDs, provider routing, reasoning/plan effort, context and compaction settings, modalities and capability assumptions. Check documented compatibility and available authorized catalogs; do not equate a valid model string with account access. Preserve deliberate pins and release channels. |
| Instructions | Applicable `AGENTS.md`, overrides, configured fallback names and referenced guidance; discovery/order, size limits, stale commands/paths, conflicts, duplication and concise ownership. Preserve unique requirements. Treat unsupported length preferences as optional improvements. |
| Agents | Role definitions, descriptions, instructions, model/provider overrides, permission inheritance, feature gates and concurrency limits. Check the files the selected client loads, including shared parent defaults. |
| Skills | Every discovered `SKILL.md`, frontmatter, folder/name identity, invocation policy, `agents/openai.yaml`, dependencies, prompts, scripts, references and assets. Check required versus optional fields, metadata paths and supported invocation behavior. Inspect disabled or shadowed copies as such; presence does not prove discovery. |
| Plugins and marketplaces | Source manifests, host adapters, catalog entries, versions, identity, package layout, source/ref paths, skill/MCP/app/hook mappings, enablement, dependencies, logos, icons, screenshots and other image pointers. Validate referenced files and applicable format/schema rules. Separate maintained source, generated metadata, installed cache and published listing; repair the owner rather than patching caches. |
| Hooks and rules | Event/matcher schemas, command declarations, timeouts, approvals, enabled/trusted state, rule syntax, precedence and supported policy semantics. Inspect scripts and references without executing hooks. Flag a control that is ignored or unenforced with evidence. |
| MCP and app integrations | Server/app declarations, transport, launch arguments, environment-variable names, auth method, tool filters, capability settings and host support. Check references without starting servers or reading tokens. Runtime connectivity and account access remain unverified unless separately tested within scope. |
| Environments and workflows | Worktree/environment definitions, setup and launcher configuration, prompt/command templates, SDK/app-server consumers, automation definitions and memory settings when present. Check declared interfaces, supported options, referenced paths and the version each consumer uses. Do not read session or memory bodies or create schedules. |
| Additional surfaces | Discover other configuration or primitive types from the selected clients' current/versioned schemas and source inventory. Add them with their owner and evidence; an unfamiliar or unreadable surface is a coverage gap, not an implicit pass. |

Start with filenames and documented discovery locations inside selected roots. Include hidden and nested definitions, installed/source duplicates and declared references. Deduplicate the same physical file while retaining its consumers and precedence. Do not follow symlinks or references outside scope. Report missing references and access failures without guessing their contents. Parse sensitive configuration selectively and keep secret values out of output.

Maintain an item ledger: path/identity, primitive type, owner, consumer, target, active/shadowed/disabled state, evidence, checks and coverage status. Give absent categories a reason rather than inventing files to satisfy the table. Report checked/total counts over the actual inventoried items; list discovery gaps separately so an incomplete denominator cannot imply complete coverage.

## Evidence and validation

For a finding, retain the smallest source locator that establishes the requirement and its applicability. Separate these outcomes:

- `Required`: proven incompatibility, broken reference or behavior needed by the selected setup.
- `Deprecated`: supported behavior with a documented retirement or migration path.
- `Optional`: a supported improvement in clarity, maintenance or capability.
- `Unverified`: insufficient evidence, inaccessible state or unknown version applicability.

Validate changes in layers: parse/schema checks, local reference/package checks, then documented consumer checks appropriate to the authorized effects. Use temporary fixtures or isolated configuration for checks that would otherwise alter live state. Confirm the intended values are effective and required restrictions remain enforced. Report static validation separately from live loading, installation and publication. Roll back only task-owned changes if validation fails, preserving unrelated work and recoverable originals.

Official starting points (resolve their current destinations and select versioned evidence where needed):

- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) and [managed configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration).
- [Customization](https://learn.chatgpt.com/docs/customization/overview), [AGENTS guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
- [Skill metadata and invocation](https://learn.chatgpt.com/docs/build-skills#optional-metadata).
- [Plugin formats and marketplaces](https://learn.chatgpt.com/docs/enterprise/plugin-management#supported-formats).
- [Official Codex source and releases](https://github.com/openai/codex); use the matching release tag or commit, not an unversioned branch as historical proof.

Use available official documentation tools or permitted direct retrieval. No external skill, connector or account-wide source is a prerequisite. Report unavailable sources and continue independent checks.
