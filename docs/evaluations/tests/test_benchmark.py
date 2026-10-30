import argparse
import copy
from contextlib import nullcontext, redirect_stdout, redirect_stderr
import io
import fcntl
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmark as B
import native_panel as N
import workers


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(redirect_stdout(io.StringIO()))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.state = self.temp / "state"
        self.bundle = self.temp / "bundles"
        self.root = self.state / "runs/trial"
        self.pin = {"schedule": ["a", "b"], "order": {"a": ["develop", "control"], "b": ["control", "develop"]},
                    "judge_rotations": 3}
        for name, value in (("STATE", self.state), ("BUNDLES", self.bundle)):
            self.enterContext(patch.object(B, name, value))
        self.enterContext(patch.object(N.E, "STATE", self.state))

    def test_qualification_requires_the_child_to_inherit_its_parent_history(self):
        log = self.temp / "profile/sessions/rollout-test-child.jsonl"
        self.assertFalse(N.E.native.inherited_context(self.temp, "parent", "child"))
        save(log, {"type": "session_meta", "payload": {"id": "child"}})
        self.assertFalse(N.E.native.inherited_context(self.temp, "parent", "child"))
        with log.open("a") as stream:
            stream.write('\n{"type":"session_meta","payload":{"id":"parent"}}\n')
        self.assertTrue(N.E.native.inherited_context(self.temp, "parent", "child"))

    def test_pilot_export_rejects_an_unbound_result_before_writing(self):
        folder = self.state / "pilots/trial"
        destination = self.temp / "portable.json"
        save(folder / "registration.json", {"name": "trial"})
        source = {"registration": {"path": "another/registration.json", "sha256": "a" * 64}}
        checksum = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        save(folder / ("result-" + checksum[:12] + ".json"), source)
        with self.assertRaisesRegex(ValueError, "registration or content hash"):
            N.export_panel.export_pilot("trial", destination)
        self.assertFalse(destination.exists())

    def test_pilot_status_counts_only_its_three_allocations(self):
        save(self.state / "pilots/trial/registration.json", {"name": "trial", "case": "a",
             "order": [["candidate", "control"], ["prior", "develop"], ["candidate", "develop"]]})
        save(self.state / "runs/trial-candidate/attempts/a/control/result.json", {"state": "completed"})
        save(self.state / "runs/trial-prior/attempts/a/develop/release.json", {})
        snapshot = B.status("trial")
        self.assertEqual(snapshot["phase"], "proposals")
        self.assertEqual(snapshot["proposal_states"], {"candidate/control": "completed", "prior/develop": "allocated",
                                                       "candidate/develop": "unreleased"})

    def test_published_status_shows_prior_gates_and_blind_merge_scores(self):
        from records import blinded_proposal_verdict
        name = "declared-entry-pytest-01"
        record = B.read(B.HERE / "runs/tuning" / name / "result.json")
        save(B.pilot_file(name), record)
        status = B.status(name)
        prior = status["outcomes"]["prior_develop"]
        self.assertEqual(prior["stage_exits"]["preserve"], 42)
        self.assertIsNone(prior["readiness"])
        self.assertIsNone(prior["pr_score_100"])
        for role in ("develop", "control"):
            self.assertEqual(status["blind_full_pr_vs_merged"][role],
                             blinded_proposal_verdict(record["submissions"][role],
                                                      record["submissions"]["upstream"], 3))
        self.assertEqual(status["outcomes"]["upstream"]["readiness"], "failed")

    def test_pilot_prepares_only_its_case_before_the_first_plan(self):
        import efficiency_pilot
        args = argparse.Namespace(action="pilot", name="trial", case="black")
        with patch.object(B, "configure_temp"), patch.object(N, "setup") as prepare, \
                patch.object(B.os, "sched_setaffinity"), patch.dict(B.os.environ, DEVELOP_EVAL_COHORT=N.E.PANEL["protocol"]), \
                patch.object(efficiency_pilot, "run", return_value=0):
            self.assertEqual(B.dispatch(args), 0)
            prepare.assert_called_once_with([N.E.CASES["black"]])
            save(self.state / "runs/trial-prior/plan.json", {"protocol":N.E.PANEL["protocol"], "name":"trial-prior",
                 "runtime":{"source_sha256":N.E.version_digest()}, "rubric_sha256":N.E.sha(N.E.HERE/"rubric.md")})
            self.assertEqual(B.dispatch(args), 0)
            self.assertEqual(prepare.call_count, 1)

    def test_copied_pilot_report_verifies_the_win_without_private_state(self):
        name = "caller-werkzeug-01"
        record = B.read(B.HERE / "runs/tuning" / name / "result.json")
        path = B.pilot_file(name)
        save(path, record)
        args = argparse.Namespace(action="report", name=name)
        self.assertEqual(B.dispatch(args), 0)
        summary = B.status(name)
        self.assertEqual(summary["control_headroom"]["maximum_median_lead"], 25)
        self.assertEqual(summary["outcomes"]["control"]["pr_score_100"], 75)
        self.assertEqual(summary["outcomes"]["control"]["diff_score_85"], 63.75)
        self.assertIsNone(summary["outcomes"]["prior_develop"]["diff_score_85"])
        self.assertEqual(summary["outcomes"]["develop"]["estimated_usd"], record["submissions"]["develop"]["effort"]["estimated_usd"])
        self.assertIsNone(summary["outcomes"]["prior_develop"]["pr_score_100"])
        self.assertIsNone(summary["outcomes"]["upstream"]["estimated_usd"])
        for role, row in (record["submissions"] | {"prior_develop": record["prior_develop"]}).items():
            self.assertEqual(summary["outcomes"][role]["through_grading_seconds"],
                             (row["effort"] or {}).get("through_grading_seconds"))
        costs = record["assessor_costs"]
        self.assertEqual(summary["assessor_costs"], {
            "coverage": "complete", "estimated_usd": sum(a["usd_estimate"] for a in costs),
            "observed_usd": sum(a["usd_estimate"] for a in costs),
            "attempts": 3, "complete_receipts": 3})
        retry_costs = costs + [dict(costs[0])]
        save(path, dict(record, assessor_costs=retry_costs))
        self.assertEqual(B.status(name)["assessor_costs"], {
            "coverage": "complete", "estimated_usd": sum(a["usd_estimate"] for a in retry_costs),
            "observed_usd": sum(a["usd_estimate"] for a in retry_costs),
            "attempts": 4, "complete_receipts": 4})
        from records import proposal_points, proposal_verdict
        missing_rotation = copy.deepcopy(record)
        for row in missing_rotation["submissions"].values():
            quality = row["quality"]
            quality["assessments"] = [a for a in quality["assessments"] if a["rotation"] != 2]
            quality["axes"] = {axis: statistics.median(a["scores"][axis] for a in quality["assessments"])
                               for axis in quality["axes"]}
            quality["proposal_points_100"] = proposal_points(quality["axes"])
            quality["diff_points_85"] = None
            del quality["rotation_points_85"]["2"]
            row["bindings"]["judges"] = [j for j in row["bindings"]["judges"] if j["rotation"] != 2]
            row["readiness"] = "pending"
        for pair in missing_rotation["comparisons"]:
            left, right = pair.split("_")
            missing_rotation["comparisons"][pair] = proposal_verdict(
                missing_rotation["submissions"][left], missing_rotation["submissions"][right], 3)
        missing_rotation["goal_win"] = False
        save(path, missing_rotation)
        status = B.status(name)
        for comparison in status["blind_full_pr_vs_merged"].values():
            self.assertEqual(comparison["verdict"], "unresolved")
        self.assertEqual(status["assessor_costs"], {
            "coverage": "lower bound", "estimated_usd": None,
            "observed_usd": sum(a["usd_estimate"] for a in costs),
            "attempts": 3, "complete_receipts": 3})
        partial = [dict(a) for a in costs]
        partial[-1]["coverage"] = "lower bound"
        for receipts in (partial, costs[:-1], costs[:-1] + [dict(costs[-1], usd_estimate=None)]):
            with self.subTest(receipts=receipts):
                save(path, dict(record, assessor_costs=receipts))
                price = B.status(name)["assessor_costs"]
                self.assertEqual(price["coverage"], "lower bound")
                self.assertIsNone(price["estimated_usd"])
                self.assertEqual(price["observed_usd"], sum(a["usd_estimate"] or 0 for a in receipts))
        for receipts in ([], None):
            save(path, dict(record, assessor_costs=receipts))
            self.assertEqual(B.status(name)["assessor_costs"], {
                "coverage": "unknown", "estimated_usd": None, "observed_usd": None,
                "attempts": 0, "complete_receipts": 0})
        legacy = dict(record)
        del legacy["assessor_costs"]
        effort = record["submissions"]["develop"]["effort"]
        through_grading = effort.pop("through_grading_seconds")
        save(path, legacy)
        legacy_status = B.status(name)
        self.assertIsNone(legacy_status["outcomes"]["develop"]["through_grading_seconds"])
        self.assertEqual(legacy_status["assessor_costs"]["coverage"], "unknown")
        effort["through_grading_seconds"] = through_grading
        self.assertFalse(self.state.exists())
        save(path, dict(record, goal_win=True))
        with self.assertRaisesRegex(ValueError, "outcome differs"):
            B.dispatch(args)
        record["profiles"]["candidate/control"]["ephemeral"] = True
        save(path, record)
        with self.assertRaisesRegex(ValueError, "stock profile differs"):
            B.dispatch(args)

    def test_prior_patch_and_proposal_are_bound_in_both_export_formats(self):
        from records import read_pilot
        source = B.HERE / "runs/tuning/caller-werkzeug-01"
        path = self.temp / source.name / "result.json"
        record = B.read(source / "result.json")
        artifacts = B.read(source / "prior.json")
        save(path, record)
        save(path.with_name("prior.json"), artifacts)
        read_pilot(path)
        save(path.with_name("prior.json"), dict(artifacts, patch=""))
        with self.assertRaisesRegex(ValueError, "prior Develop patch digest"):
            read_pilot(path)
        record["prior_develop"].update(artifacts)
        save(path, record)
        read_pilot(path)
        record["prior_develop"]["proposal"] = None
        save(path, record)
        with self.assertRaisesRegex(ValueError, "prior Develop proposal digest"):
            read_pilot(path)

    def test_caller_replay_rejects_a_different_task_before_preparation(self):
        from replay_caller import replay
        with patch.object(B, "BUNDLES", B.HERE / "runs/pr-quality-panel-v2"), patch.object(N.E, "prepare") as prepare:
            with self.assertRaisesRegex(ValueError, "same repository, revisions and task"):
                replay("caller-werkzeug-01", "public-warnings", "public-result-pytest-01")
            prepare.assert_not_called()

    def test_caller_replay_requires_bound_calibration_before_preparation(self):
        import replay_caller as replay
        source = B.HERE / "runs/tuning/caller-werkzeug-01/result.json"
        for change, message in (("case", "source case"), ("stages", "calibration"),
                                ("patch", "calibration"), ("base", "configured fixture")):
            with self.subTest(change=change):
                record = B.read(source)
                evidence = next(o for o in record["observations"] if o["id"] == "public-warnings")["evidence"]
                if change == "case":
                    evidence["case"] = "pytest"
                elif change == "stages":
                    del evidence["roles"]["gold"]["stages"]
                elif change == "patch":
                    evidence["roles"]["candidate-control"]["patch_sha256"] = "0" * 64
                else:
                    record["base"] = "0" * 40
                with patch.object(replay, "read_pilot", return_value=record), patch.object(N.E, "prepare") as prepare:
                    with self.assertRaisesRegex(ValueError, message):
                        replay.replay("caller-werkzeug-01", "public-warnings", "caller-werkzeug-01")
                    prepare.assert_not_called()

    def test_pilot_reconciles_total_tokens_with_thread_meters(self):
        from records import read_pilot
        source = B.HERE / "runs/tuning/caller-review-pytest-01/result.json"
        record = read_pilot(source)
        path = self.temp / source.parent.name / source.name
        effort = record["submissions"]["develop"]["effort"]
        effort["tokens"]["totalTokens"] -= 1
        save(path, record)
        with self.assertRaisesRegex(ValueError, "root and descendant"):
            read_pilot(path)
        effort["root_tokens"]["totalTokens"] -= 1
        save(path, record)
        with self.assertRaisesRegex(ValueError, "input and output"):
            read_pilot(path)

    def test_pilot_rejects_changed_probe_or_observation(self):
        from records import read_pilot
        source = B.HERE / "runs/tuning/focused-review-pytest-01/result.json"
        path = self.temp / source.parent.name / source.name
        record = B.read(source)
        item = next(o for o in record["observations"] if "probe" in o)
        other = B.read(source.parents[1] / "scoped-pytest-01/result.json")
        transferred = next(o for o in other["observations"] if o["id"] == item["id"])
        save(path, dict(record, observations=[transferred]))
        with self.assertRaisesRegex(ValueError, "different pilot registration"):
            read_pilot(path)
        item["evidence"]["scope"] += " changed"
        save(path, record)
        with self.assertRaisesRegex(ValueError, "evidence differs"):
            read_pilot(path)
        item["probe"] += "# changed"
        save(path, record)
        with self.assertRaisesRegex(ValueError, "probe checksum"):
            read_pilot(path)

    def test_delta_requires_the_named_full_package(self):
        pin = "a" * 64
        path = self.temp / "treatments" / pin[:12] / "recipe.json"
        with patch.object(B, "HERE", self.temp):
            for recipe in ({"package_sha256": "b" * 64},
                           {"package_sha256": pin, "base_package_sha256": pin}):
                save(path, recipe)
                with self.assertRaisesRegex(ValueError, "full base recipe"):
                    N.full_recipe(pin)
            save(path, {"package_sha256": pin})
            self.assertEqual(N.full_recipe(pin), path)

    def test_status_reads_without_creating_any_files(self):
        self.assertEqual(B.status("trial")["phase"], "new")
        self.assertFalse(self.state.exists())
        save(self.root / "plan.json", dict(self.pin, recovery={}))
        save(self.root / "attempts/a/control/result.json", {"state": "blocked"})
        save(self.root / "attempts/a/develop/release.json", {})
        save(self.root / "judges/a/0/0/mapping.json", {"labels": {"A":"develop"}})
        save(self.root / "judges/a/0/judgment.json", {"scores":{"submissions":{"A":{"flags":["bad P0"]}}},
             "mapping":{"path":"runs/trial/judges/a/0/0/mapping.json"}})
        save(self.root / "judges/a/1/0/native.json",
             {"state":"blocked","assessment_started_unix":1,"assessment_finished_unix":2})
        save(self.root / "judges/a/1/0/invalid.json", {"state":"blocked","error":"no terminal answer"})
        save(self.root / "judges/a/1/1/call-limit.json", {"released":False,"reason":"one assessor call per rotation"})
        files = set(self.state.rglob("*"))
        row = B.status("trial")
        self.assertEqual(row["unadjudicated"], ["a/develop"])
        self.assertEqual(row["allocated"], ["a/develop"])
        self.assertEqual(row["unreleased"], ["b/control", "b/develop"])
        self.assertEqual(row["assessments"], {"valid":1, "exhausted":1, "unreleased":4})
        self.assertEqual(set(self.state.rglob("*")), files)
        for ruling in ({}, {"resolution":"confirmed","evidence":"  "}, {"resolution":"open","evidence":"detail"}):
            save(self.root / "adjudications/a.json", {"develop":ruling})
            self.assertEqual(B.status("trial")["unadjudicated"], ["a/develop"])
        save(self.root / "adjudications/a.json", {"develop":{"resolution":"cleared","evidence":"replayed the base"}})
        self.assertEqual(B.status("trial")["unadjudicated"], [])

    def test_lane_lock_and_older_launcher_both_block(self):
        with B.operator("trial"):
            self.assertEqual(B.status("trial")["phase"], "preparing")
            with self.assertRaisesRegex(ValueError, "another operator"):
                with B.operator():
                    self.fail("duplicate owner")
        self.root.mkdir(parents=True)
        with (self.root / "recovery.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError, "active recovery"):
                with B.operator():
                    self.fail("legacy owner")

    def test_fresh_primary_freezes_then_selects_before_releasing(self):
        args = argparse.Namespace(name="trial", jobs=1, split="tuning")
        calls = []
        def command(path, *args, **opts):
            calls.append((Path(path).name, *args))
            return 0
        def phase():
            return {"unreleased": ["a/control"] if not any(c[0]=="campaign.py" for c in calls) else [],
                    "proposal_states": {}, "allocated": [], "assessments":{"unreleased":3},
                    "pending_assessments":["a/0","a/1","a/2"],"cases":["a"]}
        def select(root, plan, split=None):
            if split:
                calls.append(("select", split))
                return {"split":split}
        with (patch.object(N, "setup", side_effect=lambda: calls.append(("prepare",))),
              patch.object(N.C, "freeze", side_effect=lambda n: calls.append(("freeze", n)) or self.pin),
              patch.object(N.export_panel, "selection", side_effect=select), patch.object(B, "command", side_effect=command),
              patch.object(B, "status", side_effect=lambda n: phase()), patch.object(N, "finalize", return_value=0)):
            self.assertEqual(N.run_primary(args, None), 0)
        self.assertEqual([c[0] for c in calls], ["prepare","controller.py","freeze","select","campaign.py","judge.py"])
        self.assertEqual(calls[-1][1:4], ("trial","--case","a"))

    def test_resume_stops_at_failed_requalification(self):
        args = argparse.Namespace(name="trial",jobs=1,split=None)
        state = {"unreleased":["b/control"], "allocated":[], "proposal_states":{"blocked":1},
                 "assessments":{"incomplete":1}, "pending_assessments":["a/1"]}
        with (patch.object(N.export_panel, "selection", return_value=None), patch.object(B,"status",return_value=state),
              patch.object(B,"command",side_effect=RuntimeError("capacity")) as command):
            with self.assertRaisesRegex(RuntimeError,"capacity"):
                N.run_primary(args,self.pin)
            command.assert_called_once_with(B.PANEL/"controller.py")

    def test_judge_only_resume_requalifies_before_spending(self):
        args = argparse.Namespace(name="trial", jobs=1, split=None)
        state = {"unreleased":[], "allocated":[], "proposal_states":{"completed":4},
                 "assessments":{"incomplete":1}, "pending_assessments":["a/1"]}
        with (patch.object(N.export_panel, "selection", return_value=None), patch.object(B, "status", return_value=state),
              patch.object(B, "command", side_effect=RuntimeError("capacity")) as command):
            with self.assertRaisesRegex(RuntimeError, "capacity"):
                N.run_primary(args, self.pin)
            command.assert_called_once_with(B.PANEL / "controller.py")

    def test_reader_is_required_before_spending(self):
        output = io.StringIO()
        with (patch.dict(B.os.environ, DEVELOP_EVAL_COHORT=N.E.PANEL["protocol"]),
              patch.object(B,"configure_temp"), patch("importlib.metadata.version",return_value="wrong"),
              patch.object(N,"operate") as live, redirect_stderr(output)):
            self.assertEqual(B.main(["run","trial"]),2)
            live.assert_not_called()
            self.assertIn("-m pip install -r", output.getvalue())

    def test_empty_ruling_blocks_finalization(self):
        plan = dict(self.pin, schedule=["a"])
        save(self.root/"plan.json",plan)
        for arm in plan["order"]["a"]:
            save(self.root/"attempts/a"/arm/"result.json",{"state":"completed"})
        for rotation in range(3):
            trial = self.root/"judges/a"/str(rotation)
            mapping = trial/"0/mapping.json"
            save(mapping,{"labels":{"A":"develop"}})
            save(trial/"judgment.json",{"mapping":{"path":str(mapping.relative_to(self.state))},
                 "scores":{"submissions":{"A":{"flags":["critical"]}}}})
        ruling = self.root/"adjudications/a.json"
        save(ruling,{"develop":{}})
        with (patch.object(N.C,"plan_for",return_value=plan), patch.object(B,"command"),
              patch.object(N.export_panel,"export") as export):
            self.assertEqual(N.finalize("trial"),3)
            export.assert_not_called()
            save(ruling,{"develop":{"resolution":"cleared","evidence":"checked against the base"}})
            self.assertEqual(N.finalize("trial"),0)
            export.assert_called_once()

    def test_portable_only_status_uses_verified_rows(self):
        from test_records import sample
        target = self.bundle / "unit"
        target.mkdir(parents=True)
        manifest, _ = sample(target, interrupted=True)
        report = B.status(manifest["name"])
        self.assertEqual(report["phase"],"published-partial")
        self.assertEqual(report["allocated"],["partial/develop"])
        self.assertEqual(report["assessments"],{"valid":6})
        self.assertEqual(report["proposal_states"],{"interrupted":1,"completed":3})
        with patch.object(B,"configure_temp"):
            self.assertEqual(B.main(["report",manifest["name"]]),3)

    def test_invalid_assessor_cannot_retire_a_worker_without_a_terminal_record(self):
        folder = self.root / "judges/a/0/0"
        save(self.root / "plan.json",self.pin)
        save(folder / "native.json",{"state":"blocked","assessment_started_unix":1,"assessment_finished_unix":2})
        for marker in ({}, {"error":"","state":"blocked"}, {"error":"incomplete","state":"completed"}):
            save(folder / "invalid.json",marker)
            with patch.object(workers.subprocess,"run") as docker:
                workers.retire("trial")
                docker.assert_not_called()
        save(folder / "invalid.json",{"error":"incomplete","state":"blocked"})
        records = list(workers.terminals(self.root))
        self.assertEqual(records, [(folder,"a",folder/"native.json",folder/"invalid.json")])

    def test_cold_import_must_equal_the_original_pinned_measurement(self):
        case = {"id":"jq","base":"git","build":"build","legacy":True}
        original = {"passed":True,"case":"jq","base":"git","worker_image":"image","build":"build",
                    "native":"test","seconds":3572.043}
        legacy = self.temp/"tmp/six-repo-workflow"
        receipt = legacy/"timings/receipt.json"
        save(receipt,original)
        sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
        save(legacy/"experiment/plan.json",{"feasibility":{"jq":{"path":"timings/receipt.json","sha256":sha}}})
        imported = dict(original,source="verified original cold timing",original_sha256=sha)
        dest = self.state/"cache/cold/jq/1/receipt.json"
        with (patch.object(N.E,"ROOT",self.temp), patch.object(N.E,"CACHE",self.state/"cache"),
              patch.object(N.E.guest,"image_id",return_value="image"), patch.object(N.E.guest,"native_tests",return_value="test")):
            save(dest,imported)
            self.assertTrue(N.cold_passed(case))
            save(dest,dict(imported,seconds=1))
            self.assertFalse(N.cold_passed(case))
            del imported["original_sha256"]
            save(dest,imported)
            self.assertFalse(N.cold_passed(case))

    def test_status_reports_a_schema_error_as_integrity_failure(self):
        save(self.bundle/"bad/run.json",{"name":"invalid"})
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(B.main(["status","invalid"]),2)
        self.assertIn("invalid run.json bundle", output.getvalue())

    def test_stranded_rotation_spends_nothing_on_repeated_resume(self):
        plan = dict(self.pin, schedule=["a"], judge_rotations=1)
        save(self.root/"plan.json",plan)
        for arm in plan["order"]["a"]:
            save(self.root/"attempts/a"/arm/"result.json",{"state":"completed"})
        for number in ("0","1"):
            (self.root/"judges/a/0"/number).mkdir(parents=True)
        state = B.status("trial")
        self.assertEqual(state["stranded_assessments"],["a/0"])
        self.assertEqual(state["pending_assessments"],[])
        args = argparse.Namespace(name="trial",jobs=1,split=None)
        with patch.object(B,"command") as command:
            for _ in range(2):
                self.assertEqual(N.run_primary(args,plan),3)
            command.assert_not_called()

    def test_recovery_after_technical_stop_cannot_spend_until_qualified(self):
        sys.path.insert(0,str(B.PANEL.parent))
        import recover_capacity
        source = self.state/"runs/base/plan.json"
        save(source,dict(self.pin,name="base"))
        plan = dict(self.pin,name="trial",schedule=["a"],recovery={"parent_plan":N.C.receipt(source)})
        save(self.root/"plan.json",plan)
        args = argparse.Namespace(action="recover",name="trial",parent="base")
        state = {"unreleased":["a/control"],"pending_assessments":["a/0"],"proposal_states":{"blocked":1},
                 "allocated":[],"assessments":{"unreleased":3}}
        with (patch.object(N,"preflight"), patch.object(N.C,"plan_for",return_value=plan),
              patch.dict(N.E.CASES,{"a":{}}), patch.object(N.C,"check_case"),
              patch.object(workers,"manage",return_value=nullcontext()), patch.object(B,"status",return_value=state),
              patch.object(B,"command",side_effect=RuntimeError("capacity")) as probe,
              patch.object(recover_capacity,"run") as release):
            with self.assertRaisesRegex(RuntimeError,"capacity"):
                N.operate(args)
            probe.assert_called_once_with(B.PANEL/"controller.py")
            release.assert_not_called()

    def test_recovery_block_leaves_the_partner_and_judges_unreleased(self):
        sys.path.insert(0,str(B.PANEL.parent))
        import recover_capacity
        self.root.mkdir(parents=True)
        plan = dict(self.pin, judge_rotations=3)
        layout = {"queues":[["a","b"]], "cpu_pairs":[[0,1]],"jobs":1}
        calls = []
        def read_attempt(name, case, arm):
            return {"state":"blocked" if (case,arm) in calls else "unreleased"}
        def run(cmd, **kwargs):
            self.assertIn("attempt",cmd)
            calls.append(tuple(cmd[-2:]))
        with (patch.object(N.C,"plan_for",return_value=plan), patch.object(N.C,"read_attempt",side_effect=read_attempt),
              patch.object(recover_capacity.subprocess,"run",side_effect=run)):
            self.assertFalse(recover_capacity.execute(self.root,layout,["a","b"],"trial",pause_on_block=True))
        self.assertEqual(calls,[("a","develop")])
        self.assertFalse((self.root/"judges").exists())

    def test_existing_plan_keeps_jobs_and_split(self):
        save(self.root / "lanes.json", {"jobs":1})
        args = argparse.Namespace(name="trial", jobs=2, split=None)
        with self.assertRaisesRegex(ValueError, "original number"):
            N.run_primary(args, self.pin)
        args.jobs, args.split = 1, "confirmation"
        with patch.object(N.export_panel, "selection", return_value={"split":"tuning"}):
            with self.assertRaisesRegex(ValueError, "original split"):
                N.run_primary(args, self.pin)

    def test_pending_scores_and_flags_prevent_publication(self):
        with patch.object(B, "status", return_value={"unreleased":[], "assessments":{"incomplete":1}}):
            self.assertEqual(N.finalize("trial"), 3)
        state = {"unreleased":[], "allocated":[], "assessments":{"valid":3}, "unadjudicated":["a/develop"]}
        with (patch.object(B,"status",return_value=state), patch.object(B,"command"), patch.object(N.C,"plan_for",return_value=self.pin),
              patch.object(N.export_panel,"export") as publish):
            self.assertEqual(N.finalize("trial"), 3)
            publish.assert_not_called()
            state.update(unadjudicated=[], assessments={"exhausted":1,"valid":2})
            self.assertEqual(N.finalize("trial"), 3)
            publish.assert_called_once()

    def test_recovery_parent_and_scope_mismatch_fail_before_preflight(self):
        save(self.state/"runs/base/plan.json",self.pin)
        save(self.root/"plan.json",dict(self.pin,recovery={"parent_plan":{"path":"wrong"}}))
        args=argparse.Namespace(action="recover",name="trial",parent="base")
        with patch.object(N,"preflight") as preflight:
            with self.assertRaisesRegex(ValueError,"different parent"):
                N.operate(args)
            save(self.state/"runs/base/selected-split.json",{"split":"tuning"})
            with self.assertRaisesRegex(ValueError,"full primary"):
                N.operate(args)
            preflight.assert_not_called()

    def test_private_package_index_leaves_main_index_untouched(self):
        root = self.temp/"source"
        root.mkdir()
        subprocess.run(["git","init","-q",root],check=True)
        save(root/".agents/plugins/marketplace.json", {"plugins":[{"name":"develop","source":{"source":"local","path":"./plugins/develop"}}]})
        package = root/"plugins/develop"
        package.mkdir(parents=True)
        (package/"removed").write_text("old")
        (package/"kept").write_text("base")
        subprocess.run(["git","-C",root,"add","."],check=True)
        (package/"removed").rename(self.temp/"removed")
        (package/"new").write_text("new")
        expected = N.E.host.package_hash(package,[package/"kept",package/"new"])
        index = root/".git/index"
        before = hashlib.sha256(index.read_bytes()).digest()
        result = N.stage_source(root,expected)
        self.assertEqual(N.git(result,"ls-files","--","plugins/develop").splitlines(),
                         [b"plugins/develop/kept",b"plugins/develop/new"])
        self.assertEqual(hashlib.sha256(index.read_bytes()).digest(),before)
        with self.assertRaisesRegex(ValueError,"differs from the treatment lock"):
            N.stage_source(root,"wrong")

    def test_worker_rejects_extra_or_writable_source_mount(self):
        base = {"Id":"worker", "Image":"pinned", "Config":{"Labels":{"law-native-trial":"named"}},
                "HostConfig":{"AutoRemove":True,"ReadonlyRootfs":True,"NetworkMode":"none"},
                "Mounts":[{"Type":"bind","Destination":"/work","Source":"/run/work","RW":True}]}
        expected = {"/work":("/run/work", True)}
        workers.verify_worker(base, "worker", "named", "pinned", expected)
        base["Mounts"].append({"Type":"bind","Destination":"/secret","Source":"/host","RW":True})
        with self.assertRaisesRegex(ValueError, "mounts differ"):
            workers.verify_worker(base,"worker","named","pinned",expected)
        base["Mounts"].pop()
        base["Mounts"][0]["Source"] = "/other/run"
        with self.assertRaisesRegex(ValueError, "mounts differ"):
            workers.verify_worker(base,"worker","named","pinned",expected)


    def test_worker_mounts_come_from_named_frozen_plan(self):
        state=self.temp/"state"; folder=state/"runs/named/attempts/werkzeug/develop"
        (folder/"profile/plugins/cache/law-config/develop/0.9.0").mkdir(parents=True)
        companion=folder/"profile/plugins/cache/superpowers-local/superpowers/6.3.0"
        companion.mkdir(parents=True)
        work=state/"cache/volatile/work"; work.mkdir(parents=True)
        cli=self.temp/"codex"; cli.touch()
        plan={"runtime":{"treatment":{"companion":{"package_sha256":"frozen"}}}}
        with patch.object(workers.E,"STATE",state), patch.object(workers.E,"CACHE",state/"cache"), \
             patch.object(workers.E,"CASES",{"werkzeug":{}}), patch.object(workers.E,"dependencies",return_value=state/"deps"), \
             patch.object(workers.C,"read_attempt",return_value={"state":"completed","workspace":"cache/volatile/work"}), \
             patch.object(workers.E,"read",return_value=plan), patch.object(workers.composite,"verify_component") as verify, \
             patch.dict("os.environ",{"BENCHMARK_CODEX":str(cli)}):
            mounts=workers.expected_mounts(folder,"werkzeug",folder/"result.json")
        self.assertEqual(mounts["/companion"],(str(companion),False))
        verify.assert_called_once_with(companion,plan["runtime"]["treatment"]["companion"])

    def test_worker_accepts_only_frozen_readonly_companion(self):
        mounts = [{"Type":"bind", "Destination":"/work", "Source":"/run/work", "RW":True},
                  {"Type":"bind", "Destination":"/companion", "Source":"/run/pinned", "RW":False}]
        data = {"Id":"worker", "Image":"pinned", "Config":{"Labels":{"law-native-trial":"named"}},
                "HostConfig":{"AutoRemove":True,"ReadonlyRootfs":True,"NetworkMode":"none"}, "Mounts":mounts}
        expected = {"/work":("/run/work", True), "/companion":("/run/pinned", False)}
        workers.verify_worker(data, "worker", "named", "pinned", expected)
        for source, writable in (("/different", False), ("/run/pinned", True)):
            mounts[1].update(Source=source, RW=writable)
            with self.assertRaisesRegex(ValueError, "mounts differ"):
                workers.verify_worker(data, "worker", "named", "pinned", expected)
        mounts.pop()
        with self.assertRaisesRegex(ValueError, "mounts differ"):
            workers.verify_worker(data, "worker", "named", "pinned", expected)


if __name__ == "__main__":
    unittest.main()
