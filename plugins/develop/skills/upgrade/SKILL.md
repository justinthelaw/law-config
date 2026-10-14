---
name: upgrade
description: Assess, plan or implement dependency and runtime upgrades, consolidate dependency PRs, and revisit failed or deferred migrations.
---

# Upgrade

Review dependency risks first, then deliver the smallest justified upgrade within the user's scope.

## Start

Read [the shared contract](../develop/references/contract.md) for target selection, authorization and review. Consider all dependency categories within selected targets unless the request is narrower; never infer an account-wide fleet.

**Assessment comes before mutation, cleanup or integration.** Read [dependency assessment](references/assessment.md) and establish owners, baselines, targets and risks. A selected review-only task ends with findings: no installation, lockfile writes, cleanup or publication. Missing prerequisites remain evidence gaps.

Only an explicit user request to proceed directly into implementation **after a concrete plan** may bypass the separate assessment stage. Record that request and plan; still verify ownership, baseline and target identities, applicable constraints and validation prerequisites. A general upgrade request is not a bypass.

## Workflow

1. **Assess.** Compare direct and transitive changes against the selected baseline. Freeze exact targets and evidence dates; preserve intentional release channels. For runtime or toolchain changes, also read [runtime contracts](references/runtime-contracts.md).
2. **Plan.** Identify compatibility groups, migration order, acceptance checks and deferrals. Separate required compatibility work from optional improvements. Continue into implementation when already authorized; do not invent another approval gate.
3. **Implement.** Use [iterate](../iterate/SKILL.md) for preparation, changes, validation and authorized delivery. Regenerate lockfiles with owner-native tooling; preserve source-PR intent and attribution. Use [clean](../clean/SKILL.md) only for a demonstrated resource need within authorization. Cleanup is not an upgrade prerequisite.
4. **Resolve or defer.** Compare failures with the baseline, trace changed contracts, and test reasonable documented migrations or compatible alternatives. Preserve successful upgrades and required tests. Record unresolved targets, attempted alternatives, retained versions, evidence and retry conditions beside maintained pins or dependency documentation; never hand-edit generated lockfiles. Revisit existing deferrals.

## Report

Account for each considered dependency or coherent group: owner, before/target/final versions, risk, decision and evidence. Use `Upgraded`, `Already current`, `Reviewed unchanged`, `Deferred` or `Blocked/unverified`; distinguish recommendations from completed changes. Include validation gaps, source-PR disposition and authorized delivery links. Report source, installed, built and deployed outcomes separately. Apply the shared evidence checkpoint and iterate's delivery checks when relevant; a review-only result needs no PR.
