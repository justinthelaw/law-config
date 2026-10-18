"""Bounded reference behaviors and seeded defects, not native agent trials."""

from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from evaluations.migration_store import Interrupted, Store


ROOT = Path(__file__).parent / "evaluations"
FIXTURE = json.loads((ROOT / "fixtures/migration-recovery.json").read_text(encoding="utf-8"))
RECORDS = [tuple(row) for row in json.loads(next(
    item["content"] for item in FIXTURE["agent"]["inputs"] if item["path"] == "records.json"))]


class RetentionUnverified(RuntimeError):
    """Text matches need provenance; this is not a candidate defect verdict."""

    def __init__(self, matches):
        self.matches = matches
        super().__init__(f"Raw retention unverified; inspect provenance for {matches!r}")


class Incompatible(Store):
    def read(self, protocol, key):
        # Seed: active N connection is silently served N+1's wire contract.
        return super().read(2, key)


class PrematureCheckpoint(Store):
    def migrate_step(self, interrupt=False):
        if interrupt:
            with self.db:
                self.db.execute("UPDATE migration SET checkpoint = checkpoint + 1")
            raise Interrupted("checkpoint committed without row")
        return super().migrate_step()


class FakeRecovery(Store):
    def finalize(self):
        # Seed: alleged rollback reconstructs text from lossy values.
        super().finalize()
        with self.db:
            self.db.execute("ALTER TABLE records ADD COLUMN raw TEXT")
            self.db.execute("UPDATE records SET raw = printf('%.2f', minor / 100.0)")
            self.db.execute("UPDATE migration SET phase = 'mixed'")

    @staticmethod
    def restore(snapshot, destination):
        pass  # Seed: recovery leaves the reconstructed database untouched.


class StaleBackfill(Store):
    overwrite_raw = False

    def migrate_step(self, interrupt=False):
        # Seed: select before acquiring the write transaction.
        checkpoint = self.db.execute("SELECT checkpoint FROM migration").fetchone()[0]
        row = self.db.execute("SELECT id, raw FROM records WHERE id > ? ORDER BY id LIMIT 1",
                              (checkpoint,)).fetchone()
        if row is None:
            return False
        key, raw = row
        with self.db:
            if self.overwrite_raw:
                self.db.execute("UPDATE records SET minor = ?, raw = ? WHERE id = ?",
                                (int(Decimal(raw) * 100), raw, key))
            else:
                self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (int(Decimal(raw) * 100), key))
            if interrupt:
                raise Interrupted("after row update, before checkpoint")
            self.db.execute("UPDATE migration SET checkpoint = ?", (key,))
        return True


class StaleRowBackfill(StaleBackfill):
    # Seed: atomically overwrite both representations of the committed write.
    overwrite_raw = True


class CorruptRejectedWrite(Store):
    def write(self, protocol, key, value):
        if protocol not in (1, 2):
            with self.db:
                self.db.execute("UPDATE records SET minor = 999 WHERE id = ?", (key,))
        return super().write(protocol, key, value)


class FinalOldWrite(Store):
    def write(self, protocol, key, value):
        if protocol == 1 and self.db.execute("SELECT phase FROM migration").fetchone()[0] == "final":
            with self.db:
                self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (int(Decimal(value) * 100), key))
            return
        return super().write(protocol, key, value)


class PartialRecovery(Store):
    corruption = "UPDATE records SET minor = 999 WHERE id = 1"

    @classmethod
    def restore(cls, snapshot, destination):
        Store.restore(snapshot, destination)
        # Seed: original text survives, but another part of the snapshot does not.
        target = sqlite3.connect(destination)
        try:
            with target:
                target.execute(cls.corruption)
        finally:
            target.close()


class EarlyInterrupted(Store):
    def migrate_step(self, interrupt=False):
        if interrupt:
            raise Interrupted("before touching the row")
        return super().migrate_step()


class NegativeFallback(Store):
    def read(self, protocol, key):
        result = super().read(protocol, key)
        if protocol == 2 and self.db.execute(
                "SELECT minor FROM records WHERE id = ?", (key,)).fetchone() == (None,):
            result["balance_minor"] = abs(result["balance_minor"])
        return result


class MutatingSnapshot(Store):
    def snapshot(self, path):
        self.db.execute("CREATE TABLE unexpected (value TEXT)")
        super().snapshot(path)


class BatchStep(Store):
    def migrate_step(self, interrupt=False):
        checkpoint = self.db.execute("SELECT checkpoint FROM migration").fetchone()[0]
        result = super().migrate_step(interrupt)
        if checkpoint == 1 and not interrupt:
            super().migrate_step()
        return result


class CompletedMutation(Store):
    def migrate_step(self, interrupt=False):
        result = super().migrate_step(interrupt)
        if not result:
            with self.db:
                self.db.execute("UPDATE migration SET checkpoint = 999")
        return result


class SplitWrite(Store):
    split_protocol = 1

    def write(self, protocol, key, value):
        if protocol != self.split_protocol or self.db.execute(
                "SELECT phase FROM migration").fetchone()[0] != "mixed":
            return super().write(protocol, key, value)
        raw = value if protocol == 1 else format(Decimal(value) / 100, ".2f")
        with self.db:
            self.db.execute("UPDATE records SET raw = ? WHERE id = ?", (raw, key))
        with self.db:
            self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (int(Decimal(raw) * 100), key))


class SplitMigrationStep(Store):
    split_commit = True

    def migrate_step(self, interrupt=False):
        if interrupt:
            return super().migrate_step(interrupt=True)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT id, raw FROM records WHERE id > "
                                  "(SELECT checkpoint FROM migration) ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return False
            key, raw = row
            self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (int(Decimal(raw) * 100), key))
            if self.split_commit:
                self.db.commit()
            self.db.execute("UPDATE migration SET checkpoint = ?", (key,))
        return True


class AtomicMigrationStep(SplitMigrationStep):
    split_commit = False


