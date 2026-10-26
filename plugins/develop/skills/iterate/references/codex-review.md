# Optional Codex review adapter

Select `--review-provider codex` only when Codex review is requested or required on GitHub. [Read-only watcher](github-monitoring.md)

- **Request.** When authorized, post `@codex review` only if the current head has no queued or completed review. [Verify the provider's current trigger](https://learn.chatgpt.com/docs/third-party/github#request-a-codex-review).
- **Coverage.** Every target, including submodules, needs an open PR and review evidence or an active request. Otherwise the watcher exits `2`. For mixed requirements, monitor CI across all targets and check reviews natively where required.
- **Completion.** An active request stays pending until a completed Codex review, run or no-findings receipt identifies the exact head and covers the latest trigger. Each push needs fresh evidence. Silence, reactions, older reviews and empty findings cannot establish completion.
- **Receipts.** Accept only the Codex bot's unedited v1 no-findings template. Resolve its ten-character commit ID through GitHub and compare the full SHA with the monitored head. Unresolved findings and standing adverse reviews take precedence.
- **Readiness.** Reconcile unknown formats or missing evidence with native read-only checks. Verify the remaining required reviews and human approvals.
