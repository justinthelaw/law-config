import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from compare_evaluations import compare_results, observation_counts
from evaluation import CONTRACT


def result():
    data = json.loads((CONTRACT.parent / "results/synthetic.json").read_text())
    data["planned_attempts"] = data["planned_attempts"][:1]
    data["attempts"] = data["attempts"][:1]
    return data


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.before = result()
        self.after = copy.deepcopy(self.before)
        self.after["source"]["revision"] = "1" * 40

    def test_known_good_preserves_exact_evidence(self):
        report = compare_results(self.before, self.after)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["candidate"], self.after)
        self.assertEqual(report["baseline"], self.before)
        self.assertEqual(report["counts"]["candidate"], {"pass": 1, "fail": 0, "incomplete": 0})
        self.assertTrue(report["limitations"])

    def test_seeded_bad_outcome_is_not_hidden_by_good_function(self):
        self.after["attempts"][0]["evaluator"] = {"verdict": "fail", "evidence": ["Unauthorized edit."]}
        report = compare_results(self.before, self.after)
        self.assertEqual(report["status"], "candidate_failed")
        self.assertEqual(report["counts"]["candidate"]["fail"], 1)

    def test_blocked_missing_and_failed_retry_remain_visible(self):
        before = json.loads((CONTRACT.parent / "results/synthetic.json").read_text())
        after = copy.deepcopy(before)
        after["attempts"][0]["functional"] = {"verdict": "fail", "evidence": ["Wrong answer."]}
        report = compare_results(before, after)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["counts"]["candidate"], {"pass": 0, "fail": 1, "incomplete": 2})
        self.assertEqual(len(report["candidate"]["attempts"]), 3)

    def test_omitted_record_is_invalid(self):
        omitted = copy.deepcopy(self.after["planned_attempts"][0])
        omitted["attempt_id"] = "omitted"
        self.after["planned_attempts"].append(omitted)
        with self.assertRaisesRegex(ValueError, "every planned"):
            compare_results(self.before, self.after)

    def test_extra_retry_is_unpaired_not_improvement(self):
        plan = copy.deepcopy(self.after["planned_attempts"][0])
        attempt = copy.deepcopy(self.after["attempts"][0])
        plan["attempt_id"] = attempt["attempt_id"] = "retry"
        self.after["planned_attempts"].append(plan)
        self.after["attempts"].append(attempt)
        report = compare_results(self.before, self.after)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["counts"]["baseline"]["incomplete"], 1)
        self.assertIsNone(report["pairs"][1]["baseline"]["attempt"])

    def test_identity_mismatches_rejected(self):
        for field in ("name", "version", "model", "effort", "selection_basis"):
            with self.subTest(field=field):
                other = copy.deepcopy(self.after)
                other["host"][field] = "different"
                with self.assertRaisesRegex(ValueError, "host/model"):
                    compare_results(self.before, other)
        self.after["planned_attempts"][0]["fixture"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "fixture"):
            compare_results(self.before, self.after)

    def test_cost_null_is_not_zero_and_application_metrics_do_not_mix(self):
        self.before["attempts"][0]["cost"] = {"wall_seconds": 20, "tokens": 100, "usd": None}
        self.after["attempts"][0]["cost"] = {"wall_seconds": 15, "tokens": 120, "usd": None}
        self.after["attempts"][0]["application_performance"] = [{"name": "latency", "value": 9, "unit": "ms"}]
        report = compare_results(self.before, self.after)
        self.assertEqual(report["agent_cost_delta"], {"wall_seconds": -5, "tokens": 20, "usd": None})
        self.assertEqual(report["agent_cost"]["candidate"]["usd"]["known_attempts"], 0)

    def test_user_updates_are_not_helper_or_tool_logs(self):
        self.after["attempts"][0]["observations"] = [
            {"channel": "helper", "text": "Said it updated the user."},
            {"channel": "tool", "text": "CI green"}]
        self.assertEqual(observation_counts(self.after), {"user": 0, "tool": 1, "helper": 1})

    def test_cli_good_bad_incomplete_and_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            before, after = [Path(directory) / name for name in ("before.json", "after.json")]
            before.write_text(json.dumps(self.before))
            for expected, mutation in [
                (0, lambda d: None),
                (1, lambda d: d["attempts"][0]["functional"].update(verdict="fail")),
                (2, lambda d: d["attempts"][0]["functional"].update(verdict="not_run")),
                (2, lambda d: d["attempts"].clear()),
            ]:
                data = copy.deepcopy(self.after)
                mutation(data)
                after.write_text(json.dumps(data))
                proc = subprocess.run([sys.executable, str(SCRIPTS / "compare_evaluations.py"),
                                       str(before), str(after)], text=True, capture_output=True)
                self.assertEqual(proc.returncode, expected, proc.stderr)
                self.assertIn("status", json.loads(proc.stdout))


if __name__ == "__main__":
    unittest.main()