class IncompleteSplitWrite(SplitWrite):
    def write(self, protocol, key, value):
        if self.db.execute("SELECT count(*) FROM records WHERE id > "
                           "(SELECT checkpoint FROM migration)").fetchone()[0]:
            return super().write(protocol, key, value)
        return Store.write(self, protocol, key, value)


class AtomicColumnWrites(Store):
    """Benign control: two statements are atomic inside one transaction."""

    def write(self, protocol, key, value):
        if protocol not in (1, 2) or self.db.execute(
                "SELECT phase FROM migration").fetchone()[0] != "mixed":
            return super().write(protocol, key, value)
        raw = value if protocol == 1 else format(Decimal(value) / 100, ".2f")
        with self.db:
            self.db.execute("UPDATE records SET raw = ? WHERE id = ?", (raw, key))
            self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (int(Decimal(raw) * 100), key))


class AlternateErrors(Store):
    """Benign control: the contract does not require exception message text."""

    def finalize(self):
        try:
            super().finalize()
        except ValueError as error:
            raise RuntimeError("try later") from error

    def read(self, protocol, key):
        try:
            return super().read(protocol, key)
        except ValueError as error:
            raise ValueError("unavailable") from error

    def write(self, protocol, key, value):
        try:
            super().write(protocol, key, value)
        except ValueError as error:
            raise ValueError("unavailable") from error


class LateInterrupted(Store):
    def migrate_step(self, interrupt=False):
        if not interrupt:
            return super().migrate_step()
        with self.db:
            self.db.execute("UPDATE records SET minor = -50 WHERE id = 2")
            self.db.execute("UPDATE migration SET checkpoint = 2")
            raise Interrupted("too late: checkpoint was already updated")


class DeferredCommit(Store):
    def migrate_step(self, interrupt=False):
        # Seed: a later call commits the first allegedly durable step.
        self.db.commit()
        if self.db.execute("SELECT checkpoint FROM migration").fetchone() == (0,):
            self.db.execute("UPDATE records SET minor = 120 WHERE id = 1")
            self.db.execute("UPDATE migration SET checkpoint = 1")
            return True
        return super().migrate_step(interrupt)


class PartialFinalize(Store):
    def finalize(self):
        if self.db.execute("SELECT checkpoint FROM migration").fetchone()[0] > 0:
            # Seed: silently finish instead of refusing incomplete backfill.
            while self.migrate_step():
                pass
        super().finalize()


class LostFinalRows(Store):
    def finalize(self):
        super().finalize()
        with self.db:
            self.db.execute("DELETE FROM records WHERE id != 1")


class ArchivedRaw(Store):
    def finalize(self):
        self.db.execute("CREATE TABLE raw_archive AS SELECT * FROM records")
        super().finalize()


class RenamedRawArchive(Store):
    def finalize(self):
        self.db.execute("CREATE TABLE legacy_payload AS SELECT raw AS saved_text FROM records")
        super().finalize()


class FinalizationMetadata(Store):
    """Benign control: unrelated metadata need not be forbidden."""

    note = "complete"

    def finalize(self):
        super().finalize()
        with self.db:
            self.db.execute("CREATE TABLE metadata (note TEXT)")
            self.db.execute("INSERT INTO metadata VALUES (?)", (self.note,))


class CoincidentMetadata(FinalizationMetadata):
    # Independent literal metadata, not copied from records.raw.
    note = "9.99"


class ReopenedCandidate(Store):
    restored_path = None
    observed_reopen = False
    corrupt_read = False

    def __init__(self, path):
        super().__init__(path)
        self.restored = str(path) == self.restored_path
        if self.restored:
            type(self).observed_reopen = True

    @classmethod
    def restore(cls, snapshot, destination):
        Store.restore(snapshot, destination)
        cls.restored_path = str(destination)

    def read(self, protocol, key):
        if self.restored and self.corrupt_read and protocol == 1:
            return {"balance": "corrupted after reopen"}
        return super().read(protocol, key)


class MixedFinalPhase(Store):
    finalized = False

    def finalize(self):
        super().finalize()
        with self.db:
            self.db.execute("UPDATE migration SET phase = 'mixed'")
        self.finalized = True

    def read(self, protocol, key):
        if self.finalized:
            if protocol != 2:
                raise ValueError("unavailable")
            return {"balance_minor": self.db.execute(
                "SELECT minor FROM records WHERE id = ?", (key,)).fetchone()[0]}
        return super().read(protocol, key)

    def write(self, protocol, key, value):
        if self.finalized:
            raise ValueError("unavailable")
        return super().write(protocol, key, value)


class MutatingFinalRead(Store):
    mutate_on = 3
    final_reads = 0

    def read(self, protocol, key):
        result = super().read(protocol, key)
        if protocol == 2 and self.db.execute("SELECT phase FROM migration").fetchone() == ("final",):
            self.final_reads += 1
            if self.final_reads == self.mutate_on:
                with self.db:
                    self.db.execute("UPDATE records SET minor = 0 WHERE id = 2")
        return result


class TransientFinalGuard(Store):
    frozen = False

    def finalize(self):
        super().finalize()
        self.frozen = True

    def write(self, protocol, key, value):
        if protocol == 2 and not self.frozen and self.db.execute(
                "SELECT phase FROM migration").fetchone() == ("final",):
            with self.db:
                self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (value, key))
            return
        return super().write(protocol, key, value)


class NonBooleanStep(Store):
    successful = 1
    completed = None

    def migrate_step(self, interrupt=False):
        return self.successful if super().migrate_step(interrupt) else self.completed


class ExtraInterruptedRow(Store):
    def migrate_step(self, interrupt=False):
        if not interrupt:
            return super().migrate_step()
        with self.db:
            self.db.execute("UPDATE records SET minor = -50 WHERE id = 2")
            self.db.execute("UPDATE records SET minor = 999 WHERE id = 3")
            raise Interrupted("touched an extra row before rollback")


