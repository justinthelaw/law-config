# Optional issue tracking

Use only when the user requests issue tracking or the selected repository requires it. Apply the [shared authorization contract](../../develop/references/contract.md). Preparing a proposal is not authority to create, edit, link, comment on or close an issue. Reuse authorization already granted for the specific scope; do not ask again merely because this reference is loaded.

The following mechanics are for GitHub. Use equivalent native identities/readback on another provider, preserving that provider's ownership and linking semantics.

1. Select one owning repository and verified branch. Do not create tracking issues automatically for recursive submodules. If a PR exists, inspect its number, same-repository status, head ref/SHA and `closingIssuesReferences`; do not associate an ambiguous or external-fork PR.
2. Reuse an unambiguous existing linked issue. Otherwise derive a stable `develop-iterate-tracking-<sha256>` marker from canonical provider/repository identity plus the exact remote upstream branch. Preserve that marker before/after PR creation and across head changes. If continuing legacy delivery, search for and reuse its existing `git-commit-push-fix-loop-tracking-<sha256>` marker rather than creating a duplicate.
3. Search all issue states for the exact marker with complete results, and verify the marker in returned bodies. Multiple matches, truncated/unavailable results or a closed match require reconciliation; none establishes permission to create another issue.
4. Only when discovery proves no matching issue exists, prepare a concise sanitized title/body containing the marker. With creation authority, create it using the provider tool's structured body or `gh issue create --repo <repository> --title <title> --body-file <file>`. Save only the requested content; exclude credentials, logs and conversation packets.
5. Edit only for material scope/status changes and preserve unrelated body content. Link a PR with `Closes #<issue-number>` only when authorized, preserving its existing description. Do not append duplicate closing references.
6. Revalidate repository, issue, PR, branch and full head immediately before each write. Read back the resulting issue body and `closingIssuesReferences`; require the exact intended issue and content.

The CI/review watcher remains read-only. It cannot create/update tracking issues or grant authority to close, label, assign, comment, merge or resolve review threads.
