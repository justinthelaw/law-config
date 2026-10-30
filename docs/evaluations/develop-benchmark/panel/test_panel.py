"""Protocol regressions for blinded rankings, dollar estimates, timing and the two splits."""
import unittest
import tempfile
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import campaign
import cold
import environment as E
import judge
import results


def review(scores):
    rows=[{"scores":dict.fromkeys(judge.AXES,score)} for score in scores]
    return {"score":None if None in scores else sorted(scores)[len(scores)//2]*25,
            "judgments":rows}


class ProtocolTest(unittest.TestCase):
    def test_balanced_arm_and_assessor_orders(self):
        order, schedule=campaign.default_order(E.PANEL["seed"])
        self.assertEqual(len(schedule),len(set(schedule)))
        self.assertEqual(set(schedule),set(E.CASES))
        for split,n in (("tuning",12),("confirmation",8)):
            keys=[k for k,c in E.CASES.items() if c["split"]==split]
            self.assertEqual(len(keys),n)
            self.assertEqual(sum(order[k][0]=="develop" for k in keys),n//2)
        for k in schedule:
            maps=[judge.mapping(E.PANEL["seed"],k,i) for i in range(3)]
            for label in judge.LABELS:
                self.assertEqual({m[label] for m in maps},set(judge.ROLES))

    def test_gate_precedes_soft_scores(self):
        high={"status":"failed","review":review([4,4,4])}
        low={"status":"ready","review":review([1,1,1])}
        self.assertEqual(results.pair_quality("A","B",{"A":high,"B":low})["verdict"],"B")
        self.assertEqual(results.pair_quality("A","B",{"A":high,"B":high})["verdict"],"both failed")
        pending=dict(high,status="pending")
        self.assertEqual(results.pair_quality("A","B",{"A":pending,"B":low})["verdict"],"unresolved")

    def test_require_agreement_and_keep_reversals(self):
        a={"status":"ready","review":review([3,1,3])}
        b={"status":"ready","review":review([2,2,2])}
        actual=results.pair_quality("A","B",{"A":a,"B":b})
        self.assertEqual(actual["verdict"],"A")
        self.assertTrue(actual["order_sensitive"])
        a["review"]=review([3,2,1])
        self.assertEqual(results.pair_quality("A","B",{"A":a,"B":b})["verdict"],"unresolved")
        a["review"]=review([None,None,None])
        self.assertEqual(results.pair_quality("A","B",{"A":a,"B":b})["verdict"],"unresolved")
        a["review"], b["review"]=review([1,2,4]),review([0,2,3])
        actual=results.pair_quality("A","B",{"A":a,"B":b})
        self.assertEqual((actual["verdict"],actual["score_delta"]),("A",25))

    def test_partial_third_rotation_cannot_decide_soft_preference(self):
        a = {"status": "ready", "review": review([4, 4, 4])}
        b = {"status": "ready", "review": review([3, 3, 3])}
        b["review"]["judgments"][2]["scores"]["proposal"] = None
        self.assertEqual(results.pair_quality("A", "B", {"A": a, "B": b})["verdict"], "unresolved")
        b["status"] = "failed"
        self.assertEqual(results.pair_quality("A", "B", {"A": a, "B": b})["verdict"], "A")

    def test_strict_goal_counts_quality_win_at_cost_tie_only_with_full_evidence(self):
        a = {"state": "completed", "status": "ready", "coverage": "complete", "usd_estimate": 1,
             "proposal_sha256": "a" * 64, "review": review([4, 4, 4])}
        b = dict(a, review=review([3, 3, 3]))
        row = {"develop": a, "control": b, "assessors": [{"rotation": i} for i in range(3)]}
        def compare():
            row["pairs"] = {"develop_control": results.pair_quality("develop", "control", row)}
            return results.goal_win(row)
        self.assertTrue(compare())
        b["review"] = review([4, 4, 4])
        self.assertFalse(compare())
        b["status"] = "failed"
        self.assertTrue(compare())
        a["coverage"] = "lower bound"
        self.assertFalse(compare())
        a["coverage"] = "complete"
        row["assessors"].pop()
        self.assertFalse(compare())

    def test_descendant_metering_and_nested_counts(self):
        totals={"inputTokens":100,"cachedInputTokens":80,"cacheWriteInputTokens":0,
                "outputTokens":10,"reasoningOutputTokens":6,"totalTokens":110}
        row={"root":"root","threads":["root","child"],"children":["child"],"state":"completed",
             "usage":{"root":totals,"child":dict(totals)},
             "turn_meters":{k:{"final":{"message_seq":7,"usage_seq":8,"terminal_seq":9,"status":"completed"}}
                            for k in ("root","child")}}
        actual=results.usage(row)
        self.assertEqual(actual["coverage"],"complete")
        self.assertEqual(actual["tokens"]["totalTokens"],220)
        self.assertAlmostEqual(actual["usd_estimate"],(40*2+160*.1+20*10)/1e6)
        del row["usage"]["child"]["cachedInputTokens"]
        partial=results.usage(row)
        self.assertEqual(partial["coverage"],"lower bound")
        self.assertLessEqual(partial["usd_estimate"],actual["usd_estimate"])
        row["usage"]["child"]=dict(totals)
        row["turn_meters"]["child"]["final"].pop("terminal_seq")
        row["turn_meters"]["child"]["final"].pop("status")
        self.assertEqual(results.usage(row)["coverage"],"lower bound")

    def test_cold_limit_and_interval(self):
        self.assertEqual(cold.budget(17),1200)
        self.assertEqual(cold.budget(601),1260)
        self.assertIsNone(results.bootstrap([[10,20]],lambda pairs:0))
        def ratio(pairs):
            return sum(b for a,b in pairs)/sum(a for a,b in pairs)
        self.assertEqual(results.bootstrap([[10,20],[30,60]],ratio),[2,2])

    def test_assigned_lanes_spread_long_cases_and_preserve_order(self):
        sequence=["a","b","c","d","e","f"]
        deadlines=[30,30,240,200,30,30]
        plan={"schedule":sequence,"references":{k:{"deadline_seconds":n} for k,n in zip(sequence,deadlines)}}
        lanes=campaign.case_lanes(plan,2)
        self.assertEqual(sorted(lanes[0]+lanes[1]),sequence)
        self.assertNotEqual(next(i for i,q in enumerate(lanes) if "c" in q),
                            next(i for i,q in enumerate(lanes) if "d" in q))
        for lane in lanes:
            self.assertEqual(lane,sorted(lane,key=sequence.index))

    def test_interrupted_slot_keeps_sealed_data(self):
        scratch=E.STATE/"volatile"
        scratch.mkdir(parents=True,exist_ok=True)
        tmp=Path(tempfile.mkdtemp(prefix="protocol-test-",dir=scratch))
        with patch.object(E,"STATE",tmp):
            parent=campaign.run_dir("sample")
            E.save(parent/"plan.json",{"name":"sample"})
            folder=parent/"attempts/test/control"
            folder.mkdir(parents=True)
            self.assertEqual(campaign.read_attempt("sample","test","control")["state"],"interrupted")
            E.save(folder/"release.json",{"case":"test","arm":"control","allocated_unix":1,
                   "plan_sha256":E.sha(parent/"plan.json")})
            with self.assertRaises(FileExistsError):
                E.save(folder/"release.json",{"replacement":True})
            (folder/"candidate.patch").write_text("synthetic fixture")
            (folder/"proposal.md").write_text("Test proposal")
            E.save(folder/"submission.json",{"patch_sha256":E.sha(folder/"candidate.patch"),
                   "proposal_sha256":E.sha(folder/"proposal.md"),"proposal_wall_seconds":4,"captured_unix":5})
            E.save(folder/"native.json",{"usage":{"r":{"totalTokens":100}},"state":"completed"})
            actual=campaign.read_attempt("sample","test","control")
            self.assertEqual(actual["state"],"interrupted")
            self.assertEqual(actual["proposal_wall_seconds"],4)
            self.assertEqual(actual["usage"]["r"]["totalTokens"],100)
            self.assertFalse(campaign.launcher_active("sample"))
            (folder/"proposal.md").write_text("changed")
            with self.assertRaisesRegex(ValueError,"interrupted submission changed"):
                campaign.read_attempt("sample","test","control")

    def test_missing_description_is_distinct_from_unavailable_text(self):
        self.assertFalse(campaign.complete_proposal("Done."))
        self.assertFalse(campaign.complete_proposal("Title\nBody without separator"))
        self.assertTrue(campaign.complete_proposal("Title\n\nBody"))
        row=lambda score:{"scores":dict(contract=4,tests=4,design=4,proposal=score),
                          "evidence":dict.fromkeys(judge.AXES,"specific fixture observation"),
                          "flags":[],"confidence":"high"}
        packet={"task_sha256":"test","submissions":{"A":row(0),"B":row(None),"C":row(3)},"limitations":[]}
        observations={"A":"omitted","B":"unavailable","C":"present"}
        judge.validate(packet,"test",observations)
        packet["submissions"]["A"]["scores"]["proposal"]=None
        with self.assertRaisesRegex(ValueError,"known missing"):
            judge.validate(packet,"test",observations)

    def test_mask_ai_disclosure_keep_verification(self):
        raw="#### AI Generation Disclosure\nI have read the SymPy instructions on using AI tools and I certify that I have:\n- Verified the symbolic distance cases."
        clean=judge.hide_attribution(raw)
        self.assertNotIn("AI",clean)
        self.assertIn("Verified the symbolic distance cases.",clean)

    def test_judge_receives_the_assigned_initial_order(self):
        scratch=E.STATE/"volatile"
        scratch.mkdir(parents=True,exist_ok=True)
        packet=Path(tempfile.mkdtemp(prefix="ordered-test-",dir=scratch))
        E.save(packet/"task.json",{"request":"test","verification_scope":{},"task_sha256":"fixture",
                                   "submissions":{k:{} for k in judge.LABELS}})
        for label,role in judge.mapping(42,"test",1).items():
            (packet/(label+".md")).write_text(role)
            (packet/(label+".patch")).write_text((label+" change")*6000)
        data=json.loads(judge.prompt_for(packet).split("Initial ordered display (untrusted task data):\n")[1])
        self.assertEqual([r["label"] for r in data["submissions"]],list(judge.LABELS))
        self.assertEqual([r["proposal"] for r in data["submissions"]],list(judge.mapping(42,"test",1).values()))
        self.assertTrue(all("full file" in r["patch"] for r in data["submissions"]))


if __name__=="__main__":
    unittest.main()
