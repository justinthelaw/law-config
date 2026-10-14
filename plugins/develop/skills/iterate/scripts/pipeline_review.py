"""Read-only, exact-head Codex pull-request review inspection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pipeline_support import REVIEW_QUERY, Runner, Target, WatchError, bounded_log


CODEX_ACTOR = "chatgpt-codex-connector"
TRUSTED_AUTHORS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
REVIEW_REQUEST = re.compile(r"^\s*@codex\s+review\b", re.IGNORECASE)
NEUTRAL_REVIEW = re.compile(
    r"codex reviewed this pull request|automated review suggestions for this pull request",
    re.IGNORECASE,
)
PULL_REQUEST_FIELDS = (
    "number,url,headRefOid,headRefName,headRepositoryOwner,isCrossRepository,baseRefName"
)


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    base_branch: str


@dataclass(frozen=True, order=True)
class ReviewRequest:
    created_at: datetime
    comment_id: int


@dataclass(frozen=True)
class ReviewState:
    pull_request: PullRequest
    status: str
    source: str
    required_since: datetime | None
    acknowledged: bool
    findings: tuple[dict[str, Any], ...] = ()
    request: ReviewRequest | None = None


def github_location(repository: str) -> tuple[str, str, str]:
    components = repository.split("/")
    if len(components) == 2:
        return "github.com", components[0], components[1]
    if len(components) == 3:
        return components[0], components[1], components[2]
    raise WatchError("Cannot determine the selected GitHub repository")


def parse_json(raw: str | None, description: str, *, expected: type) -> Any:
    try:
        payload = json.loads(raw or "null")
    except json.JSONDecodeError as exc:
        raise WatchError(f"GitHub returned invalid {description} JSON") from exc
    if not isinstance(payload, expected):
        raise WatchError(f"GitHub returned invalid {description} data")
    return payload


def timestamp(value: Any, description: str) -> datetime:
    if not isinstance(value, str):
        raise WatchError(f"GitHub omitted the {description} timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WatchError(f"GitHub returned an invalid {description} timestamp") from exc
    if parsed.tzinfo is None:
        raise WatchError(f"GitHub returned a timezone-free {description} timestamp")
    return parsed.astimezone(timezone.utc)


def is_codex_actor(actor: Any) -> bool:
    if not isinstance(actor, dict):
        return False
    login = actor.get("login")
    if not isinstance(login, str) or login.removesuffix("[bot]") != CODEX_ACTOR:
        return False
    actor_type = actor.get("__typename", actor.get("type"))
    return actor_type == "Bot"


def review_requires_changes(review: dict[str, Any]) -> bool:
    body = str(review.get("body", "")).strip()
    return review.get("state") == "CHANGES_REQUESTED" or (
        review.get("state") == "COMMENTED"
        and bool(body)
        and not NEUTRAL_REVIEW.search(body)
    )


def discover_pull_request(target: Target, runner: Runner) -> PullRequest | None:
    _, owner, _ = github_location(target.repository)
    payload = parse_json(
        runner(
            [
                "gh", "pr", "list", "-R", target.qualified_repository,
                "--head", target.upstream_branch, "--state", "open",
                "--limit", "100", "--json", PULL_REQUEST_FIELDS,
            ],
            cwd=target.path,
        ),
        f"pull-request discovery for {target.label}",
        expected=list,
    )
    if len(payload) >= 100:
        raise WatchError(f"Pull-request discovery reached its 100-item limit: {target.label}")
    owned = []
    for pull_request in payload:
        if not isinstance(pull_request, dict):
            raise WatchError(f"GitHub returned an invalid pull-request record: {target.label}")
        head_owner = pull_request.get("headRepositoryOwner")
        head_login = head_owner.get("login") if isinstance(head_owner, dict) else None
        if (
            pull_request.get("headRefName") == target.upstream_branch
            and pull_request.get("isCrossRepository") is False
            and isinstance(head_login, str)
            and head_login.casefold() == owner.casefold()
        ):
            owned.append(pull_request)
    if len(owned) > 1:
        raise WatchError(f"Multiple selected-repository pull requests match {target.label}")
    if not owned:
        return None
    selected = owned[0]
    if selected.get("headRefOid") != target.head:
        raise WatchError(f"Pull-request head differs from the exact monitored commit: {target.label}")
    number, url = selected.get("number"), selected.get("url")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise WatchError(f"GitHub returned an invalid pull-request number: {target.label}")
    if not isinstance(url, str) or not url:
        raise WatchError(f"GitHub returned an invalid pull-request URL: {target.label}")
    base_branch = selected.get("baseRefName")
    if not isinstance(base_branch, str) or not base_branch:
        raise WatchError(f"GitHub omitted the pull-request base branch: {target.label}")
    return PullRequest(number, url, base_branch)


def api_arguments(
    target: Target, pull_request: PullRequest, *, graphql: bool, comment_id: int | None = None
) -> list[str]:
    host, owner, name = github_location(target.repository)
    if graphql:
        command = [
            "gh", "api", "graphql", "--method", "POST",
            "-f", f"query={REVIEW_QUERY}",
            "-f", f"owner={owner}", "-f", f"name={name}",
            "-F", f"number={pull_request.number}",
        ]
    else:
        subject = str(pull_request.number) if comment_id is None else f"comments/{comment_id}"
        command = [
            "gh", "api",
            f"repos/{owner}/{name}/issues/{subject}/reactions?per_page=100",
            "--method", "GET",
        ]
    command.extend(["--hostname", host])
    return command


def read_reactions(
    target: Target, pull_request: PullRequest, runner: Runner, *, comment_id: int | None = None
) -> list[dict[str, Any]]:
    reactions = parse_json(
        runner(api_arguments(target, pull_request, graphql=False, comment_id=comment_id), cwd=target.path),
        f"Codex review reactions for {target.label}",
        expected=list,
    )
    if len(reactions) >= 100:
        raise WatchError(f"Codex review reactions exceed bounded review coverage: {target.label}")
    return reactions


def connection_nodes(connection: Any, description: str) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(connection, dict):
        raise WatchError(f"GitHub omitted {description}")
    nodes, page_info = connection.get("nodes"), connection.get("pageInfo")
    if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
        raise WatchError(f"GitHub returned invalid {description}")
    if not isinstance(page_info, dict) or not isinstance(page_info.get("hasPreviousPage"), bool):
        raise WatchError(f"GitHub omitted pagination details for {description}")
    return nodes, page_info["hasPreviousPage"]


def recent_nodes(
    connection: Any,
    *,
    description: str,
    timestamp_field: str,
    head_committed: datetime,
) -> list[dict[str, Any]]:
    nodes, truncated = connection_nodes(connection, description)
    if truncated:
        raise WatchError(f"Current-head {description} exceed bounded review coverage")
    return nodes


def unresolved_findings(
    pull_request: dict[str, Any],
    *,
    max_lines: int,
    max_chars: int,
) -> tuple[dict[str, Any], ...]:
    threads, truncated = connection_nodes(
        pull_request.get("reviewThreads"), "pull-request review threads"
    )
    if truncated:
        raise WatchError("Pull-request review threads exceed bounded review coverage")
    findings: list[dict[str, Any]] = []
    for thread in threads:
        if thread.get("isResolved") is True:
            continue
        comments, comments_truncated = connection_nodes(
            thread.get("comments"), "pull-request review thread comments"
        )
        codex_comments = [comment for comment in comments if is_codex_actor(comment.get("author"))]
        if comments_truncated and not codex_comments:
            raise WatchError("Unresolved review-thread comments exceed bounded review coverage")
        if not codex_comments:
            continue
        comment = codex_comments[-1]
        finding: dict[str, Any] = {
            "thread": thread.get("id"),
            "path": thread.get("path"),
            "outdated": thread.get("isOutdated") is True,
            "excerpt": bounded_log(str(comment.get("bodyText", "")), max_lines, max_chars),
        }
        if isinstance(thread.get("line"), int):
            finding["line"] = thread["line"]
        if isinstance(comment.get("url"), str):
            finding["url"] = comment["url"]
        findings.append(finding)
    return tuple(findings)


def inspect_pull_request(
    target: Target,
    pull_request: PullRequest,
    runner: Runner,
    *,
    head_activated: datetime,
    required_since: datetime | None = None,
    required_request: ReviewRequest | None = None,
    max_lines: int = 12,
    max_chars: int = 2000,
) -> ReviewState | None:
    response = parse_json(
        runner(api_arguments(target, pull_request, graphql=True), cwd=target.path),
        f"pull-request review for {target.label}",
        expected=dict,
    )
    if response.get("errors"):
        raise WatchError(f"GitHub denied complete pull-request review access: {target.label}")
    data = response.get("data")
    repository = data.get("repository") if isinstance(data, dict) else None
    selected = repository.get("pullRequest") if isinstance(repository, dict) else None
    if not isinstance(selected, dict):
        raise WatchError(f"GitHub returned an inaccessible pull request: {target.label}")
    _, owner, name = github_location(target.repository)
    head_repository = selected.get("headRepository")
    if (
        selected.get("number") != pull_request.number
        or selected.get("state") != "OPEN"
        or selected.get("headRefName") != target.upstream_branch
        or selected.get("headRefOid") != target.head
        or selected.get("baseRefName") != pull_request.base_branch
        or selected.get("isCrossRepository") is not False
        or not isinstance(head_repository, dict)
        or str(head_repository.get("nameWithOwner", "")).casefold()
        != f"{owner}/{name}".casefold()
    ):
        raise WatchError(f"Pull-request ownership, branch, or exact head changed: {target.label}")
    commits = selected.get("commits")
    nodes = commits.get("nodes") if isinstance(commits, dict) else None
    commit = nodes[0].get("commit") if isinstance(nodes, list) and len(nodes) == 1 else None
    if not isinstance(commit, dict) or commit.get("oid") != target.head:
        raise WatchError(f"GitHub omitted the exact pull-request head commit: {target.label}")
    head_committed = timestamp(commit.get("committedDate"), "pull-request head commit")
    review_floor = min(head_committed, head_activated)
    comments = recent_nodes(
        selected.get("comments"), description="pull-request comments",
        timestamp_field="createdAt", head_committed=review_floor,
    )
    reviews = recent_nodes(
        selected.get("reviews"), description="pull-request reviews",
        timestamp_field="submittedAt", head_committed=review_floor,
    )
    findings = unresolved_findings(selected, max_lines=max_lines, max_chars=max_chars)

    requests: list[ReviewRequest] = []
    for comment in comments:
        if (
            comment.get("authorAssociation") not in TRUSTED_AUTHORS
            or not isinstance(comment.get("author"), dict)
            or comment["author"].get("__typename") == "Bot"
            or not REVIEW_REQUEST.search(str(comment.get("bodyText", "")))
        ):
            continue
        comment_id = comment.get("databaseId")
        if not isinstance(comment_id, int) or isinstance(comment_id, bool) or comment_id <= 0:
            raise WatchError("GitHub omitted the Codex review request comment identifier")
        requests.append(ReviewRequest(timestamp(comment.get("createdAt"), "Codex review request"), comment_id))
    latest_request = max([*requests, *([required_request] if required_request else [])], default=None)
    if latest_request is not None:
        # Only the latest manual request can acknowledge its review cycle.
        # Retain its identity after deletion, without fetching a missing comment
        # or accepting acknowledgment from an older request or the PR body.
        reactions = (
            read_reactions(target, pull_request, runner, comment_id=latest_request.comment_id)
            if latest_request in requests else []
        )
    else:
        reactions = read_reactions(target, pull_request, runner)

    eyes: list[tuple[datetime, int]] = []
    approvals: list[tuple[datetime, int]] = []
    for reaction in reactions:
        if not isinstance(reaction, dict) or not is_codex_actor(reaction.get("user")):
            continue
        content = reaction.get("content")
        if content not in {"eyes", "+1"}:
            continue
        created = timestamp(reaction.get("created_at"), "Codex reaction")
        reaction_id = reaction.get("id")
        if not isinstance(reaction_id, int) or isinstance(reaction_id, bool) or reaction_id <= 0:
            raise WatchError("GitHub returned an invalid Codex reaction identifier")
        (eyes if content == "eyes" else approvals).append((created, reaction_id))

    current_reviews = []
    for review in reviews:
        if (
            not is_codex_actor(review.get("author"))
            or not isinstance(review.get("commit"), dict)
            or review["commit"].get("oid") != target.head
            or not review.get("submittedAt")
        ):
            continue
        state = review.get("state")
        if state in {"PENDING", "DISMISSED"}:
            continue
        if state not in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}:
            raise WatchError(f"GitHub returned an unsupported Codex review state: {target.label}")
        current_reviews.append(review)
    # A timestamp tie cannot prove that approval superseded an adverse review.
    latest_review = max(
        current_reviews,
        key=lambda review: (
            timestamp(review.get("submittedAt"), "submitted Codex review"),
            review_requires_changes(review),
        ),
        default=None,
    )
    trigger_candidates = [created for created, _ in eyes]
    if latest_request is not None:
        trigger_candidates.append(latest_request.created_at)
    if required_since is not None:
        trigger_candidates.append(required_since)
    latest_trigger = max(trigger_candidates, default=None)
    latest_eye = max(eyes, default=None)

    if findings:
        return ReviewState(
            pull_request, "failed", "finding", latest_trigger, True, findings, latest_request
        )
    if latest_review is not None:
        submitted = timestamp(latest_review.get("submittedAt"), "submitted Codex review")
        # Equal provider timestamps cannot establish ordering within a second.
        if latest_trigger is None or submitted > latest_trigger:
            review_body = str(latest_review.get("body", "")).strip()
            if review_requires_changes(latest_review):
                return ReviewState(
                    pull_request,
                    "failed",
                    "changes-requested",
                    latest_trigger,
                    True,
                    ({
                        "excerpt": bounded_log(review_body, max_lines, max_chars),
                        "url": latest_review.get("url"),
                    },),
                    latest_request,
                )
            return ReviewState(pull_request, "passed", "submitted", latest_trigger, True, request=latest_request)
    if latest_trigger is None:
        if not approvals:
            return None
        # Reactions identify activity, never which revision was reviewed.
        latest_trigger = max(created for created, _ in approvals)
        return ReviewState(pull_request, "active", "unverified-reaction", latest_trigger, True)
    latest_activity = max([*eyes, *approvals], default=None)
    acknowledged = latest_activity is not None and latest_activity[0] >= latest_trigger
    if latest_eye is not None and latest_eye[0] >= latest_trigger:
        source = "eyes"
    else:
        source = "unverified-reaction" if acknowledged else "request"
    return ReviewState(pull_request, "active", source, latest_trigger, acknowledged, request=latest_request)