class RepeatedNextRow(Store):
    def migrate_step(self, interrupt=False):
        if not interrupt:
            return super().migrate_step()
        with self.db:
            for _ in range(2):
                self.db.execute("UPDATE records SET minor = -50 WHERE id = 2")
            raise Interrupted("multiple statements, only the next row")


class MutatingUnsupportedRead(Store):
    def read(self, protocol, key):
        if protocol not in (1, 2):
            with self.db:
                self.db.execute("UPDATE migration SET checkpoint = 999")
        return super().read(protocol, key)


class BadSeed(Store):
    mutation = "ALTER TABLE migration ADD COLUMN unexpected TEXT"

    def seed(self, records):
        super().seed(records)
        with self.db:
            self.db.execute(self.mutation)


class SeedMetadataIndex(Store):
    def seed(self, records):
        super().seed(records)
        with self.db:
            self.db.execute("CREATE INDEX record_text ON records(raw)")
            self.db.execute("CREATE TABLE metadata (note TEXT)")
            self.db.execute("INSERT INTO metadata VALUES ('complete')")


class AuxiliaryRows(SeedMetadataIndex):
    def seed(self, records):
        super().seed(records)
        with self.db:
            self.db.execute('CREATE TABLE "quoted""metadata" (value)')
            self.db.executemany('INSERT INTO "quoted""metadata" VALUES (?)',
                                [(None,), ("unrelated",), (7,), (b"bytes",), (7,)])


class MutatingAuxiliary(SeedMetadataIndex):
    transition = "completed"

    def mutate(self):
        with self.db:
            self.db.execute("UPDATE metadata SET note = note || '!'")

    def migrate_step(self, interrupt=False):
        try:
            result = super().migrate_step(interrupt)
        except Interrupted:
            if self.transition == "interrupted":
                self.mutate()
            raise
        if self.transition == ("step" if result else "completed"):
            self.mutate()
        return result

    def write(self, protocol, key, value):
        super().write(protocol, key, value)
        if self.transition == "write":
            self.mutate()


class ConsecutiveOnly(Store):
    def migrate_step(self, interrupt=False):
        if self.db.execute("SELECT id FROM records WHERE id = "
                           "(SELECT checkpoint + 1 FROM migration)").fetchone() is None:
            return False
        return super().migrate_step(interrupt)


class StalledStep(Store):
    calls = 0

    def migrate_step(self, interrupt=False):
        self.calls += 1
        if self.calls > len(RECORDS) + 1:
            # Test-only escape makes the old unbounded checker reproducible
            # without a wall-clock timeout or hanging the suite.
            raise RuntimeError("test sentinel: completion checker exceeded finite fixture")
        return True


class MetadataRejectedWrite(Store):
    mutation = "UPDATE migration SET checkpoint = 999"

    def write(self, protocol, key, value):
        if protocol not in (1, 2):
            with self.db:
                self.db.execute(self.mutation)
        super().write(protocol, key, value)


class MutatingRetiredRead(Store):
    def read(self, protocol, key):
        if protocol == 1 and self.db.execute("SELECT phase FROM migration").fetchone() == ("final",):
            with self.db:
                self.db.execute("UPDATE records SET minor = 0 WHERE id = 2")
        return super().read(protocol, key)


class CollateralWrite(Store):
    corrupt_protocol = 1

    def write(self, protocol, key, value):
        super().write(protocol, key, value)
        if protocol == self.corrupt_protocol:
            with self.db:
                self.db.execute("UPDATE records SET raw = '0.00', minor = 0 WHERE id = 3")


class OptimisticBackfill(Store):
    """Benign control: compare-and-retry preserves a concurrent writer."""

    def migrate_step(self, interrupt=False):
        checkpoint = self.db.execute("SELECT checkpoint FROM migration").fetchone()[0]
        while True:
            row = self.db.execute("SELECT id, raw FROM records WHERE id > ? ORDER BY id LIMIT 1",
                                  (checkpoint,)).fetchone()
            if row is None:
                return False
            key, raw = row
            with self.db:
                changed = self.db.execute("UPDATE records SET minor = ? WHERE id = ? AND raw = ?",
                                          (int(Decimal(raw) * 100), key, raw)).rowcount
                if not changed:
                    continue
                if interrupt:
                    raise Interrupted("after row update, before checkpoint")
                self.db.execute("UPDATE migration SET checkpoint = ?", (key,))
                return True


class ConflictCollateral(OptimisticBackfill):
    mutation = "UPDATE records SET raw = '0.00', minor = 0 WHERE id = 2"

    def migrate_step(self, interrupt=False):
        before = self.db.execute("SELECT raw FROM records WHERE id = 1").fetchone()
        result = super().migrate_step(interrupt)
        if self.db.execute("SELECT raw FROM records WHERE id = 1").fetchone() != before:
            with self.db:
                self.db.execute(self.mutation)
        return result


class TransientRetry(OptimisticBackfill):
    def migrate_step(self, interrupt=False):
        checkpoint = self.db.execute("SELECT checkpoint FROM migration").fetchone()[0]
        while True:
            row = self.db.execute("SELECT id, raw FROM records WHERE id > ? ORDER BY id LIMIT 1",
                                  (checkpoint,)).fetchone()
            if row is None:
                return False
            key, raw = row
            with self.db:
                changed = self.db.execute("UPDATE records SET minor = ? WHERE id = ? AND raw = ?",
                                          (int(Decimal(raw) * 100), key, raw)).rowcount
                if not changed:
                    saved = self.db.execute("SELECT raw, minor FROM records WHERE id = 2").fetchone()
                    self.db.execute("UPDATE records SET raw = '0.00', minor = 0 WHERE id = 2")
                    self.db.commit()
                    self.db.execute("UPDATE records SET raw = ?, minor = ? WHERE id = 2", saved)
                    continue
                if interrupt:
                    raise Interrupted("after row update, before checkpoint")
                self.db.execute("UPDATE migration SET checkpoint = ?", (key,))
                return True


