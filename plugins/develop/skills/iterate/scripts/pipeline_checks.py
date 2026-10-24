"""Bounded GitHub policy discovery and exact-commit CI coverage.

The API sources are branches/branches#get-a-branch,
repos/rules#get-rules-for-a-branch, checks/runs#list-check-runs-for-a-git-reference,
and commits/statuses#get-the-combined-status-for-a-specific-reference at
https://docs.github.com/en/rest/. These are reads, not a mergeability oracle.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from pipeline_review import PullRequest, github_location, parse_json
from pipeline_support import FULL_SHA, Runner, Target, WatchError


PAGE_SIZE = 100
MAX_PAGES = 5
MAX_WORKFLOW_SOURCES = MAX_PAGES * PAGE_SIZE
PR_WORKFLOW_EVENTS = frozenset({
    "push", "pull_request", "pull_request_review", "pull_request_target", "deployment", "deployment_status",
})
NON_CI_RULES = frozenset({
    "creation", "update", "deletion", "required_linear_history", "required_signatures",
    "pull_request", "non_fast_forward", "commit_message_pattern", "commit_author_email_pattern",
    "committer_email_pattern", "branch_name_pattern", "tag_name_pattern", "file_path_restriction",
    "max_file_path_length", "file_extension_restriction", "max_file_size", "merge_queue",
    "copilot_code_review",
})


@dataclass(frozen=True, order=True)
class RequiredCheck:
    context: str
    app_id: int = -1  # -1 means any provider; status REST records have no app ID.


@dataclass(frozen=True)
class CheckPolicy:
    branches: tuple[str, ...]
    required: tuple[RequiredCheck, ...]
    branch_requirements: tuple[tuple[str, tuple[RequiredCheck, ...]], ...] | None = None

    def for_branch(self, branch: str) -> CheckPolicy:
        required = self.required if self.branch_requirements is None else dict(self.branch_requirements)[branch]
        return CheckPolicy((branch,), required)


@dataclass(frozen=True)
class CheckResult:
    context: str
    app_id: int
    status: str
    source: str
    url: str
    successful: bool
    producer: tuple[str, int, int]
    pr_eligible: bool | None = True
    record_id: int = 0
    attempt: int = 0

    @property
    def logical_identity(self) -> tuple[str, str, int, tuple[str, int, int]]:
        return self.source, self.context, self.app_id, self.producer

    @property
    def identity(self) -> tuple[Any, ...]:
        return (*self.logical_identity, self.record_id if self.producer[0] == "actions" else 0)


@dataclass(frozen=True)
class WorkflowSource:
    workflow_id: int
    run_id: int
    head_sha: str
    event: str | None
    attempt: int
    check_attempts: dict[int, int]


@dataclass(frozen=True)
class CheckCoverage:
    required: int
    observed: int
    passed: int
    successful: int
    active: int
    failed: int
    missing: tuple[str, ...]
    findings: tuple[dict[str, str], ...]
    sha: str = ""
    results: tuple[CheckResult, ...] = ()


@dataclass(frozen=True)
class CheckRevision:
    base_sha: str
    merge_sha: str | None


def commit_sha(value: Any, description: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(FULL_SHA, value):
        raise WatchError(f"Missing or invalid {description}")
    return value


def inspect_revision(target: Target, runner: Runner, pull_request: PullRequest) -> CheckRevision:
    """Bind GitHub's test merge to this open PR's exact head and current base."""
    pull = api_get(target, runner, f"pulls/{pull_request.number}", dict)
    _, owner, name = github_location(target.repository)
    repository = f"{owner}/{name}".casefold()
    if (type(pull.get("number")) is not int or pull["number"] != pull_request.number
        or pull.get("state") != "open" or pull.get("merged") is not False):
        raise WatchError("Pull-request identity changed during CI coverage")
    for side, branch in (("head", target.upstream_branch), ("base", pull_request.base_branch)):
        ref = pull.get(side)
        repo = ref.get("repo") if isinstance(ref, dict) else None
        full_name = repo.get("full_name") if isinstance(repo, dict) else None
        if (not isinstance(ref, dict) or ref.get("ref") != branch
            or not isinstance(full_name, str) or full_name.casefold() != repository):
            raise WatchError("Pull-request repository or ref changed during CI coverage")
        commit_sha(ref.get("sha"), f"pull-request {side} SHA")
    if pull["head"]["sha"] != target.head:
        raise WatchError("Pull-request head changed during CI coverage")
    if "merge_commit_sha" not in pull:
        raise WatchError("Pull-request test-merge identity is unavailable")
    if type(pull.get("mergeable")) is not bool:
        # Null means GitHub is still calculating; it is not proof that the
        # test merge has no checks. A later bounded watcher run can retry.
        raise WatchError("Pull-request test-merge calculation is incomplete; CI is unverified")
    merge_sha = pull["merge_commit_sha"]
    if pull["mergeable"]:
        commit_sha(merge_sha, "pull-request test-merge SHA")
    else:
        merge_sha = None
    return CheckRevision(pull["base"]["sha"], merge_sha)


def verify_merge_parents(target: Target, runner: Runner, revision: CheckRevision) -> None:
    # Git commit objects omit potentially large patches and are immutable by SHA.
    commit = api_get(target, runner, f"git/commits/{revision.merge_sha}", dict)
    parents = records(commit.get("parents"), "test-merge parents")
    if (commit.get("sha") != revision.merge_sha
        or [parent.get("sha") for parent in parents] != [revision.base_sha, target.head]):
        raise WatchError("Test-merge commit does not match the current PR head and base")


def verify_base_head(target: Target, runner: Runner, pull_request: PullRequest, revision: CheckRevision) -> None:
    branch = api_get(target, runner, f"branches/{quote(pull_request.base_branch, safe='')}", dict)
    commit = branch.get("commit")
    if (branch.get("name") != pull_request.base_branch or not isinstance(commit, dict)
        or commit.get("sha") != revision.base_sha):
        raise WatchError("Pull-request base branch changed before completion")


def api_get(target: Target, runner: Runner, suffix: str, expected: type) -> Any:
    host, owner, name = github_location(target.repository)
    command = ["gh", "api", f"repos/{owner}/{name}/{suffix}", "--method", "GET"]
    command.extend(["--hostname", host])
    return parse_json(runner(command, cwd=target.path), f"CI coverage for {target.label}", expected=expected)


def records(value: Any, description: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise WatchError(f"Incomplete {description}: expected a list of objects")
    return value


def count(value: Any, description: str) -> int:
    if type(value) is not int or value < 0:
        raise WatchError(f"Missing or invalid {description}")
    return value


def positive_identity(value: Any, description: str) -> int:
    result = count(value, description)
    if not result:
        raise WatchError(f"Missing or invalid {description}")
    return result


def workflow_source(
    target: Target, runner: Runner, check: dict[str, Any], source_head: str | None,
    cache: dict[tuple[str, int], WorkflowSource], check_ids: frozenset[int],
) -> WorkflowSource:
    suite = check.get("check_suite")
    suite_id = positive_identity(suite.get("id") if isinstance(suite, dict) else None, "Actions check suite identity")
    key = (target.qualified_repository, suite_id)
    previous = cache.get(key)
    value = previous
    if previous is None or not check_ids.issubset(previous.check_attempts):
        if previous is None and len(cache) >= MAX_WORKFLOW_SOURCES:
            raise WatchError("Actions provenance exceeds bounded suite coverage")
        payload = api_get(target, runner, f"actions/runs?check_suite_id={suite_id}&per_page=2", dict)
        runs = records(payload.get("workflow_runs"), "Actions suite workflows")
        if count(payload.get("total_count"), "Actions suite workflow count") != 1 or len(runs) != 1:
            raise WatchError("Actions suite workflow provenance is missing or ambiguous")
        run = runs[0]
        repository = run.get("repository")
        _, owner, name = github_location(target.repository)
        full_name = repository.get("full_name") if isinstance(repository, dict) else None
        if (not isinstance(full_name, str) or full_name.casefold() != f"{owner}/{name}".casefold()
            or positive_identity(run.get("check_suite_id"), "workflow check suite identity") != suite_id):
            raise WatchError("Actions workflow repository or suite does not match the check")
        event = run.get("event")
        attempt = positive_identity(run.get("run_attempt"), "workflow run attempt")
        # Reruns expose old and new job IDs together. An unchanged ID retains
        # its observed attempt; keep only this bounded snapshot's IDs.
        check_attempts = {identifier: previous.check_attempts.get(identifier, attempt) if previous else attempt
                          for identifier in check_ids}
        value = WorkflowSource(
            positive_identity(run.get("workflow_id"), "workflow identity"),
            positive_identity(run.get("id"), "workflow run identity"),
            commit_sha(run.get("head_sha"), "workflow head SHA"),
            event if isinstance(event, str) and event else None,
            attempt, check_attempts,
        )
        if previous is not None and (
            (value.workflow_id, value.run_id, value.head_sha) != (previous.workflow_id, previous.run_id, previous.head_sha)
            or previous.event is not None and value.event != previous.event or value.attempt < previous.attempt
        ):
            raise WatchError("Actions suite provenance changed unexpectedly")
    if value.head_sha not in {target.head, source_head}:
        raise WatchError("Actions workflow head does not match the evaluated commit or verified PR head")
    cache[key] = value
    return value


def requirement(value: dict[str, Any], id_field: str) -> RequiredCheck:
    name = value.get("context")
    if not isinstance(name, str) or not name:
        raise WatchError("Required-check inventory contains an invalid context")
    app_id = value.get(id_field)
    if app_id is None:
        app_id = -1
    if type(app_id) is not int or app_id < -1:
        raise WatchError("Required-check inventory contains an invalid app identity")
    return RequiredCheck(name, app_id)


def classic_requirements(target: Target, runner: Runner, branch: dict[str, Any], encoded: str) -> set[RequiredCheck]:
    if type(branch.get("protected")) is not bool:
        raise WatchError("Branch protection visibility is incomplete")
    protection = branch.get("protection")
    if not isinstance(protection, dict) or "required_status_checks" not in protection:
        if branch["protected"]:
            raise WatchError("Protected branch required-check inventory is inaccessible")
        return set()
    checks = protection["required_status_checks"]
    if checks is None:
        return set()
    if not isinstance(checks, dict) or not isinstance(checks.get("contexts"), list):
        raise WatchError("Classic required-check inventory is incomplete")
    if "checks" not in checks and checks["contexts"]:
        # Older branch summaries omit the app binding. Do not silently discard it.
        checks = api_get(target, runner, f"branches/{encoded}/protection/required_status_checks", dict)
    contexts = checks.get("contexts")
    if not isinstance(contexts, list) or any(not isinstance(name, str) or not name for name in contexts):
        raise WatchError("Classic required-check contexts are invalid")
    bindings = records(checks.get("checks", []), "classic required-check app bindings")
    if contexts and "checks" not in checks:
        raise WatchError("Classic required-check app bindings are unavailable")
    result = {requirement(value, "app_id") for value in bindings}
    bound_names = {item.context for item in result}
    result.update(RequiredCheck(name) for name in contexts if name not in bound_names)
    return result


def branch_rules(target: Target, runner: Runner, encoded: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    previous_pages: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        values = records(api_get(target, runner, f"rules/branches/{encoded}?per_page=100&page={page}", list), "active rules")
        if len(values) > PAGE_SIZE:
            raise WatchError("Active rules returned an invalid page size")
        identities = {json.dumps(value, sort_keys=True) for value in values}
        if previous_pages & identities:
            raise WatchError("Active rules changed during pagination; bounded inventory coverage is incomplete")
        previous_pages.update(identities)
        result.extend(values)
        if len(values) < PAGE_SIZE:
            return result
    raise WatchError("Active rules exceed bounded inventory coverage")


def discover_policy(target: Target, runner: Runner, base_branch: str | None) -> CheckPolicy:
    # Both branch restrictions apply: publication branch and, where present, PR base.
    branches = tuple(dict.fromkeys([target.upstream_branch, *([base_branch] if base_branch else [])]))
    by_branch: list[tuple[str, tuple[RequiredCheck, ...]]] = []
    for name in branches:
        required: set[RequiredCheck] = set()
        encoded = quote(name, safe="")
        branch = api_get(target, runner, f"branches/{encoded}", dict)
        if branch.get("name") != name:
            raise WatchError("GitHub branch identity changed during required-check discovery")
        if name == target.upstream_branch:
            commit = branch.get("commit")
            if not isinstance(commit, dict) or commit.get("sha") != target.head:
                raise WatchError(f"Published branch head changed: {target.label}")
        required.update(classic_requirements(target, runner, branch, encoded))
        for rule in branch_rules(target, runner, encoded):
            kind = rule.get("type")
            if not isinstance(kind, str):
                raise WatchError("Active rules contain an invalid rule type")
            if kind != "required_status_checks" and kind not in NON_CI_RULES:
                raise WatchError(f"Unsupported required CI rule {kind} on {name}; observed runs alone cannot establish required coverage")
            if kind == "required_status_checks":
                parameters = rule.get("parameters")
                if not isinstance(parameters, dict):
                    raise WatchError("Required-check ruleset parameters are missing")
                required.update(requirement(item, "integration_id") for item in records(
                    parameters.get("required_status_checks"), "ruleset required checks"
                ))
        by_branch.append((name, tuple(sorted(required))))
    combined = tuple(sorted({item for _, requirements in by_branch for item in requirements}))
    return CheckPolicy(branches, combined, tuple(by_branch))


def verify_published_head(target: Target, runner: Runner) -> None:
    """Read back immediately before reporting success, after polling evidence."""
    branch = api_get(target, runner, f"branches/{quote(target.upstream_branch, safe='')}", dict)
    commit = branch.get("commit")
    if branch.get("name") != target.upstream_branch or not isinstance(commit, dict) or commit.get("sha") != target.head:
        raise WatchError(f"Published branch head changed: {target.label}")


def paged_results(target: Target, runner: Runner, suffix: str, field: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    expected_total: int | None = None
    seen_ids: set[int] = set()
    for page in range(1, MAX_PAGES + 1):
        separator = "&" if "?" in suffix else "?"
        payload = api_get(target, runner, f"{suffix}{separator}per_page=100&page={page}", dict)
        if field == "statuses" and payload.get("sha") != target.head:
            raise WatchError("Combined status returned a different commit SHA")
        total = count(payload.get("total_count"), f"{field} total_count")
        if total > MAX_PAGES * PAGE_SIZE:
            raise WatchError(f"{field} exceed bounded CI coverage")
        if expected_total is not None and total != expected_total:
            raise WatchError(f"{field} changed during pagination; restart the snapshot")
        expected_total = total
        values = records(payload.get(field), field)
        if len(values) > PAGE_SIZE:
            raise WatchError(f"Invalid {field} page size")
        for value in values:
            identifier = count(value.get("id"), f"{field} record identity")
            if identifier in seen_ids:
                raise WatchError(f"Duplicate {field} across pages; coverage is incomplete")
            seen_ids.add(identifier)
        result.extend(values)
        if len(result) == total:
            return result
        if len(result) > total or len(values) < PAGE_SIZE:
            raise WatchError(f"Incomplete {field} pagination")
    raise WatchError(f"{field} exceed bounded CI coverage")


def inspect_coverage(
    target: Target, runner: Runner, policy: CheckPolicy, *,
    pr_required: tuple[RequiredCheck, ...] = (), source_head: str | None = None,
    workflow_sources: dict[tuple[str, int], WorkflowSource] | None = None,
) -> CheckCoverage:
    workflow_sources = {} if workflow_sources is None else workflow_sources
    suites = api_get(target, runner, f"commits/{target.head}/check-suites?per_page=1&page=1", dict)
    # GitHub's commit check-runs endpoint silently caps its search at 1000 suites.
    if count(suites.get("total_count"), "check suite total_count") >= 1000:
        raise WatchError("Check suites reach GitHub's 1000-suite coverage limit")
    checks = paged_results(target, runner, f"commits/{target.head}/check-runs?filter=latest", "check_runs")
    statuses = paged_results(target, runner, f"commits/{target.head}/status", "statuses")
    suite_checks: dict[int, set[int]] = {}
    for check in checks:
        app = check.get("app")
        if isinstance(app, dict) and str(app.get("slug", "")).casefold() == "github-actions":
            suite = check.get("check_suite")
            suite_id = positive_identity(suite.get("id") if isinstance(suite, dict) else None, "Actions check suite identity")
            suite_checks.setdefault(suite_id, set()).add(positive_identity(check.get("id"), "check run identity"))
    observed: list[CheckResult] = []
    for check in checks:
        if check.get("head_sha") != target.head:
            raise WatchError("Check run returned a different commit SHA")
        name, app = check.get("name"), check.get("app")
        if not isinstance(name, str) or not name or not isinstance(app, dict):
            raise WatchError("Check run identity is incomplete")
        app_id = positive_identity(app.get("id"), "check run app identity")
        app_slug = app.get("slug")
        if not isinstance(app_slug, str) or not app_slug:
            raise WatchError("Check run app provenance is unavailable")
        check_id = positive_identity(check.get("id"), "check run identity")
        eligible: bool | None = True
        attempt = 0
        if app_slug.casefold() == "github-actions":
            origin = workflow_source(target, runner, check, source_head, workflow_sources,
                                     frozenset(suite_checks[check["check_suite"]["id"]]))
            producer = ("actions", origin.workflow_id, origin.run_id)
            eligible = origin.event in PR_WORKFLOW_EVENTS if origin.event is not None else None
            attempt = origin.check_attempts[check_id]
        else:
            # External apps do not share Actions trigger/rerun semantics. Only an
            # update of the same check record proves continuity without an adapter.
            producer = ("external", app_id, check_id)
        state, conclusion = check.get("status"), check.get("conclusion")
        if not isinstance(state, str) or state not in {"queued", "in_progress", "completed", "waiting", "pending", "requested"}:
            raise WatchError("Unknown check run status")
        if state == "completed" and not isinstance(conclusion, str):
            raise WatchError("Completed check run has no conclusion")
        result = "active" if state != "completed" else (
            "passed" if conclusion in {"success", "neutral", "skipped"} else "failed"
        )
        observed.append(CheckResult(name, app_id, result, "check", str(check.get("html_url", "")),
                                    conclusion == "success" and state == "completed", producer, eligible, check_id, attempt))
    for status in statuses:
        name, state = status.get("context"), status.get("state")
        if (not isinstance(name, str) or not name or not isinstance(state, str)
            or state not in {"success", "failure", "error", "pending"}):
            raise WatchError("Commit status identity or state is incomplete")
        result = "passed" if state == "success" else "active" if state == "pending" else "failed"
        # The combined-status endpoint exposes the latest record per context,
        # without creator/app identity. New status IDs are normal updates.
        observed.append(CheckResult(name, -1, result, "status", str(status.get("target_url", "")),
                                    state == "success", ("status", 0, 0)))
    if any(item.pr_eligible is None and any(matches_requirement(item, required) for required in pr_required)
           for item in observed):
        raise WatchError("Required PR check workflow trigger is unavailable; CI is unverified")
    return coverage_for_policy(target.head, tuple(observed), policy, pr_required=pr_required)


def matches_requirement(item: CheckResult, required: RequiredCheck) -> bool:
    return item.context == required.context and (required.app_id == -1 or item.app_id == required.app_id)


def coverage_for_policy(
    sha: str, results: tuple[CheckResult, ...], policy: CheckPolicy, *, required_only: bool = False,
    pr_required: tuple[RequiredCheck, ...] = (),
) -> CheckCoverage:
    observed = tuple(item for item in results if not required_only or any(
        item.context == required.context for required in policy.required
    ))
    missing: list[str] = []
    for required in policy.required:
        matches = [item for item in observed if matches_requirement(item, required)
                   and (required not in pr_required or item.pr_eligible is True)]
        if not matches:
            suffix = "" if required.app_id == -1 else f" (app {required.app_id})"
            missing.append(required.context + suffix)
    findings = tuple({"context": item.context, "source": item.source, "url": item.url, "status": item.status}
                     for item in observed if item.status != "passed")
    return CheckCoverage(
        len(policy.required), len(observed),
        sum(item.status == "passed" for item in observed),
        sum(item.successful for item in observed),
        sum(item.status == "active" for item in observed),
        sum(item.status == "failed" for item in observed),
        tuple(missing), findings,
        sha, observed,
    )


def combine_coverage(effective: CheckCoverage, publication: CheckCoverage) -> CheckCoverage:
    """Combine different revisions without letting either supply the other's checks."""
    coverages = (effective, publication)
    return CheckCoverage(
        *(sum(getattr(item, name) for item in coverages) for name in
          ("required", "observed", "passed", "successful", "active", "failed")),
        tuple(f"{item.sha[:12]}: {missing}" for item in coverages for missing in item.missing),
        tuple({**finding, "sha": item.sha} for item in coverages for finding in item.findings),
        effective.sha,
    )


def coverage_disappeared(previous: CheckCoverage, current: CheckCoverage) -> bool:
    lost = Counter(item.identity for item in previous.results) - Counter(item.identity for item in current.results)
    for item in previous.results:
        if item.identity not in lost:
            continue
        older = [value for value in previous.results if value.logical_identity == item.logical_identity]
        newer = [value for value in current.results if value.logical_identity == item.logical_identity]
        # A higher native attempt proves a rerun only for one unambiguous job
        # context in the same workflow/run. Duplicate-name members need readback.
        if not (item.producer[0] == "actions" and len(older) == len(newer) == 1
                and newer[0].attempt > item.attempt and newer[0].record_id != item.record_id):
            return True
    return False
