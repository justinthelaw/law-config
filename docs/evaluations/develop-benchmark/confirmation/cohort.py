"""Load the fresh repository tasks and run their grader-only operations."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
NAME = "pr-quality-confirmation-v1"
AUTHORITY = ("I waive interactive review of the local implementation plan and authorize you to proceed unattended. "
             "Follow all applicable repository requirements and complete any required independent review of "
             "consequential design or public contracts.")
ROWS = {v["id"]: v for v in json.loads((HERE / "fixtures.json").read_bytes())["cases"]}
RUNTIME = json.loads((HERE / "runtime.json").read_bytes())
BASELINE = {}


def load(panel):
    if set(ROWS) != set(RUNTIME) or set(ROWS) != {c["id"] for c in panel["cases"]} or len(ROWS) != 20:
        raise ValueError("confirmation requires the same twenty repositories")
    implementation = Path(__file__).read_bytes()
    cases = []
    for previous in panel["cases"]:
        key = previous["id"]
        source, control = ROWS[key], RUNTIME[key]
        if source["repository"] != previous["repo"] or source["pr"] == previous["pr"]:
            raise ValueError("invalid fresh repository or PR: " + key)
        probe = HERE / source["probe"]
        if probe.parent != HERE / "checks" or sha256(probe.read_bytes()).hexdigest() != control["active_probe_sha256"]:
            raise ValueError("fresh behavior probe changed: " + key)
        oracle = [source[field] for field in ("probe_build", "probe_run", "grader_only_reference_files")]
        oracle_hash = sha256(implementation + json.dumps(oracle, sort_keys=True).encode()).hexdigest()
        BASELINE[key] = previous
        authorship = {"fd": "upstream author discloses AI assistance", "pytest": "upstream author discloses AI generation",
                      "django": "upstream author reports no AI assistance"}.get(key, "assistance unverified")
        cases.append({**previous, **{f: source[f] for f in ("base", "gold", "pr", "prompt", "first_commit")},
                      **{f: control[f] for f in ("base_files", "base_bytes", "delta", "build", "native")},
                      "split": "confirmation", "independent": False, "complexity": None, "oracle_sha256": oracle_hash,
                      "merged": source["merged_at"],
                      "opened": source["created_at"], "authorship": authorship,
                      "legacy": previous.get("legacy", False) or key == "commander", "check": probe.name})
    return {**panel, "protocol": NAME, "cases": cases}


def upstream(key):
    row = ROWS[key]["upstream"]
    return {**row, "observed_at": RUNTIME[key]["observed_at"], "body_available": bool(row["body"])}


def profiler(engine):
    tag = "law-benchmark-ripgrep-profiler:confirmation-v1"
    if subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode:
        engine.lab.call("docker", "build", "--platform", "linux/amd64", "-t", tag,
                        "-f", HERE / "Dockerfile.profiler", HERE)
    return engine.lab.call("docker", "image", "inspect", "-f", "{{.Id}}", tag,
                           capture_output=True, text=True).stdout.strip()


def command(case):
    row = ROWS[case["id"]]
    path = HERE / row["probe"]
    return path, "/probe" + path.suffix, row["probe_run"]


def checks(engine, stage, case, work, folder):
    key = case["id"]
    row = ROWS[key]
    source, target, cmd = command(case)
    mounts = [(source, target)]
    for rel, digest in row["grader_only_reference_files"].items():
        destination = work / rel
        if destination.resolve() != destination or not destination.is_relative_to(work):
            raise ValueError("unsafe grader overlay: " + rel)
        data = subprocess.check_output(["git", "--git-dir", engine.lab.objects(case), "show", case["gold"] + ":" + rel])
        if sha256(data).hexdigest() != digest:
            raise ValueError("changed merged test: " + rel)
        reference = folder / (digest + ".go")
        with reference.open("xb") as output:
            output.write(data)
        mounts.append((reference, "/work/" + rel))
    if key == "commander":
        compiler = engine.dependencies(case) / "node_modules/typescript"
        locked = json.loads((work / "package-lock.json").read_bytes())["packages"]["node_modules/typescript"]["version"]
        if json.loads((compiler / "package.json").read_bytes())["version"] != locked:
            raise ValueError("unmatched TypeScript compiler")
        mounts.append((compiler, "/fixture-tool"))
    image = profiler(engine) if key == "ripgrep" else None
    results = {}
    if row["probe_build"]:
        results["oracle_build"] = stage(case, work, folder, "oracle_build", row["probe_build"],
                                        extra_mounts=mounts, toolchain=image, operation="build")
    for name in ("contract", "preserve"):
        if results.get("oracle_build", {}).get("exit", 0):
            results[name] = {"exit": None, "reason": "grader build failed"}
        else:
            results[name] = stage(case, work, folder, name, cmd, extra_mounts=mounts, toolchain=image)
    return results
