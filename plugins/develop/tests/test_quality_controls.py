"""Execute trusted, bounded test-quality controls; never an agent-code sandbox."""
import ast
import io
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluation import load_json, materialize, validate_fixture

CASES = ROOT / "tests/evaluations"
ACTIVE_BODY = ContextVar("quality_active_body", default=None)

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
    """A skip needs observed assertion evidence; count each affected method once."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.skipped_methods = set()
        self.active_test = None
        self.passed_assertions = set()
        self.failed_assertions = set()

    @property
    def wholly_skipped(self):
        return len(self.skipped_methods)

    def startTest(self, test):
        self.active_test = test
        test._quality_assertion_executed = False
        test._quality_passed_assertions = set()
        super().startTest(test)

    def addSkip(self, test, reason):
        if self.active_test is not None:
            self.skipped_methods.add(id(self.active_test))
        super().addSkip(test, reason)

    def stopTest(self, test):
        self.passed_assertions.update(test._quality_passed_assertions)
        if test._quality_assertion_executed:
            self.skipped_methods.discard(id(test))
        super().stopTest(test)
        self.active_test = None

    def record_failure_site(self, err):
        site = getattr(err[1], "_quality_assertion_site", None)
        if site is not None:
            self.failed_assertions.add(site)

    def addFailure(self, test, err):
        self.record_failure_site(err)
        super().addFailure(test, err)

    def addSubTest(self, test, subtest, err):
        if err is not None and issubclass(err[0], test.failureException):
            self.record_failure_site(err)
        super().addSubTest(test, subtest, err)


@contextmanager
def body_execution(test):
    token = ACTIVE_BODY.set(test)
    try:
        yield
    finally:
        ACTIVE_BODY.reset(token)


def assertion_site():
    """Identify the source call, including distinct calls on the same line."""
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_filename == "test_shipping.py":
            return ("call", frame.f_code.co_firstlineno, frame.f_lasti)
        frame = frame.f_back
    return None


def record_assertion(site, error=None):
    test = ACTIVE_BODY.get()
    if test is not None and site is not None:
        test._quality_assertion_executed = True
        site = (test.id(), site)
        if error is None:
            test._quality_passed_assertions.add(site)
        else:
            error._quality_assertion_site = site


class ObservedAssertionContext:
    """Context construction alone is not execution of its assertion."""
    def __init__(self, context, site):
        self.context = context
        self.site = site

    def __getattr__(self, name):
        return getattr(self.context, name)

    def __enter__(self):
        return self.context.__enter__()

    def __exit__(self, exc_type, value, traceback):
        try:
            suppressed = self.context.__exit__(exc_type, value, traceback)
        except AssertionError as error:
            record_assertion(self.site, error)
            raise
        if exc_type is None or suppressed:
            record_assertion(self.site)
        return suppressed


def observe_assertion(method):
    @wraps(method)
    def observed(*args, **kwargs):
        site = assertion_site()
        try:
            result = method(*args, **kwargs)
        except AssertionError as error:
            record_assertion(site, error)
            raise
        if hasattr(result, "__enter__") and hasattr(result, "__exit__"):
            return ObservedAssertionContext(result, site)
        record_assertion(site)
        return result
    return observed


def observe_python_assert(site, failed=False):
    error = sys.exc_info()[1] if failed else None
    if not failed or isinstance(error, AssertionError):
        record_assertion(site, error)


class ObservePythonAssertions(ast.NodeTransformer):
    def __init__(self, observer_name):
        self.observer_name = observer_name

    def visit_Assert(self, node):
        site = ast.Constant(value=("assert", node.lineno, node.col_offset))

        def observed(failed):
            return ast.Expr(value=ast.Call(
                func=ast.Name(id=self.observer_name, ctx=ast.Load()),
                args=[site, ast.Constant(value=failed)], keywords=[]))

        # Keep Python's original truth/message evaluation and exception object.
        return ast.copy_location(ast.Try(
            body=[node],
            handlers=[ast.ExceptHandler(type=None, name=None,
                                       body=[observed(True), ast.Raise()])],
            orelse=[observed(False)], finalbody=[]), node)


def track_body(method):
    """Observe the trusted test body separately from setup/teardown/cleanup."""
    if inspect.iscoroutinefunction(method):
        @wraps(method)
        async def tracked(test, *args, **kwargs):
            with body_execution(test):
                return await method(test, *args, **kwargs)
    else:
        @wraps(method)
        def tracked(test, *args, **kwargs):
            with body_execution(test):
                return method(test, *args, **kwargs)
    return tracked


def run_suite(source, implementation, test_name=None):
    """Run trusted packaged Python in fresh modules, restoring the import table."""
    shipping = types.ModuleType("shipping")
    tests = types.ModuleType("quality_case")
    with patch.dict(sys.modules, {"shipping": shipping}):
        try:
            exec(compile(implementation, "shipping.py", "exec"), shipping.__dict__)
            observer_name = "_quality_assert"
            while observer_name in source:
                observer_name += "_"
            tree = ast.fix_missing_locations(
                ObservePythonAssertions(observer_name).visit(ast.parse(source)))
            tests.__dict__[observer_name] = observe_python_assert
            exec(compile(tree, "test_shipping.py", "exec"), tests.__dict__)
        except Exception:
            result = QualityResult(io.StringIO(), descriptions=False, verbosity=0)
            module_load = unittest.FunctionTestCase(lambda: None, description="module loading")
            result.addError(module_load, sys.exc_info())
            return result
        loader = unittest.TestLoader()
        for candidate in vars(tests).values():
            if (isinstance(candidate, type) and issubclass(candidate, unittest.TestCase)
                    and candidate.__module__ == tests.__name__):
                for name in dir(unittest.TestCase):
                    method = getattr(unittest.TestCase, name)
                    if (callable(method)
                            and (name.startswith(("assert", "failUnless", "failIf")) or name == "fail")
                            and getattr(candidate, name, None) is method):
                        setattr(candidate, name, observe_assertion(method))
                for name in loader.getTestCaseNames(candidate):
                    setattr(candidate, name, track_body(getattr(candidate, name)))
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
                and results["benign"].wasSuccessful()
                and bool(results["defect"].failed_assertions
                         & results["reference"].passed_assertions
                         & results["benign"].passed_assertions))
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

    def test_boundary_assertion_before_in_body_skip_is_preserved(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        self.assertEqual(shipping_fee(5000), 0)
        self.skipTest("unrelated remaining work")
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertEqual(len(results["reference"].skipped), 1)
        self.assertEqual(len(results["defect"].failures), 1)

    def test_conditional_skipped_only_subtests_cannot_certify_controls(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        with self.subTest(boundary=True):
            if shipping_fee(5000) == 0:
                self.skipTest("control assertion never runs")
            self.assertEqual(shipping_fee(5000), 0)
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertEqual(len(results["reference"].skipped), 1)
        self.assertEqual(len(results["defect"].failures), 1)

    def test_unrelated_assertion_cannot_replace_skipped_detecting_site(self):
        for assertion in (
            "self.assertEqual(shipping_fee(5000), 0)",
            "assert shipping_fee(5000) == 0",
            "with self.assertRaises(ZeroDivisionError):\n"
            "    1 // shipping_fee(5000)",
        ):
            source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        self.assertTrue(True)
        with self.subTest(boundary=True):
            if shipping_fee(5000) == 0:
                self.skipTest("detecting assertion never runs on controls")
ASSERTION
""".replace("ASSERTION", "\n".join("            " + line
                                      for line in assertion.splitlines()))
            with self.subTest(assertion=assertion):
                accepted, results = assess(source, self.sound["shipping.py"])
                self.assertFalse(accepted)
                self.assertEqual(len(results["defect"].failures), 1)
                self.assertTrue(results["reference"].wasSuccessful())
                self.assertTrue(results["benign"].wasSuccessful())

    def test_different_assertions_on_same_line_do_not_certify_controls(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        self.assertTrue(True) if shipping_fee(5000) == 0 else self.assertEqual(shipping_fee(5000), 0)
"""
        accepted, _ = assess(source, self.sound["shipping.py"])
        self.assertFalse(accepted)

    def test_same_context_assertion_passes_controls_and_detects_defect(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        with self.assertRaises(ZeroDivisionError):
            1 // shipping_fee(5000)
        self.skipTest("unrelated remaining work")
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertEqual(len(results["defect"].failures), 1)

    def test_caught_assertion_is_not_the_reported_defect_failure(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        try:
            self.assertEqual(shipping_fee(5000), 0)
        except AssertionError:
            pass
        if shipping_fee(5000) != 0:
            self.fail("unmatched assertion site")
"""
        accepted, _ = assess(source, self.sound["shipping.py"])
        self.assertFalse(accepted)

    def test_python_assert_before_skip_preserves_boundary_evidence(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        assert shipping_fee(5000) == 0, "boundary"
        self.skipTest("unrelated remaining work")
"""
        accepted, _ = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)

    def test_python_assert_keeps_truth_evaluation_and_failure_message(self):
        source = """import unittest
class Truth:
    calls = 0
    def __bool__(self):
        self.calls += 1
        return True
class Tests(unittest.TestCase):
    def test_truth(self):
        value = Truth()
        assert value
        self.assertEqual(value.calls, 1)
    def test_message(self):
        assert False, "preserved assertion message"
"""
        result = run_suite(source, self.sound["shipping.py"])
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.errors, [])
        self.assertIn("preserved assertion message", result.failures[0][1])

    def test_unentered_assertion_contexts_do_not_certify_skipped_controls(self):
        for context in ('self.assertRaises(ValueError)', 'self.assertLogs("quality")'):
            source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        CONTEXT
        if shipping_fee(5000) == 0:
            self.skipTest("context was never entered")
        self.assertEqual(shipping_fee(5000), 0)
""".replace("CONTEXT", context)
            with self.subTest(context=context):
                accepted, results = assess(source, self.sound["shipping.py"])
                self.assertFalse(accepted)
                self.assertEqual(results["reference"].wholly_skipped, 1)

    def test_skip_inside_assertion_context_does_not_certify_controls(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        with self.assertRaises(ValueError):
            if shipping_fee(5000) == 0:
                self.skipTest("assertion context did not finish")
            self.assertEqual(shipping_fee(5000), 0)
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertEqual(results["reference"].wholly_skipped, 1)

    def test_completed_assertion_context_retains_its_exception(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        with self.assertRaises(ValueError) as caught:
            shipping_fee(-1)
        self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual(shipping_fee(5000), 0)
        self.skipTest("unrelated remaining work")
"""
        accepted, _ = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)

    def test_saved_assertion_context_exposes_standard_attributes(self):
        for context_body in (
            "caught = self.assertRaises(ValueError)\n"
            "with caught:\n    shipping_fee(-1)\n"
            "self.assertIsInstance(caught.exception, ValueError)",
            "caught = self.assertWarns(UserWarning)\n"
            "with caught:\n    warnings.warn('observed', UserWarning)\n"
            "self.assertIsInstance(caught.warning, UserWarning)",
            "caught = self.assertLogs('quality', level='WARNING')\n"
            "with caught as captured:\n    logging.getLogger('quality').warning('observed')\n"
            "self.assertIs(caught.watcher, captured)\n"
            "self.assertEqual(caught.watcher.records[0].getMessage(), 'observed')\n"
            "self.assertEqual(captured.output, ['WARNING:quality:observed'])",
        ):
            source = """import logging
import unittest
import warnings
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
CONTEXT
        self.assertEqual(shipping_fee(5000), 0)
        self.skipTest("unrelated remaining work")
""".replace("CONTEXT", "\n".join("        " + line for line in context_body.splitlines()))
            with self.subTest(context=context_body):
                accepted, results = assess(source, self.sound["shipping.py"])
                self.assertTrue(accepted)
                self.assertTrue(all(not result.errors for result in results.values()))

    def test_available_legacy_assertions_before_skip_remain_evidence(self):
        assertions = {
            "failUnlessEqual": "self.failUnlessEqual(shipping_fee(5000), 0)",
            "failIfEqual": "self.failIfEqual(shipping_fee(5000), 500)",
            "failUnlessAlmostEqual": "self.failUnlessAlmostEqual(shipping_fee(5000), 0)",
            "failIfAlmostEqual": "self.failIfAlmostEqual(shipping_fee(5000), 500)",
            "failUnless": "self.failUnless(shipping_fee(5000) == 0)",
            "failIf": "self.failIf(shipping_fee(5000) != 0)",
            "failUnlessRaises": "with self.failUnlessRaises(ZeroDivisionError):\n"
                                "    1 // shipping_fee(5000)",
        }
        available = {name: body for name, body in assertions.items()
                     if hasattr(unittest.TestCase, name)}
        if not available:
            self.skipTest("this Python has removed the legacy assertion aliases")
        for name, body in available.items():
            source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
ASSERTION
        self.skipTest("unrelated remaining work")
""".replace("ASSERTION", "\n".join("        " + line for line in body.splitlines()))
            with self.subTest(alias=name):
                accepted, _ = assess(source, self.sound["shipping.py"])
                self.assertTrue(accepted)

    def test_python_assert_observer_does_not_shadow_source_bindings(self):
        source = """import unittest
from shipping import shipping_fee
_quality_assert = lambda value: bool(value)
def _quality_assert_():
    return 'candidate helper'
class Tests(unittest.TestCase):
    def test_boundary(self):
        _quality_assert__ = 'candidate local'
        assert shipping_fee(5000) == 0
        assert _quality_assert_() == 'candidate helper'
        assert _quality_assert__ == 'candidate local'
        self.skipTest("unrelated remaining work")
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertEqual(len(results["defect"].failures), 1)

    def test_async_assertion_before_in_body_skip_is_preserved(self):
        source = """import asyncio
import unittest
from shipping import shipping_fee
class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_boundary(self):
        await asyncio.sleep(0)
        self.assertEqual(shipping_fee(5000), 0)
        self.skipTest("unrelated remaining work")
"""
        accepted, _ = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)

    def test_post_body_skips_preserve_boundary_evidence(self):
        for setup in (
            '    def tearDown(self):\n        self.skipTest("optional teardown")\n',
            '    def setUp(self):\n        self.addCleanup(self.skipTest, "optional cleanup")\n',
        ):
            source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        self.assertEqual(shipping_fee(5000), 0)
""" + setup
            with self.subTest(setup=setup):
                accepted, results = assess(source, self.sound["shipping.py"])
                self.assertTrue(accepted)
                self.assertTrue(all(len(result.skipped) == 1 for result in results.values()))
                self.assertEqual(len(results["defect"].failures), 1)

    def test_repeated_pre_body_skips_preserve_other_executed_tests(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def test_boundary(self):
        self.assertEqual(shipping_fee(5000), 0)
class OptionalTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.skipTest, "optional cleanup")
        self.skipTest("optional setup")
    def test_optional(self):
        self.fail("body must not run")
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertTrue(all(len(result.skipped) == 2 for result in results.values()))

    def test_async_body_keeps_awaited_assertions_before_teardown_skip(self):
        source = """import asyncio
import unittest
from shipping import shipping_fee
class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_boundary(self):
        await asyncio.sleep(0)
        self.assertEqual(shipping_fee(5000), 0)
    async def asyncTearDown(self):
        self.skipTest("optional async teardown")
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertTrue(accepted)
        self.assertEqual(len(results["defect"].failures), 1)

    def test_pre_body_skip_cannot_certify_reference(self):
        source = """import unittest
from shipping import shipping_fee
class Tests(unittest.TestCase):
    def setUp(self):
        if shipping_fee(5000) == 0:
            self.skipTest("reference behavior not exercised")
    def test_boundary(self):
        self.assertEqual(shipping_fee(5000), 0)
"""
        accepted, results = assess(source, self.sound["shipping.py"])
        self.assertFalse(accepted)
        self.assertEqual(len(results["defect"].failures), 1)

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

    def test_module_load_errors_are_recorded_for_every_variant(self):
        for source, error in (
            ("import quality_dependency_that_does_not_exist", "ModuleNotFoundError"),
            ("raise RuntimeError('module load failed')", "RuntimeError"),
            ("def invalid syntax", "SyntaxError"),
        ):
            with self.subTest(error=error):
                original_shipping = types.ModuleType("shipping")
                with patch.dict(sys.modules, {"shipping": original_shipping}):
                    accepted, results = assess(source, self.sound["shipping.py"])
                    self.assertIs(sys.modules["shipping"], original_shipping)
                self.assertFalse(accepted)
                self.assertEqual(set(results), {"reference", "defect", "benign"})
                for result in results.values():
                    self.assertEqual(result.testsRun, 0)
                    self.assertEqual(len(result.errors), 1)
                    self.assertIn(error, result.errors[0][1])
                    self.assertFalse(result.failures)

    def test_implementation_load_error_preserves_other_variant_results(self):
        accepted, results = assess(self.sound["test_shipping.py"],
                                   "raise RuntimeError('implementation load failed')")
        self.assertFalse(accepted)
        self.assertEqual(len(results["reference"].errors), 1)
        self.assertEqual(len(results["defect"].failures), 1)
        self.assertTrue(results["benign"].wasSuccessful())

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
