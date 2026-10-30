"""Pinned, offline execution environment shared by both arms and the grader."""
import hashlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent / "workflow"
sys.path.insert(0, str(WORKFLOW))
import guest
import host
import lab
import run as native

ROOT = lab.ROOT
STATE = ROOT / "tmp/pr-quality-panel"
CACHE = STATE / "cache"
PANEL = json.loads((HERE / "panel.json").read_bytes())
COHORT = None
cohort_name = os.environ.get("DEVELOP_EVAL_COHORT", PANEL["protocol"])
if cohort_name == "pr-quality-runner-v3":
    PANEL["protocol"] = cohort_name
    runner = next(c for c in PANEL["cases"] if c["id"] == "runner-space")
    runner.update(check="runner_lint_ledger_v3.mjs", loopback_hosts=True)
elif cohort_name != PANEL["protocol"]:
    sys.path.insert(0, str(HERE.parent))
    from confirmation import cohort as COHORT
    if cohort_name != COHORT.NAME:
        raise ValueError("unknown PR benchmark cohort: " + cohort_name)
    PANEL = COHORT.load(PANEL)
    CACHE = STATE / "confirmation-cache"
CASES = {c["id"]: c for c in PANEL["cases"]}


def upstream(key):
    return COHORT.upstream(key) if COHORT else read(HERE / "upstream.json")[key]
LEGACY_DEPS = lab.dependency_dir
LEGACY_PREPARE = lab.prepare
LEGACY_DOCKER = lab.docker
DEFAULT_PYTHON = "pytest==8.4.2 iniconfig==2.3.0 packaging==25.0 pluggy==1.6.0 pygments==2.19.2"


def read(path):
    return json.loads(path.read_bytes())


