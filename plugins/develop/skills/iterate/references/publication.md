# Publish selected repository work

Publication requires authority for the selected targets. Inspect applicable instructions, repository/remote/ref identities, index, worktree and outgoing range; preserve unrelated changes and submodules. The optional GitHub inventory helper accepts explicit roots:

```sh
python3 "$ITERATE_SKILL_DIR/scripts/repository_inventory.py" --repo "$ITERATE_REPO"
```

Use native tools for other providers or when the helper cannot establish identity. Confirm destination, actor and effective branch rules before pushing; follow repository contribution rules. Stage explicit paths and inspect the staged diff. Process authorized submodules before parent gitlinks. Use the [nonblocking signing policy](../../develop/references/contract.md#nonblocking-commit-signing). Read back the remote ref and verify its full SHA. Reconcile an uncertain external write before retrying.

History replacement requires explicit authority, inspection of the replaced range and a fresh exact remote SHA; use an exact-ref `--force-with-lease`, never plain force. Commit or push authority does not imply merge, issue edits, thread resolution or deployment. Verify applicable checks and requested reviews on the current revision. For deployment handoff, identify target, candidate, acceptance evidence, recovery owner and missing authority; publication alone does not establish deployment.
