"""Fault injection for opt-in preservation; no host policy or trust edits."""
import hashlib
import importlib.util
import json
import os
import select
import stat
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "develop_response_store", Path(__file__).resolve().parents[1] / "hooks/response_store.py")
store = importlib.util.module_from_spec(SPEC)
exec(compile(Path(SPEC.origin).read_bytes(), SPEC.origin, "exec"), store.__dict__)


@unittest.skipUnless(os.name == "posix", "POSIX private storage")
class ResponseStore(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="develop-response-store-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root.chmod(0o700)
        environment = mock.patch.dict(os.environ, {
            "DEVELOP_GUARD_ROOT": str(self.root), "DEVELOP_GUARD_SESSION": "session",
            "DEVELOP_GUARD_EXPIRES": str(int(time.time()) + 3600),
            "DEVELOP_GUARD_AUTHORIZATION": store.ATTESTATION,
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.raw = '{"tool_input":"PRIVATE_ARGUMENT", "tool_response": { "x": [1.00000000000000000000, 1e+001, -0, "é"] }}'
        self.payload = '{ "x": [1.00000000000000000000, 1e+001, -0, "é"] }'.encode()

    @staticmethod
    def stop_worker(worker):
        if worker.poll() is None:
            worker.kill()
        try:
            worker.communicate(timeout=5)
        finally:
            for stream in (worker.stdin, worker.stdout, worker.stderr):
                if stream is not None:
                    stream.close()

    def preserve(self):
        return store.preserve(self.raw, "session")

    def test_exact_original_json_and_receipt_hash(self):
        receipt = self.preserve()
        paths = list(self.root.glob("response-*.json"))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].read_bytes(), self.payload)
        self.assertIn(hashlib.sha256(self.payload).hexdigest(), receipt)
        self.assertIn(str(len(self.payload)), receipt)
        self.assertNotIn("PRIVATE_ARGUMENT", receipt)
        self.assertNotIn("1.00000000000000000000", receipt)
        self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.root.glob("*.part")))

    def test_response_extraction_handles_envelope_order_and_escaped_keys(self):
        for raw, expected in (
            (' {"tool_response": "a\\\"b", "other": 3}', b'"a\\\"b"'),
            ('{"other": {"tool_response": false}, "tool_response": [true, null]}', b'[true, null]'),
            ('{"tool_\\u0072esponse": -0.000e+000}', b'-0.000e+000'),
            ('{"tool_response":' + '9' * 21000 + '}', b'9' * 21000),
        ):
            self.assertEqual(store.response_bytes(raw), expected)

    def test_unknown_readonly_stale_or_expired_authorization_never_writes(self):
        for changes in (
            {"DEVELOP_GUARD_AUTHORIZATION": ""},
            {"DEVELOP_GUARD_AUTHORIZATION": "read-only"},
            {"DEVELOP_GUARD_SESSION": "previous-session"},
            {"DEVELOP_GUARD_EXPIRES": "0"},
            {"DEVELOP_GUARD_EXPIRES": str(int(time.time()) + 100000)},
        ):
            with self.subTest(changes=changes), mock.patch.dict(os.environ, changes):
                with mock.patch.object(store.os, "open", side_effect=AssertionError("must not open")):
                    with self.assertRaises(ValueError):
                        self.preserve()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_permission_denial_is_not_success(self):
        with mock.patch.object(store.os, "open", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                self.preserve()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_partial_writes_are_completed(self):
        original = os.write
        with mock.patch.object(store.os, "write", side_effect=lambda fd, data: original(fd, data[:3])):
            self.preserve()
        self.assertEqual(next(self.root.glob("response-*.json")).read_bytes(), self.payload)

    def test_failed_or_zero_write_cleans_partial_and_does_not_publish(self):
        original = os.write
        for failure in (OSError("disk full"), 0):
            calls = 0
            def write(fd, data):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return original(fd, data[:3])
                if isinstance(failure, Exception):
                    raise failure
                return failure
            with mock.patch.object(store.os, "write", side_effect=write):
                with self.assertRaises(OSError):
                    self.preserve()
            self.assertFalse(list(self.root.glob("response-*")))

    def test_byte_and_file_quotas_include_orphan_files(self):
        orphan = self.root / "orphan.part"
        orphan.write_bytes(b"12345")
        orphan.chmod(0o600)
        for limits in ({"MAX_FILES": 1}, {"MAX_BYTES": len(self.payload) + 4}):
            with mock.patch.multiple(store, **limits):
                with self.assertRaises(ValueError):
                    self.preserve()
            self.assertEqual(orphan.read_bytes(), b"12345")
            self.assertFalse(list(self.root.glob("response-*.json")))
        orphan.unlink()
        with mock.patch.object(store, "MAX_BYTES", len(self.payload) - 1):
            with self.assertRaises(ValueError):
                self.preserve()

    def test_concurrent_owner_causes_passthrough_instead_of_waiting(self):
        import fcntl
        fd = os.open(self.root / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.preserve()
            self.assertFalse(list(self.root.glob("response-*")))
        finally:
            os.close(fd)

    def test_raced_lock_create_reopens_only_existing_private_lock(self):
        original_open = os.open
        lock_flags = []

        def raced_open(path, flags, *args, **kwargs):
            if path == ".lock":
                lock_flags.append(flags)
                if len(lock_flags) == 1:
                    os.close(original_open(path, flags, *args, **kwargs))
                    raise FileNotFoundError("concurrent creator published the lock")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(store.os, "open", side_effect=raced_open):
            receipt = self.preserve()
        self.assertIn("verified readable now", receipt)
        safe_flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        self.assertEqual(lock_flags, [safe_flags | os.O_CREAT, safe_flags])
        self.assertEqual(next(self.root.glob("response-*.json")).read_bytes(), self.payload)

    def test_raced_lock_create_still_missing_fails_without_recreation(self):
        original_open = os.open
        lock_flags = []

        def missing_open(path, flags, *args, **kwargs):
            if path == ".lock":
                lock_flags.append(flags)
                if len(lock_flags) == 1:
                    raise FileNotFoundError("no lock was published")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(store.os, "open", side_effect=missing_open):
            with self.assertRaises(FileNotFoundError):
                self.preserve()
        self.assertEqual(len(lock_flags), 2)
        self.assertFalse(lock_flags[-1] & os.O_CREAT)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_raced_lock_create_reopen_obeys_original_deadline(self):
        original_open = os.open
        lock_attempts = []

        def missing_open(path, flags, *args, **kwargs):
            if path == ".lock":
                lock_attempts.append(flags)
                raise FileNotFoundError("concurrent creation")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(store.os, "open", side_effect=missing_open), \
                mock.patch.object(store.time, "monotonic", side_effect=[0, store.BUDGET_SECONDS]):
            with self.assertRaisesRegex(RuntimeError, "storage deadline"):
                self.preserve()
        self.assertEqual(len(lock_attempts), 1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_raced_lock_create_rejects_unsafe_existing_locks(self):
        original_open = os.open
        lock = self.root / ".lock"
        target = self.root / "unsafe-target"
        target.write_bytes(b"private data")
        target.chmod(0o600)
        for kind in ("symlink", "hardlink", "permissions"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    lock.symlink_to(target)
                elif kind == "hardlink":
                    os.link(target, lock)
                else:
                    lock.write_bytes(b"nonprivate lock")
                    lock.chmod(0o644)
                lock_flags = []

                def raced_open(path, flags, *args, **kwargs):
                    if path == ".lock":
                        lock_flags.append(flags)
                        if flags & os.O_CREAT:
                            raise FileNotFoundError("raced lock creation")
                    return original_open(path, flags, *args, **kwargs)

                with mock.patch.object(store.os, "open", side_effect=raced_open):
                    with self.assertRaises((OSError, ValueError)):
                        self.preserve()
                self.assertEqual(len(lock_flags), 2)
                self.assertFalse(lock_flags[-1] & os.O_CREAT)
                self.assertFalse(list(self.root.glob("response-*")))
                self.assertEqual(target.read_bytes(), b"private data")
                lock.unlink()

    def test_verification_failure_never_returns_receipt(self):
        with mock.patch.object(store.os, "read", return_value=b""):
            with self.assertRaises(ValueError):
                self.preserve()
        # Published but unverified content remains quota-accounted, never claimed successful.
        self.assertEqual(len(list(self.root.glob("response-*.json"))), 1)

    def test_sync_and_publication_failures_never_return_receipt(self):
        for name in ("fsync", "link"):
            with self.subTest(operation=name), mock.patch.object(store.os, name, side_effect=OSError("fault")):
                with self.assertRaises(OSError):
                    self.preserve()
            self.assertFalse(list(self.root.glob("*.part")))
            self.assertFalse(list(self.root.glob("response-*.json")))

    def test_symlink_root_lock_and_artifact_are_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with mock.patch.dict(os.environ, {"DEVELOP_GUARD_ROOT": str(alias)}):
            with self.assertRaises(OSError):
                self.preserve()
        alias.unlink()
        target = self.root / "target"
        target.write_text("untouched")
        target.chmod(0o600)
        for name in (".lock", "artifact"):
            link = self.root / name
            link.symlink_to(target)
            with self.assertRaises((OSError, ValueError)):
                self.preserve()
            self.assertEqual(target.read_text(), "untouched")
            link.unlink()

    def test_nonprivate_root_and_hardlinked_content_are_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.preserve()
        self.assertEqual(list(self.root.iterdir()), [])
        self.root.chmod(0o700)
        first = self.root / "first"
        first.write_bytes(b"private")
        first.chmod(0o600)
        os.link(first, self.root / "second")
        with self.assertRaises(ValueError):
            self.preserve()

    def test_publication_collision_never_overwrites_existing_artifact(self):
        existing = self.root / ("response-" + "a" * 32 + ".json")
        existing.write_bytes(b"previous response")
        existing.chmod(0o600)
        with mock.patch.object(store.uuid, "uuid4", return_value=mock.Mock(hex="a" * 32)):
            with self.assertRaises(FileExistsError):
                self.preserve()
        self.assertEqual(existing.read_bytes(), b"previous response")
        self.assertFalse(list(self.root.glob("*.part")))

    def test_temporary_collision_never_removes_existing_orphan(self):
        orphan = self.root / ("response-" + "b" * 32 + ".json.part")
        orphan.write_bytes(b"previous interrupted response")
        orphan.chmod(0o600)
        before = orphan.stat()
        with mock.patch.object(store.uuid, "uuid4", return_value=mock.Mock(hex="b" * 32)):
            with self.assertRaises(FileExistsError):
                self.preserve()
        self.assertEqual(orphan.read_bytes(), b"previous interrupted response")
        self.assertEqual(orphan.stat().st_ino, before.st_ino)
        self.assertEqual(orphan.stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.root.glob("response-*.json")))

    def test_revoked_authorization_before_receipt_never_claims_success(self):
        authorize = store.authorized_root
        calls = 0
        def authorize_once(session):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise ValueError("authorization expired")
            return authorize(session)
        with mock.patch.object(store, "authorized_root", side_effect=authorize_once):
            with self.assertRaises(ValueError):
                self.preserve()
        self.assertEqual(calls, 2)
        self.assertEqual(len(list(self.root.glob("response-*.json"))), 1)

    def test_real_concurrent_processes_preserve_complete_unique_artifacts(self):
        script = '''import json, runpy, sys
store = runpy.run_path(sys.argv[1])
raw = sys.stdin.readline()
print("ready", flush=True)
sys.stdin.readline()
try:
    print(json.dumps({"receipt": store["preserve"](raw, "session")}))
except BlockingIOError:
    print(json.dumps({"contention": True}))
'''
        workers = []
        for index in range(6):
            worker = subprocess.Popen([sys.executable, "-I", "-B", "-c", script, SPEC.origin],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True)
            workers.append(worker)
            self.addCleanup(self.stop_worker, worker)
        expected = []
        for index, worker in enumerate(workers):
            payload = json.dumps({"worker": index, "content": "x" * 100000}).encode()
            expected.append(payload)
            worker.stdin.write('{"tool_response":' + payload.decode() + '}\n')
            worker.stdin.flush()
            ready, _, _ = select.select([worker.stdout], [], [], 10)
            self.assertTrue(ready, "worker did not reach start barrier")
            self.assertEqual(worker.stdout.readline(), "ready\n")
        for worker in workers:
            worker.stdin.write("go\n")
            worker.stdin.flush()
        receipts = []
        for worker, payload in zip(workers, expected):
            stdout, stderr = worker.communicate(timeout=15)
            self.assertEqual(worker.returncode, 0, stderr)
            self.assertEqual(stderr, "")
            result = json.loads(stdout)
            if "receipt" in result:
                receipt = result["receipt"]
                metadata, _ = json.JSONDecoder().raw_decode(receipt[receipt.index("{"):])
                artifact = Path(metadata["path"])
                self.assertEqual(artifact.parent, self.root)
                self.assertEqual(artifact.read_bytes(), payload)
                self.assertEqual(metadata["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(metadata["bytes"], len(payload))
                self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
                receipts.append(artifact)
            else:
                self.assertEqual(result, {"contention": True})
        self.assertGreaterEqual(len(receipts), 1)
        self.assertEqual(len(receipts), len(set(receipts)))
        self.assertEqual(set(receipts), set(self.root.glob("response-*.json")))
        self.assertFalse(list(self.root.glob("*.part")))

    def test_killed_writer_leaves_private_quota_accounted_orphan_without_receipt(self):
        script = '''import os, runpy, signal, sys
store = runpy.run_path(sys.argv[1])
original_write = os.write
def interrupted_write(fd, data):
    original_write(fd, data[:3])
    print("partial-written", flush=True)
    signal.pause()
os.write = interrupted_write
print(store["preserve"](sys.stdin.readline(), "session"), flush=True)
'''
        worker = subprocess.Popen([sys.executable, "-I", "-B", "-c", script, SPEC.origin],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
        try:
            worker.stdin.write(self.raw + "\n")
            worker.stdin.flush()
            ready, _, _ = select.select([worker.stdout], [], [], 10)
            self.assertTrue(ready, "writer did not reach partial write")
            self.assertEqual(worker.stdout.readline(), "partial-written\n")
            worker.kill()
            stdout, stderr = worker.communicate(timeout=5)
            self.assertEqual(stdout, "", "interrupted writer emitted a receipt")
            self.assertEqual(stderr, "")
            self.assertLess(worker.returncode, 0)
        finally:
            self.stop_worker(worker)
        orphans = list(self.root.glob("*.part"))
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0].read_bytes(), self.payload[:3])
        self.assertEqual(orphans[0].stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.root.glob("response-*.json")))
        for limits in ({"MAX_FILES": 1}, {"MAX_BYTES": len(self.payload) + 2}):
            with mock.patch.multiple(store, **limits):
                with self.assertRaisesRegex(ValueError, "quota exhausted"):
                    self.preserve()
        self.assertEqual(orphans[0].read_bytes(), self.payload[:3])

    def test_uid_mapped_administrator_ancestry_is_accepted(self):
        original = os.fstat
        destination = self.root.stat()
        mapped_uid = max(os.getuid(), destination.st_uid) + 10000
        def mapped_stat(fd):
            info = original(fd)
            if (info.st_dev, info.st_ino) == (destination.st_dev, destination.st_ino):
                return info
            fields = list(info)
            fields[4] = mapped_uid
            return os.stat_result(fields)
        with mock.patch.object(store.os, "fstat", side_effect=mapped_stat):
            root, fd = store.authorized_root("session")
            try:
                self.assertEqual(root, str(self.root))
                self.assertEqual(original(fd).st_ino, destination.st_ino)
            finally:
                os.close(fd)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unrelated_owner_or_writable_parent_is_rejected(self):
        destination = self.root / "responses"
        destination.mkdir(mode=0o700)
        original = os.fstat
        parent = self.root.stat()
        unrelated_uid = max(os.getuid(), Path('/').stat().st_uid) + 10000
        for uid, mode in ((unrelated_uid, 0o777), (unrelated_uid, 0o755),
                          (os.getuid(), 0o777)):
            def unsafe_parent(fd):
                info = original(fd)
                if (info.st_dev, info.st_ino) != (parent.st_dev, parent.st_ino):
                    return info
                fields = list(info)
                fields[4] = uid
                fields[0] = stat.S_IFDIR | mode
                return os.stat_result(fields)
            with self.subTest(uid=uid, mode=oct(mode)), \
                 mock.patch.dict(os.environ, {"DEVELOP_GUARD_ROOT": str(destination)}), \
                 mock.patch.object(store.os, "fstat", side_effect=unsafe_parent):
                with self.assertRaisesRegex(ValueError, "replaceable parent directory"):
                    self.preserve()
            self.assertEqual(list(destination.iterdir()), [])

    def test_home_and_entire_home_subtree_rejected_before_open(self):
        for destination in (self.root, self.root / "responses", self.root / "nested" / "responses"):
            with self.subTest(destination=destination), \
                 mock.patch.object(store.Path, "home", return_value=self.root), \
                 mock.patch.dict(os.environ, {"DEVELOP_GUARD_ROOT": str(destination)}), \
                 mock.patch.object(store.os, "open", side_effect=AssertionError("must not open")):
                with self.assertRaisesRegex(ValueError, "protected root"):
                    self.preserve()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_resolved_home_subtree_is_protected_when_home_is_a_symlink(self):
        home = self.root / "real-home"
        home.mkdir(mode=0o700)
        destination = home / "responses"
        destination.mkdir(mode=0o700)
        alias = self.root / "home-alias"
        alias.symlink_to(home, target_is_directory=True)
        with mock.patch.object(store.Path, "home", return_value=alias), \
             mock.patch.dict(os.environ, {"DEVELOP_GUARD_ROOT": str(destination)}):
            with self.assertRaisesRegex(ValueError, "protected root"):
                self.preserve()
        self.assertEqual(list(destination.iterdir()), [])

    def test_mode_0500_root_rejected_before_any_write_even_as_root(self):
        self.root.chmod(0o500)
        try:
            original_open = os.open
            def read_only_open(path, flags, *args, **kwargs):
                self.assertFalse(flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR),
                                 "attempted a write before validating root mode")
                return original_open(path, flags, *args, **kwargs)
            with mock.patch.object(store.os, "open", side_effect=read_only_open):
                with self.assertRaisesRegex(ValueError, "not private"):
                    self.preserve()
            self.assertEqual(list(self.root.iterdir()), [])
        finally:
            self.root.chmod(0o700)

    def test_deadline_failure_never_publishes(self):
        with mock.patch.object(store, "check_time", side_effect=RuntimeError("deadline")):
            with self.assertRaises(RuntimeError):
                self.preserve()
        self.assertFalse(list(self.root.glob("response-*")))


if __name__ == "__main__":
    unittest.main()
