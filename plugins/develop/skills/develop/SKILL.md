---
name: develop
description: Implement and verify repository changes through their callers.
---

# Develop

Find the caller that observes the requested change. Reuse its existing representation and change the smallest owner that satisfies the contract.

For a bug, reproduce it through that caller, then rerun the same example after the fix. Check one nearby behavior the change could break. For data or resource operations, verify the resulting state, error or cleanup. Exercise changed public entry points as users invoke them. Run added tests under the project's configuration and finish required checks.

Work directly on clear tasks. Use [design or independent review](references/planning-and-review.md) for a consequential decision, identified risk or explicit request. Give reviewers the actual diff and completed evidence. Use [Iterate](../iterate/SKILL.md) for delivery tools. Report the result and material gaps.

Invoke Upgrade, Upgrade Codex, Kaizen, Clean or Deep Clean only by explicit user selection.
