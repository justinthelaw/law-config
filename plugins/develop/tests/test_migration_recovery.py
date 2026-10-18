"""Bounded reference behaviors and seeded defects, not native agent trials."""

import json
from pathlib import Path
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
        new = self.open()
        self.assertEqual(old.read(1, 1), {"balance": "001.20"})
        self.assertEqual(new.read(2, 1), {"balance_minor": 120})
        new.migrate_step()
        old.write(1, 1, "002.35")
        self.assertEqual(new.read(2, 1), {"balance_minor": 235})
        new.write(2, 2, -75)
        self.assertEqual(old.read(1, 2), {"balance": "-0.75"})
        while new.migrate_step():
            pass
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})
        self.assertEqual(new.read(2, 2), {"balance_minor": -75})
        with self.assertRaises(ValueError):
            new.write(3, 1, "99.00")
        with self.assertRaises(ValueError):
            new.read(3, 1)
        self.assertEqual(old.read(1, 1), {"balance": "002.35"})

    def assert_restart(self, kind=Store):
        store = self.seeded(kind)
        self.assertTrue(store.migrate_step())
        with self.assertRaises(Interrupted):
            store.migrate_step(interrupt=True)
        store.close()
        resumed = self.open(kind)
        self.assertEqual(resumed.db.execute("SELECT checkpoint FROM migration").fetchone(), (1,))
        self.assertEqual(resumed.db.execute("SELECT minor FROM records WHERE id = 2").fetchone(), (None,))
        while resumed.migrate_step():
            pass
        expected = [(1, "001.20", 120), (2, "-0.50", -50), (3, "9.99", 999)]
        self.assertEqual(resumed.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)
        resumed.close()
        again = self.open(kind)
        self.assertFalse(again.migrate_step())
        self.assertEqual(again.db.execute("SELECT * FROM records ORDER BY id").fetchall(), expected)

    def assert_recovery(self, kind=Store):
        store = self.seeded(kind)
        while store.migrate_step():
            pass
        # Both protocols are drained; writes remain frozen through recovery.
        snapshot = Path(self.temp.name) / "before.sqlite"
        store.snapshot(snapshot)
        backup = self.open(path=snapshot)
        self.assertEqual([backup.read(1, key)["balance"] for key, _ in RECORDS],
                         [raw for _, raw in RECORDS])
        backup.close()
        store.finalize()
        self.assertEqual(store.read(2, 1), {"balance_minor": 120})
        store.close()
        kind.restore(snapshot, self.path)
        recovered = self.open()
        self.assertEqual([recovered.read(1, key)["balance"] for key, _ in RECORDS],
                         [raw for _, raw in RECORDS])
        backup = self.open(path=snapshot)
        self.assertEqual(backup.read(1, 1), {"balance": "001.20"})

    def test_old_and_new_connections_share_behavior(self):
        self.assert_coexistence()

    def test_committed_and_interrupted_restart(self):
        self.assert_restart()

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

    def test_incomplete_backfill_cannot_drop_originals(self):
        store = self.seeded()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            store.finalize()
        self.assertEqual(store.read(1, 1), {"balance": "001.20"})

    def test_final_phase_retires_old_protocol_and_freezes_writes(self):
        store = self.seeded()
        while store.migrate_step():
            pass
        store.finalize()
        self.assertEqual([row[1] for row in store.db.execute("PRAGMA table_info(records)")],
                         ["id", "minor"])
        with self.assertRaisesRegex(ValueError, "retired"):
            store.read(1, 1)
        with self.assertRaisesRegex(ValueError, "frozen"):
            store.write(2, 1, 999)
        self.assertEqual(store.read(2, 1), {"balance_minor": 120})

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
