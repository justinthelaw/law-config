"""Ambient GitHub CLI settings cannot redirect evidence to a different host."""

import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline_monitor import Watcher
from pipeline_test_support import FakeRunner, run_payload, target
from test_pipeline_review import ReviewRunner, review


class HostRoutingTests(unittest.TestCase):
    def assert_explicit_routing(self, calls, host, repository):
        seen = set()
        for argv in calls:
            if argv[:2] == ["gh", "api"] or argv[:3] == ["gh", "auth", "status"]:
                self.assertIn("--hostname", argv)
                self.assertEqual(argv[argv.index("--hostname") + 1], host)
                seen.add("api" if argv[1] == "api" else "auth")
            elif argv[:2] in (["gh", "run"], ["gh", "pr"]):
                self.assertIn("-R", argv)
                self.assertEqual(argv[argv.index("-R") + 1], repository)
                seen.add(argv[1])
        return seen

    def test_public_target_pins_all_reads_despite_enterprise_environment(self):
        current = target()
        runner = ReviewRunner(current, reviews=[review(current)])
        with patch.dict(os.environ, {"GH_HOST": "unrelated.enterprise.example", "GH_REPO": "unrelated/other"}):
            result = Watcher([current], runner=runner, emit=lambda event: None, monitor_reviews=True).watch(once=True)
        self.assertEqual(result, 0)
        self.assertEqual(self.assert_explicit_routing(runner.calls, "github.com", "github.com/owner/project"), {"api", "auth", "run", "pr"})
        graph_calls = [argv for argv in runner.calls if argv[:3] == ["gh", "api", "graphql"]]
        self.assertTrue(graph_calls)

    def test_enterprise_target_pins_all_reads_despite_public_environment(self):
        current = replace(target(), repository="verified.enterprise.example/owner/project")
        runner = ReviewRunner(current, reviews=[review(current)])
        with patch.dict(os.environ, {"GH_HOST": "github.com", "GH_REPO": "unrelated/other"}):
            result = Watcher([current], runner=runner, emit=lambda event: None, monitor_reviews=True).watch(once=True)
        self.assertEqual(result, 0)
        self.assertEqual(self.assert_explicit_routing(runner.calls, "verified.enterprise.example", current.repository), {"api", "auth", "run", "pr"})

    def test_workflow_details_and_failed_logs_use_fully_qualified_target(self):
        current = target()
        failure = run_payload(current, conclusion="failure")
        details = {**failure, "jobs": [{"databaseId": 17, "name": "test", "conclusion": "failure", "steps": []}]}
        runner = FakeRunner([[failure]], [details])
        monitor = Watcher([current], runner=runner, emit=lambda event: None)
        with patch.dict(os.environ, {"GH_HOST": "unrelated.enterprise.example"}):
            monitor.view_run(current, failure)
            monitor.fetch_failure(current, failure)
        calls = [list(argv) for argv in runner.calls]
        self.assertEqual(self.assert_explicit_routing(calls, "github.com", "github.com/owner/project"), {"run"})
        self.assertTrue(any("--log-failed" in argv for argv in calls))


if __name__ == "__main__":
    unittest.main()
