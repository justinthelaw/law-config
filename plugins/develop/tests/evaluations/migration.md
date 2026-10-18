# Mixed-version migration and recovery

Extends the preserved N connection scenario in [consumer acceptance](../scenarios.md#upgrade-and-consumer-acceptance).
The existing [runtime contract owner](../../skills/upgrade/references/runtime-contracts.md)
already covers consumed semantics, interrupted runs and evidence layers; no new
deployment policy is needed. Apply these cases when the selected system has
overlapping protocol versions or persistent data conversion. The stateless
formatter control requires no migration machinery.

| Public fixture | Evaluator-only criteria | Purpose |
| --- | --- | --- |
| [migration-recovery](fixtures/migration-recovery.json) | [grader](graders/migration-recovery.json) | Two live SQLite connections, row/checkpoint restart, lossy conversion and snapshot restoration |
| [migration-not-applicable](fixtures/migration-not-applicable.json) | [grader](graders/migration-not-applicable.json) | Review a stateless upgrade without inventing migration work |

Use the [shared fixture contract](README.md) for materialization, isolation and
results. Give the agent only its prompt, declared inputs and selected plugin
instructions. Keep this page, graders, reference implementation and tests out of
its accessible context. Record every attempt and fixture digest; do not replace
failed attempts with repaired outcomes.

The public exercise defines a bounded SQLite API and data schema. An already-open
N connection retains original decimal text; N+1 sees integer minor units. Both
write while backfill runs. A controlled exception between row update and
checkpoint must roll back both; closing and reopening the file checks durable
restart. After draining both clients and freezing writes, a separate snapshot
permits recovery of text such as `001.20` that cannot be reconstructed from `120`.
There are no post-snapshot writes or replay requirements in this toy.

The evaluator-only [reference store](migration_store.py) and
[tests](../test_migration_recovery.py) check executable behaviors and bounded
seeded defects: incompatible wire output, stale backfill overwriting a writer,
negative fallback conversion, split write commits, rejected writes corrupting
minor units, early or late interruption, deferred commits, premature checkpoints,
batched steps, mutation after completion, partial finalization, final-phase N
writes, lost finalized rows, retained raw archives, lossy reconstruction and
snapshot mutation or partial restoration. Benign controls accept different
exception messages, multiple write statements within one transaction and
optimistic backfill with compare-and-retry. Restore checks
compare all records, migration metadata and schema with the snapshot, then read
both protocols and resume completed migration. Rejected writes and retired reads
must preserve records, migration metadata and schema. Supported-write probes
require every unaddressed record to remain unchanged. The tests also
reject finalization with pending checkpoint work even when all minor values are
populated or one step has completed. Finalized IDs and values must all survive;
the main database's logical tables must have no remaining `raw` column or exact
original text values, even under renamed columns. The latter check uses the
fixture's known spellings in scalar text cells; it does not establish forensic
erasure or detect encoded, fragmented or otherwise transformed copies. Unrelated
metadata remains permitted, as a benign control verifies.
Run from the plugin directory:

```bash
python -m unittest discover -s tests -p test_migration_recovery.py -v
```

These tests validate the synthetic reference and the sensitivity of its checks.
They are **not agent runs** or a universal candidate acceptance harness. To use
the state assertions for a candidate, substitute its `Store` and `Interrupted`
exports in an isolated evaluator copy and adapt the observation probes first.
The overlapping-write probe targets the reference's backfill UPDATE. Temporary
row and checkpoint triggers observe interruption ordering on the exposed
connection; restart checks reopen immediately after a committed step and inspect
each remaining step and unchanged completion.

The write-atomicity probe samples a second connection only at statements traced
on `writer.db`. An implementation that commits through auxiliary connections can
pass those samples despite a partial write. Before drawing a candidate verdict,
the controller must identify and instrument every write connection and adapt
the controlled interleavings to that implementation. Missing instrumentation is
**unverified coverage**, never evidence of atomicity. No general connection
tracing framework or exhaustive concurrency schedule is supplied here. Keep
seeded-defect tests attributed to the reference suite and grade observed agent
decisions separately with the linked criteria. A passing reference run cannot
supply a candidate or native-host verdict.

The injected interruption models a transaction failure at one controlled point;
it does not simulate OS crashes, power loss, concurrent schema writers or actual
deployment cutovers. Snapshot recovery assumes drained clients and no writes
after the snapshot. Product-specific acceptance remains with its existing owner.
Do not infer deployment readiness, a production rollback guarantee or behavioral
improvement from these offline checks.
