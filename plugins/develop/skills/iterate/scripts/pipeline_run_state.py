"""Track attempt-aware workflow state without retaining stale failures."""

from typing import Any
from pipeline_support import Target, WatchError, classify


class RunStateMixin:
    @staticmethod
    def run_id(run: dict[str, Any]) -> int:
        identifier = run.get("databaseId")
        if type(identifier) is not int or identifier < 1:
            raise WatchError("Workflow run identity is missing or invalid")
        return identifier

    @staticmethod
    def run_attempt(run: dict[str, Any]) -> int:
        attempt = run.get("attempt")
        if type(attempt) is not int or attempt < 1:
            raise WatchError("Workflow attempt identity is missing or invalid")
        return attempt

    def remember_run(self, target: Target, run: dict[str, Any]) -> bool:
        if (not isinstance(run.get("status"), str)
            or run.get("conclusion") is not None and not isinstance(run["conclusion"], str)):
            raise WatchError("Workflow status or conclusion is invalid")
        key = (target.key, self.run_id(run))
        previous = self.runs.get(key, (target, {}))[1]
        attempt = self.run_attempt(run)
        if previous and attempt < self.run_attempt(previous):
            return False
        restarted = bool(previous and (
            attempt > self.run_attempt(previous)
            or previous.get("status") == "completed" and run.get("status") != "completed"
        ))
        if restarted:
            self.fingerprints.pop(key, None)
            self.reported_failures.discard(key)
            previous = {}
        self.runs[key] = (target, {**previous, **run})
        return not previous or restarted

    def counts(self) -> dict[str, int]:
        if hasattr(self, "root_watchers"):
            totals: dict[str, int] = {}
            for watcher in self.root_watchers:
                for key, value in watcher.counts().items():
                    totals[key] = totals.get(key, 0) + value
            return totals
        counts = {"active": 0, "passed": 0, "failed": 0, "skipped": 0}
        for _, run in self.runs.values():
            counts[classify(run)] += 1
        for status in ("active", "passed", "failed"):
            counts[f"checks_{status}"] = sum(getattr(coverage, status) for coverage in self.check_coverage.values())
        if self.monitor_reviews:
            for status in ("active", "passed", "failed"):
                counts[f"reviews_{status}"] = sum(
                    review.status == status for review in self.review_states.values()
                )
        return counts
