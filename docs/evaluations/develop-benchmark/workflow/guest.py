"""Offline worker transport for Docker hosts that restrict nested user namespaces."""
from contextlib import contextmanager
import hashlib
import json
import os
import shlex
import shutil

from lab import HERE, SPEC, call, docker


def tag(case):
    return f"law-benchmark-{case['image']}:workflow-v1"


def build(case):
    call("docker", "build", "--platform", "linux/amd64", "--build-arg",
         "TOOLCHAIN=" + SPEC["images"][case["image"]], "-t", tag(case), HERE / "vm")


def image_id(case):
    return call("docker", "image", "inspect", "-f", "{{.Id}}", tag(case),
                capture_output=True, text=True).stdout.strip()


def label(run):
    return "law-native-trial=" + hashlib.sha256(os.fsencode(run)).hexdigest()


@contextmanager
def frozen(run):
    """Pause only this disposable worker while collecting its patch."""
    ids = call("docker", "ps", "-q", "--filter", "label=" + label(run),
               capture_output=True, text=True).stdout.split()
    held = []
    try:
        for cid in ids:
            call("docker", "pause", cid, capture_output=True, timeout=15)
            held.append(cid)
        yield
    finally:
        for cid in held:
            call("docker", "unpause", cid, capture_output=True, timeout=15)


def native_tests(case):
    # Marked's quadratic fixture time limits fail on the unmodified tree under TCG.
    # The independent native-speed grader still executes the full upstream suite.
    if case["id"] == "marked":
        return "node --test --test-skip-pattern='^quadratic_' --test-reporter=spec test/run-spec-tests.js"
    return case["native"]


def args(case, run, work, cli, bwrap, installed, canary, *, verification=False, companion=None):
    base, image = docker(case, work)
    env = dict(value.split("=", 1) for value in json.loads(call(
        "docker", "image", "inspect", "-f", "{{json .Config.Env}}", image,
        capture_output=True, text=True).stdout))
    env.update(value.split("=", 1) for i, value in enumerate(base) if i and base[i - 1] == "-e")
    env.update(HOME="/home/worker", CODEX_HOME="/home/worker/.codex", LAB_NONCE=canary,
               CARGO_TARGET_DIR=str(work / "target"), PYTHONPATH=str(work / "src") + ":/deps/lib")
    setup = run / "guest-setup"
    setup.mkdir()
    if canary:
        shutil.copyfile(HERE / "vm/prove.py", setup / "prove.py")
        (setup / "controller-path").write_text(str(run / "controller-only"))
    script = ["#!/bin/sh", "set -eu", "mkdir -p /dev/pts /dev/shm",
              "mount -t devpts devpts /dev/pts", "mount -t tmpfs -o nosuid,nodev tmpfs /dev/shm",
              "mkdir -p /home/worker/.codex", "chmod 700 /home/worker /home/worker/.codex",
              f"chown -R {os.getuid()}:{os.getgid()} /home/worker"]
    mounts = []
    if case.get("loopback_hosts", False):
        mounts += ["--mount", f"type=bind,src={HERE / 'vm/loopback.hosts'},dst=/guest/etc/hosts,readonly"]
    shares = [("root", "/guest", True), ("work", "/work", False),
              ("deps", "/deps", True), ("setup", "/setup", True)]
    assets = [("skills", run / "profile/skills")]
    if installed:
        assets.append(("plugin", installed))
    if companion:
        if not installed:
            raise ValueError("companion requires the Develop arm")
        assets.append(("companion", companion))
    for name, source in assets:
        mounts += ["--mount", f"type=bind,src={source},dst=/{name},readonly"]
        shares += [(name, "/" + name, True)]
        path = shlex.quote(str(source))
        script += [f"mkdir -p {path}", f"mount -t 9p -o trans=virtio,version=9p2000.L,ro {name} {path}"]
    # The native controller runs the pinned command hooks with this cwd; only the one
    # worker mount exists at the matching guest path. General tool execution stays remote.
    workspace = shlex.quote(str(work))
    script += [f"mkdir -p {workspace}", f"mount --bind /work {workspace}"]
    script += ["export " + key + "=" + shlex.quote(value) for key, value in env.items()]
    prefix = f"setpriv --reuid={os.getuid()} --regid={os.getgid()} --clear-groups --no-new-privs"
    command = "/opt/codex/codex exec-server --listen stdio"
    if verification:
        # Use the same toolchain, VM, cold writable caches, namespace helper and CPU/memory limits.
        check = ("set -e\n" + case["build"] + "\nprintf '\\nBENCH_BUILD_OK\\n'\n"
                 + native_tests(case) + "\nprintf '\\nBENCH_NATIVE_OK\\n'")
        command = (f"/opt/codex/codex-resources/bwrap --unshare-all --die-with-parent"
                   f" --ro-bind / / --dev /dev --proc /proc --bind {workspace} {workspace}"
                   f" --bind /tmp /tmp --chdir {workspace} -- /bin/sh -ec {shlex.quote(check)}")
    script += [f"cd {workspace}", f"{prefix} {command} 2>&1" if verification else
               f"{prefix} {command} || true", "/opt/codex/busybox poweroff -f"]
    (setup / "session.sh").write_text("\n".join(script) + "\n")
    (setup / "executor-marker").touch()
    mounts += ["--mount", f"type=bind,src={setup},dst=/setup,readonly",
               "--mount", f"type=bind,src={cli},dst=/guest/opt/codex/codex,readonly",
               "--mount", f"type=bind,src={bwrap},dst=/guest/opt/codex/codex-resources/bwrap,readonly"]
    # No host devices, Linux capabilities, Docker socket, network adapter or privileged mode.
    qemu = ["qemu-system-x86_64", "-nodefaults", "-no-reboot", "-accel", "tcg,thread=multi",
            "-cpu", "max", "-smp", str(SPEC["cpus"]), "-m", "3072", "-display", "none",
            "-monitor", "none", "-nic", "none", "-serial", "none",
            "-chardev", "stdio,id=protocol,signal=off", "-device", "virtio-serial-pci",
            "-device", "virtserialport,chardev=protocol,name=lab"]
    for name, path, readonly in shares:
        qemu += ["-virtfs", f"local,path={path},mount_tag={name},security_model=none,multidevs=remap"
                 + (",readonly=on" if readonly else "")]
    return [*base, "-i", "--label", label(run), *mounts, image_id(case), *qemu, "-kernel", "/worker.kernel",
            "-initrd", "/worker.initrd", "-append", "console=ttyS0 panic=1 quiet"]
