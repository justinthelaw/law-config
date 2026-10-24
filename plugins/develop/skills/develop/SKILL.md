---
name: develop
description: Use when the user invokes Develop for repository work, dependency upgrades, incident diagnosis, deployment handoffs, cleanup, selected-session improvements or independent review.
---

# Develop

Route the user's intent into verified work.

## Start

Resolve the user's outcome, then route below. Repository workflows read [the shared contract](references/contract.md); standalone session analysis and independent review use their own scope rules. Preserve one invocation and its original/steering messages across handoffs. A bare `develop` permits context discovery. Use the [input policy](references/contract.md#unattended-continuation) if the outcome remains unclear.

## Route

| Intent | Required skill | Handoff |
| --- | --- | --- |
| Implement, fix, refactor, maintain or review repository work | [iterate](../iterate/SKILL.md) | Targets, outcome, implementation constraints; bounded refactor objective/invariants when relevant |
| Diagnose a failure or local, staged or live incident | [iterate](../iterate/SKILL.md) | Selected service/environment/log bundle, time window, diagnosis/repair boundary |
| Publish existing changes or monitor/fix CI | [iterate](../iterate/SKILL.md) | Selected roots, delivery mode, existing authority, thread signing preference |
| Prepare a deployment or operations handoff | [iterate](../iterate/SKILL.md) | Selected release/repository, target environment, candidate identity, evidence and authority gaps |
| Review or upgrade dependencies/runtimes; consolidate dependency PRs | [upgrade](../upgrade/SKILL.md) | Targets, review/implementation boundary, dependency and PR scope |
| Inspect or reclaim disk/RAM; investigate processes | [clean](../clean/SKILL.md) | Thread activity evidence, audit/cleanup authority, protected work; explicit widening only |
| Challenge facts, visuals, writing, plans or results | [adversarial-loop](../adversarial-loop/SKILL.md) | Intent, artifacts, evaluation criteria |
| Learn from selected sessions and improve agent workflows | [kaizen](../kaizen/SKILL.md) | User-selected sessions/sources and limits, desired improvement, action authority |

[deep-clean](../deep-clean/SKILL.md) is explicit-only. Route to it only when the user names it or explicitly expands cleanup/inspection beyond thread activities; pass the selected root and authority. Ordinary cleanup defaults to this thread and requires no repository discovery.

For mixed requests, select the initial owner from the requested outcome, then use the smallest ordered combination and one coordinator. Iterate owns the CI/requested-review → diagnosis → authorized repair → validation → authorized publication loop; domain references do not route recursively back here. Reuse relevant review checkpoints across nested skills. A handoff from analysis to implementation preserves its target and existing authorization; it never expands to other repositories or histories.

[upgrade-codex](../upgrade-codex/SKILL.md) is available only when the user explicitly invokes it. Do not select it from general development, maintenance or dependency-upgrade requests.

## Report

Carry an implementation/delivery invocation through Iterate's [completion and report](../iterate/SKILL.md#report); users need not invoke each phase separately. Narrow review, diagnosis, monitoring and analysis requests keep their selected stop condition and authority. For mixed work, combine the owning reports and identify incomplete gates.
