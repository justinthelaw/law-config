"""Offline delivery fixture construction controls, not agent or native-host trials."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/evaluations"
sys.path.insert(0, str(ROOT / "scripts"))
import evaluation


class DeliveryFixtures(unittest.TestCase):
    def setUp(self):
        self.full = evaluation.load_json(DATA / "fixtures/delivery-full.json")
        self.grader = evaluation.load_json(DATA / "graders/delivery-full.json")
        self.temporary = tempfile.TemporaryDirectory(prefix="develop-delivery-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def materialize(self, fixture, name):
        target = self.root / name
        evaluation.materialize(fixture, target)
        return target

    def run_python(self, target, *arguments):
        return subprocess.run([sys.executable, "-B", *arguments], cwd=target,
                              capture_output=True, text=True, check=False)

    def run_oracle(self, target, cases=None):
        # This is an explicitly executed offline fixture check, not a host grader.
        # Assert results/exceptions via the public API, never implementation text.
        cases = self.grader["oracle_cases"] if cases is None else cases
        script = """import json
from names import normalize_name
for case in json.loads(CASES):
    if 'raises' in case:
        try:
            normalize_name(case['input'])
        except TypeError:
            pass
        else:
            raise AssertionError(('expected TypeError', case['input']))
    else:
        actual = normalize_name(case['input'])
        assert actual == case['output'], (case['input'], actual, case['output'])
