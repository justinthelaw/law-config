"""Coordinate native benchmark jobs that share host CPUs."""
from contextlib import contextmanager, ExitStack
import fcntl
import json
from pathlib import Path


def groups(cpus):
    keys=set()
    for cpu in cpus:
        topology=Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list")
        keys.add(topology.read_text().strip() if topology.is_file() else str(cpu))
    return keys


def verify_existing_operator(state,physical):
    # Earlier operators used a single global lock. Only a registered disjoint
    # lane can overlap such a process while it finishes its original protocol.
    import benchmark as B
    lock=state/"operator.lock"
    if not B.active(lock):
        return
    owner=json.loads(lock.read_text())
    if owner.get("cpu_leases") is True:
        return
    registered=state/"pilots"/B.valid_name(owner["name"])/"registration.json"
    data=B.read(registered) if registered.is_file() else {}
    used=data.get("cpus")
    if not used or physical & groups(used):
        raise ValueError("an earlier benchmark owns these or unverified CPUs; use a disjoint taskset or wait")


@contextmanager
def lease(state, cpus):
    physical=groups(cpus)
    verify_existing_operator(state,physical)
    if not physical:
        raise ValueError("empty CPU lease")
    locks=state/"cpu-leases"
    locks.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        for group in sorted(physical):
            file=stack.enter_context((locks/(group+".lock")).open("a"))
            fcntl.flock(file,fcntl.LOCK_EX)
        yield
