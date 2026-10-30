"""Preflight and resume the frozen native runner. Imported only for live operations."""
from pathlib import Path
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# The CLI script is also importable by the offline tests.
import benchmark as B

sys.path.insert(0, str(B.PANEL))
import campaign as C
import export_panel
import prepare
from verify_treatment import omissions, verify

E = C.E
RECIPE = B.HERE / "treatments/c619be0cc266/recipe.json"
CURRENT = B.HERE / B.read(B.HERE / "catalog.json")["current_treatment"]


def git(root, *args):
    return subprocess.check_output(["git", "-C", root, *args])


def full_recipe(package):
    if not re.fullmatch(r"[0-9a-f]{64}", package):
        raise ValueError("invalid base package hash")
    path = B.HERE / "treatments" / package[:12] / "recipe.json"
    recipe = B.read(path)
    if recipe["package_sha256"] != package or "base_package_sha256" in recipe:
        raise ValueError("a treatment delta requires one full base recipe")
    return path


def restore_source(recipe_path):
    recipe_path = recipe_path.resolve(strict=True)
    if not recipe_path.is_relative_to(B.HERE / "treatments") or recipe_path.name != "recipe.json":
        raise ValueError("select a versioned recipe under docs/evaluations/treatments")
    recipe = B.read(recipe_path)
    patch = recipe_path.parent / recipe["patch"]
    if (recipe["scope"] != "plugins/develop" or not re.fullmatch(r"[0-9a-f]{40}", recipe["git_base"])
            or patch.is_symlink() or patch.resolve().parent != recipe_path.parent or E.sha(patch) != recipe["patch_sha256"]):
        raise ValueError("recipe scope or patch differs")
    omitted = omissions(recipe)
    if "base_package_sha256" in recipe:
        dest = restore_source(full_recipe(recipe["base_package_sha256"]))
    else:
        dest = Path(tempfile.mkdtemp(prefix="reference-source-"))
        git(dest, "init", "--quiet")
        repository = git(B.ROOT, "rev-parse", "--show-toplevel").decode().strip()
        git(dest, "fetch", "--quiet", "--depth=1", repository, recipe["git_base"])
        if omitted:
            git(dest, "config", "core.sparseCheckout", "true")
            patterns = ["/.agents/plugins/marketplace.json", "/plugins/develop/"]
            patterns.extend("!/plugins/develop/" + p.as_posix() for p in omitted)
            (dest / ".git/info/sparse-checkout").write_text("\n".join(patterns) + "\n")
        git(dest, "checkout", "--quiet", "--detach", recipe["git_base"])
    git(dest, "apply", "--index", patch)
    verify(dest, recipe_path)
    return dest


