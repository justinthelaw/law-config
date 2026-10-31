---
name: upgrade
description: Use when explicitly selected to assess or implement dependency and runtime upgrades or consolidate dependency PRs.
---

# Upgrade

Start only when the user names or selects Upgrade. Identify the selected repositories, owners, requested mode and existing authority using the [shared contract](../develop/references/contract.md).

1. **Assess before mutation.** Follow the [dependency assessment](references/assessment.md) for all in-scope direct and transitive categories. Pin baselines, targets, channels and dated evidence. Check [runtime contracts](../develop/references/runtime-contracts.md) for toolchain changes. An assessment ends with findings. Only an explicit request to implement after a concrete plan may bypass a separate assessment stage. Still verify ownership, pins, constraints and prerequisites.
2. **Plan.** Group compatible changes, order migrations and name acceptance checks and justified deferrals. Use the assessment as the [planning brief](../develop/references/planning-and-review.md#applicable-planning). Reuse its accepted review at handoff.
3. **Implement within authority.** Pass the plan to [Iterate](../iterate/SKILL.md). Preserve source-PR intent and attribution. Regenerate locks with the owning package manager. Address a resource shortage within the selected operation. Use Clean only when the user explicitly selects that skill.
4. **Resolve or defer.** Reproduce failures against the baseline. Try documented migrations or compatible alternatives. Preserve working upgrades and required tests. Record retained pins, attempted alternatives, evidence and retry conditions with maintained dependency records. Revisit existing deferrals.

Report each dependency group's owner, before/target/final versions, risk, evidence and decision. Use `Upgraded`, `Already current`, `Reviewed unchanged`, `Deferred` or `Blocked/unverified`. Include validation gaps, source-PR disposition and authorized delivery links. Distinguish changes to source, installation, build and deployment.
