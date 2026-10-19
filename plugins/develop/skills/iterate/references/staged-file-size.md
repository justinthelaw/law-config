# Explicit staged-file size check

Use only when requested or required by the selected repository. The bundled
[checker](../scripts/check_staged_file_size.py) is an offline, read-only Python
3.10+ and Git utility. It does not edit, stage, install, register hooks, discover
profiles or call other plugins. A successful check is a size-policy result, not
a security scan or proof that source is well structured.

This Git-index helper is separate from the bundled [Codex context guard](../../../docs/context-guard.md), which checks tool inputs/results without Git or staging. Their default 20,000-byte thresholds serve different checks; invoking this helper does not activate or configure the native hook.

Resolve `ITERATE_SKILL_DIR` to the selected Iterate skill's directory and
`ITERATE_REPO` to the selected checkout's absolute root. Invoke from any working
directory:

```sh
python3 "$ITERATE_SKILL_DIR/scripts/check_staged_file_size.py" \
  --repo "$ITERATE_REPO"
```

## Stable interface

```text
python check_staged_file_size.py [--repo DIR] [--profile REPO_RELATIVE_JSON] [--max-bytes N]
```

- Without `--repo`, use the caller's current Git context, including inherited
  repository and index selectors. No broader repository discovery occurs.
- With `--repo`, inherited worktree, Git-directory and common-directory selectors
  must match the selected checkout or the check fails before loading the profile.
  Temporary hook indexes inside that checkout's Git directory remain supported;
  an inherited `GIT_INDEX_FILE` outside it is rejected. This also handles the
  separate Git directory of a linked worktree. An external temporary index needs
  an intentional current-context invocation without `--repo`.
- The default limit is **20,000 bytes**. Equality passes; a larger authored file
  fails. Bytes divided by four gives only an approximate token estimate; this is
  not a tokenizer or a host context-window limit.
- `--max-bytes` must be a positive integer and overrides the profile's optional
  `max_bytes`, which overrides the default.
- Exit `0` means the check passed, `1` means oversized files or an inspection or
  profile error, and `2` means invalid command-line usage. Treat every nonzero
  exit as failure. Reports escape unusual filenames and show at most ten files.

Candidates are staged additions, copies, modifications and type changes from
Git's index, with regular modes `100644` or `100755`. Deletions, symbolic links
and gitlinks are ignored; an unmerged index fails closed. Renames are inspected
as deletion/addition pairs. Unstaged edits to candidate files do not affect the
result. Object replacements and lazy fetches are disabled for inspection;
missing objects and Git failures fail closed.

## Explicit repository profile

This optional configuration is the intentional **working-tree read** exception.
It must be explicitly selected; a similarly named file has no effect by itself.
The helper reads at most 64 KiB plus one overflow-detection byte from a regular
UTF-8 JSON file inside the selected checkout, rejecting symlink path components.
The file need not be staged; review its current contents before relying on it.
These checks do not isolate the checkout from concurrent filesystem changes.

```json
{
  "schema_version": 1,
  "max_bytes": 20000,
  "exclude_paths": ["docs/generated-index.md"],
  "exclude_prefixes": ["private-state"]
}
```

Only `schema_version` is required. Unknown or duplicate fields, unsupported
versions, wrong types and malformed JSON fail closed. Exclusions are additive:
`exclude_paths` matches exact paths; `exclude_prefixes` matches the named path
and descendants at component boundaries (`private-state/`, not
`private-state-old/`). Use canonical repository-relative POSIX paths without
leading/trailing slashes, `.` or `..` components, backslashes, colons or NULs.
The same path rules apply to `--profile`.

Profile and built-in path exclusions are applied before blob size or content
reads. Each repository owns its protected paths and reviewed policy exceptions;
do not discover another repository's configuration or exempt authored content
merely to make a failing check pass.

## Classification and limits

The checker excludes common generated directories, lockfiles, binary suffixes,
generated filename patterns and private names such as `.env`, `.env.*`, `auth.json`,
`credentials.json`, key files and registry credentials. The exact lists live in
the helper; they are heuristics, not exhaustive protection for private data.
Supply additional protected paths explicitly before running it.

For oversized candidates, `git check-attr --cached` evaluates
`linguist-generated` and `linguist-vendored`; `set` or `true` excludes the file.
This uses indexed `.gitattributes` rather than dirty working-tree copies, but
Git's applicable info/global/system attribute sources still participate. The
result is therefore not determined solely by the index. Keep those settings
under the repository's existing trust policy.

Remaining candidates receive a bounded probe of the first
`min(8192, staged_size)` bytes. A NUL or recognized generated-comment header in
that prefix excludes the file. Binary bytes or generated markers beyond that
prefix are not detected. The helper reads no complete oversized blob into
Python memory, but Git may still decompress objects internally. Size limits
and exclusions are policy aids, not resource or security guarantees.

On failure, use [focused search](documentation.md) before reading a large
document or corpus. For code, split cohesive responsibilities and update callers
with their checks through [bounded refactoring](refactoring.md). Do not remove
useful comments, shave whitespace or fragment documents merely to satisfy a
byte limit. Mark only genuinely generated or vendored content through reviewed
attributes. The helper makes no changes; restaging remains an explicit action.

## Inert repository binding examples

The examples below are documentation only. Shipping or invoking Develop does not
activate them. Adopting a repository binding is a separate authorized change:
inspect existing hook owners and security checks, preserve their chain, and bind
the checker once. Do not change global `core.hooksPath`, overwrite a hook or
install a framework just to use this helper.

For a standalone repository binding, keep a reviewed copy at an owner-chosen
path such as `tools/check_staged_file_size.py`, with its license/provenance header,
the package's [Apache-2.0 license](../../../LICENSE), and a recorded source
version/hash. Keep the declarative profile in that
repository. This copy runs with Python and Git alone; never locate it through
an installed plugin cache. Updating the copy is an explicit source change.

An existing pre-commit configuration can incorporate this local entry after
choosing those paths and an available Python 3.10+ interpreter:

```yaml
repos:
  - repo: local
    hooks:
      - id: staged-authored-size
        name: Staged authored file size
        entry: python tools/check_staged_file_size.py --profile .staged-file-size.json
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
```

`pass_filenames: false` matters: the helper inspects the index itself. Omit
`--profile` when no explicit profile is needed. Do not create a second binding
when an existing hook already dispatches this check.

For a repository-owned POSIX Git pre-commit hook, integrate the following into
its existing dispatch chain instead of replacing that hook:

```sh
repo=$(git rev-parse --show-toplevel) || exit 1
python3 "$repo/tools/check_staged_file_size.py" \
  --repo "$repo" --profile .staged-file-size.json || exit $?
```

Use the owner's native launcher on other platforms. Validate the adopted
binding in an isolated checkout with a staged violation and a passing case;
verify existing checks still run. These examples neither install that binding
nor certify its activation.
