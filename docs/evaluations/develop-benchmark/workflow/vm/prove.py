"""Qualification only. Run under the same workspace policy as a scored tool command."""
import hashlib
import os
from pathlib import Path
import sys

role, = sys.argv[1:]
assert role in {"root", "child"}
assert Path("/setup/executor-marker").is_file() and os.listdir("/sys/class/net") == ["lo"]
controller = Path(Path("/setup/controller-path").read_text().strip())
try:
    controller.read_bytes()
except (FileNotFoundError, PermissionError):
    pass
else:
    raise RuntimeError("the controller-only file is readable")
nonce = os.environ["LAB_NONCE"]
proof = hashlib.sha256((nonce + role).encode()).hexdigest()
Path(role + "-proof").write_text(proof)
print("BENCH_PROOF " + proof)
