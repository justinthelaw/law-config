"""Regressions for portable scoring, artifact integrity and comparison eligibility."""
import copy
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
sys.path.insert(0, str(ROOT/"develop-benchmark"))
import records
import diff_quality as D
import export_panel as exporter

R = D.R
HASH = "a"*64
GIT = "f"*40


def sample(temp, interrupted=False):
    rows, native, cases = [], [], []
    for index, key in enumerate(("full","partial")):
        case = {"case":key,"split":"tuning","stratum":"external","assessors":[0,1,2]}
        for role_index, role in enumerate(records.ROLES):
            patch = f"patch {key} {role}\n"
            proposal = f"Title {key} {role}\n\nChecks performed."
            vals = {"control":[1,3,4],"develop":[2,4,3],"upstream":[3,3,3]}[role]
            judgments = []
            for rotation, contract in enumerate(vals):
                anchors = dict(contract=contract,tests=3,design=3,proposal=3)
                judgments.append(dict(rotation=rotation,label="ABC"[(role_index+rotation)%3],scores=anchors,
                    evidence={k:"Synthetic parity fixture" for k in anchors},flags=[],confidence="medium"))
            axes = {axis:statistics.median(j["scores"][axis] for j in judgments) for axis in D.R.J.AXES}
            review = {"axes":axes,"judgments":judgments,"score":R.weighted(axes)}
            native_role = {"state":"merged" if role=="upstream" else "completed","status":"ready","review":review}
            available = not (key=="partial" and role=="develop")
            if interrupted and not available:
                native_role.update(state="interrupted",status="unavailable")
            tokens = {k:0 for k in R.TOKENS};tokens.update(inputTokens=1000,cachedInputTokens=600,outputTokens=100,totalTokens=1100)
            native_role.update(coverage="complete" if available else "lower bound",tokens=tokens,
                usd_estimate=.00186,proposal_wall_seconds=100+10*role_index,wall_seconds=90+10*role_index,
                end_to_end_seconds=110+10*role_index)
            case[role] = native_role
            diff = D.diff(native_role)
            psha = records.digest(patch.encode()); ptext = records.digest(proposal.encode())
            rows.append({"format":"law-config.eval-submission/v1","plan_sha256":HASH,"case_id":key,"role":role,
                "state":native_role["state"],"readiness":native_role["status"],"executable_pass":native_role["status"]=="ready",
                "failure_kind":"interrupted" if native_role["state"]=="interrupted" else None,
                "stages":{k:{"exit":0,"log_sha256":HASH,"reason":None,"command":"check"}
                          for k in ("build","native","contract","preserve")},
                "patch":patch,"patch_sha256":psha,"proposal":proposal,"proposal_sha256":ptext,"proposal_observation":"present",
                "bindings":{"grade_patch_sha256":psha,"judges":[{"rotation":j["rotation"],"label":j["label"],
                    "patch_sha256":psha,"proposal_sha256":ptext,**{name:HASH for name in
                    ("judgment_sha256","mapping_sha256","assessor_sha256","packet_sha256","prompt_sha256")}} for j in judgments]},
                "quality":{"axes":axes,"proposal_points_100":review["score"],"diff_points_85":diff["points"],
                           "rotation_points_85":{str(k):v for k,v in diff["rotations"].items()},"assessments":judgments},
                "adjudication":None,"receipt_sha256":{"grade":HASH},"effort":None if role=="upstream" else {
                    "coverage":native_role["coverage"],"tokens":tokens,"estimated_usd":native_role["usd_estimate"],
                    "billed_usd":None,"checkout_to_proposal_seconds":native_role["proposal_wall_seconds"],
                    "prompt_to_terminal_seconds":native_role["wall_seconds"],"through_grading_seconds":native_role["end_to_end_seconds"],
                    "setup_seconds":1,"grading_seconds":10,"thread_count":1,"child_count":0,"root_tokens":tokens,
                    "descendant_tokens":{},"observed_commands":1,"native_hook_receipts":0}})
        case["pairs"]={a+"_"+b:R.pair_quality(a,b,case) for a,b in R.PAIRS};native.append(case)
        cases.append({"id":key,"repo":"sample/"+key,"pr":index+1,"base":GIT,"merged":GIT,"split":"tuning",
            "stratum":"external","language":"Python","domain":"test","complexity":None,"prompt":"Synthetic fixture",
            "first_commit":"2026-10-21","authorship":"synthetic","base_files":1,"base_bytes":20,
            "pr_delta":[1,1,1],"pr_open_to_merge_seconds":70,"controls":{"fixture_sha256":HASH,"cpu_pair":[0,1],
            "prompt_sha256":HASH,"merged_patch_sha256":records.digest(f"patch {key} upstream\n".encode()),"dependencies_sha256":HASH,"workers":{"toolchain":HASH,"worker":HASH},
            "deadline_seconds":300,"arm_order":["control","develop"],"build":"build","worker_native":"test","grader_native":"test","independent_check":False},
            "comparison":dict(case["pairs"],diff_85={a+"_"+b:D.compare(case,a,b) for a,b in R.PAIRS}),
            "judge_attempts":[{"coverage":"complete","tokens":tokens,"threads":1,"usd_estimate":.00186,
                "rotation":r,"attempt":0,"native_sha256":HASH,"accepted":True,"state":"completed",
                "wall_seconds":10,"limitations":[]} for r in range(3)]})
    run = {"format":"law-config.eval-run/v1","protocol":"synthetic-parity","name":"test","plan_sha256":HASH,
        "cohort":"primary","selection":None,"parent_plan_sha256":None,"frozen_unix":1,"runtime":{"source_sha256":HASH,
        "implementation_sha256":HASH,"package_sha256":HASH,"cli_sha256":HASH,"bwrap_sha256":HASH,"treatment":{},
        "model":"synthetic","effort":"medium","seed":42,"rubric_sha256":HASH,"qualifier":HASH,
        "rates_usd_per_million":{"uncached_input":2,"cached_input":.1,"output":10},"executor":{"cpus_per_worker":2,"memory":"4g","lanes":3,
        "boundary":{},"managed_hooks":{},"judge":{"model":"synthetic","effort":"medium","rotations":3,"entrypoint_sha256":HASH,"max_attempts_per_rotation":2}}},
        "cases":cases,"groups":{"all":R.group(native)},"evaluator":{"attempts":6,"complete_receipts":6,"observed_usd":.00186*6},"campaign_elapsed_seconds":None,
        "submission_span_seconds":None,"observations":[],"source":{}}
    run["groups"]["all"]["code_and_tokens"] = records.code_and_tokens(
        [c["id"] for c in cases], {(r["case_id"],r["role"]):r for r in rows})
    write(temp,run,rows)
    return run, rows


