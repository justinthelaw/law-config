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
optimistic backfill with compare-and-retry. Seed checks require the declared core
columns, types and primary key, the supplied records with null minor values, and
exactly one initial `(0, 'mixed')` migration row; unrelated metadata tables and
indexes are permitted. Restore checks
compare all records, migration metadata and schema with the snapshot, then read
both protocols and resume completed migration. Rejected writes, unsupported and retired reads
and permitted finalized reads must preserve records, migration metadata and
schema. Final-phase behavior is checked after closing and reopening the candidate,
so retired reads and frozen writes must follow persisted state. Migration-step
results must be the booleans `True` and `False`, not merely truthy or falsy values.
For the finite fixtures, each successful step must transform only the next
existing ID and advance the checkpoint to that ID. A gapped, unsorted input
checks that progress does not assume consecutive IDs. Completion uses at most
the initial pending-row count plus one call, checking progress after each call
and unchanged state on completion; it does not rely on a timeout.
Supported-write probes require every unaddressed record to remain unchanged. The tests also
reject finalization with pending checkpoint work even when all minor values are
populated or one step has completed. Finalized IDs and values must all survive;
the main database's logical tables must have no remaining `raw` column.
Matching original spellings in other scalar text cells is collected as table,
column and value evidence. `assert_finalized_records` returns these matches;
the final-phase and recovery probes finish their independent checks before
raising `RetentionUnverified`. Definite violations of final-state, read/write or
restore behavior take precedence over uncertain retention. Recovery reopens the
restored database using the candidate implementation, and finalized state must
persist `migration.phase='final'`. Equality alone
cannot distinguish copied raw data from unrelated metadata such as a literal
`9.99`. This exception is distinct from `AssertionError`: a controller must report
unverified retention coverage and obtain provenance before assigning a candidate
pass or defect. It must not translate this outcome into either verdict.

Controls verify both outcomes: unrelated nonmatching metadata passes, while
coincident metadata and a renamed raw archive produce `RetentionUnverified`.
Combined controls verify that coincident metadata cannot hide definite defects,
and successful recovery finishes before retention uncertainty is reported.
The archive is a known defect because its seeded source explicitly copies
`records.raw`; the value scan does not establish that provenance. Passing these
calibration tests verifies their outcome classification, not candidate erasure.
The scan does not establish forensic erasure or detect encoded, fragmented or
otherwise transformed copies.
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
each remaining step and unchanged completion. An interrupted step may issue
multiple updates to its next row, but must not touch another row or the
checkpoint before the controlled exception.

Write and migration-step checks share a second-connection sampler at statements
traced on `writer.db`, plus an observation after the operation returns. Migration
samples read records and checkpoint together in one SQLite snapshot; only the
complete before or after state may be visible. A split row/checkpoint commit is
rejected even when interruption rollback works. Multiple statements in one
transaction and optimistic compare-and-retry remain accepted.
An implementation that commits through auxiliary connections can pass these
samples despite a partial transition. Before drawing a candidate verdict,
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
