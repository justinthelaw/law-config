# GitHub CI and review adapter

For selected GitHub roots, the read-only watcher is optional. Resolve `ITERATE_SKILL_DIR` to this installed skill and pass each selected checkout explicitly:

```sh
python3 "$ITERATE_SKILL_DIR/scripts/watch_pipelines.py" --repo "$ITERATE_REPO"
```

Repeat `--repo` for independent roots; use `--github-host` only for a verified GitHub Enterprise host. The default monitors CI; select `--review-provider codex` only when requested or required. Other providers need native tools. The default budget is 30 minutes; use `--timeout` for another finite limit and retain the emitted deadline with `--deadline` on restart. `--timeout 0` selects indefinite monitoring. `--once` is a snapshot.

Exit 0 reports observed checks passed; reconcile additional repository requirements and actual current head. Exit 1 reports failure, 2 a blocker, and 3 pending in snapshot mode. Missing checks, access or changed revisions prevent a readiness claim. Reconcile required reviews and unresolved findings separately; repair or external writes require authority. New commits invalidate affected evidence. Do not create a recurring schedule unless requested.
