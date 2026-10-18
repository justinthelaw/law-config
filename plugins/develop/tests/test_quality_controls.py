"""Execute trusted, bounded test-quality controls; never an agent-code sandbox."""
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluation import load_json, materialize, validate_fixture

CASES = ROOT / "tests/evaluations"

# Evaluator-owned variants: one boundary defect and one equivalent refactor.
# They stay outside the materialized agent inputs.
VARIANTS = {
    "defect": '''def shipping_fee(subtotal_cents):
    if subtotal_cents < 0:
        raise ValueError("subtotal must be nonnegative")
    return 0 if subtotal_cents > 5000 else 500
''',
    "benign": '''def shipping_fee(subtotal_cents):
    if subtotal_cents < 0:
        raise ValueError("subtotal must be nonnegative")
    if subtotal_cents < 5000:
        return 500
    return 0
''',
}


def fixture(name):
    data = load_json(CASES / "fixtures" / f"quality-{name}.json")
    validate_fixture(data)
    return data


def inputs(name):
    return {item["path"]: item["content"] for item in fixture(name)["agent"]["inputs"]}


class QualityResult(unittest.TextTestResult):
    """Distinguish a skipped method from a skipped subtest within a method."""
    wholly_skipped = 0
    active_test = None

    def startTest(self, test):
        self.active_test = test
        super().startTest(test)

    def addSkip(self, test, reason):
        if test is self.active_test:
            self.wholly_skipped += 1
        super().addSkip(test, reason)

    def stopTest(self, test):
        super().stopTest(test)
        self.active_test = None


def run_suite(source, implementation, test_name=None):
    """Run trusted packaged Python in fresh modules, restoring the import table."""
    shipping = types.ModuleType("shipping")
    tests = types.ModuleType("quality_case")
    exec(compile(implementation, "shipping.py", "exec"), shipping.__dict__)
    with patch.dict(sys.modules, {"shipping": shipping}):
        exec(compile(source, "test_shipping.py", "exec"), tests.__dict__)
        loader = unittest.TestLoader()
        suite = (loader.loadTestsFromName(test_name, tests) if test_name
                 else loader.loadTestsFromModule(tests))
        return unittest.TextTestRunner(stream=io.StringIO(), resultclass=QualityResult).run(suite)


def assess(source, reference):
    """Accept only useful runs on both controls and assertion detection of the bug."""
    results = {name: run_suite(source, implementation)
               for name, implementation in {"reference": reference, **VARIANTS}.items()}
    complete = all(result.testsRun > result.wholly_skipped + len(result.expectedFailures)
                   and not result.errors and not result.unexpectedSuccesses
                   for result in results.values())
    accepted = (complete and results["reference"].wasSuccessful()
                and results["benign"].wasSuccessful() and bool(results["defect"].failures))
    return accepted, results


