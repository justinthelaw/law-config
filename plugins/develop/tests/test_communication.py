"""Public-input isolation and synthetic channel accounting, not model grading."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/evaluations"
sys.path.insert(0, str(ROOT / "scripts"))
import evaluation
import compare_evaluations


class CommunicationFixtures(unittest.TestCase):
    def test_public_materialization_and_separate_grader(self):
        fixtures = sorted((DATA / "fixtures").glob("communication-*.json"))
        self.assertEqual(len(fixtures), 7)
        with tempfile.TemporaryDirectory() as temporary:
            for path in fixtures:
                with self.subTest(fixture=path.name):
                    fixture = evaluation.load_json(path)
                    grader = evaluation.load_json(DATA / "graders" / path.name)
                    evaluation.validate_fixture(fixture)
                    self.assertEqual(grader["fixture_id"], fixture["id"])
                    self.assertEqual(grader["fixture_revision"], fixture["revision"])
                    self.assertTrue(grader["criteria"])
                    target = Path(temporary) / fixture["id"]
                    evaluation.materialize(fixture, target)
                    expected = {item["path"] for item in fixture["agent"]["inputs"]}
                    actual = {file.relative_to(target).as_posix()
                              for file in target.rglob("*") if file.is_file()}
                    self.assertEqual(actual, expected)
                    for item in fixture["agent"]["inputs"]:
                        self.assertEqual((target / item["path"]).read_text(), item["content"])


    def test_poll_inputs_do_not_reveal_future_observations(self):
        fixture = evaluation.load_json(DATA / "fixtures/communication-polls.json")
        grader = evaluation.load_json(DATA / "graders/communication-polls.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "agent"
            evaluation.materialize(fixture, root)
            initial = evaluation.load_json(root / "poll-stream.json")
            # A terminal observation visible initially makes cadence untestable.
            self.assertEqual([item["unit"] for item in initial["snapshots"]], ["running"])
            stages = grader["subsequent_observations"]
            self.assertEqual([item["unit"] for item in stages],
                             ["running", "running", "success"])
            self.assertEqual([item["poll"] for item in initial["snapshots"] + stages],
                             [1, 2, 3, 4])
            self.assertNotIn("subsequent_observations", initial)


class CommunicationAccounting(unittest.TestCase):
    def setUp(self):
        # The comparator is the single owner of channel accounting.
        self.result = evaluation.load_json(evaluation.CONTRACT.parent / "results/synthetic.json")
        self.result["planned_attempts"] = self.result["planned_attempts"][:1]
        self.result["attempts"] = self.result["attempts"][:1]
        self.attempt = self.result["attempts"][0]
        self.attempt["functional"] = {"verdict": "not_run", "evidence": []}
        self.attempt["evaluator"] = {"verdict": "not_run", "evidence": []}

    def counts(self, observations):
        self.attempt["observations"] = observations
        evaluation.validate_result(self.result)
        before = copy.deepcopy(self.result)
        counts = compare_evaluations.observation_counts(self.result)
        self.assertEqual(self.result, before, "Accounting cannot assign behavior verdicts")
        return counts

    def test_helper_only_bad_control_and_actual_visible_relay(self):
        # Identical prose has different communication provenance.
        text = "Current check passed; deployment still needs approval."
        logs = [{"channel": "helper", "text": text},
                {"channel": "tool", "text": text}]
        self.assertEqual(self.counts(logs), {"user": 0, "tool": 1, "helper": 1})
        self.assertEqual(self.counts(logs + [{"channel": "user", "text": text}]),
                         {"user": 1, "tool": 1, "helper": 1})

    def test_repeated_polls_and_final_handoff(self):
        trace = [{"channel": "helper", "text": "poll: running"} for _ in range(3)]
        trace += [{"channel": "tool", "text": "poll: success"},
                  {"channel": "user", "text": "Check finished successfully."}]
        self.assertEqual(self.counts(trace), {"user": 1, "tool": 1, "helper": 3})
        trace[-1]["text"] = "All production systems are deployed."
        # This materially false claim needs semantic grading: counts cannot detect it.
        self.assertEqual(self.counts(trace), {"user": 1, "tool": 1, "helper": 3})

    def test_no_observations_is_not_a_behavior_pass(self):
        with self.assertRaises(ValueError):
            self.counts([])  # An evidence-free attempt cannot claim completion.
        self.attempt["state"] = "missing"
        self.attempt["reason"] = "No attempt evidence or user-event capture obtained."
        self.assertEqual(self.counts([]), {"user": 0, "tool": 0, "helper": 0})
        self.assertEqual(self.attempt["evaluator"]["verdict"], "not_run")

    def test_unknown_channel_is_rejected(self):
        self.attempt["observations"] = [{"channel": "analysis", "text": "Ready"}]
        with self.assertRaises(ValueError):
            evaluation.validate_result(self.result)


if __name__ == "__main__":
    unittest.main()
