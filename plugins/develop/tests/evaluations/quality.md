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

Run each suite unchanged against the reference, defect and benign variants. For
the supported observation paths described below:

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
invalid loader return or an exception escaping suite loading, tracking or execution
is also an error; already completed test outcomes are retained. A module-level
`SkipTest` produces one wholly skipped entry rather than a harness error. Process
interruptions such as `KeyboardInterrupt` and `SystemExit` are not swallowed. An
unrelated skip or expected failure does not erase an executed assertion that
detects the defect and passes both controls. Skipped-only and expected-failure-only
runs remain incomplete; unexpected successes are not passing control evidence.
The helper temporarily registers the source modules with file/import metadata,
including `test_shipping` as an alias for the test module, and restores the import
table after each run. Those filenames identify the
in-memory source; the helper does not materialize source files on disk. Standard
`TestCase` assertion methods and standard synchronous/asynchronous body invocation
methods are temporarily wrapped, respecting the case's configured `failureException`
and observing direct, inherited and `super()` assertion calls. Runs must
remain sequential within a process because those wrappers modify shared classes.
Assertion failure metadata is stored separately from the exception, without
requiring custom failure exceptions to accept evaluator attributes or be hashable.
The result owns observation state for its active suite entry; submitted test cases
receive no evaluator metadata fields. Existing `_quality_*` names on those cases
are neither reserved nor used for correlation or skip accounting.
Body tracking applies to local `TestCase` instances in the loaded suite, including
local classes returned by `load_tests` in nested standard suites. Locality comes
from membership in the compiled submitted source, so changing `__module__` does
not affect it. The standard invocation receives a wrapper around the resolved
callable; submitted instances and their methods are not modified. This preserves
static/class method binding, inherited methods, coroutine bodies and unittest
skip/expected-failure markers. Bodies changed after suite registration remain
unverified, as do custom invocation paths that bypass the standard methods.
Standard `FunctionTestCase` leaves wrapping functions defined in the submitted
module are tracked around the function body, separately from setup and teardown.
External functions and custom callable objects in those leaves remain unverified.
The helper correlates standard `unittest` assertion call sites and Python
`assert` statements in the submitted source across variants, within the same test
method or test function. Calls in separate code objects, including same-line
lambdas, remain distinct; their identity is correlated only across the unchanged
submitted source.
The standard assertion callable is part of each call's identity, including context
assertions, so selecting different assertions at one call instruction does not
create matching evidence. Aliases of the same callable share its identity.
Test identities combine the loaded suite entry's position and body identity;
overridden display IDs do not participate. Repeated entries using the same case
object remain distinct, including their skip counts. Correlation assumes unchanged
suite structure and does not establish equivalent inputs for parameterized cases.
A reported defect failure must come from an assertion site that passed on
both controls; an unrelated assertion cannot substitute for a skipped detecting
site. A body assertion before an in-body, subtest, teardown or cleanup skip remains
evidence; constructing an assertion context without executing it does not.
Assertions executed only in
`setUp`, `tearDown` or cleanup callbacks are outside body correlation and cannot
certify a skipped body. Saved context copies cannot extend body tracking after
that body invocation ends, even if the same test instance runs again.
Assertion observations in worker threads without the
active body context are also not correlated; the helper does not propagate that
context or verify concurrent test execution. These paths can produce real
assertion failures while the bounded gate returns no verified sensitivity.
An unverified result for these paths does not demonstrate weak tests or failure
of the grader's sensitivity criterion; inspect the preserved variant outcomes
separately.
Custom assertion APIs and assertions in external helper modules are not verified.
Standard assertion calls require a direct submitted caller; an external helper's
assertions cannot borrow the submitted caller's site. Nested standard unittest
assertions are accounted for by their outer observed call.
Matching sites does not establish matching inputs for every loop iteration or
helper invocation. These execution events do not prove relevance or general
coverage; the bounded defect
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
