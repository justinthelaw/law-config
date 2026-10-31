---
name: upgrade
description: Explicit dependency and runtime upgrades or dependency PR consolidation.
---

# Upgrade

Identify selected repositories, owners and whether the user wants assessment or implementation. Use the [assessment](references/assessment.md) to group compatible upgrades, record current and target versions, migration order, checks and deferrals. For toolchain changes verify [runtime identities](../develop/references/runtime-contracts.md). An accepted plan can supply the assessment.

Implement authorized groups with the owning package manager. Regenerate locks, preserve source PR intent and attribution, run consumers and compare failures against baseline. Keep working upgrades separable. Report actual versions, deferred pins, retry conditions and publication status. Diagnosis or resource pressure cannot authorize cleanup.
