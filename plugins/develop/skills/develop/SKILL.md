---
name: develop
description: Use when the user invokes develop for repository work, dependency upgrades, environment cleanup, session improvement, independent review, or a combination of these tasks.
---

# Develop

Route the user's intent into verified work.

## Start

Resolve the user's outcome, then route below. Repository workflows read [the shared contract](references/contract.md); standalone session analysis and independent review use their own scope rules. Preserve one invocation and its original/steering messages across handoffs. A bare `develop` permits context discovery; ask for the missing outcome only if it remains unclear.

## Route

| Intent | Required skill | Handoff |
| --- | --- | --- |
| Implement, fix, maintain or review repository work | [iterate](../iterate/SKILL.md) | Targets, outcome, implementation constraints |
| Publish existing changes or monitor/fix CI | [iterate](../iterate/SKILL.md) | Selected roots, delivery mode, existing authority, thread signing preference |
| Review or upgrade dependencies/runtimes; consolidate dependency PRs | [upgrade](../upgrade/SKILL.md) | Targets, review/implementation boundary, dependency and PR scope |
| Inspect or reclaim disk/RAM; investigate processes | [clean](../clean/SKILL.md) | Environment, exact scope, protected work |
| Challenge facts, visuals, writing, plans or results | [adversarial-loop](../adversarial-loop/SKILL.md) | Intent, artifacts, evaluation criteria |
| Learn from selected sessions and improve agent workflows | [kaizen](../kaizen/SKILL.md) | User-selected sessions/sources and limits, desired improvement, action authority |

For mixed requests, use the smallest ordered combination and one coordinator. Reuse relevant review checkpoints across nested skills. A handoff from analysis to implementation preserves its target and existing authorization; it never expands to other repositories or histories.

## Report

Use the selected skill's report. For mixed work, combine target, result and evidence with required dependency/resource details; identify incomplete gates.
