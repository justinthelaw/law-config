"""Exact-commit GitHub Actions monitoring and bounded failure reporting."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from functools import partial
from typing import Any, Callable, Generator, Sequence

from pipeline_failure_reporting import FailureReportingMixin
from pipeline_checks import CheckCoverage, CheckPolicy, discover_policy, inspect_coverage, verify_published_head
from pipeline_run_state import RunStateMixin
from pipeline_review import (
    PullRequest,
    ReviewState,
    discover_pull_request,
    inspect_pull_request,
    github_location,
    timestamp,
)
from pipeline_support import (
    VIEW_FILTER,
    Deadline,
    Runner,
    Target,
    WatchError,
    WatchTimeout,
    build_target,
    classify,
    redact,
    run_command,
    validate_timings,
)


DEFAULT_TIMEOUT = 30 * 60


def monitor_deadline(
    timeout: float = DEFAULT_TIMEOUT,
    deadline: Deadline | str | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
) -> Deadline | None:
    """Restore an absolute budget once; enforce elapsed time monotonically thereafter."""
    validate_timings(timeout=timeout)
    if isinstance(deadline, Deadline):
        return deadline
    now, wall_now = clock(), wall_clock()
    if deadline is not None:
        try:
            absolute = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            if absolute.utcoffset() is None:
                raise ValueError("timezone required")
            wall_expires = absolute.timestamp()
        except (ValueError, TypeError, OverflowError) as exc:
            raise WatchError("deadline must be an ISO 8601 timestamp with a timezone") from exc
        return Deadline(now + (wall_expires - wall_now), clock, wall_expires)
    return Deadline(now + timeout, clock, wall_now + timeout) if timeout else None


def budget_event(deadline: Deadline | None) -> dict[str, Any]:
    absolute = None
    if deadline is not None:
        wall_expires = deadline.wall_expires_at
        if wall_expires is None:
            wall_expires = time.time() + deadline.expires_at - deadline.clock()
        absolute = datetime.fromtimestamp(wall_expires, timezone.utc).isoformat()
    return {"event": "budget", "deadline": absolute, "indefinite": deadline is None}


def watch_roots(
    watchers: Sequence[Watcher], *, blocked: dict[str, str] | None = None,
    once: bool = False, emit: Callable[[dict[str, Any]], None],
    clock: Callable[[], float], sleep: Callable[[float], None], deadline: Deadline | None,
) -> int:
    """Step independent root groups fairly, sharing only the global budget."""
    outcomes = {root: 2 for root in (blocked or {})}
    jobs = []
    for watcher in watchers:
        root = str(watcher.targets[0].root)
        watcher.emit = lambda event, root=root: emit({
            **event, "event": {"summary": "root-summary", "blocked": "root-blocked"}.get(event["event"], event["event"]),
            "root": root,
        })
        jobs.append((root, watcher._watch(once=once), clock()))

    def counts() -> dict[str, int]:
        totals: dict[str, int] = {}
        for watcher in watchers:
            for key, value in watcher.counts().items():
                totals[key] = totals.get(key, 0) + value
        for status, code in (("passed", 0), ("failed", 1), ("blocked", 2), ("pending", 3)):
            totals[f"roots_{status}"] = sum(value == code for value in outcomes.values())
        totals["roots_pending"] += len(jobs)
        return totals

    final_snapshot = False
    try:
        while jobs:
            if deadline is not None:
                deadline.remaining()
            ready = min(due for _, _, due in jobs)
            if ready > clock():
                delay = ready - clock()
                sleep(min(delay, deadline.remaining()) if deadline is not None else delay)
                continue
            for job in list(jobs):
                root, steps, due = job
                if due > clock():
                    continue
                if deadline is not None:
                    deadline.remaining()
                try:
                    delay = next(steps)
                except StopIteration as done:
                    outcomes[root] = done.value
                    jobs.remove(job)
                    if final_snapshot and done.value == 3:
                        emit({"event": "root-reopened", "root": root, "reason": "new pending exact-commit work"})
                except WatchTimeout:
                    raise
                except WatchError as error:
                    outcomes[root] = 2
                    jobs.remove(job)
                    emit({"event": "root-blocked", "root": root, "reason": str(error)})
                else:
                    jobs[jobs.index(job)] = (root, steps, clock() + delay)
            if not jobs:
                if final_snapshot:
                    selected = [watcher for watcher in watchers
                                if outcomes[str(watcher.targets[0].root)] == 3] if not once else []
                    final_snapshot = False
                elif len(watchers) > 1 and outcomes and all(value == 0 for value in outcomes.values()):
                    # A root may have completed long before another root. Refresh its
                    # exact-head CI/reviews and identity before any aggregate pass.
                    selected = list(watchers)
                    final_snapshot = True
                else:
                    selected = []
                for watcher in selected:
                    root = str(watcher.targets[0].root)
                    outcomes.pop(root)
                    jobs.append((root, watcher._watch(once=final_snapshot), clock()))
        if deadline is not None:
            deadline.remaining()
    except WatchTimeout:
        emit({"event": "blocked", "reason": "monitor timeout", **counts()})
        return 2
    result = next((code for code in (2, 1, 3) if code in outcomes.values()), 0) if outcomes else 2
    emit({"event": "summary", "result": {0: "passed", 1: "failed", 2: "blocked", 3: "pending"}[result], **counts()})
    return result


class Watcher(FailureReportingMixin, RunStateMixin):
    def __init__(
        self,
        targets: Sequence[Target],
        *,
        runner: Runner | None = None,
        emit: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        interval: float = 20,
        max_interval: float = 60,
        heartbeat: float = 60,
        rediscover: float = 90,
        discovery_grace: float = 120,
        settle: float = 120,
        timeout: float = DEFAULT_TIMEOUT,
        deadline: Deadline | str | None = None,
        wall_clock: Callable[[], float] = time.time,
        max_log_lines: int = 40,
        max_log_chars: int = 4000,
        max_failed_jobs: int = 2,
        max_runs: int = 100,
        monitor_reviews: bool = False,
    ) -> None:
        validate_timings(interval=interval, max_interval=max_interval, heartbeat=heartbeat,
                         rediscover=rediscover, discovery_grace=discovery_grace, settle=settle, timeout=timeout)
        self.started = clock()
        self.deadline = monitor_deadline(timeout, deadline, clock=clock, wall_clock=wall_clock)
        if runner is None:
            runner = partial(run_command, deadline=self.deadline, sleep=sleep)
        self.targets = list(targets)
        self.runner = self.deadline.bind(runner) if self.deadline is not None else runner
        self.clock, self.sleep = clock, sleep
        self.emit = emit or self.print_event
        self.interval, self.heartbeat = interval, heartbeat
        self.max_interval = max(interval, max_interval)
        self.current_interval = interval
        self.rediscover, self.discovery_grace = rediscover, discovery_grace
        self.settle, self.max_log_lines = settle, max_log_lines
        self.max_log_chars, self.max_failed_jobs = max_log_chars, max_failed_jobs
        self.max_runs = max_runs
        self.monitor_reviews = monitor_reviews
        self.runs: dict[tuple[str, int], tuple[Target, dict[str, Any]]] = {}
        self.fingerprints: dict[tuple[str, int], str] = {}
        self.reported_failures: set[tuple[str, int]] = set()
        self.reported_excerpts: set[str] = set()
        self.first_seen: dict[str, float] = {}
        self.pull_requests: dict[str, PullRequest] = {}
        self.review_states: dict[str, ReviewState] = {}
        self.review_fingerprints: dict[str, str] = {}
        self.unacknowledged_reviews: dict[str, float] = {}
        self.review_activation: dict[str, datetime] = {}
        self.check_policies: dict[str, CheckPolicy] = {}
        self.check_coverage: dict[str, CheckCoverage] = {}
        self.last_heartbeat = self.started
        self.last_discovery = self.started
        self.child_options = dict(
            runner=self.runner, clock=clock, sleep=sleep, timeout=0, deadline=self.deadline,
            interval=interval, max_interval=max_interval, heartbeat=heartbeat,
            rediscover=rediscover, discovery_grace=discovery_grace, settle=settle,
            max_log_lines=max_log_lines, max_log_chars=max_log_chars,
            max_failed_jobs=max_failed_jobs, max_runs=max_runs, monitor_reviews=monitor_reviews,
        )

    @staticmethod
    def print_event(event: dict[str, Any]) -> None:
        print(redact(json.dumps(event, separators=(",", ":"), ensure_ascii=True)), flush=True)

    def list_runs(self, target: Target) -> list[dict[str, Any]]:
        raw = self.runner(
            [
                "gh", "run", "list", "-R", target.qualified_repository,
                "--branch", target.upstream_branch, "--commit", target.head,
                "--limit", str(self.max_runs), "--json",
                "databaseId,attempt,workflowName,status,conclusion,url,headSha,headBranch,createdAt",
            ],
            cwd=target.path,
        )
        try:
            payload = json.loads(raw or "[]")
        except json.JSONDecodeError as exc:
            raise WatchError(f"GitHub returned invalid workflow JSON for {target.label}") from exc
        if not isinstance(payload, list) or any(not isinstance(run, dict) for run in payload):
            raise WatchError(f"GitHub returned an invalid workflow list for {target.label}")
        if len(payload) >= self.max_runs:
            raise WatchError(
                f"Workflow listing reached its {self.max_runs}-run limit for {target.label}; "
                "increase --max-runs to avoid incomplete CI results"
            )
        return [
            run for run in payload
            if run.get("headSha") == target.head
            and run.get("headBranch") == target.upstream_branch
        ]

    def discover_runs(self, *, initial: bool = False) -> bool:
        now = self.clock()
        changed = False
        for target in self.targets:
            matching = self.list_runs(target)
            self.first_seen.setdefault(target.key, now)
            fresh = 0
            for run in matching:
                key = (target.key, int(run["databaseId"]))
                previous = self.runs.get(key, (target, {}))[1]
                self.run_attempt(run)
                if (previous and self.run_attempt(run) == self.run_attempt(previous)
                    and previous.get("status") == "completed" and run.get("status") != "completed"):
                    run = self.view_run(target, run)
                if self.remember_run(target, run):
                    fresh += 1
                    changed = True
            if initial or fresh:
                self.emit({
                    "event": "target" if initial else "discovered",
                    "target": target.label,
                    "sha": target.head[:12],
                    "workflows": len(matching),
                    "active": sum(classify(run) == "active" for run in matching),
                })
            pull_request = discover_pull_request(target, self.runner)
            previous = self.pull_requests.get(target.key)
            if pull_request is None:
                if previous is not None:
                    raise WatchError(f"Monitored pull request is no longer open: {target.label}")
            elif previous is not None and previous != pull_request:
                raise WatchError(f"Monitored pull request or base changed unexpectedly: {target.label}")
            else:
                self.pull_requests[target.key] = pull_request
                if self.monitor_reviews:
                    # This time is only a review-history bound, never completion evidence.
                    self.review_activation[target.key] = min(
                        (timestamp(run.get("createdAt"), f"exact-head workflow creation for {target.label}")
                         for run in matching), default=datetime(1970, 1, 1, tzinfo=timezone.utc),
                    )
            policy = discover_policy(target, self.runner, pull_request.base_branch if pull_request else None)
            changed |= policy != self.check_policies.get(target.key)
            self.check_policies[target.key] = policy
        self.last_discovery = now
        return changed

    def view_run(self, target: Target, run: dict[str, Any], *, attempt: int | None = None) -> dict[str, Any]:
        raw = self.runner(
            [
                "gh", "run", "view", str(run["databaseId"]),
                "-R", target.qualified_repository,
                "--json", "attempt,status,conclusion,url,workflowName,headSha,headBranch,jobs",
                *(["--attempt", str(attempt)] if attempt is not None else []),
                "--jq", VIEW_FILTER,
            ],
            cwd=target.path,
        )
        try:
            details = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise WatchError(f"Invalid workflow details for {target.label}") from exc
        head = details.get("headSha")
        branch = details.get("headBranch")
        if head != target.head or branch != target.upstream_branch:
            raise WatchError(f"Workflow SHA or branch changed unexpectedly: {target.label}")
        observed_attempt = self.run_attempt(details)
        if attempt is not None and observed_attempt != attempt:
            raise WatchError("Workflow failure attempt changed unexpectedly")
        base = run if observed_attempt == self.run_attempt(run) else {
            key: value for key, value in run.items() if key != "jobs"
        }
        return {**base, **details}

    def poll_reviews(self) -> bool:
        if not self.monitor_reviews:
            return False
        changed = False
        for target in self.targets:
            pull_request = self.pull_requests.get(target.key)
            activated = self.review_activation.get(target.key)
            if pull_request is None:
                raise WatchError(f"Codex review monitoring requires an open pull request: {target.label}")
            if activated is None:
                raise WatchError(f"Current-head review discovery is missing: {target.label}")
            previous = self.review_states.get(target.key)
            review = inspect_pull_request(
                target,
                pull_request,
                self.runner,
                head_activated=activated,
                required_since=previous.required_since if previous else None,
                required_request=previous.request if previous else None,
                max_lines=min(self.max_log_lines, 12),
                max_chars=min(self.max_log_chars, 2000),
            )
            if review is None:
                if previous is None:
                    raise WatchError(
                        f"No current-head Codex review evidence or active review request: {target.label}; "
                        "request a review before restarting monitoring"
                    )
                # Once review activity has been observed, losing its evidence
                # cannot erase the review requirement or preserve an earlier verdict.
                self.review_states.pop(target.key, None)
                self.review_fingerprints.pop(target.key, None)
                self.unacknowledged_reviews.pop(target.key, None)
                raise WatchError(
                    f"Previously observed Codex review evidence disappeared: {target.label}; "
                    "obtain a fresh exact-head review before restarting monitoring"
                )
            self.review_states[target.key] = review
            if review.status == "active" and not review.acknowledged:
                if previous is not None and review.request != previous.request:
                    self.unacknowledged_reviews[target.key] = self.clock()
                else:
                    self.unacknowledged_reviews.setdefault(target.key, self.clock())
            else:
                self.unacknowledged_reviews.pop(target.key, None)
            fingerprint = json.dumps(
                {
                    "status": review.status,
                    "source": review.source,
                    "required_since": (
                        review.required_since.isoformat() if review.required_since else None
                    ),
                    "request": (
                        [review.request.created_at.isoformat(), review.request.comment_id]
                        if review.request else None
                    ),
                    "acknowledged": review.acknowledged,
                    "findings": review.findings,
                },
                sort_keys=True,
            )
            if self.review_fingerprints.get(target.key) == fingerprint:
                continue
            self.review_fingerprints[target.key] = fingerprint
            changed = True
            event: dict[str, Any] = {
                "event": "review",
                "target": target.label,
                "pull_request": pull_request.number,
                "status": review.status,
                "source": review.source,
                "url": pull_request.url,
            }
            if review.findings:
                event["findings"] = len(review.findings)
            self.emit(event)
            for finding in review.findings[:5]:
                self.emit({
                    "event": "review-finding",
                    "target": target.label,
                    "pull_request": pull_request.number,
                    **finding,
                })
        return changed

    def poll_checks(self) -> bool:
        changed = False
        for target in self.targets:
            coverage = inspect_coverage(target, self.runner, self.check_policies[target.key])
            if coverage != self.check_coverage.get(target.key):
                changed = True
                self.emit({
                    "event": "check-coverage", "target": target.label, "target_id": target.key,
                    "sha": target.head, "policy_branches": self.check_policies[target.key].branches,
                    "required": coverage.required, "observed": coverage.observed,
                    "passed": coverage.passed, "active": coverage.active, "failed": coverage.failed,
                    "missing": coverage.missing, "findings": coverage.findings[:5],
                })
            self.check_coverage[target.key] = coverage
        return changed

    def unacknowledged_review_targets(self, now: float) -> list[str]:
        return [
            target for target, first_seen in self.unacknowledged_reviews.items()
            if now - first_seen >= self.discovery_grace
        ]

    def heartbeat_if_due(self, now: float, *, force: bool = False) -> bool:
        if not force and now - self.last_heartbeat < self.heartbeat:
            return False
        self.last_heartbeat = now
        self.emit({"event": "heartbeat", **self.counts()})
        return True

    def poll_active(self) -> bool:
        changed = False
        for key, (target, run) in list(self.runs.items()):
            if classify(run) == "active":
                previous = (run.get("status"), run.get("conclusion"))
                run = self.view_run(target, run)
                changed |= self.remember_run(target, run)
                run = self.runs[key][1]
                changed |= previous != (run.get("status"), run.get("conclusion"))
            changed |= self.emit_transition(target, run)
            if classify(run) == "failed":
                self.fetch_failure(target, run)
        return changed

    def next_interval(
        self, now: float, *, changed: bool, terminal_since: float | None
    ) -> float:
        if changed:
            self.current_interval = self.interval
        else:
            self.current_interval = min(self.max_interval, self.current_interval * 1.5)
        deadlines = [
            self.current_interval,
            max(0.0, self.heartbeat - (now - self.last_heartbeat)),
            max(0.0, self.rediscover - (now - self.last_discovery)),
        ]
        if terminal_since is not None:
            deadlines.append(max(0.0, self.settle - (now - terminal_since)))
        if self.deadline is not None:
            deadlines.append(self.deadline.remaining())
        positive = [deadline for deadline in deadlines if deadline > 0]
        return min(positive, default=self.interval)

    def missing_targets(self) -> list[str]:
        represented = {target.key for target, _ in self.runs.values()}
        represented.update(key for key, coverage in self.check_coverage.items() if coverage.observed)
        return [target.key for target in self.targets if target.key not in represented]

    def unsuccessful_targets(self) -> list[str]:
        successful = {
            target.key
            for target, run in self.runs.values()
            if classify(run) == "passed"
        }
        successful.update(key for key, coverage in self.check_coverage.items() if coverage.successful)
        return [target.label for target in self.targets if target.key not in successful]

    def watch(self, *, once: bool = False) -> int:
        self.emit(budget_event(self.deadline))
        if not self.targets:
            self.emit({"event": "blocked", "reason": "no monitoring targets"})
            return 2
        groups: dict[str, list[Target]] = {}
        for target in self.targets:
            groups.setdefault(str(target.root), []).append(target)
        if len(groups) > 1:
            self.root_watchers = [Watcher(targets, **self.child_options) for targets in groups.values()]
            result = watch_roots(
                self.root_watchers, once=once, emit=self.emit,
                clock=self.clock, sleep=self.sleep, deadline=self.deadline,
            )
            # Preserve the library's observed-state access; scheduling never shares these maps.
            for watcher in self.root_watchers:
                for name in ("runs", "check_policies", "check_coverage", "pull_requests", "review_states"):
                    getattr(self, name).update(getattr(watcher, name))
            return result
        try:
            steps = self._watch(once=once)
            while True:
                try:
                    delay = next(steps)
                except StopIteration as done:
                    self.check_deadline()
                    return done.value
                self.sleep(delay)
        except WatchTimeout:
            self.emit({"event": "blocked", "reason": "monitor timeout", **self.counts()})
            return 2

    def check_deadline(self) -> None:
        if self.deadline is not None:
            self.deadline.remaining()

    def _watch(self, *, once: bool = False) -> Generator[float, None, int]:
        self.check_deadline()
        for host in sorted({github_location(target.repository)[0] for target in self.targets}):
            self.runner(["gh", "auth", "status", "--hostname", host], cwd=self.targets[0].root)
        self.discover_runs(initial=True)
        terminal_since: float | None = None
        while True:
            self.check_deadline()
            changed = self.poll_active()
            changed |= self.poll_checks()
            changed |= self.poll_reviews()
            now = self.clock()
            self.check_deadline()
            missing = self.missing_targets()
            required_missing = [target.key for target in self.targets if self.check_coverage[target.key].missing]
            if required_missing and (once or any(now - self.first_seen[key] >= self.discovery_grace for key in required_missing)):
                self.emit({"event": "blocked", "reason": "required exact-commit checks are missing", "targets": [
                    {"target": target.label, "target_id": target.key, "missing": self.check_coverage[target.key].missing}
                    for target in self.targets if target.key in required_missing
                ]})
                return 2
            if missing and (once or any(now - self.first_seen[label] >= self.discovery_grace for label in missing)):
                self.emit({"event": "blocked", "reason": "no exact-commit workflows", "targets": [target.label for target in self.targets if target.key in missing]})
                return 2
            unacknowledged = self.unacknowledged_review_targets(now)
            if unacknowledged:
                self.emit({
                    "event": "blocked",
                    "reason": "Codex review request was not acknowledged",
                    "targets": unacknowledged,
                })
                return 2
            counts = self.counts()
            if not missing and not required_missing and not counts["active"] and not counts.get("reviews_active", 0) and not counts["checks_active"]:
                if once:
                    if counts["failed"] or counts.get("reviews_failed", 0) or counts["checks_failed"]:
                        self.emit({"event": "summary", "result": "failed", **counts})
                        return 1
                    unsuccessful = self.unsuccessful_targets()
                    if unsuccessful:
                        self.emit({
                            "event": "blocked",
                            "reason": "no successful exact-commit workflows",
                            "targets": unsuccessful,
                        })
                        return 2
                    self.verify_completion_identity()
                    self.emit({"event": "summary", "result": "passed", **counts})
                    return 0
                if terminal_since is None:
                    terminal_since = now
                if now - terminal_since >= self.settle:
                    discovered = self.discover_runs()
                    self.poll_active()
                    self.poll_checks()
                    self.poll_reviews()
                    counts = self.counts()
                    self.check_deadline()
                    missing = self.missing_targets()
                    if (
                        missing
                        or counts["active"]
                        or counts["checks_active"]
                        or any(coverage.missing for coverage in self.check_coverage.values())
                        or counts.get("reviews_active", 0)
                        or discovered
                    ):
                        terminal_since = None
                        continue
                    if counts["failed"] or counts.get("reviews_failed", 0) or counts["checks_failed"]:
                        self.emit({"event": "summary", "result": "failed", **counts})
                        return 1
                    unsuccessful = self.unsuccessful_targets()
                    if unsuccessful:
                        self.emit({
                            "event": "blocked",
                            "reason": "no successful exact-commit workflows",
                            "targets": unsuccessful,
                        })
                        return 2
                    self.verify_completion_identity()
                    self.emit({"event": "summary", "result": "passed", **counts})
                    return 0
            else:
                terminal_since = None
            if once:
                self.emit({"event": "summary", "result": "pending", **counts})
                return 3
            self.check_deadline()
            self.heartbeat_if_due(now)
            yield self.next_interval(now, changed=changed, terminal_since=terminal_since)
            now = self.clock()
            if missing or now - self.last_discovery >= self.rediscover:
                if self.discover_runs():
                    self.current_interval = self.interval
                    terminal_since = None

    def verify_completion_identity(self) -> None:
        for target in self.targets:
            verify_published_head(target, self.runner)
            if discover_pull_request(target, self.runner) != self.pull_requests.get(target.key):
                raise WatchError(f"Pull-request identity changed before completion: {target.label}")
        for target in self.targets:
            # Reuse discovery's bounded local reads after the network readback.
            # Only the already-verified target host may remain an enterprise host.
            current = build_target(
                target.path, target.root, self.runner,
                github_hosts=(github_location(target.repository)[0],),
            )
            if (current.key, current.branch, current.remote) != (target.key, target.branch, target.remote):
                raise WatchError(f"Local Git target changed before completion: {target.label}; restart monitoring")
