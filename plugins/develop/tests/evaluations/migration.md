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
minor units, early interruption, premature checkpoints, batched steps, mutation
after completion, final-phase N writes, lossy reconstruction and snapshot
mutation or partial restoration. Benign controls accept different exception
messages and multiple write statements within one transaction. Restore checks
compare all records, migration metadata and schema with the snapshot, then read
both protocols and resume completed migration. Rejection checks preserve full
rows, including writes through both protocols after finalization. The tests also
reject finalization with pending checkpoint work even when all minor values are
populated, and verify removal of the original column.
Run from the plugin directory:

```bash
python -m unittest discover -s tests -p test_migration_recovery.py -v
```

These tests validate the synthetic reference and the sensitivity of its checks.
They are **not agent runs**. For a candidate implementation, the controller can
substitute its `Store` and `Interrupted` exports in an isolated evaluator copy
and run the positive behavior tests. The overlapping-write reproduction uses a
SQLite trace callback at the reference's backfill UPDATE; adapt that controlled
interleaving to a candidate's SQL before using it as candidate evidence. Keep
seeded-defect tests attributed to the reference suite. Temporary row triggers
verify that interruption follows an executed row change; restart checks inspect
every step and unchanged completion. Supported-write checks sample a second
connection at SQL statement boundaries to detect partially committed values.
These are bounded observations, not an exhaustive concurrency schedule.
Grade observed agent
decisions separately with the linked criteria. A passing reference run cannot
supply a candidate or native-host verdict.

The injected interruption models a transaction failure at one controlled point;
it does not simulate OS crashes, power loss, concurrent schema writers or actual
deployment cutovers. Snapshot recovery assumes drained clients and no writes
after the snapshot. Product-specific acceptance remains with its existing owner.
Do not infer deployment readiness, a production rollback guarantee or behavioral
improvement from these offline checks.
