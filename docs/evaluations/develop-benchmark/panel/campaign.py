"""Freeze one paired panel, resume unreleased slots, and verify its immutable receipts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import composite
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller
import cold
import environment as E
import grading

PROMPT = ("Implement the following task in this checkout and add relevant tests. Use your natural "
          "local workflow and verification tools. Design and unattended implementation are approved. "
          "Work offline and leave the proposed changes in the checkout. In your final message, "
          "put a concise PR title on the first line, followed by a blank line and a PR body explaining "
          "the change, motivation, verification actually performed and any material gaps.\n\n")


def run_dir(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}", name):
        raise ValueError("invalid experiment name")
    return E.STATE / "runs" / name


def prompt(case):
    intro = PROMPT
    if E.COHORT:
        intro = intro.replace("Design and unattended implementation are approved.", E.COHORT.AUTHORITY)
    return intro + case["prompt"] + "\n\nAvailable offline verification commands:\n" + case["build"] + "\n" + E.guest.native_tests(case)


def complete_proposal(text):
    lines=text.strip().splitlines()
    return len(lines)>=3 and bool(lines[0].strip()) and not lines[1].strip() and any(s.strip() for s in lines[2:])


def receipt(path):
    return {"path":str(path.relative_to(E.STATE)), "sha256":E.sha(path)}


def verify_receipt(entry):
    path = E.STATE / entry["path"]
    if E.sha(path) != entry["sha256"]:
        raise ValueError(f"changed receipt {path}")
    return E.read(path)


def verified_grade(entry):
    grade = verify_receipt(entry)
    folder = E.STATE / grade["directory"]
    if folder / "grade.json" != E.STATE / entry["path"]:
        raise ValueError("grade location differs from its frozen receipt")
    if "apply_log_sha256" in grade and E.sha(folder/"apply.log")!=grade["apply_log_sha256"]:
        raise ValueError("patch application log changed")
    for stage, details in grade["stages"].items():
        if "log_sha256" in details and E.sha(folder / (stage+".log")) != details["log_sha256"]:
            raise ValueError(f"stage log changed: {folder}/{stage}")
    return grade


def latest_valid(folder, filename, valid):
    for p in sorted(folder.glob("*/" + filename), reverse=True):
        if valid(E.read(p)):
            return p
    raise ValueError(f"no qualifying {filename} under {folder}")


def qualifier(entry):
    qual=verify_receipt(entry)
    base=(E.STATE/entry["path"]).parent
    expected={f"{arm}/{name}" for arm in ("control","develop")
              for name in ("probe.json","inventory.json","hook-calls.log")}
    if set(qual["evidence"])!=expected:
        raise ValueError("qualification is missing a probe, inventory or hook dispatch record")
    for rel,checksum in qual["evidence"].items():
        if E.sha(base/rel)!=checksum:
            raise ValueError("qualification evidence changed: "+rel)
    from results import usage
    for arm in ("control","develop"):
        probe=E.read(base/arm/"probe.json")
        if not probe["passed"] or usage(probe)["coverage"]!="complete" or probe.get("final_phase")!="final_answer":
            raise ValueError("qualification has no terminal answer or incomplete token coverage: "+arm)
    if not qual["passed"] or qual["execution_boundary"]!=controller.execution_boundary():
        raise ValueError("qualification is stale")
    return qual


def runtime():
    lock=controller.select_treatment()
    return {"cli":E.sha(Path(os.environ["BENCHMARK_CODEX"]).resolve(strict=True)),
            "bwrap":E.sha(Path(os.environ["BENCHMARK_CODEX"]).resolve().parent.parent/"codex-resources/bwrap"),
            "package_sha256":lock["package_sha256"],
            "treatment":lock,
            "source_sha256":E.version_digest()}


def default_order(seed):
    rng=random.Random(seed)
    order={}
    schedule=[]
    parts={}
    for split in ("tuning","confirmation"):
        keys=[c["id"] for c in E.CASES.values() if c["split"]==split]
        rng.shuffle(keys)
        for i,k in enumerate(keys):
            order[k]=["control","develop"] if i%2==0 else ["develop","control"]
        parts[split]=keys
    while any(parts.values()):
        for keys in parts.values():
            if keys: schedule.append(keys.pop())
    return order,schedule


def freeze(name, seed=None, *, pilot=None):
    ident=runtime()
    if ident["cli"] != E.host.CLI_SHA256 or ident["bwrap"] != E.host.BWRAP_SHA256:
        raise ValueError("wrong executable")
    q = latest_valid(E.STATE/"qualification","qualification.json",
        lambda r:r["passed"] and r.get("execution_boundary")==controller.execution_boundary()
                 and r["controller_sha256"]==E.sha(E.HERE/"controller.py")
                 and composite.qualification_matches(r,ident["treatment"]) and r["python_worker"]==E.worker_ids(E.CASES["packaging"]))
    qualifier(receipt(q))
    seed=E.PANEL["seed"] if seed is None else seed
    order,schedule=default_order(seed)
    if pilot:
        key = pilot["case"]
        if E.CASES[key]["split"] != "tuning" or pilot["role"] not in ("candidate", "prior"):
            raise ValueError("a pilot requires a tuning case and named treatment")
        order = {key: order[key] if pilot["role"] == "candidate" else ["develop"]}
        schedule = [key]
    plan={"protocol":E.PANEL["protocol"],"name":name,"frozen_unix":time.time(),"runtime":ident,
          "qualification":receipt(q),"seed":seed,"order":order,"schedule":schedule,"references":{},
          "rubric_sha256":E.sha(E.HERE/"rubric.md"),"judge_rotations":3,
          "cost_usd_per_million":{"uncached_input":2,"cached_input":0.10,"output":10}}
    if pilot:
        plan["pilot"] = pilot
    for key in schedule:
        c=E.CASES[key]
        fp=grading.fixture_hash(c)
        worker=E.worker_ids(c)
        deps=E.dependency_digest(c)
        admit=latest_valid(E.CACHE/"calibration"/key,"admission.json",
             lambda r:r["passed"] and r["fingerprint"]==fp and r["workers"]==worker and r["deps_sha256"]==deps)
        cold_path=latest_valid(E.CACHE/"cold"/key,"receipt.json",lambda r:r["passed"] and r["base"]==c["base"]
                          and r["worker_image"]==worker["worker"] and r["build"]==c["build"] and r["native"]==E.guest.native_tests(c)
                          and r.get("fixture_sha256")== (fp if c.get("loopback_hosts") else None))
        plan["references"][key]={"admission":receipt(admit),"base_grade":receipt(admit.parent/"base/grade.json"),
             "gold_grade":receipt(admit.parent/"gold/grade.json"),"cold":receipt(cold_path),
             "deadline_seconds":cold.budget(E.read(cold_path)["seconds"]),"workers":worker,
             "deps_sha256":deps,"base":c["base"],"gold":c["gold"],"split":c["split"],
             "prompt_sha256":hashlib.sha256(prompt(c).encode()).hexdigest(),
             "merged_patch_sha256":hashlib.sha256(E.original_diff(c)).hexdigest()}
        check_case(c,plan,deps=False)
    dest=run_dir(name)
    plan["frozen_unix"]=time.time()
    dest.mkdir(parents=True,exist_ok=False)
    E.save(dest/"plan.json",plan)
    print("Frozen",name,E.sha(dest/"plan.json"),flush=True)
    return plan


def plan_for(name):
    path=run_dir(name)/"plan.json"
    plan=E.read(path)
    if plan["protocol"] != E.PANEL["protocol"]:
        raise ValueError(f"frozen protocol {plan['protocol']}; set DEVELOP_EVAL_COHORT={plan['protocol']} and resume {name}")
    if runtime()!=plan["runtime"] or plan["rubric_sha256"]!=E.sha(E.HERE/"rubric.md"):
        raise ValueError("frozen runtime or rubric differs; version a new experiment")
    qualification = qualifier(plan["qualification"])
    if not composite.qualification_matches(qualification, plan["runtime"]["treatment"]):
        raise ValueError("qualification does not match frozen treatment")
    return plan


def check_case(case, plan, deps=True):
    ref=plan["references"][case["id"]]
    adm=verify_receipt(ref["admission"])
    timing=verify_receipt(ref["cold"])
    if timing.get("fixture_sha256") != (grading.fixture_hash(case) if case.get("loopback_hosts") else None):
        raise ValueError("cold fixture changed: " + case["id"])
    if timing.get("log_sha256"):
        log=(E.STATE/ref["cold"]["path"]).parent/"worker.log"
        if E.sha(log)!=timing["log_sha256"]:
            raise ValueError("cold verification log changed: "+case["id"])
    verified_grade(ref["base_grade"])
    gold=verified_grade(ref["gold_grade"])
    if (not adm["passed"] or adm["fingerprint"]!=grading.fixture_hash(case)
            or not gold.get("applied") or gold["patch_sha256"]!=ref["merged_patch_sha256"]
            or gold["replayed_tree"]!=gold["target_tree"]
            or ref["workers"]!=E.worker_ids(case) or (deps and ref["deps_sha256"]!=E.dependency_digest(case))
            or hashlib.sha256(E.original_diff(case)).hexdigest()!=ref["merged_patch_sha256"]
            or hashlib.sha256(prompt(case).encode()).hexdigest()!=ref["prompt_sha256"]):
        raise ValueError("frozen fixture changed: "+case["id"])


def attempt(name, key, arm):
    case=E.CASES[key]
    plan=plan_for(name)
    if arm not in plan["order"].get(key, []):
        raise ValueError("attempt is outside the frozen scope")
    if pilot := plan.get("pilot"):
        register = E.read(E.STATE / "pilots" / pilot["name"] / "registration.json")
        if (register["plans"][pilot["role"]] != receipt(run_dir(name) / "plan.json")
                or register["case"] != key):
            raise ValueError("pilot plan differs from preregistration")
    check_case(case,plan)
    parent=run_dir(name)
    folder=parent/"attempts"/key/arm
    folder.parent.mkdir(parents=True,exist_ok=True)
    folder.mkdir()  # A prior allocation, including a partial one, is never rerun.
    budget=plan["references"][key]["deadline_seconds"]
    E.save(folder/"release.json",{"case":key,"arm":arm,"base":case["base"],"gold":case["gold"],"budget":budget,
           "plan_sha256":E.sha(parent/"plan.json"),"allocated_unix":time.time(),
           "controller_cpuset":sorted(os.sched_getaffinity(0)),"docker_cpuset":os.environ.get("PANEL_CPUSET")})
    (folder/"prompt.txt").write_text(prompt(case))
    start=time.monotonic()
    row={"case":key,"arm":arm,"state":"blocked","start_unix":time.time()}
    try:
        work=grading.snapshot(case,case["base"],Path(tempfile.mkdtemp(prefix="worker-")))
        starting=E.lab.git(work/".git","rev-parse","HEAD")
        def capture():
            E.native.collect_patch(case,folder,work,starting)
            submission={"patch_sha256":E.sha(folder/"candidate.patch"),"proposal_sha256":E.sha(folder/"proposal.md"),
                        "captured_unix":time.time(),"proposal_wall_seconds":time.monotonic()-start}
            E.save(folder/"submission.json",submission)
            row.update(submission)
        observed=E.native.native(case,arm,folder,work,prompt(case),budget=budget,capture=capture)
        E.save(folder/"native.json",observed)
        row.update(observed)
        row["hook_attestation"]=controller.verify_hooks(folder,observed,arm)
        patch=folder/"candidate.patch"
        if patch.exists():
            row["patch_sha256"]=E.sha(patch)
        if patch.exists() and patch.stat().st_size:
            t=time.monotonic()
            grade=grading.grade(case,case["base"],folder/"grade",patch)
            row["grading_seconds"]=time.monotonic()-t
            row["grade"]=receipt(folder/"grade/grade.json")
        row["workspace"]=str(work.relative_to(E.STATE))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as err:
        row.update(state="blocked",error=str(err))
    row["end_to_end_seconds"]=time.monotonic()-start
    E.save(folder/"result.json",row)
    print(key,arm,row["state"],round(row.get("proposal_wall_seconds") or 0),flush=True)
    return row


def read_attempt(name, key, arm):
    folder=run_dir(name)/"attempts"/key/arm
    if not folder.exists():
        return {"state":"unreleased"}
    try:
        release=E.read(folder/"release.json")
    except (FileNotFoundError,json.JSONDecodeError):
        return {"case":key,"arm":arm,"state":"interrupted","error":"allocation has no complete release receipt"}
    plan_hash=E.sha(run_dir(name)/"plan.json")
    if (release["case"],release["arm"],release["plan_sha256"])!=(key,arm,plan_hash):
        raise ValueError("release attribution mismatch")
    if not (folder/"result.json").exists():
        row={"case":key,"arm":arm,"state":"interrupted","release":release,"start_unix":release["allocated_unix"]}
        if (folder/"native.json").is_file():
            row.update(E.read(folder/"native.json"),state="interrupted")
        if (folder/"submission.json").is_file():
            row.update(E.read(folder/"submission.json"))
            for field,file in (("patch_sha256","candidate.patch"),("proposal_sha256","proposal.md")):
                if row[field]!=E.sha(folder/file):
                    raise ValueError("interrupted submission changed: "+key)
            grade_path=folder/"grade/grade.json"
            if grade_path.is_file():
                row["grade"]=receipt(grade_path)
                if verified_grade(row["grade"])["patch_sha256"]!=row["patch_sha256"]:
                    raise ValueError("interrupted grade belongs to another submission")
        return row
    row=E.read(folder/"result.json")
    if (row["case"],row["arm"])!=(key,arm):
        raise ValueError("result attribution mismatch")
    for field,file in (("patch_sha256","candidate.patch"),("proposal_sha256","proposal.md")):
        if field in row and row[field]!=E.sha(folder/file):
            raise ValueError("submission bytes changed: "+key)
    if (folder/"submission.json").is_file() and any(row.get(k)!=v for k,v in E.read(folder/"submission.json").items()):
        raise ValueError("sealed proposal record changed: "+key)
    if (folder/"native.json").is_file():
        obs=E.read(folder/"native.json")
        for field,value in obs.items():
            if field not in {"state","error"} and row.get(field)!=value:
                raise ValueError("native measurement changed: "+key+" "+field)
        if row["state"]!="blocked" and (row["state"],row.get("error"))!=(obs["state"],obs.get("error")):
            raise ValueError("native outcome changed: "+key)
    if row.get("grade"):
        grade=verified_grade(row["grade"])
        if grade["patch_sha256"] != row["patch_sha256"]:
            raise ValueError("graded patch mismatch")
    return row


def launcher_active(name):
    with (run_dir(name)/"launcher.lock").open("a+") as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_SH|fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def case_lanes(plan, jobs):
    """Spread long cases across lanes, retaining the frozen schedule order within each lane."""
    schedule=plan["schedule"]
    durations={key:plan["references"][key]["deadline_seconds"] for key in schedule}
    loads=[0]*jobs
    assignments={}
    for key in sorted(schedule,key=durations.get,reverse=True):
        index=min(range(jobs),key=loads.__getitem__)
        assignments[key]=index
        loads[index]+=durations[key]
    return [[key for key in schedule if assignments[key]==index] for index in range(jobs)]


def run_panel(name, jobs=2, split="all"):
    parent=run_dir(name)
    plan=plan_for(name)
    cpus=sorted(os.sched_getaffinity(0))
    if jobs<1 or 2*jobs>len(cpus):
        raise ValueError("each lane requires two distinct CPUs")
    lanes=case_lanes(plan,jobs)
    def lane(index):
        pair=cpus[2*index:2*index+2]
        for key in lanes[index]:
            if split!="all" and E.CASES[key]["split"]!=split:
                continue
            for arm in plan["order"][key]:
                before=read_attempt(name,key,arm)
                if before["state"]!="unreleased":
                    continue
                env=dict(os.environ,PANEL_CPUSET=",".join(str(i) for i in pair))
                cmd=["taskset","-c",env["PANEL_CPUSET"],sys.executable,"-B",__file__,"attempt",name,key,arm]
                res=subprocess.run(cmd,env=env)
                if res.returncode: return False
                if read_attempt(name,key,arm)["state"]=="blocked": return False
        return True
    with (parent/"launcher.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        layout={"jobs":jobs,"cpu_pairs":[cpus[2*i:2*i+2] for i in range(jobs)],"queues":lanes}
        if (parent/"lanes.json").exists():
            if E.read(parent/"lanes.json")!=layout:
                raise ValueError("resume with the original CPU pairs and concurrency")
        else:
            E.save(parent/"lanes.json",layout)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            return all(list(pool.map(lane,range(jobs))))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="action",required=True)
    freeze_p=sub.add_parser("freeze");freeze_p.add_argument("name");freeze_p.add_argument("--seed",type=int)
    run_p=sub.add_parser("run");run_p.add_argument("name");run_p.add_argument("--jobs",type=int,default=2)
    run_p.add_argument("--split",choices=("all","tuning","confirmation"),default="all")
    trial_p=sub.add_parser("attempt");trial_p.add_argument("name");trial_p.add_argument("key",choices=E.CASES)
    trial_p.add_argument("arm",choices=("control","develop"))
    args=parser.parse_args()
    controller.activate()
    if args.action=="freeze":freeze(args.name,args.seed)
    elif args.action=="run":raise SystemExit(0 if run_panel(args.name,args.jobs,args.split) else 2)
    else:attempt(args.name,args.key,args.arm)
