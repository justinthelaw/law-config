# Scoped implementation

Use for authorized changes; review-only and prepared-change publication retain their own boundaries. No external workflow framework is required.

1. Establish the requested behavior, affected owners/interfaces and a concrete success check. Read their instructions and current source. Separate user requirements from assumptions; ask only when a missing decision materially changes the solution.
2. Choose the smallest coherent change. For a simple fix, a short plan suffices; for cross-component work, identify ordering, contracts, migration and rollback concerns. Honor an explicit plan-only or approval boundary. Reuse an accepted current plan instead of restarting design.
3. Reuse a suitable checkout/branch. Isolate work when concurrent or unrelated changes could interfere, using native workspace tools or worktrees. Preserve existing work and keep writers on disjoint files; parallelize only independent tasks.
4. Reproduce a defect before changing it. Compare a known-good baseline and trace the actual failing contract. For behavior changes, use a regression that fails for the relevant behavior and passes after the smallest fix. Tests should assert public behavior, not duplicate the implementation. Reversible prose/metadata changes need proportionate artifact checks.
5. Keep responsibilities with their existing owner. Reuse a shared cause's fix instead of adding copies or speculative abstraction. Preserve APIs and security controls; investigate unexpected failures before stacking retries or workarounds.
6. Follow [validation evidence](validation.md) and the shared review checkpoints. A fresh result establishes only the artifact and environment actually tested. Hand authorized publication to [publication](publication.md); local completion does not imply deployment.

Compatible installed planning, debugging or review skills can supplement this process. Their tool names, installation state and permissions are host capabilities to verify, not assumptions to copy into the task.