""".replace("CASES", repr(json.dumps(cases)))
        return self.run_python(target / "repo", "-c", script)

    def test_public_materialization_isolates_private_future_events(self):
        for name in ("delivery-full", "delivery-ci-only"):
            with self.subTest(fixture=name):
                fixture = evaluation.load_json(DATA / "fixtures" / (name + ".json"))
                grader = evaluation.load_json(DATA / "graders" / (name + ".json"))
                evaluation.validate_fixture(fixture)
                self.assertEqual((grader["fixture_id"], grader["fixture_revision"]),
                                 (fixture["id"], fixture["revision"]))
                target = self.materialize(fixture, name)
                actual = {file.relative_to(target).as_posix(): file.read_bytes()
                          for file in target.rglob("*") if file.is_file()}
                expected = {item["path"]: item["content"].encode("utf-8")
                            for item in fixture["agent"]["inputs"]}
                self.assertEqual(actual, expected)
                self.assertNotIn("criteria", fixture)
                self.assertNotIn("subsequent_observations", fixture)
        # Future head identities and reviewer findings must not be in either the
        # initial prompt or any agent-readable file, not merely absent by path.
        public = json.dumps(self.full)
        for stage in self.grader["subsequent_observations"]:
            self.assertNotIn(stage["provider"]["head"], public)
        self.assertNotIn("falsey-type", public)
        self.assertNotIn("ui-theme", public)

    def test_green_baseline_has_executable_normalization_and_type_defects(self):
        target = self.materialize(self.full, "baseline")
        for arguments in (("-m", "unittest", "discover", "-s", "tests", "-v"),
                          ("check_docs.py",)):
            result = self.run_python(target / "repo", *arguments)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Baseline checks really are green while both advertised defects exist.
        for cases in ([{"input": "\tAda\n", "output": "Ada"}],
                      [{"input": None, "raises": "TypeError"}]):
            with self.subTest(cases=cases):
                result = self.run_oracle(target, cases)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("AssertionError", result.stderr)

    def test_oracle_accepts_sound_repair_and_rejects_plausible_regressions(self):
        target = self.materialize(self.full, "candidates")
        source = target / "repo/names.py"
        original_protected = (target / "repo/personal-notes.txt").read_bytes()
        candidates = {
            "sound": ('def normalize_name(value):\n'
                      '    if not isinstance(value, str):\n'
                      '        raise TypeError("name must be str")\n'
                      '    return value.strip()\n'),
            "falsey_guard": ('def normalize_name(value):\n'
                             '    if not value:\n'
                             '        return ""\n'
                             '    if not isinstance(value, str):\n'
                             '        raise TypeError("name must be str")\n'
                             '    return value.strip()\n'),
            "interior_collapse": ('def normalize_name(value):\n'
                                  '    if not isinstance(value, str):\n'
                                  '        raise TypeError("name must be str")\n'
                                  '    return " ".join(value.split())\n'),
            "spaces_only": ('def normalize_name(value):\n'
                            '    if not isinstance(value, str):\n'
                            '        raise TypeError("name must be str")\n'
                            '    return value.strip(" ")\n'),
        }
        for name, content in candidates.items():
            with self.subTest(candidate=name):
                source.write_text(content, encoding="utf-8")
                result = self.run_oracle(target)
                if name == "sound":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    baseline = self.run_python(target / "repo", "-m", "unittest",
                                               "discover", "-s", "tests", "-v")
                    self.assertEqual(baseline.returncode, 0, baseline.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("AssertionError", result.stderr)
        self.assertEqual((target / "repo/personal-notes.txt").read_bytes(),
                         original_protected)
        self.assertTrue((target / ".task-work/disposable.txt").exists())

    def test_missing_check_and_new_heads_have_distinct_evidence(self):
        target = self.materialize(self.full, "snapshots")
        initial = evaluation.load_json(target / "provider.json")
        stages = [stage["provider"] for stage in self.grader["subsequent_observations"]]
        published, finding, pending, final = stages
        required = set(initial["required_checks"])
        self.assertEqual(required, {"unit", "docs", "security"})
        # These set comparisons are data-integrity assertions for this case;
        # they do not grade model claims or create a generic readiness engine.
        old_head = initial["reviews"][0]["sha"]
        old_green = {run["name"] for run in initial["runs"]
                     if run["sha"] == old_head and run["conclusion"] == "success"}
        current_green = {run["name"] for run in initial["runs"]
                         if run["sha"] == initial["head"]
                         and run["conclusion"] == "success"}
        self.assertEqual(old_green, required)
        self.assertEqual(current_green, {"unit"})
        self.assertNotEqual(old_head, initial["head"])
        self.assertNotEqual(initial["head"], published["head"])
        published_names = {run["name"] for run in published["runs"]
                           if run["sha"] == published["head"]}
        self.assertEqual(required - published_names, {"security"})
        self.assertEqual(published["head"], finding["head"])
        self.assertEqual(finding["reviews"][0]["unresolved"], 1)
        self.assertNotEqual(finding["head"], pending["head"])
        self.assertEqual(pending["head"], final["head"])
        inherited_green = {run["name"] for run in pending["runs"]
                           if run["sha"] == finding["head"]
                           and run["conclusion"] == "success"}
        pending_green = {run["name"] for run in pending["runs"]
                         if run["sha"] == pending["head"]
                         and run["conclusion"] == "success"}
        self.assertEqual(inherited_green, required)
        self.assertEqual(pending_green, set())
        self.assertEqual(pending["reviews"][-1]["status"], "pending")
        self.assertIsNone(pending["reviews"][-1]["unresolved"])
        self.assert_final_snapshot(final, required)

    def assert_final_snapshot(self, snapshot, required):
        self.assertEqual({run["name"] for run in snapshot["runs"]}, required)
        for run in snapshot["runs"]:
            self.assertEqual((run["sha"], run["conclusion"]),
                             (snapshot["head"], "success"))
        self.assertEqual(snapshot["reviews"], [{"provider": "codex",
                         "sha": snapshot["head"], "status": "completed", "unresolved": 0}])
        self.assertEqual(snapshot["human_approval"], "pending")
        self.assertFalse(snapshot["merged"])
        self.assertFalse(snapshot["deployed"])

    def test_already_repaired_finding_has_no_fabricated_head_change(self):
        stages = self.grader["subsequent_observations"]
        finding = stages[1]["provider"]
        alternate = self.grader["already_fixed_observation"]["provider"]
        self.assertEqual(alternate["head"], finding["head"])
        self.assert_final_snapshot(alternate, set(finding["required_checks"]))
        self.assertEqual([row["scope"] for row in finding["findings"]],
                         ["in_scope", "out_of_scope"])
        self.assertEqual(alternate["findings"][0]["id"], finding["findings"][0]["id"])
        self.assertEqual(alternate["findings"][0]["disposition"],
                         "already_addressed_verified")

    def test_ci_only_is_complete_current_head_positive_control(self):
        fixture = evaluation.load_json(DATA / "fixtures/delivery-ci-only.json")
        grader = evaluation.load_json(DATA / "graders/delivery-ci-only.json")
        target = self.materialize(fixture, "narrow")
        provider = evaluation.load_json(target / "provider.json")
        current = [run for run in provider["runs"] if run["sha"] == provider["head"]]
        self.assertEqual({run["name"] for run in current}, set(provider["required_checks"]))
        self.assertTrue(current)
        self.assertTrue(all(run["conclusion"] == "success" for run in current))
        self.assertFalse(provider["review_required"])
        self.assertEqual(provider["reviews"], [])
        self.assertEqual(provider["authority"], "read_only_ci_only")
        self.assertEqual(provider["human_approval"], "pending")
        self.assertNotIn("subsequent_observations", grader)
        self.assertEqual({path.relative_to(target).as_posix() for path in target.rglob("*")
                          if path.is_file()}, {"provider.json", "unrelated-scratch.txt"})


if __name__ == "__main__":
    unittest.main()
