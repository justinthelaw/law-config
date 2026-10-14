---
name: iterate
description: Implement or review repository changes, publish selected existing work, and monitor or repair CI and review findings on GitHub, GitLab, Bitbucket or Hugging Face.
---

# Iterate

Deliver repository work through scoped changes, verified publication and current-commit review.

## Start

Read [the shared contract](../develop/references/contract.md); reuse its intent, authorization, signing preference, target selection and adversarial checkpoints. Reading this skill does not authorize publication or other external writes.

Choose the mode that matches the request; change modes only within its authorized scope:

| Mode | Target default and workflow |
| --- | --- |
| **Implement** | Build, fix or maintain behavior in selected repositories. Use the bundled [implementation guidance](references/implementation.md) for planning, isolation, debugging and meaningful tests. |
| **Review** | Inspect selected code or [documentation drift](references/documentation.md). Report findings without repair or publication unless authorized. |
| **Publish existing changes** | Use selected checkouts and initialized recursive submodules; otherwise resolve the current checkout. Preserve unrelated siblings. Read [publication](references/publication.md); prepared work needs no new design process. |
| **Monitor/fix** | Use the selected published repository/ref/SHA and submodules. Monitor through native provider tools or the [GitHub adapter](references/github-monitoring.md). Actual code repairs re-enter implementation requirements for that bounded target. |

Missing implementation access does not prevent safe read-only inspection. If publication validation exposes a code defect, use the implementation workflow for an authorized repair instead of expanding delivery scope.

## Implementation workflow

1. **Resolve.** Inspect the selected checkout's origin/upstream and exact provider identity. Preserve nested groups, change-request paths and artifact namespaces. Resolve an ambiguous shorthand through user/repository context; ask if its provider remains unclear. Use supported native tools for that host; never reroute an unsupported provider to another service.
2. **Prepare.** Inspect access, current default branch, related PRs/issues, instructions/templates, `CODEOWNERS`, security/CLA/DCO requirements, CI, manifests, lockfiles and pinned tools. Honor required maintainer acceptance; create prerequisite issues only when required and authorized. Reuse matching branches/requests in an isolated checkout. Preserve dirty/untracked work, stashes, unpublished commits and other worktrees. Start new work from the current default branch; use an authorized fork if upstream writes are unavailable.
3. **Implement.** Follow the scoped plan and [implementation guidance](references/implementation.md). Preserve interfaces, fix causes once and generate artifacts with pinned native tools. For documentation changes, use [current-source evidence](references/documentation.md).
4. **Validate.** Run repository-required checks and affected regression coverage using [validation evidence](references/validation.md). Inspect the full diff and `git diff --check`. Resolve material findings and rerun affected checks; distinguish defects from infrastructure/access failures.
5. **Publish.** When authorized, follow [publication](references/publication.md) for scoped staging, submodule order, nonblocking signing and remote readback. Open/update the native change request only within granted authority, preserving its template and stating purpose, behavior and actual validation evidence. Use [optional issue tracking](references/issue-tracking.md) when requested or required by repository policy; a normal delivery does not create an issue automatically.
6. **Verify each head.** Reconcile expected checks with actual provider results and complete required CI and configured/requested reviews for the unchanged current SHA. Diagnose failures; rerun unchanged code only for evidenced transient problems and within authorization. Inspect comments and unresolved threads, fix actionable findings and support disagreements with evidence. Resolve addressed threads only when that external write is authorized. Every push invalidates affected checks and reviews.

The bundled [GitHub adapter](references/github-monitoring.md) is read-only and provider-specific; optional automated reviewers require explicit adapter selection. Other hosts use their native checks and reviews with the same exact-revision evidence rules. Unsupported monitoring is not success.

An explicit request for one remaining consolidated PR permits closing fully incorporated source PRs only after replacement readiness. Re-read source heads/inventory, incorporate new in-scope work and reverify before closure. Cross-link sources to the replacement; preserve branches and incomplete sources.

## Report

Complete the final adversarial checkpoint and reread the current head, required checks, reviews and threads. Claim readiness only when applicable gates pass; list outstanding human approvals separately. Never merge without authorization. Continue unaffected targets. Report remaining protected unrelated work rather than cleaning it to manufacture a clean-worktree result.

Use the caller's format, otherwise:

| Repository | Change | Result and evidence |
| --- | --- | --- |

Link actual change requests and current-head evidence. Include commits/destinations, signed or unsigned status, executed validation, branch updates and any authorized history replacement or issue tracking. Report no-ops/blockers; use `—` for unpublished work.
