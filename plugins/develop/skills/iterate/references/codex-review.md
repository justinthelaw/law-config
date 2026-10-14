# Optional Codex review adapter

Use only when this specific reviewer is requested or required for a selected GitHub repository. This adapter's API identities and signals are vendor-specific; they are not requirements for other reviewers or providers.

Pass `--review-provider codex` to the [GitHub watcher](github-monitoring.md). It reads review state but never posts comments or triggers reviews. For authorized review requests, verify the [provider's current trigger](https://learn.chatgpt.com/docs/third-party/github#request-a-codex-review); post `@codex review` only when none is queued/completed for the current head.

Selection requires an open PR and qualifying review evidence for every monitored target, including discovered submodules. A missing PR or absent review evidence/request blocks immediately (exit2); an active request remains pending until current-SHA evidence arrives. The watcher never submits that request. If targets have different review requirements, use CI-only monitoring plus native review checks for required targets; preserve the complete selected inventory.

Require a completed reviewer-authored review/run or documented no-findings signal explicitly bound to the exact current SHA and relevant request. A timestamp-correlated thumbs-up reaction has no commit identity. Silence, reactions, old reviews and an empty findings list are insufficient. Every push needs fresh current-commit evidence; do not spam repeated requests.

The watcher recognizes this provider's actor, request and response formats. Unsupported or missing evidence stays unverified; use native read-only inspection to reconcile it. Keep all other required reviews and human approvals in the coordinator's final readiness check.
