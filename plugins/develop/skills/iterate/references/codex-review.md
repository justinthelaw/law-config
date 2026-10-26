# Optional Codex review adapter

Select `--review-provider codex` only when Codex review is requested or required on GitHub. [Read-only watcher](github-monitoring.md)

- **Request.** When authorized, post `@codex review` only if the current head has no queued or completed review. [Verify the provider's current trigger](https://learn.chatgpt.com/docs/third-party/github#request-a-codex-review).
- **Coverage.** Every target, including submodules, needs an open PR and review evidence or an active request. Otherwise the watcher exits `2`. For mixed requirements, monitor CI across all targets and check reviews natively where required.
- **Completion.** A positive review, run or no-findings receipt must identify the exact head and postdate both the latest trigger and any undismissed change request. Each push needs fresh evidence. Silence, reactions, older reviews and empty findings cannot establish completion.
- **Receipts.** Require the Codex bot's complete, unedited v1 no-findings template, including its help footer. Resolve ten-character commit IDs through GitHub and match the full head SHA. Outstanding feedback from any revision blocks a receipt if it arrived at or after the latest trigger. Unresolved findings always block, as do change requests until dismissed or superseded by approval.
- **Readiness.** Reconcile unknown formats or missing evidence with native read-only checks. Verify the remaining required reviews and human approvals.
