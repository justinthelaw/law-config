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
    def migrate_step(self, interrupt=False):
        # Seed: select before acquiring the write transaction.
        checkpoint = self.db.execute("SELECT checkpoint FROM migration").fetchone()[0]
        row = self.db.execute("SELECT id, raw FROM records WHERE id > ? ORDER BY id LIMIT 1",
                              (checkpoint,)).fetchone()
        if row is None:
            return False
        key, raw = row
        with self.db:
            self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (int(Decimal(raw) * 100), key))
            if interrupt:
                raise Interrupted("after row update, before checkpoint")
            self.db.execute("UPDATE migration SET checkpoint = ?", (key,))
        return True


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


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "store.sqlite"

    def open(self, kind=Store, path=None):
        store = kind(path or self.path)
        self.addCleanup(store.close)
        return store

    def seeded(self, kind=Store):
        store = self.open(kind)
        store.seed(RECORDS)
        return store

    def assert_coexistence(self, kind=Store):
        old = self.seeded(kind)
        new = self.open(kind)
        self.assertEqual(old.read(1, 1), {"balance": "001.20"})
        self.assertEqual(new.read(2, 1), {"balance_minor": 120})
        self.assertEqual(new.read(2, 2), {"balance_minor": -50})
        new.migrate_step()
        old.write(1, 1, "002.35")
        self.assertEqual(new.read(2, 1), {"balance_minor": 235})
        new.write(2, 2, -75)
        self.assertEqual(old.read(1, 2), {"balance": "-0.75"})
        while new.migrate_step():
            pass
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})
        self.assertEqual(new.read(2, 2), {"balance_minor": -75})
        before = new.db.execute("SELECT * FROM records ORDER BY id").fetchall()
        with self.assertRaises(ValueError):
            new.write(3, 1, "99.00")
        self.assertEqual(new.db.execute("SELECT * FROM records ORDER BY id").fetchall(), before)
        with self.assertRaises(ValueError):
            new.read(3, 1)
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})
        self.assertEqual(new.read(2, 1), {"balance_minor": 235})

    def assert_concurrent_write(self, kind=Store):
        old = self.seeded()
        new = self.open(kind)
        old.db.execute("PRAGMA busy_timeout = 0")
        outcomes = []

        def interleave(statement):
            # The trace fires before SQLite executes the backfill UPDATE, after
            # the source row was fetched. No threads, sleeps or timing race.
            if statement.startswith("UPDATE records SET minor"):
                try:
                    old.write(1, 1, "002.35")
                except sqlite3.OperationalError as error:
                    outcomes.append(str(error))
                else:
                    outcomes.append("written")

        new.db.set_trace_callback(interleave)
        try:
            self.assertTrue(new.migrate_step())
        finally:
            new.db.set_trace_callback(None)
        self.assertEqual(len(outcomes), 1)
        raw = old.read(1, 1)["balance"]
        self.assertEqual(new.read(2, 1), {"balance_minor": int(Decimal(raw) * 100)})
        self.assertEqual(outcomes, ["database is locked"])
        # The rejected overlapping write succeeds after backfill commits.
        old.write(1, 1, "002.35")
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})
        self.assertEqual(new.read(2, 1), {"balance_minor": 235})
        self.assertEqual(new.db.execute("SELECT checkpoint FROM migration").fetchone(), (1,))

    @staticmethod
    def database_state(store):
        return {
            "records": store.db.execute("SELECT * FROM records ORDER BY id").fetchall(),
            "migration": store.db.execute("SELECT * FROM migration").fetchall(),
            "schema": store.db.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall(),
        }

    def assert_restart(self, kind=Store):
        store = self.seeded(kind)
        self.assertTrue(store.migrate_step())
        expected = [(1, "001.20", 120), (2, "-0.50", None), (3, "9.99", None)]
        self.assertEqual(store.db.execute("SELECT checkpoint FROM migration").fetchone(), (1,))
        self.assertEqual(store.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)
        touched = []
        store.db.create_function("observe_row", 2, lambda key, minor: touched.append((key, minor)))
        # AFTER triggers observe executed row changes, including replacements;
        # unlike transaction state alone, they distinguish an early exception.
        for event in ("UPDATE", "INSERT"):
            store.db.execute(f"CREATE TEMP TRIGGER observe_{event} AFTER {event} ON records "
                             "BEGIN SELECT observe_row(NEW.id, NEW.minor); END")
        with self.assertRaises(Interrupted):
            store.migrate_step(interrupt=True)
        self.assertIn((2, -50), touched)
        store.close()
        resumed = self.open(kind)
        self.assertEqual(resumed.db.execute("SELECT checkpoint FROM migration").fetchone(), (1,))
        self.assertEqual(resumed.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)
        for index, minor in ((1, -50), (2, 999)):
            self.assertTrue(resumed.migrate_step())
            key, raw, _ = expected[index]
            expected[index] = (key, raw, minor)
            self.assertEqual(resumed.db.execute("SELECT checkpoint FROM migration").fetchone(), (key,))
            self.assertEqual(resumed.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)
        resumed.close()
        again = self.open(kind)
        before = self.database_state(again)
        self.assertFalse(again.migrate_step())
        self.assertEqual(self.database_state(again), before)

    def assert_supported_write_atomicity(self, kind=Store):
        writer = self.seeded(kind)
        observer = self.open()
        observer.db.execute("PRAGMA busy_timeout = 0")
        while writer.migrate_step():
            pass
        for protocol, value, expected in ((1, "002.35", ("002.35", 235)), (2, -75, ("-0.75", -75))):
            before = observer.db.execute("SELECT raw, minor FROM records WHERE id = 1").fetchone()
            observed = []

            def observe(statement):
                try:
                    observed.append(observer.db.execute(
                        "SELECT raw, minor FROM records WHERE id = 1").fetchone())
                except sqlite3.OperationalError as error:
                    # Exclusive writers may block reads; partial committed rows
                    # must never be visible. Record errors outside the callback.
                    observed.append(error)

            writer.db.set_trace_callback(observe)
            try:
                writer.write(protocol, 1, value)
            finally:
                writer.db.set_trace_callback(None)
            self.assertTrue(observed)
            for row in observed:
                if isinstance(row, sqlite3.OperationalError):
                    self.assertIn(getattr(row, "sqlite_errorcode", None),
                                  (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED))
                else:
                    self.assertIn(row, (before, expected))
            self.assertEqual(observer.db.execute(
                "SELECT raw, minor FROM records WHERE id = 1").fetchone(), expected)

    def assert_recovery(self, kind=Store):
        store = self.seeded(kind)
        while store.migrate_step():
            pass
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
        self.assertEqual(store.read(2, 1), {"balance_minor": 120})
        store.close()
        kind.restore(snapshot, self.path)
        recovered = self.open()
        self.assertEqual(self.database_state(recovered), expected)
        self.assertEqual([recovered.read(1, key)["balance"] for key, _ in RECORDS],
                         [raw for _, raw in RECORDS])
        self.assertEqual([recovered.read(2, key)["balance_minor"] for key, _ in RECORDS],
                         [120, -50, 999])
        self.assertFalse(recovered.migrate_step())
        self.assertEqual(self.database_state(recovered), expected)
        backup = self.open(path=snapshot)
        self.assertEqual(self.database_state(backup), expected)

    def test_old_and_new_connections_share_behavior(self):
        self.assert_coexistence()

    def test_committed_and_interrupted_restart(self):
        self.assert_restart()

    def test_backfill_serializes_an_overlapping_old_protocol_write(self):
        self.assert_concurrent_write()

    def test_stale_backfill_seed_is_detected(self):
        with self.assertRaises(AssertionError):
            self.assert_concurrent_write(StaleBackfill)

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

    def assert_incomplete_backfill(self, kind=Store, populate=False):
        store = self.seeded(kind)
        if populate:
            for key, raw in RECORDS:
                store.write(1, key, raw)
        before = self.database_state(store)
        with self.assertRaises(Exception):
            store.finalize()
        self.assertEqual(self.database_state(store), before)

    def test_incomplete_backfill_cannot_drop_originals(self):
        self.assert_incomplete_backfill()

    def assert_final_phase(self, kind=Store):
        store = self.seeded(kind)
        while store.migrate_step():
            pass
        store.finalize()
        self.assertEqual([row[1] for row in store.db.execute("PRAGMA table_info(records)")],
                         ["id", "minor"])
        with self.assertRaises(ValueError):
            store.read(1, 1)
        before = self.database_state(store)
        for protocol, value in ((1, "9.99"), (2, 999)):
            with self.assertRaises(ValueError):
                store.write(protocol, 1, value)
            self.assertEqual(self.database_state(store), before)
        self.assertEqual(store.read(2, 1), {"balance_minor": 120})

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

    def test_supported_writes_are_atomic(self):
        self.assert_supported_write_atomicity()

    def test_split_write_seed_is_detected(self):
        for protocol in (1, 2):
            with self.subTest(protocol=protocol):
                class NonatomicProtocol(SplitWrite):
                    split_protocol = protocol

                self.path = Path(self.temp.name) / f"split-{protocol}.sqlite"
                with self.assertRaises(AssertionError):
                    self.assert_supported_write_atomicity(NonatomicProtocol)

    def test_atomic_multistatement_writes_are_accepted(self):
        self.assert_supported_write_atomicity(AtomicColumnWrites)

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
