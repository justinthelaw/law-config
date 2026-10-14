"""Deterministic fixtures shared by the exact-commit watcher test modules."""

from __future__ import annotations

import json
from pathlib import Path

import watch_pipelines as watcher
from pipeline_support import UPSTREAM_FORMAT


def target(
    name: str = "project",
    *,
    branch: str = "main",
    head: str = "a" * 40,
    component: str | None = None,
) -> watcher.Target:
    root = Path("/tmp") / name
    path = root / component if component else root
    repo = f"owner/{component or name}"
    return watcher.Target(path, root, repo, branch, branch, head, "origin")


def run_payload(
    current: watcher.Target,
    *,
    run_id: int = 1,
    attempt: int = 1,
    status: str = "completed",
    conclusion: str = "success",
    workflow: str = "Test",
) -> dict[str, object]:
    return {
        "databaseId": run_id,
        "attempt": attempt,
        "workflowName": workflow,
        "status": status,
        "conclusion": conclusion,
        "url": f"https://github.com/{current.repository}/actions/runs/{run_id}",
        "headSha": current.head,
        "headBranch": current.upstream_branch,
        "createdAt": "2026-01-01T01:00:00Z",
    }


class FakeRunner:
    def __init__(
        self, lists: list[list[dict[str, object]]], views: list[dict[str, object]] | None = None,
        *, local_target: watcher.Target | None = None,
    ):
        self.lists = lists
        self.views = views or []
        self.local_target = local_target or target()
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: list[str], cwd: Path | None = None, optional: bool = False) -> str:
        self.calls.append(tuple(argv))
        local = local_metadata_response(argv, self.local_target)
        if local is not None:
            return local
        if argv[:3] == ["gh", "auth", "status"]:
            return ""
        if argv[:3] == ["gh", "run", "list"]:
            if len(self.lists) > 1:
                return json.dumps(self.lists.pop(0))
            return json.dumps(self.lists[0])
        if argv[:3] == ["gh", "run", "view"] and "--log-failed" in argv:
            return "first line\nsecret ghp_abcdefghijklmnopqrstuvwx\nlast line"
        if argv[:3] == ["gh", "run", "view"]:
            if len(self.views) > 1:
                return json.dumps(self.views.pop(0))
            return json.dumps(self.views[0])
        return default_ci_response(argv, self.lists[0] if self.lists else [])


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def now(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += seconds


def local_metadata_response(argv: list[str], current: watcher.Target) -> str | None:
    """Read mutable local fixture facts independently of published CI evidence."""
    if argv[0] != "git":
        return None
    watcher.ensure_read_only(argv)
    selected_ref = f"refs/heads/{current.branch}"
    responses = {
        ("git", "branch", "--show-current"): current.branch,
        ("git", "rev-parse", "HEAD"): current.head,
        ("git", "for-each-ref", "--count=2", f"--format={UPSTREAM_FORMAT}", selected_ref):
            f"{selected_ref}\0{current.remote}\0refs/heads/{current.upstream_branch}",
        ("git", "remote", "get-url", current.remote): f"https://{current.qualified_repository}.git",
    }
    if tuple(argv) not in responses:
        raise AssertionError(f"Unexpected local metadata command: {argv}")
    return responses[tuple(argv)]


def default_ci_response(argv: list[str], runs: list[dict[str, object]]) -> str:
    """A fully visible repository with no required or external checks."""
    if argv[:3] == ["gh", "pr", "list"]:
        return "[]"
    if argv[:2] == ["gh", "api"]:
        endpoint = argv[2]
        if "/rules/branches/" in endpoint:
            return "[]"
        if "/branches/" in endpoint:
            from urllib.parse import unquote
            branch = unquote(endpoint.split("/branches/")[1])
            return json.dumps({"name": branch, "commit": {"sha": runs[-1]["headSha"] if runs else "a" * 40}, "protected": False})
        if "/check-suites?" in endpoint:
            return '{"total_count":0}'
        if "/check-runs?" in endpoint:
            return '{"total_count":0,"check_runs":[]}'
        if "/status?" in endpoint:
            sha = endpoint.split("/commits/")[1].split("/")[0]
            return json.dumps({"sha": sha, "total_count": 0, "statuses": []})
    raise AssertionError(f"Unexpected fake command: {argv}")
