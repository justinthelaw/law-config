# Publish selected repository work

Use the [shared contract](../../develop/references/contract.md) for authorization and signing policy. Keep this mode scoped to selected checkouts and initialized recursive submodules. Commit/push authority does not imply issue edits, review-thread resolution, merging or history replacement.

## Inventory and preserve

For GitHub checkouts, resolve `ITERATE_SKILL_DIR` to the installed `iterate/SKILL.md` parent and `ITERATE_REPO` to the absolute selected Git root. Do not assume the current directory is the plugin or use a source-checkout path in an installed invocation.

```bash
python3 "$ITERATE_SKILL_DIR/scripts/repository_inventory.py" \
  --repo "$ITERATE_REPO"
```

Repeat `--repo` for explicitly selected independent roots. Pass `--github-host <verified-host>` for each explicitly selected GitHub Enterprise host; do not use that flag to reinterpret another provider. `--include-siblings` is allowed only when every included sibling is selected. Consume the compact deepest-first JSON inventory; request a bounded file diff with `--patch --path <repository-relative-filename>`. Use the exact filename relative to each explicit `--repo` checkout, or the current checkout when no root is specified. Implicit children and siblings supply metadata only for filtered requests. Name a child or sibling with `--repo` to read its patch. Empty, directory and overlapping parent/child selectors are rejected. Request overlapping filenames separately. Omitting `--path` requests the broad patch. Filesystem name normalization or unverifiable identity can withhold an affected file's unstaged patch; `patch_withheld.unstaged` gives the reason, while staged patches, safe siblings and change counts remain available. Refresh inventory after relevant Git state changes, not on every progress update.

The packaged helpers are GitHub adapters. For GitLab, Bitbucket and Hugging Face, use native Git/provider tools to gather the same inventory and publication evidence. Keep provider identities and selected scope intact; an unsupported helper does not authorize rerouting or skipping validation.

Read applicable `AGENTS.md` files and identify branch, remote/upstream, full local/remote SHAs, initialized submodules, index and worktree changes. Derive identities from evidence; never assume `origin`, `main`, repository basenames or matching directory names. Fetch selected upstreams when authorized to refresh their ahead/behind state; inventory itself does not prove freshness.

Missing or partial tracking blocks the helpers, even with one remote. For a new branch, gather inventory with native Git and verify the approved remote/ref from task and repository evidence. Follow the commit and publish steps below, using an explicit refspec and `--set-upstream` on the authorized first push; rerun the helpers once tracking exists. Never infer the destination from the sole remote or local branch name.

Protect unrelated staged/unstaged/untracked work, stashes, unpublished commits and other worktrees. An ambiguous target, detached head, conflict, unexplained gitlink mismatch or unavailable provider access blocks that target. Do not initialize an unselected submodule or include its work implicitly. An intended child commit may temporarily differ from its parent's gitlink until the parent records it.

## Choose the delivery route

Follow the selected repository's contribution and branch rules. If authorized delivery leaves the route open, use a permitted work branch and a pull request. Use the host's change-request tool or authenticated CLI. Hold a direct push to a restricted destination unless the user explicitly names that branch and bypass, repository policy allows it, and the provider permits this actor to use it. An account's ability to bypass does not establish user direction. Merge requires separate authority.

Before **every push**, including creation of a work branch, confirm the destination repository and full ref, the actor, the outgoing range and the effective rules. On GitHub inspect [classic protection](https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection) and [active rulesets for the exact branch name](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch). For a new ref, include applicable classic branch-name patterns. On another host use its equivalent. A failed or inaccessible read leaves the rule unknown. Use a verified permitted PR route or hold the affected push.

