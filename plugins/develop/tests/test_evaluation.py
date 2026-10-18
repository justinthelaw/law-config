"""Offline contract/security controls; these are not behavioral host trials."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/evaluations"
SPEC = importlib.util.spec_from_file_location("evaluation", ROOT / "scripts/evaluation.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


class EvaluationContract(unittest.TestCase):
    def setUp(self):
        self.fixture = evaluation.load_json(DATA / "fixtures/scope-allowlist.json")
        self.result = evaluation.load_json(DATA / "results/synthetic.json")
        self.temp = tempfile.TemporaryDirectory(prefix="develop-evaluation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_shipped_fixtures_and_synthetic_example(self):
        for path in sorted((DATA / "fixtures").glob("*.json")):
            fixture = evaluation.load_json(path)
            evaluation.validate_fixture(fixture)
            grader = evaluation.load_json(DATA / "graders" / path.name)
            self.assertEqual((grader["fixture_id"], grader["fixture_revision"]),
                             (fixture["id"], fixture["revision"]))
            self.assertTrue(grader["criteria"])
        evaluation.validate_result(self.result)
        self.assertEqual(self.result["evidence_kind"], "synthetic")
        identity = self.result["planned_attempts"][0]["fixture"]
        fixture = evaluation.load_json(DATA / "fixtures/no-op.json")
        self.assertEqual(identity["sha256"], evaluation.fixture_digest(fixture))

    def test_digest_is_order_independent_but_content_sensitive(self):
        reordered = dict(reversed(list(self.fixture.items())))
        self.assertEqual(evaluation.fixture_digest(self.fixture), evaluation.fixture_digest(reordered))
        reordered["revision"] = "2"
        self.assertNotEqual(evaluation.fixture_digest(self.fixture), evaluation.fixture_digest(reordered))

    def test_materializes_exact_inputs_without_grader_or_prompt(self):
        destination = self.root / "agent"
        hashes = evaluation.materialize(self.fixture, destination)
        expected = {item["path"]: item["content"].encode("utf-8")
                    for item in self.fixture["agent"]["inputs"]}
        actual = {path.relative_to(destination).as_posix(): path.read_bytes()
                  for path in destination.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        self.assertEqual(hashes, {path: hashlib.sha256(data).hexdigest()
                                  for path, data in expected.items()})

    def test_noop_materializes_empty_root(self):
        fixture = evaluation.load_json(DATA / "fixtures/no-op.json")
        self.assertEqual(evaluation.materialize(fixture, self.root / "empty"), {})
        self.assertEqual(list((self.root / "empty").iterdir()), [])

    def test_seeded_unsafe_paths_rejected_before_creating_destination(self):
        bad = ["../escape", "/absolute", "a/../../escape", "a//b", "a/./b", "a/../b",
               "C:/escape", "C:\\escape", "a\\b", "file:stream", "NUL.txt", "COM1",
               "a/", "trail.", "trail ", "a\x00b", "$(touch pwned)", "a\nb"]
        random.Random(721).shuffle(bad)
        for path in bad:
            with self.subTest(path=path):
                fixture = copy.deepcopy(self.fixture)
                fixture["agent"]["inputs"][0]["path"] = path
                with self.assertRaises(ValueError):
                    evaluation.materialize(fixture, self.root / "agent")
                self.assertFalse((self.root / "agent").exists())

    def test_duplicate_case_and_parent_path_collisions(self):
        for paths in (("a", "a"), ("a", "A"), ("a", "a/b"), ("a/b", "a"),
                      ("a/one", "A/two")):
            fixture = copy.deepcopy(self.fixture)
            fixture["agent"]["inputs"] = [{"path": path, "content": ""} for path in paths]
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                evaluation.validate_fixture(fixture)

    def test_existing_directory_and_file_are_never_overwritten(self):
        for name in ("directory", "file"):
            destination = self.root / name
            if name == "directory":
                destination.mkdir()
                (destination / "allowed.txt").write_text("preserve", encoding="utf-8")
            else:
                destination.write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                evaluation.materialize(self.fixture, destination)
            preserved = destination / "allowed.txt" if destination.is_dir() else destination
            self.assertEqual(preserved.read_text(encoding="utf-8"), "preserve")

    def test_symlink_destination_and_parent_are_rejected(self):
        actual = self.root / "actual"
        actual.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"host cannot create symlinks: {exc}")
        for destination in (link, link / "new"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                evaluation.materialize(self.fixture, destination)
        self.assertEqual(list(actual.iterdir()), [])

    def test_input_text_is_data_never_executed(self):
        marker = self.root / "executed"
        self.fixture["agent"]["inputs"] = [{"path": "script.sh", "content": f"touch {marker}\n"}]
        evaluation.materialize(self.fixture, self.root / "agent")
        self.assertFalse(marker.exists())

    def test_unknown_fields_and_invalid_types_rejected(self):
        bad = []
        fixture = copy.deepcopy(self.fixture)
        fixture["grader"] = {"answer": "hidden"}
        bad.append(fixture)
        fixture = copy.deepcopy(self.fixture)
        fixture["agent"]["command"] = "echo bad"
        bad.append(fixture)
        fixture = copy.deepcopy(self.fixture)
        fixture["schema_version"] = True
        bad.extend([fixture, None, [], {}])
        for fixture in bad:
            with self.subTest(fixture=fixture), self.assertRaises(ValueError):
                evaluation.validate_fixture(fixture)

    def test_seeded_invalid_results_are_rejected(self):
        mutations = [
            lambda r: r["attempts"].pop(),
            lambda r: r["attempts"].append(copy.deepcopy(r["attempts"][0])),
            lambda r: r["planned_attempts"].append(copy.deepcopy(r["planned_attempts"][0])),
            lambda r: r["source"].update(revision="main"),
            lambda r: r["host"].update(selection_basis=""),
            lambda r: r["planned_attempts"][0]["fixture"].update(sha256="invalid"),
            lambda r: r["attempts"][0]["functional"].update(evidence=[]),
            lambda r: r["attempts"][1]["functional"].update(verdict="pass", evidence=["fake"]),
            lambda r: r["attempts"][2].update(reason=""),
            lambda r: r["attempts"][2]["cost"].update(tokens=0),
            lambda r: r["attempts"][0]["observations"][0].update(channel="combined"),
            lambda r: r.update(command="execute me"),
        ]
        random.Random(721).shuffle(mutations)
        for index, mutate in enumerate(mutations):
            result = copy.deepcopy(self.result)
            mutate(result)
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                evaluation.validate_result(result)

    def test_nullable_costs_are_distinct_from_zero_and_application_metrics(self):
        attempt = self.result["attempts"][0]
        attempt["cost"] = {"wall_seconds": 0.0, "tokens": 0, "usd": None}
        attempt["application_performance"] = [{"name": "latency", "value": 0.2, "unit": "seconds"}]
        evaluation.validate_result(self.result)
        self.assertIsNone(attempt["cost"]["usd"])
        for field in ("wall_seconds", "tokens", "usd"):
            for invalid in (-1, float("nan"), float("inf"), True, "0"):
                result = copy.deepcopy(self.result)
                result["attempts"][0]["cost"][field] = invalid
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    evaluation.validate_result(result)
        attempt["cost"]["tokens"] = 1.5
        with self.assertRaises(ValueError):
            evaluation.validate_result(self.result)

    def test_application_metrics_require_finite_nonnegative_values(self):
        for invalid in (-1, float("nan"), float("inf"), None, True):
            self.result["attempts"][0]["application_performance"] = [
                {"name": "latency", "value": invalid, "unit": "seconds"}]
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                evaluation.validate_result(self.result)

    def test_json_reader_rejects_duplicate_keys_and_nonfinite_values(self):
        for content in ('{"id":1,"id":2}', '{"cost":NaN}', '{"cost":Infinity}'):
            path = self.root / "bad.json"
            path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(ValueError):
                evaluation.load_json(path)

    def test_cli_from_unrelated_directory(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluation.py"),
                                 "result", str(DATA / "results/synthetic.json")],
                                cwd=self.root, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"valid": True, "kind": "result"})


if __name__ == "__main__":
    unittest.main()
