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
snapshot mutation or partial restoration. Additional controls cover auxiliary
corruption during finalization, guards that apply to only one key, stale peer
read caches after completed backfill, float conversion and snapshots that omit
legal writes. Benign controls accept different
exception messages, multiple write statements within one transaction and
optimistic backfill with compare-and-retry. A refreshed peer read control remains
accepted. Precision probes use a legal protocol-1 write of `001.15` and a bounded
alternate seed of positive and negative `1.15` to check exact fallback and
backfill conversion separately; the public fixture is unchanged. Seed checks
require the declared core
columns, types and primary key, the supplied records with null minor values, and
exactly one initial `(0, 'mixed')` migration row; unrelated metadata tables and
indexes are permitted. Recovery performs legal writes from both protocols before
capturing the snapshot, retains an untouched original spelling and compares all
records, migration metadata and schema with the snapshot, then reads
both protocols and resumes completed migration. Rejected writes, unsupported and retired reads
and permitted finalized reads must preserve records, migration metadata and
schema. State snapshots also preserve the contents of permitted logical auxiliary
tables, including across interrupted/repeated work and snapshot restoration.
Successful steps and writes compare that full state while allowing only their
specified row/checkpoint changes; the overlap probe allows only the known
concurrent write and next-row migration. It repeats the controlled interleaving
at each seeded checkpoint, including the second and last backfill rows, so a
correct first transaction cannot mask stale reads in later steps. Final-phase
behavior is checked after closing and reopening the candidate,
so retired reads and frozen writes must follow persisted state for every seeded
key. Both final-phase and recovery checks compare full state before and after
finalization: only the records representation and migration phase may change
among existing data. Existing auxiliary contents and schema objects not owned by
`records` must survive. The preservation check excludes the rebuilt `records`
table and its owned indexes and triggers; it does not establish trigger retention.
New unrelated finalization metadata remains permitted subject to the retention checks. These finalization
comparisons cover returned state, not transient changes within `finalize()`.
Existing views also undergo `SELECT * ... LIMIT 0` before and after finalization:
preserving identical DDL must not leave a previously compilable view with missing
column or table dependencies. An unusable pre-finalization view raises
`ValueError` as invalid probe input before `finalize()` runs; it is not attributed
to finalization. Controls accept a preserved `id, minor` view and reject a
recreated `id, raw` view after `raw` removal through both final-phase and recovery
checks. This bounded compilation check does not execute view rows, establish
result semantics or validate arbitrary triggers and other SQL dependencies. It
adds no auxiliary-schema requirement to the public fixture; candidate-specific
schema semantics still require adapted probes.
Migration-step
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
The overlapping-write probe targets the reference's backfill UPDATE on each
seeded row; it does not enumerate all concurrent schedules. Temporary
row and checkpoint triggers observe interruption ordering on the exposed
connection; restart checks reopen immediately after a committed step and inspect
each remaining step and unchanged completion. An interrupted step may issue
multiple updates to its next row, but must not touch another row or the
checkpoint before the controlled exception.

The shared successful-write assertion samples writes during and after backfill.
After backfill, a candidate peer opened before the writes reads both protocols
before each write and checks both updated representations afterward. This API
check complements the sampler's direct database observations and detects stale
per-instance reads on the exercised path.
Write, normal migration-step and interrupted-step checks share a second-connection sampler at statements
traced on `writer.db`, plus an observation after the operation returns. Each
sample reads the covered records, migration metadata, schema and auxiliary
contents in one read transaction, released before the writer continues. The
overlap probe uses this same sampler with its controlled write callback and
permits that known write's intermediate state alongside the initial and final
states. Other sampled collateral changes fail even if restored before return;
distinguishable samples must progress from initial through the optional middle
state to one final state, without regression or switching final alternatives.
Identical states do not establish a phase change; uncommitted internal changes
remain accepted. Whole-state comparisons still run
after return. These observations do not establish absence of transient changes
between samples or on other scheduling paths. The seeded split row/checkpoint
commit on this observed path is rejected even when interruption rollback works.
Multiple statements in one transaction and optimistic compare-and-retry remain
accepted.

These samples check visible consistency at the observed points, not physical
transaction membership. This limit applies to every value-preserving or redundant
update: already-consistent backfill rows, same-value protocol writes and retries
after an overlapping write. Splitting an unchanged update from the remaining
commit can produce the same visible states as one atomic transaction. Value
sampling cannot distinguish them, and a legitimate concurrent write must not be
rejected as a partial migration. Before assigning a physical atomicity verdict,
inspect the candidate's transaction boundaries or obtain instrumentation that
establishes them. Without that evidence, physical atomicity is **unverified**,
even when the functional checks pass; the public atomic-write and commit-together
requirements remain unchanged.

Observation availability is also limited. Exclusive locking can block samples
across either atomic or split commits; `SQLITE_BUSY`/`SQLITE_LOCKED` establishes
only that the observer could not read. Missing callbacks, including a candidate
clearing or replacing `writer.db`'s callback, can leave only the final snapshot.
The helper may return after its available functional checks in either case;
that return is not successful transition coverage or an atomicity verdict.
The controller must report the affected coverage as **unverified** and obtain
independent, adapted observation or transaction-boundary evidence before judging
atomicity. Neither blocked reads nor missing observations alone establish a
candidate defect. This bounded sampler does not automatically diagnose callback
replacement or produce a candidate verdict.

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
