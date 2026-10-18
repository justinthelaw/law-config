"""Evaluator-only SQLite reference toy; no product migration or deployment API."""

from decimal import Decimal
import sqlite3


class Interrupted(RuntimeError):
    pass


def minor_units(raw):
    return int(Decimal(raw) * 100)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)

    def close(self):
        self.db.close()

    def seed(self, records):
        with self.db:
            self.db.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, raw TEXT, minor INTEGER)")
            self.db.execute("CREATE TABLE migration (checkpoint INTEGER, phase TEXT)")
            self.db.execute("INSERT INTO migration VALUES (0, 'mixed')")
            self.db.executemany("INSERT INTO records VALUES (?, ?, NULL)", records)

    def read(self, protocol, key):
        if protocol not in (1, 2):
            raise ValueError("unsupported protocol")
        phase = self.db.execute("SELECT phase FROM migration").fetchone()[0]
        if phase == "final":
            if protocol == 1:
                raise ValueError("protocol 1 retired")
            value = self.db.execute("SELECT minor FROM records WHERE id = ?", (key,)).fetchone()[0]
        else:
            raw, value = self.db.execute("SELECT raw, minor FROM records WHERE id = ?", (key,)).fetchone()
            if protocol == 1:
                return {"balance": raw}
            if value is None:
                value = minor_units(raw)
        return {"balance_minor": value}

    def write(self, protocol, key, value):
        if protocol not in (1, 2):
            raise ValueError("unsupported protocol")
        phase = self.db.execute("SELECT phase FROM migration").fetchone()[0]
        if phase != "mixed":
            raise ValueError("writes frozen at recovery boundary")
        raw = value if protocol == 1 else format(Decimal(value) / 100, ".2f")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?)",
                            (key, raw, minor_units(raw)))

    def migrate_step(self, interrupt=False):
        with self.db:
            # The connection context commits/rolls back; it does not BEGIN for
            # SELECT. Acquire the write transaction before reading source data.
            self.db.execute("BEGIN IMMEDIATE")
            checkpoint = self.db.execute("SELECT checkpoint FROM migration").fetchone()[0]
            row = self.db.execute("SELECT id, raw FROM records WHERE id > ? ORDER BY id LIMIT 1",
                                  (checkpoint,)).fetchone()
            if row is None:
                return False
            key, raw = row
            self.db.execute("UPDATE records SET minor = ? WHERE id = ?", (minor_units(raw), key))
            if interrupt:
                raise Interrupted("after row update, before checkpoint")
            self.db.execute("UPDATE migration SET checkpoint = ?", (key,))
        return True

    def snapshot(self, path):
        target = sqlite3.connect(path)
        try:
            self.db.backup(target)
        finally:
            target.close()

    def finalize(self):
        if self.db.execute("SELECT count(*) FROM records WHERE minor IS NULL").fetchone()[0]:
            raise ValueError("backfill incomplete")
        with self.db:
            self.db.execute("CREATE TABLE final_records (id INTEGER PRIMARY KEY, minor INTEGER)")
            self.db.execute("INSERT INTO final_records SELECT id, minor FROM records")
            self.db.execute("DROP TABLE records")
            self.db.execute("ALTER TABLE final_records RENAME TO records")
            self.db.execute("UPDATE migration SET phase = 'final'")

    @staticmethod
    def restore(snapshot, destination):
        source, target = sqlite3.connect(snapshot), sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
