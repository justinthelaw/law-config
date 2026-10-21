"""Concurrent, byte-bounded subprocess capture for read-only inspectors."""

from __future__ import annotations

import math
import subprocess
import threading
import time
from typing import Mapping, Sequence


OUTPUT_BYTES = 1024 * 1024
READ_BYTES = 64 * 1024


class CapturedCommand(subprocess.CompletedProcess):
    """A completed command whose stream completeness remains explicit."""

    def __init__(self, args, returncode, stdout, stderr, *,
                 stdout_overflow=False, stderr_overflow=False):
        super().__init__(args, returncode, stdout, stderr)
        self.stdout_overflow = stdout_overflow
        self.stderr_overflow = stderr_overflow


def capture_command(
    command: Sequence[str], *, cwd: str | None = None,
    env: Mapping[str, str] | None = None, timeout: float = 60,
    max_bytes: int = OUTPUT_BYTES, tail: bool = False,
) -> CapturedCommand:
    """Drain both pipes without retaining more than max_bytes from either.

    stdout may retain its tail for logs; stderr always retains its prefix.
    Reader threads support Windows pipes as well as POSIX. Raw, fixed-size reads
    avoid an unbounded readline/communicate buffer and let cleanup close a pipe
    even when a descendant has inherited its writing end.
    """
    if max_bytes < 1 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("capture requires a positive byte limit and finite timeout")
    expires_at = time.monotonic() + timeout
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
    )
    buffers = [bytearray(), bytearray()]
    overflow = [False, False]
    errors = []

    def read_stream(stream, index):
        try:
            while chunk := stream.read(READ_BYTES):
                buffer = buffers[index]
                overflow[index] |= len(buffer) + len(chunk) > max_bytes
                if tail and index == 0:
                    buffer.extend(chunk)
                    del buffer[:max(0, len(buffer) - max_bytes)]
                else:
                    buffer.extend(chunk[:max_bytes - len(buffer)])
        except (OSError, ValueError) as exc:
            errors.append(exc)

    readers = [threading.Thread(target=read_stream, args=(stream, index), daemon=True)
               for index, stream in enumerate((process.stdout, process.stderr))]
    for reader in readers:
        reader.start()
    try:
        process.wait(timeout=max(0, expires_at - time.monotonic()))
        for reader in readers:
            reader.join(timeout=max(0, expires_at - time.monotonic()))
        if any(reader.is_alive() for reader in readers):
            raise subprocess.TimeoutExpired(command, timeout)
        if errors:
            raise OSError("Unable to capture complete command output") from errors[0]
        return CapturedCommand(
            command, process.returncode,
            buffers[0].decode("utf-8", errors="replace"),
            buffers[1].decode("utf-8", errors="replace"),
            stdout_overflow=overflow[0], stderr_overflow=overflow[1],
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=1)
        process.stdout.close()
        process.stderr.close()