def save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Publish only complete immutable JSON. A crash can leave a hidden staging file.
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        if os.path.lexists(path):
            raise FileExistsError(path)
        with tempfile.NamedTemporaryFile(mode="w",dir=path.parent,prefix=".pending-",delete=False) as tmp:
            json.dump(record,tmp,indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.rename(tmp.name,path)
        os.fsync(fd)
    finally:
        os.close(fd)


def configure():
    """The original library keeps its active experiment in process-local configuration."""
    os.umask(0o077)
    lab.STATE = CACHE
    lab.SPEC.update(PANEL)
    lab.CASES = CASES
    lab.dependency_dir = dependencies
    lab.archive = archive_blobs
    lab.docker = guest.docker = docker
    lab.start_state()
    for key in ("TEMP", "TMP", "TMPDIR"):
        os.environ[key] = str(CACHE / "volatile")
    tempfile.tempdir = str(CACHE / "volatile")
    if len(CASES) != 20 or len({c["repo"] for c in CASES.values()}) != 20:
        raise ValueError("twenty unique repositories required")
    if [c["repo"] for c in CASES.values() if c["repo"].startswith("justinthelaw/")] != ["justinthelaw/maximize-github-runner-space"]:
        raise ValueError("one owner stratum required")


def sha(path):
    return lab.digest(path)


def docker(case, workspace, *, online=False):
    args, image = LEGACY_DOCKER(case, workspace, online=online)
    if fixed := os.environ.get("PANEL_CPUSET"):
        args += ["--cpuset-cpus", fixed]
    return args, image


def archive_blobs(objects, revision, destination):
    """Materialize literal blobs even when checkout attributes would convert line endings."""
    destination.mkdir(parents=True, exist_ok=True)
    entries = lab.tree_entries(objects, revision)
    with subprocess.Popen(["git", "--git-dir", objects, "cat-file", "--batch"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as reader:
        for raw_path, meta in entries.items():
            mode, kind, oid = meta.split()
            path = destination / os.fsdecode(raw_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if kind == b"commit":
                path.mkdir(exist_ok=True)
                continue
            reader.stdin.write(oid + b"\n")
            reader.stdin.flush()
            got, obj_type, size = reader.stdout.readline().split()
            if (got, obj_type) != (oid, b"blob"):
                raise ValueError("pinned blob is missing")
            data = reader.stdout.read(int(size))
            if reader.stdout.read(1) != b"\n" or len(data) != int(size):
                raise ValueError("truncated Git blob")
            if mode == b"120000":
                path.symlink_to(os.fsdecode(data))
            else:
                path.write_bytes(data)
                path.chmod(0o755 if mode == b"100755" else 0o644)
        reader.stdin.close()
        if reader.wait():
            raise ValueError("Git object reader failed")


def public_files(case):
    path = HERE / "public" / case["id"]
    return sorted(path.glob("*")) if path.exists() else []


def recipe(case):
    family = case["image"]
    if family == "python":
        packages = (DEFAULT_PYTHON + " " + case["requirements"]).strip()
        return "python -m pip --disable-pip-version-check install --no-cache-dir --no-deps -t /deps/lib " + packages
    if family == "golang":
        return "go mod download"
    if family == "rust":
        return "cargo fetch --locked"
    return ""


def dependencies(case):
    if case.get("legacy"):
        return LEGACY_DEPS(case)
    inputs = [case["base"], PANEL["images"][case["image"]], recipe(case), *(sha(p) for p in public_files(case))]
    digest = hashlib.sha256("\n".join(inputs).encode()).hexdigest()
    return CACHE / "dependencies" / case["id"] / digest[:16]


def cache_objects(case):
    lab.fetch(lab.objects(case), case["repo"], case["gold"])
    if lab.git(lab.objects(case), "rev-parse", case["gold"] + "^1") != case["base"]:
        raise ValueError("reference parent changed: " + case["id"])


def prepare(case):
    if case.get("legacy"):
        LEGACY_PREPARE(case)
        return
    cache_objects(case)
    deps = dependencies(case)
    deps.mkdir(parents=True, exist_ok=True)
    if (deps / "ready").exists():
        return
    image = PANEL["images"][case["image"]]
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode:
        lab.call("docker", "pull", "--platform", "linux/amd64", image)
    seed = Path(tempfile.mkdtemp(prefix="prep-" + case["id"] + "-"))
    for path in public_files(case):
        (deps / "public").mkdir(exist_ok=True)
        shutil.copy2(path, deps / "public" / path.name)
    if case["image"] == "golang":
        for name in ("go.mod", "go.sum"):
            (seed / name).write_bytes(lab.call("git", "--git-dir", lab.objects(case), "show",
                case["base"] + ":" + name, capture_output=True).stdout)
    if case["image"] == "rust":
        lab.archive(lab.objects(case), case["base"], seed)
    if command := recipe(case):
        args, image = lab.docker(case, seed, online=True)
        ca = os.environ.get("BENCHMARK_CA_FILE")
        if ca:
            args += ["--mount", f"type=bind,src={Path(ca).resolve(strict=True)},dst=/prep-ca.pem,readonly",
                     "-e", "SSL_CERT_FILE=/prep-ca.pem", "-e", "PIP_CERT=/prep-ca.pem"]
        with (deps / "preparation.log").open("a") as out:
            lab.call(*args, image, "sh", "-ec", command, stdout=out, stderr=subprocess.STDOUT, timeout=1200)
    if case["id"] == "black":
        # hatch-vcs generates this module when building an installed Black distribution.
        (deps / "lib/_black_version.py").write_text("version = __version__ = '26.10.1'\n")
    (deps / "ready").write_text(image + "\n")


def dependency_digest(case):
    """Hash file contents, modes and symlink destinations, including unpacked dependency caches."""
    root = dependencies(case)
    h = hashlib.sha256()
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files + [d for d in dirs if (Path(base) / d).is_symlink()]):
            p = Path(base) / name
            if p == root / "preparation.log":
                continue
            h.update(str(p.relative_to(root)).encode() + b"\0" + str(p.lstat().st_mode).encode() + b"\0")
            if p.is_symlink():
                h.update(os.fsencode(os.readlink(p)))
            else:
                with p.open("rb") as f:
                    for block in iter(lambda: f.read(1048576), b""):
                        h.update(block)
            h.update(b"\0")
    return h.hexdigest()


def original_diff(case):
    return lab.call("git", "--git-dir", lab.objects(case), "diff", "--binary", "--no-ext-diff",
                    "--no-textconv", case["base"], case["gold"], capture_output=True).stdout


def worker_ids(case):
    base = lab.call("docker", "image", "inspect", "-f", "{{.Id}}", PANEL["images"][case["image"]],
                    capture_output=True, text=True).stdout.strip()
    images = {"toolchain": base, "worker": guest.image_id(case)}
    if COHORT and case["id"] == "ripgrep":
        images["grader"] = COHORT.profiler(sys.modules[__name__])
    return images


def version_digest():
    h = hashlib.sha256()
    for root in (HERE, WORKFLOW, *((COHORT.HERE,) if COHORT else ())):
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".md":
                h.update(str(p.relative_to(root.parent)).encode() + b"\0" + bytes.fromhex(sha(p)))
    h.update(bytes.fromhex(sha(HERE / "rubric.md")))
    return h.hexdigest()
