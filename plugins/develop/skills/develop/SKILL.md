---
name: develop
description: Use when the user invokes Develop for repository work, dependency upgrades, incident diagnosis, deployment handoffs, cleanup, selected-session improvements or independent review.
---

# Develop

For local implementation, use Iterate's [local changes](../iterate/references/local-changes.md). Keep an existing representation when it fits. Before replacing it, test an operation exposed to callers even without an in-tree use. Check the requested behavior and a working neighbor on base and patch. Follow the wider workflow for listed risks.

For other work, carry the original request, steering, scope and authority to one owner. A bare `develop` permits context discovery. Use the [input policy](references/contract.md#unattended-continuation) if the outcome remains unclear.

| Requested outcome | Owner and scope |
| --- | --- |
| Implement, refactor, maintain or review a repository | [Iterate](../iterate/SKILL.md) owns the selected targets, constraints and behavior to preserve. |
| Diagnose, publish, monitor CI or prepare a deployment | [Iterate](../iterate/SKILL.md) owns the selected environment, revision, evidence and authorized repairs or delivery. |
| Design a change | [Engineering Design](../engineering-design/SKILL.md) and [Interface Design](../interface-design/SKILL.md) share one applicable brief and review. Return decisions to the execution owner. |
| Challenge a plan, artifact or result | [Adversarial Loop](../adversarial-loop/SKILL.md) reviews it against the original intent and evidence. |
| Improve a workflow from selected sessions | [Kaizen](../kaizen/SKILL.md) follows the selected sources, limits and action authority. |

Clean, Deep Clean, Upgrade and Upgrade Codex require explicit selection of the specific skill. Route ordinary dependency work to Iterate and handle resource questions within their requested scope.

For repository work outside the local path, use the applicable [shared contract](references/contract.md) and [planning gates](references/planning-and-review.md#applicable-planning). Reuse current checkpoints across handoffs. Carry authorized implementation and delivery through [Iterate's report](../iterate/SKILL.md#report). For review, diagnosis, monitoring or analysis, honor the requested stopping condition and report any unmet gate.
