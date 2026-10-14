"""Bounded GitHub policy discovery and exact-commit CI coverage.

The API sources are branches/branches#get-a-branch,
repos/rules#get-rules-for-a-branch, checks/runs#list-check-runs-for-a-git-reference,
and commits/statuses#get-the-combined-status-for-a-specific-reference at
https://docs.github.com/en/rest/. These are reads, not a mergeability oracle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from pipeline_review import github_location, parse_json
from pipeline_support import Runner, Target, WatchError


PAGE_SIZE = 100
MAX_PAGES = 5
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
    required: set[RequiredCheck] = set()
    for name in branches:
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
    return CheckPolicy(branches, tuple(sorted(required)))


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


def inspect_coverage(target: Target, runner: Runner, policy: CheckPolicy) -> CheckCoverage:
    suites = api_get(target, runner, f"commits/{target.head}/check-suites?per_page=1&page=1", dict)
    # GitHub's commit check-runs endpoint silently caps its search at 1000 suites.
    if count(suites.get("total_count"), "check suite total_count") >= 1000:
        raise WatchError("Check suites reach GitHub's 1000-suite coverage limit")
    checks = paged_results(target, runner, f"commits/{target.head}/check-runs?filter=latest", "check_runs")
    statuses = paged_results(target, runner, f"commits/{target.head}/status", "statuses")
    observed: list[tuple[str, int, str, str, str]] = []
    for check in checks:
        if check.get("head_sha") != target.head:
            raise WatchError("Check run returned a different commit SHA")
        name, app = check.get("name"), check.get("app")
        if not isinstance(name, str) or not name or not isinstance(app, dict):
            raise WatchError("Check run identity is incomplete")
        app_id = count(app.get("id"), "check run app identity")
        state, conclusion = check.get("status"), check.get("conclusion")
        if state not in {"queued", "in_progress", "completed", "waiting", "pending", "requested"}:
            raise WatchError("Unknown check run status")
        result = "active" if state != "completed" else (
            "passed" if conclusion in {"success", "neutral", "skipped"} else "failed"
        )
        if state == "completed" and not isinstance(conclusion, str):
            raise WatchError("Completed check run has no conclusion")
        observed.append((name, app_id, result, "check", str(check.get("html_url", ""))))
    for status in statuses:
        name, state = status.get("context"), status.get("state")
        if not isinstance(name, str) or not name or state not in {"success", "failure", "error", "pending"}:
            raise WatchError("Commit status identity or state is incomplete")
        result = "passed" if state == "success" else "active" if state == "pending" else "failed"
        observed.append((name, -1, result, "status", str(status.get("target_url", ""))))
    missing: list[str] = []
    for required in policy.required:
        matches = [item for item in observed if item[0] == required.context and (
            required.app_id == -1 or item[1] == required.app_id
        )]
        if not matches:
            suffix = "" if required.app_id == -1 else f" (app {required.app_id})"
            missing.append(required.context + suffix)
    findings = tuple({"context": name, "source": kind, "url": url, "status": result}
                     for name, _, result, kind, url in observed if result != "passed")
    return CheckCoverage(
        len(policy.required), len(observed),
        sum(item[2] == "passed" for item in observed),
        sum(item.get("conclusion") == "success" for item in checks) + sum(item.get("state") == "success" for item in statuses),
        sum(item[2] == "active" for item in observed),
        sum(item[2] == "failed" for item in observed),
        tuple(missing), findings,
    )
