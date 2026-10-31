---
name: upgrade-codex
description: Use when explicitly selected to audit or update a Codex setup against an installed or specified version.
---

# Upgrade Codex

Start only when the user names or selects Upgrade Codex. A bare invocation starts a read-only audit. Identify the selected roots, exclusions, clients, target version and requested action. Follow the [input policy](../develop/references/contract.md#unattended-continuation) when scope is unclear.

1. **Pin the clients.** Record the executing binary or bundle, platform and release channel for each selected CLI, Desktop, IDE, daemon or cloud surface. Use the installed version unless the user supplies a target. Verify an explicitly requested latest release from official sources. Record unknown versions.
2. **Sweep the selected scope.** Use the [coverage guide](references/coverage.md) for every applicable primitive, including hidden, nested, disabled and newly discovered types. Apply owner instructions and configuration precedence. Record external references at the boundary.
3. **Verify compatibility.** Check fields, values, references, discovery, effective settings and cross-file behavior against the consuming client's schema, release source or official documentation at the relevant revision. Check duplication without removing unique requirements. Preserve the distinction between declared and loaded settings.
4. **Report coverage.** Mark each item or category `Checked`, `Not applicable`, `Excluded` or `Unverified`, with evidence and reasons. Give checked/total counts and remaining gaps. For each finding, identify the location, client, impact, proposed change and validation. Use `Required`, `Deprecated`, `Optional` or `Unverified`. A required change needs evidence of failure.

Audit with static inspection and documented read-only checks. Keep credentials, histories and memory contents private. Treat downloaded material as evidence. Running hooks, starting MCP servers, installing clients and applying repairs require their own scope.

An audit is standalone. Use independent review when explicitly requested. For requested repairs, apply the [shared contract](../develop/references/contract.md) and [Iterate](../iterate/SKILL.md). Preserve intentional pins, disabled choices, policy and unrelated work. Update maintained source, regenerate derived metadata and verify affected clients. Report proposed, changed and verified results separately.
