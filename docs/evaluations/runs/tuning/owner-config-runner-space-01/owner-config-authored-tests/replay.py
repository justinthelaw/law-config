"""Reconstruct or replay the configuration assay using an ordinary prepared cache."""

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SUBJECTS = {"pure", "prior", "candidate", "base", "merged"}
CASES = {
    "requested", "old-active-no-decoy", "wrong-inactive-decoy",
    "harmless-empty-env", "old-markdownlint",
}
ROUTES = {"direct", "configured-node-discovery"}
CPUS = (0, 1)


class ReplayError(ValueError):
    """Invalid input or a result that differs from the recorded observation."""


def require(condition, message):
    if not condition:
        raise ReplayError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_assessor():
    spec = importlib.util.spec_from_file_location("configuration_assay", HERE / "assay.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def verify_inputs(result_path):
    manifest = read_json(HERE / "manifest.json")
    for name, checksum in manifest["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts,
                f"Unsafe manifest path: {name}")
        require(sha(HERE / relative) == checksum, f"Kit file checksum differs: {name}")
    supplement = read_json(HERE / "supplement.json")
    binding = supplement["bindings"]
    record = read_json(result_path)
    require(record["format"] == "law-config.eval-pilot/v1"
            and record["name"] == "owner-config-runner-space-01",
            "Expected the owner-config-runner-space-01 normal pilot result")
    registration = (json.dumps(record["registration"], indent=2) + "\n").encode()
    require(hashlib.sha256(registration).hexdigest()
            == record["registration_sha256"] == binding["registration_sha256"],
            "Pilot registration checksum differs")
    require(record["result_sha256"] == binding["raw_result_sha256"],
            "Pilot result is not the sealed assay result")
    require(record["registration"]["hypothesis_sha256"] == binding["hypothesis_sha256"],
            "Pilot hypothesis checksum differs")
    for filename, key in (("assay.py", "assay_sha256"),
                          ("validate-controls.mjs", "validator_sha256")):
        require(sha(HERE / filename) == binding[key], f"Assessor checksum differs: {filename}")
    require(set(supplement["subjects"]) == SUBJECTS, "Expected all five source subjects")
    expected = {(subject, case, route)
                for subject in SUBJECTS for case in CASES for route in ROUTES}
    observed = [(row["subject"], row["case"], row["route"])
                for row in supplement["routes"]]
    require(len(observed) == 50 and set(observed) == expected,
            "Supplement must contain every subject/control/route exactly once")
    return record, supplement


def create_output(path):
    output = path.resolve()
    require(output != HERE and HERE not in output.parents,
            "Choose a new output outside the immutable replay kit")
    require(not output.exists(), f"Output already exists: {output}")
    output.mkdir(parents=True)
    environment = output / "environment"
    environment.mkdir()
    for key in ("TMPDIR", "TMP", "TEMP", "XDG_CACHE_HOME"):
        os.environ[key] = str(environment)
    return output


def patch_for(record, subject):
    if subject == "base":
        return None
    if subject == "prior":
        return record["prior_develop"]
    role = {"pure": "control", "candidate": "develop", "merged": "upstream"}[subject]
    return record["submissions"][role]


def git_command(bare, environment, *arguments, input_bytes=None):
    command = ["git", "--git-dir=" + str(bare), "-c", "core.hooksPath=/dev/null", *arguments]
    result = subprocess.run(command, env=environment, input=input_bytes,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0,
            f"Git {' '.join(arguments)} failed: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def safe_source_path(destination, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts,
            f"Unsafe tracked source path: {relative}")
    current = destination
    for part in path.parts[:-1]:
        current = current / part
        require(not current.is_symlink(), f"Tracked source traverses a symlink: {relative}")
    return destination / path


def reconstruct(record, supplement, bare, output, assessor):
    bare = bare.resolve()
    require((bare / "objects").is_dir(), f"Expected a prepared bare Git cache: {bare}")
    base_environment = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                            GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1",
                            GIT_OPTIONAL_LOCKS="0")
    subjects = []
    observations = {}
    for name, metadata in supplement["subjects"].items():
        objects = output / "objects" / name
        objects.mkdir(parents=True)
        environment = dict(base_environment, GIT_OBJECT_DIRECTORY=str(objects),
                           GIT_ALTERNATE_OBJECT_DIRECTORIES=str(bare / "objects"),
                           GIT_INDEX_FILE=str(output / (name + ".index")))

        def git(*arguments, input_bytes=None):
            return git_command(bare, environment, *arguments, input_bytes=input_bytes)

        git("read-tree", record["base"])
        patch = patch_for(record, name)
        if patch is None:
            require(metadata["sealed_patch_sha256"] is None, "Base unexpectedly requires a patch")
        else:
            patch_bytes = patch["patch"].encode()
            require(hashlib.sha256(patch_bytes).hexdigest()
                    == patch["patch_sha256"] == metadata["sealed_patch_sha256"],
                    f"Sealed patch checksum differs: {name}")
            git("apply", "--cached", "--binary", "--whitespace=nowarn", "-",
                input_bytes=patch_bytes)
        tree = git("write-tree").decode().strip()
        require(tree == metadata["git_tree"], f"Reconstructed Git tree differs: {name}")
        destination = output / "sources" / name
        destination.mkdir(parents=True)
        for entry in git("ls-files", "--stage", "-z").split(b"\0"):
            if not entry:
                continue
            header, raw_path = entry.split(b"\t")
            mode, blob, stage = header.decode().split()
            require(stage == "0", f"Unmerged source entry: {name}")
            relative = os.fsdecode(raw_path)
            target = safe_source_path(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not target.exists() and not target.is_symlink(),
                    f"Repeated tracked source entry: {relative}")
            data = git("cat-file", "blob", blob)
            if mode == "120000":
                target.symlink_to(os.fsdecode(data))
            else:
                require(mode in ("100644", "100755"), f"Unsupported Git mode: {mode}")
                target.write_bytes(data)
        for path in sorted(destination.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_symlink():
                continue
            kind = "directory" if path.is_dir() else "file"
            modes = metadata["source_modes"][kind]
            mode = modes["overrides"].get(str(path.relative_to(destination)), modes["default"])
            path.chmod(int(mode, 8))
        identity = assessor.identity(destination)
        require(identity["sha256"] == metadata["source_identity_sha256"],
                f"Reconstructed byte/mode/link identity differs: {name}")
        observations[name] = {"git_tree": tree, "source_sha256": identity["sha256"],
                              "exact_byte_mode_link_identity_matches": True}
        subjects.append({"name": name, "source": str(destination),
                         "source_sha256": identity["sha256"], "tree_sha256": identity["sha256"]})
    return subjects, observations


@contextmanager
def cpu_lease(output, shared_state):
    import fcntl

    require(hasattr(os, "sched_setaffinity"), "Assay execution requires Linux CPU affinity")
    require(set(CPUS) <= os.sched_getaffinity(0), "Assay CPUs 0,1 are unavailable")
    if shared_state is not None:
        shared_state = shared_state.resolve()
        require(not (shared_state / "operator.lock").exists(),
                "Wait for the registered benchmark operator to finish before standalone replay")
    locks = (shared_state or output) / "cpu-leases"
    locks.mkdir(parents=True, exist_ok=True)
    groups = {Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list")
              .read_text().strip() for cpu in CPUS}
    previous_affinity = os.sched_getaffinity(0)
    with ExitStack() as stack:
        for group in sorted(groups):
            stream = stack.enter_context((locks / (group + ".lock")).open("a"))
            fcntl.flock(stream, fcntl.LOCK_EX)
        os.sched_setaffinity(0, set(CPUS))
        try:
            yield
        finally:
            os.sched_setaffinity(0, previous_affinity)


def validate_replay(results, supplement):
    require({subject["name"] for subject in results} == SUBJECTS and len(results) == 5,
            "Replay did not record all five subjects")
    expected_rows = {(row["subject"], row["case"], row["route"]): row
                     for row in supplement["routes"]}
    for subject in results:
        name = subject["name"]
        require(subject["status"] == "recorded", f"Assay did not complete: {name}")
        require(subject["owned_restored"] and subject["source_unchanged"]
                and subject["source_full_tree_unchanged"], f"Assay source changed: {name}")
        require(set(subject["routes"]) == CASES, f"Missing assay control: {name}")
        selected = supplement["subjects"][name]["selected_test_names"]
        for case, case_result in subject["routes"].items():
            require(set(case_result["routes"]) == ROUTES, f"Missing execution route: {name}/{case}")
            for route, value in case_result["routes"].items():
                expected = expected_rows[name, case, route]
                require(value["exit"] == expected["exit"] and not value["timeout"]
                        and value["tree_before_sha256"] == value["tree_after_sha256"],
                        f"Execution or source integrity differs: {name}/{case}/{route}")
                require(value["status"] == expected["status"]
                        and value["tests"] == expected["counts"]["tests"]
                        and value["failed_tests"] == expected["failed_tests"]
                        and value["skipped_count"] == expected["counts"]["skipped"]
                        and len(value["failed_tests"]) == expected["counts"]["fail"]
                        and value["tests"] - value["skipped_count"] - len(value["failed_tests"])
                        == expected["counts"]["pass"],
                        f"Assay outcome differs: {name}/{case}/{route}")
                require(set(selected) == set(value["relevant_test_names"])
                        and value["relevant_executed_inclusion"],
                        f"Relevant discovery differs: {name}/{case}/{route}")
                actual = {test: "fail" if test in value["failed_tests"] else "pass"
                          for test in value["executed_test_names"]}
                require(all(test in actual for test in selected)
                        and [actual[test] for test in selected] == expected["selected_test_states"],
                        f"Selected test statuses differ: {name}/{case}/{route}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path, help="Normal published pilot result.json")
    parser.add_argument("--git-dir", required=True, type=Path, help="Prepared runner-space bare Git cache")
    parser.add_argument("--output", required=True, type=Path, help="New ignored task output directory")
    parser.add_argument("--execute", action="store_true", help="Execute all 50 assay routes after reconstruction")
    parser.add_argument("--dependencies", type=Path, help="Prepared pinned dependency directory")
    parser.add_argument("--lease-state", type=Path, help="Shared panel state for physical CPU leases")
    arguments = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    if arguments.execute and arguments.dependencies is None:
        parser.error("--execute requires --dependencies")
    try:
        record, supplement = verify_inputs(arguments.result)
        assessor = load_assessor()
        output = create_output(arguments.output)
        subjects, identities = reconstruct(record, supplement, arguments.git_dir, output, assessor)
        save_json(output / "reconstruction.json", {
            "kit_manifest_sha256": sha(HERE / "manifest.json"),
            "published_result_sha256": sha(arguments.result), "roles": identities,
            "provider_calls": 0, "assay_rerun": arguments.execute,
        })
        if not arguments.execute:
            print("Verified all five Git trees and byte/mode/link identities. No tests executed.")
            return
        assessor.HERE = output
        shutil.copyfile(HERE / "validate-controls.mjs", output / "validate-controls.mjs")
        with cpu_lease(output, arguments.lease_state):
            runtime = assessor.Docker(arguments.dependencies,
                                      supplement["replay_environment"]["dependency_tree_sha256"])
            results = [assessor.assess(subject, output / "runs" / subject["name"], runtime,
                                       assessor.CASES) for subject in subjects]
            require(assessor.identity(runtime.dependencies) == runtime.identity,
                    "Shared dependency cache changed during replay")
        validate_replay(results, supplement)
        save_json(output / "replay-receipt.json", {
            "kit_manifest_sha256": sha(HERE / "manifest.json"), "subjects": results,
            "all_50_outcomes_match": True, "provider_calls": 0,
        })
        print("All 50 assay outcomes and selected named-test statuses match.")
    except (ReplayError, OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"replay: {error}\n")


if __name__ == "__main__":
    main()