After an uncertain PR create, look up the result before another write. Use the [provider's list and get operations](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests). Match the head repository, branch and full SHA and the base repository and branch. Reuse the matching PR. If it closed or moved, the search is incomplete, or identity conflicts, hold the create for reconciliation. Retry only after a complete read confirms the original write failed and the destination still matches.

## Commit and publish

1. Group selected changes by behavior, keeping tests with implementation. Run required validation and inspect the complete cached diff before each commit. Stage explicit paths only. If existing staged paths or partially staged hunks have ambiguous/unrelated ownership, stop that publication without resetting, stashing or restaging the user's index.
2. Follow repository commit-message and attribution conventions; use concise Conventional Commits where applicable. Process child repositories deepest-first. Verify each required child commit is available at its approved remote before publishing a parent gitlink that references it.
3. Apply the shared nonblocking signing policy and thread preference. After a signing-only failure, confirm `HEAD` did not advance and the index is still the intended change before retrying with command-scoped `git -c commit.gpgsign=false commit --no-gpg-sign`. Reconcile hook side effects or other failures first; do not treat identity, hook, permission or server-policy failures as signing failures.
4. Inspect the resulting commit and record its full SHA and actual signing status. Verify signatures when usable verification is available; report unavailable verification accurately. Existing unsigned outgoing commits or a missing verification key alone do not block delivery. Inspect the entire outgoing range for scope before publishing it.
5. Apply the [delivery-route preflight](#choose-the-delivery-route) immediately before pushing normally to the verified remote/ref, deepest children first and owning roots last. Never bypass hooks/security controls, alter protection or publish to an unrequested destination. A server-enforced signature requirement is an external constraint, not permission to weaken it.
6. Read back the actual ref with `git ls-remote --exit-code <remote> refs/heads/<branch>` and require one full SHA equal to local `HEAD`. Refresh the selected tracking ref and confirm equality. A successful command alone does not prove the intended ref was published.
7. Monitor expected CI and configured/requested reviews against that exact published revision. A code repair runs implementation validation, then repeats scoped publication and fresh monitoring. Retain the selected scope through every repair.

## Branch updates and history replacement

Reuse existing authorization that identifies the intended branch operation; request only authority missing from the shared contract. Revalidate the actual target immediately before acting. Branch updates require a clean affected index/worktree; never stash or reset protected work to achieve that state.

- For a behind-only branch, use an authorized `git merge --ff-only <upstream>`; do not create an incidental merge commit.
- For an authorized rebase, inspect the replaced commits and refreshed target SHA first. Do not rebase default/protected branches or discard collaborator work. Apply the same nonblocking signing policy to rewritten commits; stop on conflicts or a changed upstream and reconcile before continuing.
- For explicitly authorized published-history replacement, require a verified selected same-repository PR head, matching upstream ref and fresh full remote SHA. Inspect the replaced range and new head. Use only the exact-ref lease below; a failed lease requires renewed inspection, not a stronger push.

```bash
git push \
  --force-with-lease=refs/heads/"$ITERATE_BRANCH":"$ITERATE_EXPECTED_SHA" \
  "$ITERATE_REMOTE" HEAD:refs/heads/"$ITERATE_BRANCH"
```

Derive these variables from the verified target, not example names. Never use plain force, an unqualified lease, another/default/protected ref or a shortened expected SHA. Re-read remote/tracking/local SHAs and restart current-commit validation after an approved update.

## Requested deployment or operations handoff

Readiness and publication do not establish deployment. When deployment or an operational handoff is requested, use the selected owner's existing mechanism and [runtime contracts](../../upgrade/references/runtime-contracts.md); identify the candidate and target environment, required authority, acceptance evidence, rollback/recovery owner and remaining human gates. Carry unknown identities or unavailable checks explicitly. Only execute operational changes already authorized for that target; do not invent a deployment framework or treat merge/push authority as production authority.

## Completion

Selected changes must be accounted for in verified commits and remote refs, with expected checks and requested reviews complete for the current revision. No intended repair may remain uncommitted. Report preserved unrelated dirty work separately; do not require its removal. An unresolved fixed review thread needing external authorization is a reported blocker, not a reason to republish the same fix.
