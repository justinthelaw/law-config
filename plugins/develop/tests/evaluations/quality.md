# Bounded test-quality controls

## Bounded shipping threshold

These offline controls test whether passing tests protect a specified boundary.
They do not measure agent improvement or prescribe a mutation-score quota.
Use the shared [fixture contract](contract.json) and materializer in
[evaluation.py](../../scripts/evaluation.py); give fresh agents only the prompt
and materialized inputs. Keep graders, control variants and this protocol outside
the agent's readable workspace. Filesystem separation alone is not a sandbox.

| Fixture | Task | Evaluator expectation |
| --- | --- | --- |
| [Weak tests](fixtures/quality-weak-tests.json) | Repair tests for a documented shipping threshold. | Diagnose self-comparison, empty-input truth and an assertion after return; assert executed public behavior. |
| [Sound control](fixtures/quality-sound-control.json) | Review already adequate tests for the same boundary. | Demonstrate protection without unnecessary edits or new process. |

Shipping is 500 cents below a subtotal of 5000 cents, and free at or above that
threshold. Negative subtotals raise `ValueError`. Evaluator-owned variants in
[test_quality_controls.py](../test_quality_controls.py) change `>=` to `>` for
one defect, or express the same behavior using early returns for the benign
refactor. The control is intentionally bounded; it does not establish general
test-suite adequacy.

Run each suite unchanged against the reference, defect and benign variants:

| Suite | Reference | Defect | Benign | Quality verdict |
| --- | --- | --- | --- | --- |
| Tautological, vacuous or unreachable assertion | Pass | Pass | Pass | Reject: misses the selected defect |
| Sound public-behavior assertions | Pass | Assertion failure | Pass | Accept for this boundary |
| Always failing | Fail | Fail | Fail | Reject: no specificity |
| Empty, skipped-only, expected-failure-only or harness error | Incomplete | Incomplete or error | Incomplete | No coverage claim |

The packaged executable checks run trusted fixture code in fresh Python modules;
they are not an arbitrary-submission runner. For actual agent submissions, inspect
the submitted code and run it only in an appropriately isolated evaluation host.
Preserve production files, run counts, skips, assertion failures and errors for
all three variants. An exception in the harness is not defect detection. An
ordinary exception while compiling or loading a module is recorded as an error
with zero executed tests; evaluation continues with the remaining variants. An
unrelated skip or expected failure does not erase an executed assertion that
detects the defect and passes both controls. Skipped-only and expected-failure-only
runs remain incomplete; unexpected successes are not passing control evidence.
The helper temporarily registers the source modules with file/import metadata
and restores the import table after each run. Those filenames identify the
in-memory source; the helper does not materialize source files on disk. Standard
`TestCase` assertion methods are temporarily wrapped for direct, inherited and
`super()` calls, respecting the case's configured `failureException`. Runs must
remain sequential within a process because those wrappers modify shared classes.
The helper correlates standard `unittest` assertion call sites and Python
`assert` statements in the submitted source across variants, within the same test
method. Calls in separate code objects, including same-line lambdas, remain
distinct; their identity is correlated only across the unchanged submitted source.
A reported defect failure must come from an assertion site that passed on
both controls; an unrelated assertion cannot substitute for a skipped detecting
site. An assertion before an in-body, subtest, teardown or cleanup skip remains
evidence; constructing an
assertion context without executing it does not. Custom assertion APIs and
assertions in external helper modules are not verified. Matching sites does not
establish matching inputs for every loop iteration or helper invocation. These
execution events do not prove relevance or general coverage; the bounded defect
and benign comparisons still determine the verdict.
Use the separate matching [weak-test grader](graders/quality-weak-tests.json) or
[sound-control grader](graders/quality-sound-control.json) for diagnosis, scope
and unnecessary-change criteria; execution alone cannot judge those criteria.

From the repository root:

```bash
python -m unittest discover -s plugins/develop/tests -p test_quality_controls.py -v
```

For live trials, record every planned attempt using the shared result contract,
including exact source/fixture revisions, host/model/effort, isolation evidence
and missing/blocked attempts. Preserve logs outside tracked source. Keep agent
time/token cost separate from application runtime measurements.

## Guidance decision

The existing [implementation owner](../../skills/iterate/references/implementation.md)
already requires a relevant failing regression and public-behavior assertions;
[validation evidence](../../skills/iterate/references/validation.md) already
rejects empty or skipped-only success. The controls demonstrate a test-adequacy
trap, not a measured failure of those instructions. Leave shared guidance
unchanged unless a baseline agent trial demonstrates a specific gap. If a gap is
observed, amend that owner narrowly for the demonstrated risk and retest both
fixtures; do not add a universal quota or duplicate a testing policy here.
