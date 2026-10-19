# Bounded refactoring

Use within Iterate for an explicit refactor request or a demonstrated structural
problem in the affected scope of authorized implementation. Record the concrete
problem and smallest useful improvement; skip an unnecessary pass. Refactoring
does not authorize unrelated cleanup, speculative architecture or repository-wide
polishing. [Clean](../../clean/SKILL.md) owns disposable resources and processes,
not source-code refactoring.

Use the existing [implementation workflow](implementation.md) and shared handoff.
Before editing, bind the objective to affected files/owners and protected
invariants: public behavior and APIs, data/error semantics, security controls,
documentation meaning and applicable performance contracts. Establish a baseline
with existing tests and add characterization only for relevant unprotected
behavior. For lifecycle-sensitive work, reuse the applicable ordering,
cancellation, retry and cleanup checks in the existing
[runtime contract guidance](../../upgrade/references/runtime-contracts.md#inspect-consumed-contracts);
this does not start a dependency upgrade.

Use [focused source reading](documentation.md#focused-source-reading) to locate
affected definitions, callers and tests by owner path and relevant terms before
expanding discovery. Read enough surrounding context to preserve the invariants;
small excerpts do not replace required complete coverage.

Prefer clear responsibilities, shared fixes and small reusable units. Remove
demonstrated duplication; keep code and documentation concise without obscuring
intent or discarding constraints. Fewer lines alone are not evidence of better
design. Do not split cohesive files or remove useful comments solely to satisfy a
[staged-file byte budget](staged-file-size.md); choose a genuine ownership
improvement or report the policy conflict. Preserve functionality and performance;
use affected complexity/resource
contracts or existing performance checks, adding a bounded measurement when a
credible regression risk requires it. Keep application performance separate from
agent time/token cost.

When a focused worker helps, delegate only the bounded files, objective,
invariants and acceptance checks through the shared handoff. Give it the relevant
source/tests and protected work; keep concurrent writers disjoint. The worker
returns its patch or no-op, rationale, executed checks, limitations and open
findings. It does not publish, start a watcher or run nested independent reviews.
Without a suitable worker, the coordinator can perform the same bounded work.

Iterate remains the delivery owner: inspect and integrate the returned diff,
rerun affected regression checks and all applicable repository-required tests,
and use the existing intent/evidence adversarial checkpoints against the
integrated artifact. A worker's passing tests do not approve the integration.
Changes beyond the bound return to the coordinator for scope/authority handling;
missing independent review remains an explicit gate. Publication and exact-head
monitoring follow the existing Iterate workflow without a second coordinator.
