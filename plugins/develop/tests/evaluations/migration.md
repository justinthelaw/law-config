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
results. The private coexistence criterion explicitly requires unsupported reads
and writes to raise `ValueError` with unchanged state, matching the public
two-protocol contract and executable checks. Coexistence and restart criteria
require transaction-boundary evidence for physical atomicity, or an unverified
result when the available channel cannot establish it. Restart also requires
per-call next-row/checkpoint progress, exact boolean results and the declared
`Interrupted` subtype. These clarify the existing public API rather than add
candidate requirements. Give the agent only its prompt,
declared inputs and selected plugin instructions. Keep this page, graders, reference implementation and tests out of
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
read caches during and after backfill, float conversion and snapshots that omit
legal writes. Pending-row writes, acknowledged lock failures, undrained close,
checkpoint-specific interruption/finalization, volatile completion flags,
key-specific protocol acceptance, lost final schema constraints, value-specific
writes (including zero), repeated-completion mutation, mutating mixed reads, dropped peer writes
and transient commits during rejected operations also have controls. Pending-read
controls cover both protocols on every still-pending row at each of the three
seeded checkpoints. The common seed check requires `Interrupted` to subclass
`RuntimeError`; a different valid subtype remains accepted.
Benign controls accept different
exception messages, multiple write statements within one transaction and
optimistic backfill with compare-and-retry. A refreshed peer read control remains
accepted. Precision probes use a legal protocol-1 write of `001.15` and a bounded
alternate seed of positive and negative `1.15` to check exact fallback and
backfill conversion separately; the public fixture is unchanged. Seed and final
schema checks compare column names, declared types and primary-key flags; a
semantically equivalent table-level primary-key declaration remains accepted.
Seed checks require the declared core schema, the supplied records with null
minor values, and
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
at each seeded checkpoint, including the second and last backfill rows, with
candidate instances on both sides and each supported write protocol on a
separate seeded database. The same parameterized probe also retains a reference
writer against the optimistic candidate as a compatibility control, including
the preserved old-protocol connection. A correct first transaction cannot mask
stale reads in later steps or a
writer acknowledging a rejected lock attempt.
Finalization is also attempted after reopening completed migration state. Both
final-phase and recovery paths reopen finalized state and share retired-read and
frozen-write checks for every key, including the recovery dataset's legal writes.
Contract-significant closes verify that the old exposed SQLite connection rejects
queries. Candidate close runs at most once per instance; cleanup independently
closes the captured SQLite handle, accepting candidates that invalidate `db` on
close without requiring idempotence.
Both final-phase and recovery checks compare full state before and after
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
result semantics or validate arbitrary triggers and other SQL dependencies.
The separate retention check below reads scalar table and view results for exact
original-text matches; compilation alone does not detect literal view archives.
These checks add no auxiliary-schema requirement to the public fixture; candidate-specific
schema semantics still require adapted probes.
Migration-step
results must be the booleans `True` and `False`, not merely truthy or falsy values.
For the finite fixtures, each successful step must transform only the next
existing ID and advance the checkpoint to that ID. A gapped, unsorted input
checks that progress does not assume consecutive IDs. Completion uses at most
the initial pending-row count plus two completion calls on the same instance,
checking progress after each call and unchanged state on repeated completion;
it does not rely on a timeout.
Supported-write probes require every unaddressed record to remain unchanged. The tests also
reject finalization at every seeded pending checkpoint, both with originally
null minor values and with all minor values populated by supported writes.
Finalized IDs and values must all survive;
the main database's logical tables must have no remaining `raw` column.
Matching original spellings in scalar table or view results is collected as
object name, column and value evidence. A view column named `raw` may simply
alias minor units; the alias alone is not evidence of original-text retention.
`assert_finalized_records` returns these matches;
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
coincident metadata and renamed table or literal view archives produce
`RetentionUnverified`.
Combined controls verify that coincident metadata cannot hide definite defects,
and successful recovery finishes before retention uncertainty is reported.
The archives are known defects because their seeded source explicitly copies
`records.raw`; the value scan does not establish that provenance. An unrelated
scalar view and a minor-unit projection with a `raw` alias remain accepted.
Coincident view literals require provenance just like coincident table cells.
Passing these calibration tests verifies their outcome classification, not candidate erasure.
The scan does not establish forensic erasure or detect encoded, fragmented or
otherwise transformed copies. It does not parse view DDL or establish arbitrary
SQL behavior, safe evaluation of untrusted expressions, or complete retention
coverage. Candidate views requiring unavailable functions or unsuitable execution
need adapted observation; inability to inspect them is unverified coverage.
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
connection; restart checks inject interruption at each of the fixture's three
pending checkpoints, compare full durable state after reopening, then commit and
reopen each successful step and verify unchanged completion. The same restart
check runs on untouched rows and on rows populated through each supported write
protocol before interruption. The untouched case remains separate so populated,
value-preserving updates cannot mask the existing split-commit control. An interrupted step
may issue
multiple updates to its next row, but must not touch another row or the
checkpoint before the controlled exception.

The shared successful-write assertion samples writes during and after backfill.
While work remains, protocol 1 writes an unbackfilled row and a warmed protocol-1
peer must observe a protocol-2 write. Unsupported protocol reads and writes must
reject without changing full state for every seeded key at each checkpoint,
on completion and after finalization. Identifiers 3 and 4 provide one bounded
calibration against special-casing only 3; they do not prove rejection of all
unsupported identifiers. Unsupported writes use both decimal text and integer
minor-unit payloads so neither supported wire shape is omitted. A control that
validates value shape before rejecting the protocol remains accepted; no arbitrary
payload-type enumeration is implied. Permitted reads also compare full state
before and after, including fallback, peer warm-up and recovered reads. The write
matrix exercises positive, negative and zero values through each protocol before
and after backfill, swapping the seeded and already-open peer connections as writer and reader. The
reader warms both protocols before each write and checks both updated
representations afterward, including preserved protocol-1 `000.00` and protocol-2
`0.00` with integer zero. This finite value partition is not an all-value proof.
These API checks complement the sampler's direct database observations and detect stale per-instance reads on the exercised paths.
Supported writes, rejected operations, normal migration steps and interrupted steps
share a second-connection sampler at statements traced on `writer.db`, plus an
observation after the operation returns. Rejected operations must raise `ValueError`
and preserve the initial state at every available sample; this covers unsupported
reads and writes, retired protocol-1 reads and final-phase frozen writes. Transient committed changes fail even
when restored before rejection, while changes rolled back without becoming
visible remain accepted. Each sample reads the covered records, migration metadata, schema and auxiliary
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