class QualityControls(unittest.TestCase):
    def setUp(self):
        self.weak = inputs("weak-tests")
        self.sound = inputs("sound-control")

    def test_fixtures_share_contract_and_matching_graders(self):
        for name in ("weak-tests", "sound-control"):
            with self.subTest(name=name):
                data = fixture(name)
                grader = load_json(CASES / "graders" / f"quality-{name}.json")
                self.assertEqual(grader["fixture_id"], data["id"])
                self.assertEqual(grader["fixture_revision"], data["revision"])
                self.assertTrue(grader["criteria"])

    def test_materialized_inputs_exclude_evaluator_controls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "agent"
            materialize(fixture("weak-tests"), destination)
            self.assertEqual({p.name for p in destination.iterdir()},
                             {"README.md", "shipping.py", "test_shipping.py"})
            self.assertEqual((destination / "shipping.py").read_text(encoding="utf-8"),
                             self.weak["shipping.py"])

    def test_defect_is_bounded_to_threshold_and_benign_preserves_contract(self):
        for name, source in {"reference": self.weak["shipping.py"], **VARIANTS}.items():
            with self.subTest(name=name):
                namespace = {}
                exec(source, namespace)
                fee = namespace["shipping_fee"]
                expected = [500, 500, 500 if name == "defect" else 0, 0, 0]
                self.assertEqual([fee(n) for n in (0, 4999, 5000, 5001, 10000)], expected)
                with self.assertRaises(ValueError):
                    fee(-1)

    def test_each_known_bad_test_passes_even_with_defect(self):
        for name in ("test_tautology", "test_vacuous", "test_unreachable"):
            with self.subTest(name=name):
                result = run_suite(self.weak["test_shipping.py"], VARIANTS["defect"],
                                   f"ShippingTests.{name}")
                self.assertEqual(result.testsRun, 1)
                self.assertTrue(result.wasSuccessful())
                self.assertFalse(result.skipped)

    def test_passing_weak_suite_is_rejected(self):
        accepted, results = assess(self.weak["test_shipping.py"], self.weak["shipping.py"])
        self.assertFalse(accepted)
        for result in results.values():
            self.assertEqual(result.testsRun, 3)
            self.assertTrue(result.wasSuccessful())

    def test_sound_suite_passes_benign_and_detects_seeded_bug(self):
        accepted, results = assess(self.sound["test_shipping.py"], self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertTrue(results["reference"].wasSuccessful())
        self.assertTrue(results["benign"].wasSuccessful())
        self.assertEqual(results["defect"].testsRun, 2)
        self.assertEqual(len(results["defect"].failures), 1)
        self.assertEqual(results["defect"].errors, [])

    def test_unrelated_skip_preserves_executed_boundary_evidence(self):
        suite = self.sound["test_shipping.py"] + """
class OptionalTests(unittest.TestCase):
    @unittest.skip("unrelated optional platform")
    def test_optional(self):
        self.fail()
"""
        accepted, results = assess(suite, self.sound["shipping.py"])
        self.assertTrue(accepted)
        for result in results.values():
            self.assertEqual(result.testsRun, 3)
            self.assertEqual(len(result.skipped), 1)
        self.assertEqual(len(results["defect"].failures), 1)

    def test_unrelated_expected_failure_preserves_boundary_evidence(self):
        suite = self.sound["test_shipping.py"] + """
class OptionalTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_known_unrelated_bug(self):
        self.fail("known unrelated behavior")
"""
        accepted, results = assess(suite, self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertTrue(all(len(result.expectedFailures) == 1 for result in results.values()))
        self.assertEqual(len(results["defect"].failures), 1)

    def test_skipped_subtest_does_not_hide_executed_boundary_assertion(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        with self.subTest(optional=True):
            self.skipTest("unrelated optional case")
        self.assertEqual(shipping_fee(5000), 0)
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertTrue(all(result.testsRun == len(result.skipped) == 1
                            for result in results.values()))

    def test_only_skipped_subtests_cannot_detect_the_defect(self):
        source = """import unittest
class Tests(unittest.TestCase):
    def test_optional(self):
        with self.subTest(optional=True):
            self.skipTest("no executed assertion")
"""
        accepted, _ = assess(source, self.sound["shipping.py"])
        self.assertFalse(accepted)

    def test_expected_failure_only_suite_is_incomplete(self):
        suite = """import unittest
class Tests(unittest.TestCase):
    @unittest.expectedFailure
    def test_expected(self):
        self.fail("expected")
"""
        accepted, results = assess(suite, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertTrue(all(result.testsRun == len(result.expectedFailures)
                            for result in results.values()))

    def test_unexpected_success_is_not_sound_reference_evidence(self):
        suite = self.sound["test_shipping.py"] + """
class OptionalTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_unexpectedly_passes(self):
        self.assertTrue(True)
"""
        accepted, results = assess(suite, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertEqual(len(results["reference"].unexpectedSuccesses), 1)

    def test_empty_suite_is_incomplete(self):
        accepted, results = assess("", self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertTrue(all(result.testsRun == 0 for result in results.values()))

    def test_skipped_suite_is_incomplete(self):
        suite = '''import unittest
class Tests(unittest.TestCase):
    @unittest.skip("not exercised")
    def test_threshold(self):
        self.fail()
'''
        accepted, results = assess(suite, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertEqual(len(results["defect"].skipped), 1)

    def test_unconditional_failure_is_not_detection(self):
        suite = '''import unittest
class Tests(unittest.TestCase):
    def test_always_fails(self):
        self.fail("independent of implementation")
'''
        accepted, results = assess(suite, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertTrue(all(result.failures for result in results.values()))

    def test_error_on_defect_is_not_assertion_detection(self):
        suite = '''import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_threshold(self):
        if shipping_fee(5000) != 0:
            raise RuntimeError("test harness failed")
'''
        accepted, results = assess(suite, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertTrue(results["reference"].wasSuccessful())
        self.assertTrue(results["benign"].wasSuccessful())
        self.assertEqual(len(results["defect"].errors), 1)


if __name__ == "__main__":
    unittest.main()
