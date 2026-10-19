"""Offline delivery fixture construction controls, not agent or native-host trials."""
import hashlib
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


class RoutingFixtures(unittest.TestCase):
    """Calibrate bounded public inputs and private executable controls.

    These tests do not grade skill calls. That requires actual tool/user traces
    and the semantic criteria in each private grader, with isolation disclosed.
    """

    NAMES = ("routing-upgrade-assess", "routing-upgrade-implement",
             "routing-codex-audit", "routing-codex-implement",
             "routing-refactor", "routing-clean", "routing-simple-implement")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="develop-routing-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def materialize(self, name):
        fixture = evaluation.load_json(DATA / "fixtures" / (name + ".json"))
        grader = evaluation.load_json(DATA / "graders" / (name + ".json"))
        target = self.root / name
        hashes = evaluation.materialize(fixture, target)
        return fixture, grader, target, hashes

    @staticmethod
    def inventory(target):
        return {path.relative_to(target).as_posix(): path.read_bytes()
                for path in target.rglob("*") if path.is_file()}

    @staticmethod
    def run_python(target, *arguments):
        return subprocess.run([sys.executable, "-B", *arguments], cwd=target,
                              capture_output=True, text=True, check=False,
                              timeout=20)

    def test_all_routing_inputs_materialize_exactly_without_private_criteria(self):
        for name in self.NAMES:
            with self.subTest(fixture=name):
                fixture, grader, target, hashes = self.materialize(name)
                evaluation.validate_fixture(fixture)
                self.assertEqual((grader["fixture_id"], grader["fixture_revision"]),
                                 (fixture["id"], fixture["revision"]))
                expected = {row["path"]: row["content"].encode("utf-8")
                            for row in fixture["agent"]["inputs"]}
                self.assertEqual(self.inventory(target), expected)
                self.assertEqual(hashes, {path: hashlib.sha256(data).hexdigest()
                                          for path, data in expected.items()})
                self.assertEqual(set(fixture), {"schema_version", "id", "revision",
                                               "scenario_ref", "agent"})
                self.assertEqual(set(fixture["agent"]), {"prompt", "inputs"})
                public = json.dumps(fixture, ensure_ascii=False)
                ids = [criterion["id"] for criterion in grader["criteria"]]
                self.assertEqual(len(ids), len(set(ids)))
                for criterion in grader["criteria"]:
                    self.assertTrue(criterion["evidence"])
                    self.assertNotIn(criterion["pass_when"], public)
                    self.assertNotIn(criterion["evidence"], public)
                for key in ("oracle_python", "candidates"):
                    self.assertNotIn(key, fixture)
                    if key in grader:
                        self.assertNotIn(json.dumps(grader[key]), public)

    def test_assessment_implementation_pairs_have_identical_evidence(self):
        # The task authority changes; supplied dependency/schema facts do not.
        for prefix, audit in (("upgrade", "assess"), ("codex", "audit")):
            with self.subTest(owner=prefix):
                readonly, _, _, _ = self.materialize(f"routing-{prefix}-{audit}")
                writable, _, _, _ = self.materialize(f"routing-{prefix}-implement")
                self.assertEqual(readonly["agent"]["inputs"],
                                 writable["agent"]["inputs"])
                self.assertNotEqual(readonly["agent"]["prompt"],
                                    writable["agent"]["prompt"])

    def test_refactor_oracle_accepts_baseline_and_shared_helper_rejects_regressions(self):
        _, grader, target, _ = self.materialize("routing-refactor")
        before = self.inventory(target)
        repo = target / "repo"
        source = repo / "report.py"
        original = source.read_text(encoding="utf-8")
        candidates = [{"id": "unchanged-baseline", "passes": True,
                       "source": original}, *grader["candidates"]]
        for candidate in candidates:
            with self.subTest(candidate=candidate["id"]):
                source.write_text(candidate["source"], encoding="utf-8")
                result = self.run_python(repo, "-c", grader["oracle_python"], "-v")
                self.assertIn("Ran 6 tests", result.stderr)
                if candidate["passes"]:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    public = self.run_python(repo, "-m", "unittest", "discover",
                                             "-s", "tests", "-v")
                    self.assertEqual(public.returncode, 0, public.stderr)
                    self.assertIn("Ran 2 tests", public.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    # The named behavior must fail by assertion, not merely an
                    # import/syntax error or unrelated exception in another test.
                    self.assertIn("FAIL: " + candidate["rejected_by"], result.stderr)
                    self.assertIn("AssertionError", result.stderr)
        after = self.inventory(target)
        self.assertEqual(set(before), set(after))
        for path in before.keys() - {"repo/report.py"}:
            self.assertEqual(before[path], after[path], path)

    def test_upgrade_control_uses_target_and_preserves_public_results(self):
        _, _, target, _ = self.materialize("routing-upgrade-implement")
        repo = target / "repo"
        before = self.inventory(target)
        for content in (before["repo/invoice.py"].decode("utf-8"),
                        "from vendor_v2 import total\n\ndef invoice(cents):\n"
                        "    return total(cents)\n"):
            (repo / "invoice.py").write_text(content, encoding="utf-8")
            result = self.run_python(repo, "-m", "unittest", "discover", "-s", "tests")
            self.assertEqual(result.returncode, 0, result.stderr)
        # In this evaluator-owned copy, absence of v1 proves the candidate does
        # not merely retain the old implementation while passing its old tests.
        (repo / "vendor_v1.py").rename(repo / "vendor_v1.saved")
        result = self.run_python(repo, "-m", "unittest", "discover", "-s", "tests")
        self.assertEqual(result.returncode, 0, result.stderr)
        (repo / "vendor_v1.saved").rename(repo / "vendor_v1.py")
        after = self.inventory(target)
        self.assertEqual(set(before), set(after))
        for path in before.keys() - {"repo/invoice.py"}:
            self.assertEqual(before[path], after[path], path)

    def test_fictional_codex_check_detects_then_accepts_scoped_sample_repair(self):
        _, _, target, _ = self.materialize("routing-codex-implement")
        before = self.inventory(target)
        result = self.run_python(target / "repo", "check_sample.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AssertionError", result.stderr)
        sample = target / "repo/codex-sample.json"
        data = json.loads(sample.read_text(encoding="utf-8"))
        data["demo_timeout_seconds"] = data.pop("demo_timeout")
        sample.write_text(json.dumps(data) + "\n", encoding="utf-8")
        result = self.run_python(target / "repo", "check_sample.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.inventory(target)
        self.assertEqual(set(before), set(after))
        for path in before.keys() - {"repo/codex-sample.json"}:
            self.assertEqual(before[path], after[path], path)

    def test_cleanup_output_is_reconstructable_and_unrelated_inputs_survive(self):
        _, _, target, _ = self.materialize("routing-clean")
        before = self.inventory(target)
        output = target / ".task-work/generated.txt"
        output.unlink()
        self.assertEqual(self.inventory(target),
                         {path: content for path, content in before.items()
                          if path != ".task-work/generated.txt"})
        result = self.run_python(target / "repo", "rebuild.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.inventory(target), before)

    def test_simple_fix_leaves_visible_duplication_and_scratch_unchanged(self):
        _, _, target, _ = self.materialize("routing-simple-implement")
        before = self.inventory(target)
        oracle = ("from labels import item_label\n"
                  "for n in (0, 1, 2, 100):\n"
                  "    expected = '1 item' if n == 1 else f'{n} items'\n"
                  "    assert item_label(n) == expected, (n, item_label(n))\n")
        result = self.run_python(target / "repo", "-c", oracle)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AssertionError", result.stderr)
        (target / "repo/labels.py").write_text(
            'def item_label(count):\n'
            '    return "1 item" if count == 1 else f"{count} items"\n',
            encoding="utf-8")
        result = self.run_python(target / "repo", "-c", oracle)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.inventory(target)
        self.assertEqual(set(before), set(after))
        for path in before.keys() - {"repo/labels.py"}:
            self.assertEqual(before[path], after[path], path)


if __name__ == "__main__":
    unittest.main()
