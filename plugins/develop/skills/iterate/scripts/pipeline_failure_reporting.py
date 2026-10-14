"""Workflow transition events and bounded GitHub Actions failure reporting."""

from __future__ import annotations

import json
from typing import Any

from pipeline_support import NON_FAILURE, Target, WatchError, bounded_log, classify


class FailureReportingMixin:
    def emit_transition(self, target: Target, run: dict[str, Any]) -> bool:
        key = (target.key, int(run["databaseId"]))
        jobs = tuple(
            (
                job.get("name"), job.get("status"), job.get("conclusion"),
                tuple(step.get("name") for step in job.get("steps", [])),
            )
            for job in run.get("jobs", [])
        )
        fingerprint = json.dumps((run.get("attempt"), run.get("status"), run.get("conclusion"), jobs), sort_keys=True)
        if self.fingerprints.get(key) == fingerprint:
            return False
        self.fingerprints[key] = fingerprint
        if classify(run) == "passed" and not jobs:
            return False
        event: dict[str, Any] = {
            "event": "run",
            "target": target.label,
            "workflow": run.get("workflowName") or "unnamed",
            "status": run.get("conclusion") or run.get("status"),
        }
        if jobs:
            changed = [
                f"{job.get('name')}:{job.get('conclusion') or job.get('status')}"
                for job in run.get("jobs", [])
                if job.get("status") != "completed" or job.get("conclusion") not in NON_FAILURE
            ]
            if changed:
                event["jobs"] = changed
        if classify(run) == "failed":
            event["url"] = run.get("url")
        self.emit(event)
        return True

    def fetch_failure(self, target: Target, run: dict[str, Any]) -> None:
        key = (target.key, int(run["databaseId"]))
        if key in self.reported_failures:
            return
        self.reported_failures.add(key)
        detailed = run if run.get("jobs") else self.view_run(target, run, attempt=self.run_attempt(run))
        failed_jobs = [job for job in detailed.get("jobs", []) if job.get("conclusion") == "failure"]
        commands: list[tuple[str, str | None, list[str]]] = []
        for job in failed_jobs[: self.max_failed_jobs]:
            job_id = job.get("databaseId")
            if job_id:
                steps = [
                    str(step.get("name")) for step in job.get("steps", [])
                    if step.get("conclusion") == "failure" and step.get("name")
                ]
                commands.append((
                    str(job.get("name", "failed job")),
                    steps[0] if steps else None,
                    ["--job", str(job_id)],
                ))
        if not commands:
            commands.append(("failed workflow", None, []))
        for job_name, failed_step, extra in commands:
            try:
                output = self.runner(
                    [
                        "gh", "run", "view", str(run["databaseId"]),
                        "-R", target.qualified_repository, "--attempt", str(self.run_attempt(run)), "--log-failed", *extra,
                    ],
                    cwd=target.path,
                )
            except WatchError as exc:
                self.emit({"event": "log-error", "target": target.label, "job": job_name, "error": str(exc)})
                continue
            event: dict[str, Any] = {
                "event": "failure",
                "target": target.label,
                "workflow": run.get("workflowName") or "unnamed",
                "job": job_name,
                "url": run.get("url"),
            }
            if failed_step:
                event["step"] = failed_step
            excerpt = bounded_log(output or "", self.max_log_lines, self.max_log_chars)
            if excerpt in self.reported_excerpts:
                event["excerpt"] = "[previously reported identical failure]"
            else:
                self.reported_excerpts.add(excerpt)
                event["excerpt"] = excerpt
            self.emit(event)
