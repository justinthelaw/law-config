# Offline behavioral evaluation contract

These fixtures extend [fresh-context scenarios](../scenarios.md). They test
contract plumbing and supply controlled tasks; passing offline checks does not
establish behavioral gains, native activation, publication or deployment.

Protocols cover [paired comparison](comparison.md), [native Codex activation](native-hosts.md),
[communication](communication.md), [test quality](quality.md),
[architecture choices](architecture.md) and [migration recovery](migration.md).
Each separates offline calibration from actual agent and native-host evidence.

## Files and API

- [contract.json](contract.json) defines JSON Schema `$defs.fixture` and
  `$defs.result`. The standard-library [helper](../../scripts/evaluation.py)
  validates this fixed subset plus path, ledger and evidence constraints.
- `fixtures/*.json` contain only public prompts and explicit text input lists.
  IDs are stable; increment `revision` when changing a fixture. `scenario_ref`
  identifies the existing scenario by prompt, avoiding a duplicate policy owner.
- `graders/*.json` contain evaluator-owned criteria and required evidence, linked
  by fixture ID/revision. They are never materialized for the agent.
- [synthetic.json](results/synthetic.json) is a constructed example, not a run.
  Keep actual trial manifests, logs and private observations outside the package.

Run from the plugin directory with Python 3.10+:

```bash
python scripts/evaluation.py fixture tests/evaluations/fixtures/scope-allowlist.json
python scripts/evaluation.py result tests/evaluations/results/synthetic.json
python scripts/evaluation.py materialize tests/evaluations/fixtures/no-op.json --destination /tmp/new-agent-root
python -m unittest discover -s tests -p test_evaluation.py
```

`validate_fixture(data)` and `validate_result(data)` return `None` or raise
`ValueError`. `load_json(path)` rejects duplicate keys and non-JSON constants.
`fixture_digest(data)` hashes sorted compact JSON encoded as UTF-8 with Unicode
preserved; it covers every fixture field. `materialize(data, destination)` creates
a previously absent directory under an existing parent and returns an input-path
to SHA256 map. File bytes are UTF-8 without newline translation. It copies only
declared inputs, never directories, grader files, commands or prompt metadata.
Supply `agent.prompt` separately through the host's supported task interface.
No command runner or network integration is included.

## Isolation and evidence

Run each attempt in a fresh non-forked host context at the selected model/effort.
The controller must exclusively own the existing destination parent during
materialization. The helper resolves trusted parent aliases, including macOS
`/tmp` and `/var`, after rejecting unresolved `..` traversal. The destination
itself must be absent and cannot be a symlink, including a dangling link. Unsafe
input paths and observed links at or inside the new root remain prohibited.
Parent ownership is the caller's obligation; these checks are not a sandbox
against concurrent filesystem changes. A failed write may leave a partial root;
use a new destination on retry. No existing files are overwritten.

**Separate files alone cannot certify hidden graders.** The tested agent must not
have filesystem, tool, retrieval or inherited-context access to the controller's
checkout, graders, expected results or previous attempts. Use real host isolation
and record its basis in `grader_isolation`; use `unverified` if that boundary has
not been established. Do not expose this README or the synthetic result to the
tested agent. Scope traps are public task inputs, distinct from private graders.
Include the selected plugin instructions through the supported host mechanism.

Native trials must independently record installation, discovery, actual
instruction consumption, available tools and task success. Installation or a
successful answer cannot establish consumption. Capture positive and negative
activation controls; unavailable hosts remain blocked, without installing clients.
Offline and synthetic results cannot certify native behavior even if their
functional/evaluator verdicts are `pass`.

## Result ledger

One manifest describes one exact source revision and host/model/effort selection.
Use a full Git SHA (40 or 64 lowercase hexadecimal characters); never `main` or a
moving tag. Identity patterns require the entire string under JSON Schema search
semantics, rejecting prefixes, suffixes and trailing line terminators. Record host
version and selection basis, including exposed controls,
inheritance or the reason identity is unavailable. Do not guess model identity.
Source, fixture and grader identities are separate: every planned attempt records
fixture ID, revision and canonical SHA256, plus required `grader_sha256`: the
64-character lowercase SHA256 of the exact grader file bytes. Keep this field in
the evaluator-owned result ledger, outside public fixtures and materialized
inputs. Check both digests against the supplied fixture and private grader before
a trial; structural validation cannot authenticate claimed data. Paired trials
must retain and compare grader hashes as well as fixture identities.
Repeated attempts with the same fixture ID/revision must have identical fixture
and grader hashes; conflicting identities invalidate the manifest.

Declare all planned attempt IDs before execution. Every ID must have exactly one
record: `completed`, `blocked` or `missing`. Append retries under new planned IDs;
never replace failed attempts. Missing means no attempt evidence was obtained;
it requires a reason, null costs, no observations and no application metrics.
Blocked attempts can retain partial observations/costs, but both assessments must
be `not_run`. A completed attempt requires at least one observation, assessment
evidence entry, application measurement or non-null agent cost measurement; a
reason alone is insufficient. Executed but ungraded attempts may retain both
`not_run` verdicts when this evidence exists. A completed attempt can fail;
completion is not success. Omitted or unplanned attempts invalidate the manifest
instead of silently dropping failures.

`functional` records task correctness; `evaluator` records the evaluator's checks.
Each uses `pass`, `fail` or `not_run` and an evidence list. Pass/fail requires
evidence. These are attributed observations, not independently authenticated
proof. Preserve evidence references and failures, including unavailable graders.

`observations` label actual user-visible output as `user`, tool calls/results as
`tool`, and worker/controller/reviewer logs as `helper`. Keep user updates separate
from hidden reasoning or helper logs; do not infer visible communication from a
helper's report. Evidence text may be a concise observation or a private artifact
reference; redact sensitive content before sharing.

`cost.wall_seconds`, `cost.tokens` and `cost.usd` measure the agent attempt. Unknown
measurements are `null`, never fabricated zeroes. Values are finite, nonnegative;
tokens are integers. `application_performance` holds separate named measurements
with explicit units. It must not be substituted for agent costs. Comparisons must
retain the complete ledger and disclose incompatible identities, incomplete
evidence and selection effects; this validator makes no comparison or gain claim.
