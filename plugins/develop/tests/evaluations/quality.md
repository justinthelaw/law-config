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
| Empty, skipped-only or harness error | Incomplete | Incomplete or error | Incomplete | No coverage claim |

The packaged executable checks run trusted fixture code in fresh Python modules;
they are not an arbitrary-submission runner. For actual agent submissions, inspect
the submitted code and run it only in an appropriately isolated evaluation host.
Preserve production files, run counts, skips, assertion failures and errors for
all three variants. An exception in the harness is not defect detection. An unrelated skipped test
does not erase an executed assertion that detects the defect and passes both
controls; skipped-only runs remain incomplete.
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