class TransientAuxiliary(SeedMetadataIndex):
    transition = "step"
    commit_intermediate = True
    statements = ("UPDATE metadata SET note = 'temporary'", "UPDATE metadata SET note = 'complete'")

    def disturb(self):
        with self.db:
            self.db.execute(self.statements[0])
            if self.commit_intermediate:
                self.db.commit()
            self.db.execute(self.statements[1])

    def migrate_step(self, interrupt=False):
        try:
            result = super().migrate_step(interrupt)
        except Interrupted:
            if self.transition == "interrupted":
                self.disturb()
            raise
        if self.transition == "step" and result:
            self.disturb()
        return result

    def write(self, protocol, key, value):
        super().write(protocol, key, value)
        if self.transition == "write":
            self.disturb()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "store.sqlite"

    def open(self, kind=Store, path=None):
        store = kind(path or self.path)
        self.addCleanup(store.close)
        return store

    def seeded(self, kind=Store, records=None):
        store = self.open(kind)
        records = RECORDS if records is None else records
        store.seed(records)
        schemas = {
            "records": [("id", "INTEGER", 1), ("raw", "TEXT", 0), ("minor", "INTEGER", 0)],
            "migration": [("checkpoint", "INTEGER", 0), ("phase", "TEXT", 0)],
        }
        for table, columns in schemas.items():
            actual = [(row[1], row[2].upper(), row[5])
                      for row in store.db.execute(f"PRAGMA table_info({table})")]
            self.assertEqual(actual, columns)
        self.assertEqual(store.db.execute("SELECT * FROM migration").fetchall(), [(0, "mixed")])
        self.assertEqual(store.db.execute("SELECT * FROM records ORDER BY id").fetchall(),
                         [(key, raw, None) for key, raw in sorted(records)])
        return store

    def assert_migration_step(self, store):
        before = self.database_state(store)
        checkpoint, phase = before["migration"][0]
        pending = [row for row in before["records"] if row[0] > checkpoint]
        expected = before["records"]
        if pending:
            key, raw, _ = pending[0]
            expected = [(key, raw, int(Decimal(raw) * 100)) if row[0] == key else row
                        for row in before["records"]]
            checkpoint = key
        final = before | {"records": expected, "migration": [(checkpoint, phase)]}
        result = self.assert_sampled_transition(
            store, store.migrate_step, (final,))
        after = self.database_state(store)
        if pending:
            self.assertIs(result, True)
        else:
            self.assertIs(result, False)
        self.assertEqual(after, final)
        return result

    def finish_migration(self, store):
        checkpoint = store.db.execute("SELECT checkpoint FROM migration").fetchone()[0]
        remaining = store.db.execute("SELECT count(*) FROM records WHERE id > ?", (checkpoint,)).fetchone()[0]
        for _ in range(remaining):
            self.assertIs(self.assert_migration_step(store), True)
        self.assertIs(self.assert_migration_step(store), False)

    def assert_write_changes_only_target(self, store, protocol, key, value, expected):
        before = self.database_state(store)
        records = [(key, *expected) if row[0] == key else row for row in before["records"]]
        final = before | {"records": records}
        self.assert_sampled_transition(
            store, lambda: store.write(protocol, key, value), (final,))
        self.assertEqual(self.database_state(store), final)

    def assert_coexistence(self, kind=Store):
        old = self.seeded(kind)
        new = self.open(kind)
        self.assertEqual(old.read(1, 1), {"balance": "001.20"})
        self.assertEqual(new.read(2, 1), {"balance_minor": 120})
        self.assertEqual(new.read(2, 2), {"balance_minor": -50})
        self.assertIs(self.assert_migration_step(new), True)
        self.assert_write_changes_only_target(old, 1, 1, "002.35", ("002.35", 235))
        self.assertEqual(new.read(2, 1), {"balance_minor": 235})
        self.assert_write_changes_only_target(new, 2, 2, -75, ("-0.75", -75))
        self.assertEqual(old.read(1, 2), {"balance": "-0.75"})
        self.finish_migration(new)
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})
        self.assertEqual(new.read(2, 2), {"balance_minor": -75})
        before = self.database_state(new)
        with self.assertRaises(ValueError):
            new.write(3, 1, "99.00")
        self.assertEqual(self.database_state(new), before)
        with self.assertRaises(ValueError):
            new.read(3, 1)
        self.assertEqual(self.database_state(new), before)
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})
        self.assertEqual(new.read(2, 1), {"balance_minor": 235})

    def assert_concurrent_write(self, kind=Store):
        old = self.seeded()
        new = self.open(kind)
        old.db.execute("PRAGMA busy_timeout = 0")
        outcomes = []
        before = self.database_state(new)

        def interleave(statement):
            # The trace fires before SQLite executes the backfill UPDATE, after
            # the source row was fetched. No threads, sleeps or timing race.
            if statement.startswith("UPDATE records SET minor") and not outcomes:
                try:
                    old.write(1, 1, "002.35")
                except sqlite3.OperationalError as error:
                    outcomes.append(error)
                else:
                    outcomes.append("written")

        concurrent = before | {"records": [(1, "002.35", 235), *before["records"][1:]]}
        migrated = {"migration": [(1, "mixed")]}
        locked_final = before | migrated | {
            "records": [(1, "001.20", 120), *before["records"][1:]]}
        written_final = concurrent | migrated
        self.assertIs(self.assert_sampled_transition(
            new, new.migrate_step, (locked_final, written_final),
            interleave=interleave, intermediate_states=(concurrent,)), True)
        self.assertEqual(len(outcomes), 1)
        raw = old.read(1, 1)["balance"]
        self.assertEqual(new.read(2, 1), {"balance_minor": int(Decimal(raw) * 100)})
        if isinstance(outcomes[0], sqlite3.OperationalError):
            self.assert_database_busy(outcomes[0])
            expected = locked_final
        else:
            self.assertEqual(outcomes, ["written"])
            self.assertEqual(old.read(1, 1), {"balance": "002.35"})
            self.assertEqual(new.read(2, 1), {"balance_minor": 235})
            expected = written_final
        self.assertEqual(self.database_state(new), expected)
        # Both locking and compare-and-retry permit this subsequent write.
        self.assert_write_changes_only_target(old, 1, 1, "002.35", ("002.35", 235))
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})
        self.assertEqual(new.read(2, 1), {"balance_minor": 235})
        self.assertEqual(new.db.execute("SELECT checkpoint FROM migration").fetchone(), (1,))

    def assert_database_busy(self, error):
        code = getattr(error, "sqlite_errorcode", None)
        if code is None:
            # Python 3.10 lacks SQLite error codes and their named constants.
            self.assertRegex(str(error), r"^database(?: table| schema)? is locked(?:$|:)")
        else:
            self.assertIn(code & 0xff, (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED))

    @staticmethod
    def database_state(store):
        auxiliary = {}
        for (table,) in store.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            if table in ("records", "migration") or table.startswith("sqlite_"):
                continue
            quoted = '"' + table.replace('"', '""') + '"'
            # SQLite scalar rows may mix NULL, text, numbers and blobs. repr
            # gives a stable ordering without comparing incompatible types.
            auxiliary[table] = sorted(store.db.execute(f"SELECT * FROM {quoted}").fetchall(), key=repr)
        return {
            "records": store.db.execute("SELECT * FROM records ORDER BY id").fetchall(),
            "migration": store.db.execute("SELECT * FROM migration").fetchall(),
            "schema": store.db.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall(),
            "auxiliary": auxiliary,
        }

    def assert_restart(self, kind=Store):
        store = self.seeded(kind)
        self.assertIs(self.assert_migration_step(store), True)
        durable = self.database_state(store)
        store.close()
        store = self.open(kind)
        self.assertEqual(self.database_state(store), durable)
        expected = [(1, "001.20", 120), (2, "-0.50", None), (3, "9.99", None)]
        self.assertEqual(store.db.execute("SELECT checkpoint FROM migration").fetchone(), (1,))
        self.assertEqual(store.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)
        touched = []
        checkpoints = []
        store.db.create_function("observe_row", 2, lambda key, minor: touched.append((key, minor)))
        store.db.create_function("observe_checkpoint", 0, lambda: checkpoints.append(True))
        # AFTER triggers observe executed row changes, including replacements;
        # unlike transaction state alone, they distinguish an early exception.
        for event in ("UPDATE", "INSERT"):
            store.db.execute(f"CREATE TEMP TRIGGER observe_{event} AFTER {event} ON records "
                             "BEGIN SELECT observe_row(NEW.id, NEW.minor); END")
        for event in ("UPDATE", "INSERT", "DELETE"):
            store.db.execute(f"CREATE TEMP TRIGGER checkpoint_{event} AFTER {event} ON migration "
                             "BEGIN SELECT observe_checkpoint(); END")
        def interrupt():
            with self.assertRaises(Interrupted):
                store.migrate_step(interrupt=True)

        self.assert_sampled_transition(store, interrupt, (durable,))
        self.assertEqual({key for key, _ in touched}, {2})
        self.assertEqual(touched[-1], (2, -50))
        self.assertEqual(checkpoints, [])
        store.close()
        resumed = self.open(kind)
        self.assertEqual(self.database_state(resumed), durable)
        self.assertEqual(resumed.db.execute("SELECT checkpoint FROM migration").fetchone(), (1,))
        self.assertEqual(resumed.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)
        for index, minor in ((1, -50), (2, 999)):
            self.assertIs(self.assert_migration_step(resumed), True)
            key, raw, _ = expected[index]
            expected[index] = (key, raw, minor)
            self.assertEqual(resumed.db.execute("SELECT checkpoint FROM migration").fetchone(), (key,))
            self.assertEqual(resumed.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)
        before = self.database_state(resumed)
        resumed.close()
        again = self.open(kind)
        self.assertEqual(self.database_state(again), before)
        self.assertIs(self.assert_migration_step(again), False)
        self.assertEqual(self.database_state(again), before)

    def assert_sampled_transition(self, writer, operation, final_states,
                                  interleave=None, intermediate_states=()):
        # Samples only writer.db. Candidate auxiliary connections require their
        # own instrumentation; passing this reference probe cannot verify them.
        observer = self.open()
        observer.db.execute("PRAGMA busy_timeout = 0")

        def snapshot():
            # All covered tables and schema share one read snapshot. Release
            # it before the traced writer statement executes.
            with observer.db:
                observer.db.execute("BEGIN")
                return self.database_state(observer)

        before = snapshot()
        observed = []

        def observe(statement):
            if interleave is not None:
                interleave(statement)
            try:
                observed.append(snapshot())
            except sqlite3.OperationalError as error:
                # Check errors outside the callback: sqlite3 suppresses callback
                # exceptions. Exclusive writers may legitimately block reads.
                observed.append(error)

        writer.db.set_trace_callback(observe)
        try:
            result = operation()
            observed.append(snapshot())
        finally:
            writer.db.set_trace_callback(None)
            observer.close()
        self.assertIn(observed[-1], final_states)
        for state in observed:
            if isinstance(state, sqlite3.OperationalError):
                self.assert_database_busy(state)
            else:
                self.assertIn(state, (before, *intermediate_states, *final_states))
        return result

    def assert_sampled_write_atomicity(self, kind=Store):
        writer = self.seeded(kind)
        self.finish_migration(writer)
        for protocol, value, expected in ((1, "002.35", ("002.35", 235)), (2, -75, ("-0.75", -75))):
            self.assert_write_changes_only_target(writer, protocol, 1, value, expected)

    def assert_recovery(self, kind=Store):
        store = self.seeded(kind)
        self.finish_migration(store)
        # Both protocols are drained; writes remain frozen through recovery.
        snapshot = Path(self.temp.name) / "before.sqlite"
        expected = self.database_state(store)
        store.snapshot(snapshot)
        self.assertEqual(self.database_state(store), expected)
        backup = self.open(path=snapshot)
        self.assertEqual([backup.read(1, key)["balance"] for key, _ in RECORDS],
                         [raw for _, raw in RECORDS])
        self.assertEqual(self.database_state(backup), expected)
        backup.close()
        store.finalize()
        matches = self.assert_finalized_records(
            store, [(key, minor) for key, _, minor in expected["records"]])
        store.close()
        kind.restore(snapshot, self.path)
        recovered = self.open(kind)
        self.assertEqual(self.database_state(recovered), expected)
        self.assertEqual([recovered.read(1, key)["balance"] for key, _ in RECORDS],
                         [raw for _, raw in RECORDS])
        self.assertEqual([recovered.read(2, key)["balance_minor"] for key, _ in RECORDS],
                         [120, -50, 999])
        self.assertIs(self.assert_migration_step(recovered), False)
        self.assertEqual(self.database_state(recovered), expected)
        backup = self.open(path=snapshot)
        self.assertEqual(self.database_state(backup), expected)
        if matches:
            raise RetentionUnverified(matches)

    def test_old_and_new_connections_share_behavior(self):
        self.assert_coexistence()

    def test_committed_and_interrupted_restart(self):
        self.assert_restart()

    def test_backfill_preserves_an_overlapping_old_protocol_write(self):
        self.assert_concurrent_write()

    def test_stale_backfill_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_concurrent_write(StaleBackfill)

    def test_lost_overlapping_write_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_concurrent_write(StaleRowBackfill)

    def test_rejected_write_corruption_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_coexistence(CorruptRejectedWrite)

    def test_restore_irreversible_original_data(self):
        self.assert_recovery()

    def test_incompatible_wire_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_coexistence(Incompatible)

    def test_partial_checkpoint_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_restart(PrematureCheckpoint)

    def test_lossy_reconstruction_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_recovery(FakeRecovery)

    def test_partial_snapshot_restore_seeds_are_detected(self):
        for index, corruption in enumerate((
            "UPDATE records SET minor = 999 WHERE id = 1",
            "UPDATE migration SET checkpoint = 0",
            "ALTER TABLE records ADD COLUMN leftover TEXT",
        )):
            with self.subTest(corruption=corruption):
                class CorruptedSnapshot(PartialRecovery):
                    pass

                CorruptedSnapshot.corruption = corruption
                self.path = Path(self.temp.name) / f"restore-{index}.sqlite"
                with self.assertRaises(AssertionError):
                    self.assert_recovery(CorruptedSnapshot)

    def assert_incomplete_backfill(self, kind=Store, populate=False, steps=0):
        store = self.seeded(kind)
        if populate:
            for key, raw in RECORDS:
                self.assert_write_changes_only_target(store, 1, key, raw, (raw, int(Decimal(raw) * 100)))
        for _ in range(steps):
            self.assertIs(self.assert_migration_step(store), True)
        before = self.database_state(store)
        with self.assertRaises(Exception):
            store.finalize()
        self.assertEqual(self.database_state(store), before)

    def test_incomplete_backfill_cannot_drop_originals(self):
        self.assert_incomplete_backfill()

    def assert_finalized_records(self, store, expected):
        """Check definitive state and return retention matches for later reporting."""
        self.assertEqual(store.db.execute("SELECT id, minor FROM records ORDER BY id").fetchall(), expected)
        self.assertEqual([row[1] for row in store.db.execute("PRAGMA table_info(records)")],
                         ["id", "minor"])
        self.assertEqual(store.db.execute("SELECT phase FROM migration").fetchall(), [("final",)])
        before = self.database_state(store)
        for key, minor in expected:
            self.assertEqual(store.read(2, key), {"balance_minor": minor})
        self.assertEqual(self.database_state(store), before)
        # Inspect logical main-database tables, including renamed archives.
        original_text = {raw for _, raw in RECORDS}
        matches = []
        for (table,) in store.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [row[1] for row in store.db.execute(f"PRAGMA table_info({quoted})")]
            self.assertNotIn("raw", columns, table)
            contents = store.db.execute(f"SELECT * FROM {quoted}")
            for row in contents:
                for column, value in zip((item[0] for item in contents.description), row):
                    if isinstance(value, str) and value in original_text:
                        matches.append((table, column, value))
        return matches

    def assert_final_phase(self, kind=Store):
        store = self.seeded(kind)
        self.finish_migration(store)
        expected = store.db.execute("SELECT id, minor FROM records ORDER BY id").fetchall()
        store.finalize()
        before = self.database_state(store)
        store.close()
        store = self.open(kind)
        self.assertEqual(self.database_state(store), before)
        matches = self.assert_finalized_records(store, expected)
        with self.assertRaises(ValueError):
            store.read(1, 1)
        self.assertEqual(self.database_state(store), before)
        for protocol, value in ((1, "9.99"), (2, 999)):
            with self.assertRaises(ValueError):
                store.write(protocol, 1, value)
            self.assertEqual(self.database_state(store), before)
        self.assertEqual(store.read(2, 1), {"balance_minor": 120})
        self.assertEqual(self.database_state(store), before)
        if matches:
            raise RetentionUnverified(matches)

    def test_final_phase_retires_old_protocol_and_freezes_writes(self):
        self.assert_final_phase()

    def test_final_old_protocol_write_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_final_phase(FinalOldWrite)

    def test_early_interruption_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_restart(EarlyInterrupted)

    def test_negative_fallback_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_coexistence(NegativeFallback)

    def test_mutating_snapshot_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_recovery(MutatingSnapshot)

    def test_batch_step_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_restart(BatchStep)

    def test_completed_step_mutation_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_restart(CompletedMutation)

    def test_alternate_final_phase_errors_are_accepted(self):
        self.assert_final_phase(AlternateErrors)

    def test_alternate_incomplete_backfill_error_is_accepted(self):
        self.assert_incomplete_backfill(AlternateErrors)

    def test_populated_minor_units_do_not_complete_backfill(self):
        self.assert_incomplete_backfill(populate=True)

    def test_reference_write_samples_are_atomic(self):
        self.assert_sampled_write_atomicity()

    def test_split_write_seed_is_detected(self):
        for protocol in (1, 2):
            with self.subTest(protocol=protocol):
                class NonatomicProtocol(SplitWrite):
                    split_protocol = protocol

                self.path = Path(self.temp.name) / f"split-{protocol}.sqlite"
                with self.assertRaises(AssertionError):
                    self.assert_sampled_write_atomicity(NonatomicProtocol)

    def test_atomic_multistatement_writes_are_accepted(self):
        self.assert_sampled_write_atomicity(AtomicColumnWrites)
        self.path = Path(self.temp.name) / "atomic-mixed-write.sqlite"
        self.assert_coexistence(AtomicColumnWrites)

    def test_incomplete_split_write_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_coexistence(IncompleteSplitWrite)

    def test_conflict_collateral_changes_are_detected(self):
        for index, statement in enumerate((ConflictCollateral.mutation,
                                           "CREATE TABLE unexpected (note TEXT)")):
            with self.subTest(mutation=statement):
                class CorruptRetry(ConflictCollateral):
                    mutation = statement

                self.path = Path(self.temp.name) / f"collateral-retry-{index}.sqlite"
                with self.assertRaises(AssertionError):
                    self.assert_concurrent_write(CorruptRetry)

    def test_auxiliary_mutations_are_detected(self):
        for transition in ("step", "completed", "interrupted", "write"):
            with self.subTest(transition=transition):
                class CorruptMetadata(MutatingAuxiliary):
                    pass

                CorruptMetadata.transition = transition
                self.path = Path(self.temp.name) / f"auxiliary-{transition}.sqlite"
                check = self.assert_coexistence if transition == "write" else self.assert_restart
                with self.assertRaises(AssertionError):
                    check(CorruptMetadata)

    def test_auxiliary_rows_are_preserved(self):
        self.assert_recovery(AuxiliaryRows)

    def test_transient_retry_corruption_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_concurrent_write(TransientRetry)

    def test_transient_auxiliary_changes_are_detected(self):
        for transition in ("step", "write", "interrupted"):
            for index, statements in enumerate((TransientAuxiliary.statements,
                                               ("CREATE TABLE unexpected (value)", "DROP TABLE unexpected"))):
                with self.subTest(transition=transition, statements=statements):
                    class TemporaryChange(TransientAuxiliary):
                        pass

                    TemporaryChange.transition = transition
                    TemporaryChange.statements = statements
                    self.path = Path(self.temp.name) / f"transient-{transition}-{index}.sqlite"
                    with self.assertRaises(AssertionError):
                        check = self.assert_restart if transition == "interrupted" else self.assert_coexistence
                        check(TemporaryChange)

    def test_uncommitted_auxiliary_changes_are_accepted(self):
        for transition in ("step", "write", "interrupted"):
            with self.subTest(transition=transition):
                class InternalChange(TransientAuxiliary):
                    commit_intermediate = False

                InternalChange.transition = transition
                self.path = Path(self.temp.name) / f"internal-{transition}.sqlite"
                check = self.assert_restart if transition == "interrupted" else self.assert_coexistence
                check(InternalChange)

    def test_split_migration_commit_is_detected(self):
        for name, check in (("coexistence", self.assert_coexistence),
                            ("restart", self.assert_restart),
                            ("recovery", self.assert_recovery),
                            ("final", self.assert_final_phase),
                            ("sampled", self.assert_sampled_write_atomicity)):
            with self.subTest(scenario=name):
                self.path = Path(self.temp.name) / f"split-migration-{name}.sqlite"
                with self.assertRaises(AssertionError):
                    check(SplitMigrationStep)

    def test_atomic_multistatement_migration_is_accepted(self):
        self.assert_restart(AtomicMigrationStep)

    def test_late_interruption_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_restart(LateInterrupted)

    def test_deferred_commit_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_restart(DeferredCommit)

    def test_partially_completed_backfill_cannot_finalize(self):
        self.assert_incomplete_backfill(steps=1)

    def test_partial_finalize_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_incomplete_backfill(PartialFinalize, steps=1)

    def test_lost_final_rows_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_final_phase(LostFinalRows)

    def test_archived_raw_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_final_phase(ArchivedRaw)

    def test_optimistic_backfill_is_accepted(self):
        self.assert_concurrent_write(OptimisticBackfill)
        self.path = Path(self.temp.name) / "optimistic-restart.sqlite"
        self.assert_restart(OptimisticBackfill)

    def test_renamed_raw_archive_seed_is_flagged_unverified(self):
        # The seed's source establishes copying. Text equality alone cannot
        # distinguish that known defect from independent coincident metadata.
        with self.assertRaises(RetentionUnverified) as outcome:
            self.assert_final_phase(RenamedRawArchive)
        self.assertEqual(sorted(outcome.exception.matches),
                         sorted(("legacy_payload", "saved_text", raw) for _, raw in RECORDS))

    def test_unrelated_finalization_metadata_is_accepted(self):
        self.assert_final_phase(FinalizationMetadata)

    def test_coincident_metadata_requires_provenance(self):
        with self.assertRaises(RetentionUnverified) as outcome:
            self.assert_final_phase(CoincidentMetadata)
        self.assertEqual(outcome.exception.matches, [("metadata", "note", "9.99")])

    def test_uncertain_retention_does_not_mask_final_phase_defects(self):
        for defect in (FinalOldWrite, MutatingRetiredRead):
            with self.subTest(defect=defect.__name__):
                class Combined(CoincidentMetadata, defect):
                    pass

                self.path = Path(self.temp.name) / f"ambiguous-{defect.__name__}.sqlite"
                with self.assertRaises(AssertionError):
                    self.assert_final_phase(Combined)

    def test_uncertain_retention_does_not_mask_restore_defect(self):
        class Combined(CoincidentMetadata, PartialRecovery):
            pass

        with self.assertRaises(AssertionError):
            self.assert_recovery(Combined)

    def test_uncertain_retention_is_reported_after_successful_recovery(self):
        with self.assertRaises(RetentionUnverified) as outcome:
            self.assert_recovery(CoincidentMetadata)
        self.assertEqual(outcome.exception.matches, [("metadata", "note", "9.99")])
        recovered = self.open()
        self.assertEqual(recovered.read(1, 1), {"balance": "001.20"})

    def test_recovery_uses_candidate_after_reopen(self):
        ReopenedCandidate.observed_reopen = False
        self.assert_recovery(ReopenedCandidate)
        self.assertTrue(ReopenedCandidate.observed_reopen)

    def test_candidate_post_restore_read_defect_is_detected(self):
        class CorruptedReopen(ReopenedCandidate):
            corrupt_read = True

        with self.assertRaises(AssertionError):
            self.assert_recovery(CorruptedReopen)

    def test_wrong_persisted_final_phase_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_final_phase(MixedFinalPhase)

    def test_mutating_permitted_read_seeds_are_detected(self):
        for occurrence in (3, 4):
            with self.subTest(occurrence=occurrence):
                class CorruptingRead(MutatingFinalRead):
                    mutate_on = occurrence

                self.path = Path(self.temp.name) / f"final-read-{occurrence}.sqlite"
                with self.assertRaises(AssertionError):
                    self.assert_final_phase(CorruptingRead)

    def test_transient_final_write_guard_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_final_phase(TransientFinalGuard)

    def test_nonboolean_migration_results_are_detected(self):
        checks = (self.assert_coexistence, self.assert_restart, self.assert_recovery, self.assert_final_phase)
        for index, (successful, completed) in enumerate(((1, False), (True, None))):
            class WrongResult(NonBooleanStep):
                pass

            WrongResult.successful, WrongResult.completed = successful, completed
            for check in checks:
                with self.subTest(results=(successful, completed), check=check.__name__):
                    self.path = Path(self.temp.name) / f"step-result-{index}-{check.__name__}.sqlite"
                    with self.assertRaises(AssertionError):
                        check(WrongResult)

    def test_extra_interrupted_row_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_restart(ExtraInterruptedRow)

    def test_repeated_updates_to_next_row_are_accepted(self):
        self.assert_restart(RepeatedNextRow)

    def test_unsupported_read_mutation_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_coexistence(MutatingUnsupportedRead)

    def test_seed_schema_defect_is_detected(self):
        with self.assertRaises(AssertionError):
            self.seeded(BadSeed)

    def test_seed_metadata_defects_are_detected(self):
        for index, statement in enumerate(("UPDATE migration SET checkpoint = 1",
                                           "INSERT INTO migration VALUES (0, 'mixed')")):
            with self.subTest(statement=statement):
                class BadMetadata(BadSeed):
                    mutation = statement

                self.path = Path(self.temp.name) / f"bad-seed-{index}.sqlite"
                with self.assertRaises(AssertionError):
                    self.seeded(BadMetadata)

    def test_seed_metadata_and_index_are_accepted(self):
        self.assert_recovery(SeedMetadataIndex)

    def test_gapped_ids_migrate_in_order(self):
        store = self.seeded(records=[(9, "9.99"), (2, "001.20"), (5, "-0.50")])
        self.finish_migration(store)
        self.assertEqual(store.db.execute("SELECT checkpoint FROM migration").fetchone(), (9,))
        self.assertEqual(store.db.execute("SELECT * FROM records ORDER BY id").fetchall(),
                         [(2, "001.20", 120), (5, "-0.50", -50), (9, "9.99", 999)])

    def test_consecutive_id_assumption_is_detected(self):
        store = self.seeded(ConsecutiveOnly, records=[(9, "9.99"), (2, "001.20"), (5, "-0.50")])
        with self.assertRaises(AssertionError):
            self.finish_migration(store)

    def test_stalled_migration_fails_without_timeout(self):
        store = self.seeded(StalledStep)
        with self.assertRaises(AssertionError):
            self.finish_migration(store)
        self.assertEqual(store.calls, 1)

    def test_rejected_write_metadata_seeds_are_detected(self):
        for index, statement in enumerate((
            "UPDATE migration SET checkpoint = 999",
            "CREATE TABLE unexpected (value TEXT)",
        )):
            with self.subTest(statement=statement):
                class MetadataMutation(MetadataRejectedWrite):
                    mutation = statement

                self.path = Path(self.temp.name) / f"rejected-metadata-{index}.sqlite"
                with self.assertRaises(AssertionError):
                    self.assert_coexistence(MetadataMutation)

    def test_mutating_retired_read_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_final_phase(MutatingRetiredRead)

    def test_collateral_write_seeds_are_detected(self):
        for protocol in (1, 2):
            for name, check in (("coexistence", self.assert_coexistence),
                                ("sampled", self.assert_sampled_write_atomicity)):
                with self.subTest(protocol=protocol, check=name):
                    class CollateralProtocol(CollateralWrite):
                        corrupt_protocol = protocol

                    self.path = Path(self.temp.name) / f"collateral-{protocol}-{name}.sqlite"
                    with self.assertRaises(AssertionError):
                        check(CollateralProtocol)

    def test_fixture_and_private_grader_pairs(self):
        fixtures = sorted((ROOT / "fixtures").glob("migration-*.json"))
        self.assertEqual(len(fixtures), 2)
        for fixture_path in fixtures:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            grader = json.loads((ROOT / "graders" / fixture_path.name).read_text(encoding="utf-8"))
            self.assertEqual(grader["fixture_id"], fixture["id"])
            self.assertEqual(grader["fixture_revision"], fixture["revision"])
            self.assertNotIn("criteria", fixture)


if __name__ == "__main__":
    unittest.main()
