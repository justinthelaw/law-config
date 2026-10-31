# Staged file size

When requested or required, run the read-only [checker](../scripts/check_staged_file_size.py) against the selected Git index:

```sh
python3 "$ITERATE_SKILL_DIR/scripts/check_staged_file_size.py" --repo "$ITERATE_REPO"
```

The default limit is 20,000 bytes. A positive `--max-bytes` overrides the profile and default. Omit `--repo` only to intentionally use the caller's current Git/index context. Exit 0 passes, 1 means a violation or inspection error, and 2 signals invalid arguments. Use `--help` for options.

Select an optional reviewed working-tree JSON file with `--profile path`. Use canonical repo-relative paths, regular files and no symlinks. For example:

```json
{"schema_version": 1, "max_bytes": 20000, "exclude_paths": ["private.json"], "exclude_prefixes": ["generated"]}
```

Exclusions apply before content reads. The checker inspects staged regular files using cached attributes and a bounded prefix to identify generated or binary content. Review oversized authored changes at their owner. To bind a repository hook, preserve the existing chain, pin a reviewed copy and test both passing and violating staged files. A pre-commit binding requires `pass_filenames: false` and `always_run: true`.