def stage_source(source, pin):
    # The native installer enumerates its marketplace with Git. Give it a separate
    # source index, including intended new files and excluding removed files.
    source = source.resolve(strict=True)
    dest = Path(tempfile.mkdtemp(prefix="package-source-"))
    scope = "plugins/develop"
    listed = git(source, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", scope)
    files = []
    for rel in sorted({os.fsdecode(p) for p in listed.split(b"\0") if p}):
        path = source / rel
        if path.is_symlink() or path.resolve().parent != path.parent:
            raise ValueError(f"package source must be a regular file: {rel}")
        if path.exists():
            if not path.is_file():
                raise ValueError(f"unexpected package entry: {rel}")
            files.append(path)
    if E.host.package_hash(source / scope, files) != pin:
        raise ValueError("selected package differs from the treatment lock; select a matching checkout and lock")
    descriptor = source / ".agents/plugins/marketplace.json"
    source_def, = [p["source"] for p in B.read(descriptor)["plugins"] if p["name"] == "develop"]
    if descriptor.is_symlink() or source_def != {"source": "local", "path": "./plugins/develop"}:
        raise ValueError("unexpected marketplace source")
    for path in [*files, descriptor]:
        target = dest / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    git(dest, "init", "--quiet")
    git(dest, "add", "--", scope, ".agents/plugins/marketplace.json")
    return dest


def pinned_cli():
    try:
        cli = Path(os.environ["BENCHMARK_CODEX"]).resolve(strict=True)
        bwrap = cli.parent.parent / "codex-resources/bwrap"
    except (KeyError, FileNotFoundError):
        raise ValueError("set BENCHMARK_CODEX to the pinned native codex executable") from None
    if (not cli.is_file() or E.sha(cli) != E.host.CLI_SHA256
            or not bwrap.is_file() or E.sha(bwrap) != E.host.BWRAP_SHA256):
        raise ValueError("BENCHMARK_CODEX or its adjacent bwrap differs from the pinned Linux distribution")
    return cli


def preflight(plan=None):
    if plan is not None:
        C.verify_evaluator(plan)
    for tool in ("docker", "git", "taskset"):
        if not shutil.which(tool):
            raise ValueError(f"install {tool} before running a native evaluation")
    cli = pinned_cli()
    subprocess.run(["docker", "info", "--format", "{{.OSType}}"], stdout=subprocess.DEVNULL, check=True)
    default = CURRENT
    if plan:
        frozen = plan["runtime"]["treatment"]
        if frozen.get("companion"):
            import composite
            default = B.HERE / "treatments" / ("composite-" + composite.identity(frozen)) / "treatment.json"
        else:
            recipe_path = B.HERE / "treatments" / plan["runtime"]["package_sha256"][:12] / "recipe.json"
            if recipe_path.is_file():
                default = recipe_path.parent / B.read(recipe_path)["treatment_lock"]
    lock_path = Path(os.environ.get("PANEL_TREATMENT_LOCK", default)).resolve(strict=True)
    lock = B.read(lock_path)
    if plan and plan["runtime"]["treatment"] != lock:
        raise ValueError("the supplied treatment differs from the frozen plan")
    checkout = os.environ.get("PANEL_PLUGIN_CHECKOUT")
    recipe_path = B.HERE / "treatments" / lock["package_sha256"][:12] / "recipe.json"
    if checkout:
        source = Path(checkout)
    elif recipe_path.is_file():
        source = restore_source(recipe_path)
    else:
        source = B.ROOT
    index = stage_source(source, lock["package_sha256"])
    os.environ.update(PANEL_TREATMENT_LOCK=str(lock_path), PANEL_PLUGIN_CHECKOUT=str(index))
    if lock.get("companion"):
        import composite
        source = composite.prepare_source(B.STATE / "cache/superpowers-6.3.0.git", B.STATE / "volatile", lock["companion"])
        os.environ["PANEL_COMPANION_SOURCE"] = str(source)
    else:
        os.environ.pop("PANEL_COMPANION_SOURCE", None)
    C.controller.activate()
    home = Path(tempfile.mkdtemp(prefix="native-install-")) / "profile"
    home.mkdir(mode=0o700)
    (home / "config.toml").write_text('[features]\napps = false\nremote_plugin = false\n[plugins._default]\nenabled = false\n')
    installed = E.host.install(home, cli)
    work = home.parent / "work"
    work.mkdir()
    server = C.controller.STOCK(cli, home, work, time.monotonic() + 60)
    try:
        server.inventory(installed)
        if lock.get("companion"):
            import composite
            rows = server.rpc("skills/list", {"cwds":[str(work)]})["data"]
            skills = {s["name"]:s["path"] for row in rows for s in row["skills"] if s["enabled"]}
            markets = server.rpc("plugin/list", {"cwds":[str(work)], "marketplaceKinds":["local"]})["marketplaces"]
            active = [p["id"] for m in markets for p in m["plugins"] if p["installed"] and p["enabled"]]
            companion = home / "plugins/cache/superpowers-local/superpowers/6.3.0"
            composite.verify_component(companion, lock["companion"])
            composite.verify_inventory("develop", active, skills, installed, companion, lock["companion"]["skills"])
    finally:
        server.close()


def admitted(case):
    key = case["id"]
    fp, workers, deps = C.grading.fixture_hash(case), E.worker_ids(case), E.dependency_digest(case)
    for path in sorted((E.CACHE / "calibration" / key).glob("*/admission.json"), reverse=True):
        row = B.read(path)
        if not (row["passed"] and row["case"] == key and row["fingerprint"] == fp
                and row["workers"] == workers and row["deps_sha256"] == deps):
            continue
        C.verified_grade(C.receipt(path.parent / "base/grade.json"))
        gold = C.verified_grade(C.receipt(path.parent / "gold/grade.json"))
        if gold["applied"] and gold["replayed_tree"] == gold["target_tree"]:
            return True
    return False


def cold_passed(case):
    for path in sorted((E.CACHE / "cold" / case["id"]).glob("*/receipt.json"), reverse=True):
        row = B.read(path)
        if row.get("fixture_sha256") != (C.grading.fixture_hash(case) if case.get("loopback_hosts") else None):
            continue
        if not (row["passed"] and row["base"] == case["base"] and row["worker_image"] == E.guest.image_id(case)
                and row["build"] == case["build"] and row["native"] == E.guest.native_tests(case)):
            continue
        if row["case"] != case["id"] or not math.isfinite(row["seconds"]) or row["seconds"] <= 0:
            return False
        if row.get("source") == "verified original cold timing" and case.get("legacy"):
            state = E.ROOT / "tmp/six-repo-workflow"
            try:
                pin = B.read(state / "experiment/plan.json")["feasibility"][case["id"]]
                original = (state / pin["path"]).resolve(strict=True)
                if not original.is_relative_to(state) or E.sha(original) != pin["sha256"]:
                    return False
                expected = dict(B.read(original), source="verified original cold timing", original_sha256=pin["sha256"])
                return row == expected
            except (FileNotFoundError, KeyError):
                return False
        log = path.parent / "worker.log"
        return row.get("source") == "fresh" and log.is_file() and row.get("log_sha256") == E.sha(log)
    return False


def setup(cases=None):
    cases = E.CASES.values() if cases is None else cases
    prepare.prepare(cases)
    for case in cases:
        if not admitted(case):
            B.command(B.PANEL / "grading.py", case["id"])
        if not cold_passed(case):
            B.command(B.PANEL / "cold.py", case["id"])
            if not cold_passed(case):
                raise ValueError(f"no verified cold measurement for {case['id']}")


def finalize(name):
    state = B.status(name)
    if state["unreleased"] or state["assessments"].keys() - {"valid", "exhausted"}:
        print("Results are incomplete. Inspect status for unreleased or stranded slots.")
        return 3
    plan = C.plan_for(name)
    if "recovery" in plan:
        import recover_capacity
        recover_capacity.write_report(name)
    else:
        B.command(B.PANEL / "results.py", name)
    if state["unadjudicated"]:
        print("Review the flagged evidence, write adjudications and rerun report:", ", ".join(state["unadjudicated"]))
        return 3
    B.command(B.HERE / "develop-benchmark/diff_quality.py", name)
    target = export_panel.export(name, B.HERE / "runs")
    print(f"Verified {target}", flush=True)
    return 3 if state["allocated"] or state["assessments"].get("exhausted") else 0


def qualify_remaining(state):
    technical = (state["proposal_states"].get("blocked") or state["allocated"]
                 or state["assessments"].keys() & {"incomplete", "stranded", "exhausted"})
    if technical and (state["unreleased"] or state["pending_assessments"]):
        B.command(B.PANEL / "controller.py")


def run_primary(args, plan):
    root = C.run_dir(args.name)
    if plan and plan.get("recovery"):
        raise ValueError("use recover PARENT NAME for a recovery campaign")
    jobs = args.jobs if args.jobs is not None else (B.read(root / "lanes.json")["jobs"] if (root / "lanes.json").is_file() else 3)
    if (root / "lanes.json").is_file() and B.read(root / "lanes.json")["jobs"] != jobs:
        raise ValueError("resume with the original number of lanes")
    if jobs < 1 or 2 * jobs > len(os.sched_getaffinity(0)):
        raise ValueError("each lane requires two available CPUs")
    if not plan:
        setup()
        B.command(B.PANEL / "controller.py")
        plan = C.freeze(args.name)
    declared = export_panel.selection(root, plan)
    if not declared and args.split in ("tuning", "confirmation"):
        declared = export_panel.selection(root, plan, args.split)
    split = declared["split"] if declared else "all"
    if args.split and args.split != split:
        raise ValueError("resume with the original split")
    state = B.status(args.name)
    qualify_remaining(state)
    if state["unreleased"]:
        rc = B.command(B.PANEL / "campaign.py", "run", args.name, "--jobs", jobs, "--split", split, allow_partial=True)
        if rc:
            print("A proposal lane stopped. Inspect status and resume the same name before releasing more model calls.")
            return 3
    state = B.status(args.name)
    if state["pending_assessments"]:
        if split == "all":
            B.command(B.PANEL / "judge.py", args.name, "--jobs", jobs, allow_partial=True)
        else:
            todo = {slot.split("/")[0] for slot in state["pending_assessments"]}
            for case in state["cases"]:
                if case in todo and B.command(B.PANEL / "judge.py", args.name, "--case", case, "--jobs", jobs, allow_partial=True):
                    if B.status(args.name)["pending_assessments"]:
                        print("An assessor stopped. Inspect status and resume the same name.")
                        return 3
    return finalize(args.name)


def operate(args):
    sys.path.insert(0, str(B.HERE / "develop-benchmark"))
    root = C.run_dir(args.name)
    if not (root / "plan.json").exists() and root.exists():
        raise ValueError("run directory exists without a frozen plan; inspect it before continuing")
    plan = B.read(root / "plan.json") if root.exists() else None
    if args.action == "report" and plan is None:
        raise ValueError("no frozen plan for this name")
    parent = None
    if args.action == "recover":
        source = C.run_dir(args.parent) / "plan.json"
        parent = B.read(source)
        if args.parent == args.name or "recovery" in parent or (source.parent / "selected-split.json").exists():
            raise ValueError("capacity recovery requires a different, full primary campaign")
        if plan and plan.get("recovery", {}).get("parent_plan") != C.receipt(source):
            raise ValueError("recovery belongs to a different parent")
    preflight(plan or parent)
    frozen = plan or parent
    if frozen:
        frozen = C.plan_for(frozen["name"])
        for key in frozen["schedule"]:
            C.check_case(E.CASES[key], frozen)
    if args.action == "report":
        return finalize(args.name)
    from workers import manage
    with manage(args.name):
        if args.action == "recover":
            import recover_capacity
            if plan:
                state = B.status(args.name)
                if not (state["unreleased"] or state["pending_assessments"]):
                    return finalize(args.name)
                qualify_remaining(state)
            if not recover_capacity.run(args.parent, args.name, pause_on_block=True):
                return 3
            return finalize(args.name)
        return run_primary(args, plan)
