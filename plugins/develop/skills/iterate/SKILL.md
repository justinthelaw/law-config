---
name: iterate
description: Implement, refactor or review repository changes, diagnose incidents, prepare deployment handoffs, publish selected work, and monitor or fix CI and reviews on GitHub, GitLab, Bitbucket or Hugging Face.
---

# Iterate

Deliver repository work through scoped changes, verified publication and current-commit review.

## Start

Read [the shared contract](../develop/references/contract.md); reuse its intent, authorization, signing preference, target selection and adversarial checkpoints. Reading this skill does not authorize publication or other external writes.

Choose the mode that matches the request; change modes only within its authorized scope:

| Mode | Target default and workflow |
| --- | --- |
| **Implement** | Build, fix or maintain behavior in selected repositories. Use the bundled [implementation guidance](references/implementation.md) for planning, isolation, debugging and meaningful tests. |
| **Refactor** | Improve the structure of affected code/docs while preserving behavior and performance. Use [bounded refactoring](references/refactoring.md) for an explicit request or a demonstrated need within authorized implementation; this is not resource cleanup or a mandatory polish phase. |
| **Debug** | Investigate a selected failure, service/environment or log bundle using [incident diagnosis](references/debugging.md). Keep diagnosis, repair and operational authority distinct; a checkout is optional until code repair. |
| **Review** | Inspect selected code or [documentation drift](references/documentation.md). Report findings without repair or publication unless authorized. |
| **Publish existing changes** | Use selected checkouts and initialized recursive submodules; otherwise resolve the current checkout. Preserve unrelated siblings. Read [publication](references/publication.md); prepared work needs no new design process. |
| **Deployment/operations handoff** | Prepare the requested handoff for a selected release/repository and target environment using [publication](references/publication.md#requested-deployment-or-operations-handoff). Identify the candidate, owner mechanism, acceptance/recovery evidence and missing authority; preparing the handoff does not execute deployment or operational changes. |
| **Monitor/fix** | Use the selected published repository/ref/SHA and submodules. Monitor through native provider tools or the [GitHub adapter](references/github-monitoring.md). Actual code repairs re-enter implementation requirements for that bounded target. |

Missing implementation access does not prevent safe read-only inspection. If publication validation exposes a code defect, use the implementation workflow for an authorized repair instead of expanding delivery scope.

When the bundled [Codex context guard](../../docs/context-guard.md) flags oversized reads or returns a recovery receipt, refine the paths, terms or symbols, then read bounded relevant sections or paginate results. Preserve the task and source content; do not remove useful comments, shave whitespace or fragment files to evade the limit. Recover bounded content from a verified receipt when available; never blindly retry side effects. Preservation is opt-in and failures pass through. Hook support and trust are host-owned; the eight skills remain usable on their supported hosts.

## Compose around the outcome

For a CI and Codex-review loop, use the [GitHub adapter](references/github-monitoring.md) and explicitly requested [Codex review adapter](references/codex-review.md). CI-only requests retain the CI-only default. One coordinator classifies current-head results, verifies findings, uses [Debug](references/debugging.md) when diagnosis is needed, then performs only authorized in-scope repair, validation and publication. Out-of-scope findings remain recorded; infrastructure failures follow validation's evidence/retry bounds instead of speculative product edits.

Keep one watcher per selected target/revision. A new head replaces its watch and invalidates affected checks/reviews; preserve unresolved findings and the invocation rather than duplicating review requests or resetting budgets. Changed steering updates the shared intent contract. At the requested stop condition, reconcile the unchanged head, stop the watcher and hand off results or the precise blocker. No recurring schedule is created unless requested.

For implementation/delivery intent, carry the authorized workflow below through its requested outcome in one invocation. Preserve the selected repositories, exclusions and stack-versus-consolidation choice. Apply the existing planning/review gates, [documentation checks](references/documentation.md) and [validation](references/validation.md). When publication and current-head review are requested, a finished patch or push alone is not completion. Continue authorized repairs until success or a genuine authority, access, evidence or review-budget blocker, while completing unaffected work. Review, Debug and CI-only requests do not acquire implementation, publication or operational authority from this loop.

## Implementation workflow

1. **Resolve.** Inspect the selected checkout's origin/upstream and exact provider identity. Preserve nested groups, change-request paths and artifact namespaces. Resolve an ambiguous shorthand through user/repository context; ask if its provider remains unclear. Use supported native tools for that host; never reroute an unsupported provider to another service.
2. **Prepare.** Inspect access, current default branch, related PRs/issues, instructions/templates, `CODEOWNERS`, security/CLA/DCO requirements, CI, manifests, lockfiles and pinned tools. Honor required maintainer acceptance; create prerequisite issues only when required and authorized. Reuse matching branches/requests in an isolated checkout. Preserve dirty/untracked work, stashes, unpublished commits and other worktrees. Start new work from the current default branch; use an authorized fork if upstream writes are unavailable.
3. **Implement.** Follow the scoped plan and [implementation guidance](references/implementation.md). Preserve interfaces, fix causes once and generate artifacts with pinned native tools. Use the [Refactor mode](references/refactoring.md) only when its bounded trigger applies. For documentation changes, use [current-source evidence](references/documentation.md).
4. **Validate.** Run repository-required checks and affected regression coverage using [validation evidence](references/validation.md). Use [visual validation](references/visual-validation.md) for affected rendered surfaces. When requested or required by the selected repository, explicitly invoke the [staged-file size check](references/staged-file-size.md); it neither configures the Codex context guard nor installs a Git hook or stages files. Inspect the full diff and `git diff --check`. Resolve material findings and rerun affected checks; distinguish defects from infrastructure/access failures.
5. **Publish.** When authorized, follow [publication](references/publication.md) for scoped staging, submodule order, nonblocking signing and remote readback. Open/update the native change request only within granted authority, preserving its template and stating purpose, behavior and actual validation evidence. Use [optional issue tracking](references/issue-tracking.md) when requested or required by repository policy; a normal delivery does not create an issue automatically.
6. **Verify each head.** Reconcile expected checks with actual provider results and complete required CI and configured/requested reviews for the unchanged current SHA. Diagnose failures; rerun unchanged code only for evidenced transient problems and within authorization. Inspect comments and unresolved threads, fix actionable findings and support disagreements with evidence. Resolve addressed threads only when that external write is authorized. Every push invalidates affected checks and reviews.

The bundled [GitHub adapter](references/github-monitoring.md) is read-only and provider-specific; optional automated reviewers require explicit adapter selection. Other hosts use their native checks and reviews with the same exact-revision evidence rules. Unsupported monitoring is not success.

An explicit request for one remaining consolidated PR permits closing fully incorporated source PRs only after replacement readiness. Re-read source heads/inventory, incorporate new in-scope work and reverify before closure. Cross-link sources to the replacement; preserve branches and incomplete sources.

## Report

Complete the final adversarial checkpoint. For **Debug**, use the [incident diagnosis report](references/debugging.md): impact, cause/confidence, supporting and missing evidence, and the next gate. Preserve the selected service/environment/log-bundle scope; do not discover a repository merely to populate delivery fields.

For repository delivery, reread the current head, required checks, reviews and threads. Claim readiness only when applicable gates pass; reconcile GitHub ready/draft status with the requested delivery state rather than treating it as acceptance. Never merge without authorization. Stop task-owned watchers. For requested cleanup or an identified authorized resource need, call [Clean](../clean/SKILL.md) within the existing scope and coordinator, then integrate its measurements and removed/protected/blocked dispositions into the shared handoff. Preserve useful evidence, source and unrelated/shared resources. Continue unaffected targets; report anything retained or blocked instead of manufacturing a clean-worktree result.

Use the shared [presentation policy](../develop/references/contract.md#presentation). Lead with the outcome, relevant verification and next action; a single-repository change usually needs a short explanation. Use a table when comparing targets or findings.

Keep the full shared handoff: changed scope and actual PR links; exact verified revision/destination and signing status; local checks, CI and requested provider reviews; skips/not-run and residual limitations; documentation and cleanup outcomes; remaining user action. Surface material facts and limits, linking detailed evidence rather than repeating the ledger. Include branch/stack updates, authorized history replacement or issue tracking when applicable. Report no-ops/blockers and distinguish readiness, publication and deployment.