def write(folder, run, rows):
    blob="".join(json.dumps(r)+"\n" for r in rows).encode()
    (folder/"submissions.jsonl").write_bytes(blob)
    run["submissions"]={"path":"submissions.jsonl","rows":len(rows),"sha256":records.digest(blob)}
    (folder/"run.json").write_text(json.dumps(run))


class PortableRecords(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.run, self.rows = sample(self.path)

    def test_pilot_hard_gate_win_can_tie_the_blind_rubric(self):
        arms = {row["role"]: row for row in self.rows if row["case_id"] == "full"}
        control, develop = arms["control"], arms["develop"]
        control["readiness"] = "failed"
        develop["quality"] = copy.deepcopy(control["quality"])
        develop["effort"]["estimated_usd"] = control["effort"]["estimated_usd"]
        pair = records.proposal_verdict(develop, control, 3)
        record = {"submissions": arms, "comparisons": {"develop_control": pair}}
        self.assertTrue(records.strict_win(control, develop, pair["verdict"], [0, 1, 2]))
        signal = records.pilot_quality_signal(record)
        self.assertEqual(signal["readiness_first_pair"]["reason"], "hard gates")
        self.assertEqual(signal["blinded_full_pr"]["verdict"], "tie")
        self.assertIs(signal["ready_blind_win_at_no_more_cost"], False)
        develop["readiness"] = "pending"
        self.assertIsNone(records.pilot_quality_signal(record)["ready_blind_win_at_no_more_cost"])
        develop["proposal"] = ""
        self.assertIsNone(records.pilot_quality_signal(record)["blinded_full_pr"]["verdict"])
        develop["effort"]["coverage"] = "lower bound"
        self.assertIsNone(records.pilot_quality_signal(record)["equal_or_lower_complete_cost"])

    def test_control_headroom_respects_rotations_readiness_and_metering(self):
        row = next(r for r in self.rows if r["role"] == "control")
        for j in row["quality"]["assessments"]:
            j["scores"] = {"contract": 4, "tests": 4, "design": 4, "proposal": 3}
        self.assertEqual(records.control_headroom(row)["maximum_median_lead"], 3.75)
        self.assertEqual(records.control_headroom(row)["strict_win_route"], "score ceiling")
        row["readiness"] = "failed"
        self.assertEqual(records.control_headroom(row)["strict_win_route"], "hard gates")
        row["effort"]["coverage"] = "lower bound"
        self.assertEqual(records.control_headroom(row)["strict_win_route"], "unresolved")
        row["quality"]["assessments"].pop()
        self.assertIsNone(records.control_headroom(row)["maximum_median_lead"])

    def test_parity_and_offline_reader(self):
        m, rows = records.read_bundle(self.path/"run.json")
        a,b = rows["full","develop"],rows["full","control"]
        self.assertEqual(a["quality"]["diff_points_85"] - b["quality"]["diff_points_85"],0)
        self.assertEqual(records.within_panel_diff(a,b), {"delta":8.75,"reversal":True})
        self.assertEqual(m["cases"][0]["comparison"]["diff_85"]["develop_control"],records.within_panel_diff(a,b))
        self.assertEqual(m["groups"]["all"]["paired"]["usd_estimate"]["pairs"],1)
        self.assertEqual(m["groups"]["all"]["paired"]["proposal_wall_seconds"]["pairs"],2)
        env=dict(os.environ,PATH="",DOCKER_HOST="unix:///no-such-docker")
        env.pop("BENCHMARK_CODEX",None)
        subprocess.run([sys.executable,"-B",str(ROOT/"tools/records.py"),"validate",str(self.path/"run.json")],
                       cwd=self.path,env=env,check=True,capture_output=True)

    def test_confirmation_excludes_incomplete_cost_and_rejects_control_plugins(self):
        self.run["protocol"] = "pr-quality-confirmation-v1"
        for case in self.run["cases"]:
            profiles = {}
            for row in self.rows:
                if row["case_id"] != case["id"] or row["role"] == "upstream":
                    continue
                row["receipt_sha256"].update({"inventory":HASH, "turn-input":HASH})
                profiles[row["role"]] = {"inventory_sha256":HASH, "turn_sha256":HASH, "ephemeral":False, "apps":[], "mcp":[],
                                         "global_instructions":[], "plugins":[] if row["role"] == "control" else ["develop@law-config"]}
            case["comparison"]["confirmation"] = {"win":case["id"] == "full", "profiles":profiles}
        write(self.path,self.run,self.rows)
        records.read_bundle(self.path/"run.json")
        self.run["cases"][0]["comparison"]["confirmation"]["profiles"]["control"]["plugins"] = ["develop@law-config"]
        write(self.path,self.run,self.rows)
        with self.assertRaisesRegex(ValueError, "stock profile"):
            records.read_bundle(self.path/"run.json")

    def test_corruption_and_bad_aggregate(self):
        def corrupt(row, change):
            data=copy.deepcopy(row);change(data);return data
        for mutate in (lambda r:r.update(patch="invalid"),lambda r:r["bindings"].update(grade_patch_sha256="d"*64),
                       lambda r:r["bindings"]["judges"][0].update(proposal_sha256="c"*64)):
            rows=copy.deepcopy(self.rows);rows[0]=corrupt(rows[0],mutate)
            write(self.path,self.run,rows)
            with self.assertRaises(ValueError):
                records.read_bundle(self.path/"run.json")
        self.run["groups"]["all"]["paired"]["usd_estimate"]["pairs"]=2
        write(self.path,self.run,self.rows)
        with self.assertRaisesRegex(ValueError,"eligible pair count"):
            records.read_bundle(self.path/"run.json")

    def test_flagged_submission_requires_a_ruling(self):
        row = self.rows[0]
        row["quality"]["assessments"][0]["flags"] = ["critical test finding"]
        write(self.path, self.run, self.rows)
        with self.assertRaisesRegex(ValueError, "no substantiated adjudication"):
            records.read_bundle(self.path/"run.json")
        row["adjudication"] = {"resolution":"cleared","evidence":"Known behavior on the starting tree"}
        write(self.path, self.run, self.rows)
        records.read_bundle(self.path/"run.json")

    def test_wrong_ready_state_and_swapped_verdicts(self):
        run, rows = sample(self.path, interrupted=True)
        rows[0]["adjudication"] = {"resolution":"confirmed","evidence":"reproduced a compatibility regression"}
        write(self.path,run,rows)
        with self.assertRaisesRegex(ValueError,"readiness contradicts"):
            records.read_bundle(self.path/"run.json")
        rows[0]["adjudication"] = None
        build = rows[0]["stages"].pop("build")
        write(self.path,run,rows)
        with self.assertRaisesRegex(ValueError,"contradicts required stages"):
            records.read_bundle(self.path/"run.json")
        rows[0]["stages"]["build"] = build
        a,b = [c["comparison"] for c in run["cases"]]
        key = "develop_control"
        self.assertNotEqual(a[key]["verdict"],b[key]["verdict"])
        a[key], b[key] = b[key], a[key]
        write(self.path,run,rows)
        with self.assertRaisesRegex(ValueError,"full proposal verdict differs"):
            records.read_bundle(self.path/"run.json")

    def test_reference_identity_and_recovery_attempt_limit(self):
        run = copy.deepcopy(self.run)
        run["cases"][0]["controls"]["merged_patch_sha256"] = "0"*64
        write(self.path,run,self.rows)
        with self.assertRaisesRegex(ValueError,"frozen merged reference"):
            records.read_bundle(self.path/"run.json")
        run = copy.deepcopy(self.run)
        run.update(cohort="capacity-recovery",parent_plan_sha256="b"*64)
        run["runtime"]["executor"]["judge"]["max_attempts_per_rotation"] = 1
        attempts = run["cases"][0]["judge_attempts"]
        attempts.append(dict(attempts[0],attempt=1,accepted=False,native_sha256="c"*64))
        run["evaluator"]["attempts"] += 1
        run["evaluator"]["complete_receipts"] += 1
        run["evaluator"]["observed_usd"] += attempts[-1]["usd_estimate"]
        write(self.path,run,self.rows)
        with self.assertRaisesRegex(ValueError,"violates its cohort limit"):
            records.read_bundle(self.path/"run.json")

    def test_controlled_comparison(self):
        second=self.path/"other";second.mkdir()
        changed=copy.deepcopy(self.run)
        changed["runtime"]["package_sha256"]="c"*64
        changed["cases"][0]["controls"]["cpu_pair"]=[2,3]
        write(second,changed,self.rows)
        got=records.compare(self.path/"run.json",second/"run.json","tuning","develop")
        self.assertEqual(got["excluded"],{"full":["controls.cpu_pair"]})
        self.assertEqual(got["aggregate"]["estimated_usd_delta"]["matched"],0)
        self.assertEqual(got["aggregate"]["proposal_seconds_delta"]["matched"],1)
        changed["runtime"]["seed"]=43
        write(second,changed,self.rows)
        self.assertFalse(records.compare(self.path/"run.json",second/"run.json","all","develop")["cases"])

    def test_rotations_and_separate_assessor_budget(self):
        self.run["evaluator"]["observed_usd"] = 1
        write(self.path,self.run,self.rows)
        with self.assertRaisesRegex(ValueError, "assessor totals"):
            records.read_bundle(self.path/"run.json")
        self.run["evaluator"]["observed_usd"] = .00186 * 6
        self.rows[0]["bindings"]["judges"][1]["label"] = self.rows[0]["quality"]["assessments"][0]["label"]
        self.rows[0]["quality"]["assessments"][1]["label"] = self.rows[0]["bindings"]["judges"][1]["label"]
        write(self.path,self.run,self.rows)
        with self.assertRaisesRegex(ValueError, "repeated judge position"):
            records.read_bundle(self.path/"run.json")

    def test_split_selection_precedes_all_releases(self):
        plan = {"schedule":["one","two"], "references":{"one":{"split":"tuning"},"two":{"split":"confirmation"}}}
        (self.path/"plan.json").write_text(json.dumps(plan))
        s = exporter.selection(self.path, plan, "tuning")
        self.assertEqual(s["cases"], ["one"])
        self.assertEqual(exporter.selection(self.path, plan), s)
        with self.assertRaisesRegex(ValueError, "once on an unused"):
            exporter.selection(self.path, plan, "confirmation")
        slot = self.path/"attempts/one/develop"
        slot.mkdir(parents=True)
        (slot/"release.json").write_text(json.dumps({"allocated_unix":s["declared_unix"] - 1}))
        with self.assertRaisesRegex(ValueError, "after proposal release"):
            exporter.selection(self.path, plan)
        (self.path/"attempts/two").mkdir()
        with self.assertRaisesRegex(ValueError, "outside the declared split"):
            exporter.selection(self.path, plan)


if __name__ == "__main__":
    unittest.main()
