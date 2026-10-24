"""Read-only repository discovery and workflow-monitoring safety helpers."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urlparse

from command_capture import capture_command
from git_context import SELECTORS, repository_context


ACTIVE = frozenset({"queued", "in_progress", "pending", "requested", "waiting"})
NON_FAILURE = frozenset({"success", "neutral", "skipped"})
TRANSIENT = re.compile(r"rate.limit|timed?.out|temporar|connection|502|503|504", re.I)
SECRET = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|"
    r"Bearer\s+[A-Za-z0-9._~+/=-]{12,}|AKIA[0-9A-Z]{16}|"
    r"sk-[A-Za-z0-9_-]{12,})"
)
VIEW_FILTER = (
    '{attempt,status,conclusion,url,workflowName,headSha,headBranch,jobs:'
    '[.jobs[]?|select(.status!="completed" or '
    '(.conclusion!="success" and .conclusion!="neutral" and .conclusion!="skipped"))|'
    '{databaseId,name,status,conclusion,steps:'
    '[.steps[]?|select(.status=="in_progress" or .conclusion=="failure")|'
    '{name,status,conclusion}]}]}'
)
UPSTREAM_FORMAT = "%(refname)%00%(upstream:remotename)%00%(upstream:remoteref)"
REVIEW_QUERY = """query CodexPullRequestReview($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      url
      state
      headRefName
      headRefOid
      baseRefName
      isCrossRepository
      headRepository { nameWithOwner }
      commits(last: 1) {
        nodes { commit { oid committedDate } }
      }
      comments(last: 50) {
        pageInfo { hasPreviousPage }
        nodes { databaseId author { login __typename } authorAssociation createdAt bodyText url }
      }
      reviews(last: 50) {
        pageInfo { hasPreviousPage }
        nodes { author { login __typename } state submittedAt body url commit { oid } }
      }
      reviewThreads(last: 50) {
        pageInfo { hasPreviousPage }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(last: 10) {
            pageInfo { hasPreviousPage }
            nodes { author { login __typename } bodyText createdAt url }
          }
        }
      }
    }
  }
}"""
GITHUB_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
GITHUB_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
FULL_SHA = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
REACTION_ENDPOINT = re.compile(
    r"^repos/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*/"
    r"issues/(?:comments/)?[1-9][0-9]*/reactions\?per_page=100$"
)
CHECK_ENDPOINT = re.compile(
    r"^repos/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*/(?:"
    r"branches/[A-Za-z0-9_.%~-]+(?:/protection/required_status_checks)?|"
    r"rules/branches/[A-Za-z0-9_.%~-]+\?per_page=100&page=[1-5]|"
    rf"pulls/[1-9][0-9]*|git/commits/{FULL_SHA}|"
    r"actions/runs\?check_suite_id=[1-9][0-9]*&per_page=2|"
    rf"commits/{FULL_SHA}/(?:"
    r"check-suites\?per_page=1&page=1|"
    r"check-runs\?filter=latest&per_page=100&page=[1-5]|"
    r"status\?per_page=100&page=[1-5]))$"
)


class WatchError(RuntimeError):
    """A safe, actionable monitoring failure."""


class WatchTimeout(WatchError):
    """The shared monitoring deadline has expired."""


@dataclass(frozen=True)
class Deadline:
    expires_at: float
    clock: Callable[[], float]
    wall_expires_at: float | None = None

    def remaining(self) -> float:
        remaining = self.expires_at - self.clock()
        if remaining <= 0:
            raise WatchTimeout("monitor timeout")
        return remaining

    def bind(self, runner: Runner) -> Runner:
        """Guard injected runners as well as the subprocess runner."""
        def bounded(*args: Any, **kwargs: Any) -> str | None:
            self.remaining()
            result = runner(*args, **kwargs)
            self.remaining()
            return result
        return bounded


def validate_timings(**timings: float) -> None:
    for name, value in timings.items():
        allow_zero = name in {"timeout", "settle"}
        if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
            requirement = "nonnegative" if allow_zero else "positive"
            raise WatchError(f"{name} must be finite and {requirement}")


@dataclass(frozen=True)
class Target:
    path: Path
    root: Path
    repository: str
    branch: str
    upstream_branch: str
    head: str
    remote: str

    @property
    def qualified_repository(self) -> str:
        """Pin gh's host selection even when the shell exports a different GH_HOST."""
        return self.repository if self.repository.count("/") == 2 else f"github.com/{self.repository}"

    @property
    def key(self) -> str:
        """Machine identity; display labels need not be unique across checkouts."""
        return json.dumps([self.qualified_repository.casefold(), self.upstream_branch, self.head.lower()], separators=(",", ":"))

    @property
    def depth(self) -> int:
        return len(self.path.relative_to(self.root).parts)

    @property
    def label(self) -> str:
        relative = self.path.relative_to(self.root)
        component = self.root.name if not relative.parts else f"{self.root.name}/{relative}"
        return f"{component}:{self.upstream_branch}"


def ensure_read_only(argv: Sequence[str]) -> None:
    if not argv:
        raise WatchError("Refusing to execute an empty command")
    if argv[0] == "git":
        if len(argv) < 2 or argv[1] not in {
            "rev-parse", "branch", "remote", "submodule", "status", "diff", "for-each-ref"
        }:
            raise WatchError(f"Refusing non-read-only Git command: {' '.join(argv[:2])}")
        if argv[1] == "branch" and argv[2:] != ["--show-current"]:
            raise WatchError("Refusing a mutating Git branch command")
        if argv[1] == "for-each-ref" and not (
            len(argv) == 5
            and list(argv[2:4]) == ["--count=2", f"--format={UPSTREAM_FORMAT}"]
            and argv[4].startswith("refs/heads/")
            and len(argv[4]) > len("refs/heads/")
            and not re.search(r"[\s*?\[\\]", argv[4])
        ):
            raise WatchError("Refusing an unbounded or unapproved Git upstream query")
        if argv[1] == "remote" and argv[2:] and (
            len(argv) != 4 or argv[2] != "get-url"
        ):
            raise WatchError("Refusing a mutating Git remote command")
        if argv[1] == "submodule" and argv[2:4] != ["status", "--recursive"]:
            raise WatchError("Refusing a mutating Git submodule command")
        if argv[1] == "status" and argv[2:] != [
            "--porcelain=v2", "--branch", "-z", "--untracked-files=all"
        ]:
            raise WatchError("Refusing an unapproved Git status command")
        if argv[1] == "diff":
            if "--" not in argv or "--no-ext-diff" not in argv or "--no-textconv" not in argv:
                raise WatchError("Refusing a Git diff without explicit safe boundaries")
            boundary = argv.index("--")
            allowed = {
                "--cached", "--numstat", "-z", "--no-renames", "--no-ext-diff",
                "--no-color", "--unified=2", "--no-textconv",
                "--submodule=short",
            }
            if any(argument not in allowed for argument in argv[2:boundary]):
                raise WatchError("Refusing an unapproved Git diff option")
        return
    if argv[0] == "gh":
        if list(argv[1:3]) == ["auth", "status"]:
            if list(argv) != ["gh", "auth", "status"] and not (
                len(argv) == 5 and argv[3] == "--hostname" and GITHUB_HOST.fullmatch(argv[4])
            ):
                raise WatchError("Refusing an unapproved GitHub authentication command")
            return
        if tuple(argv[1:3]) in {("run", "list"), ("run", "view")}:
            return
        if list(argv[1:3]) == ["pr", "list"]:
            if (
                len(argv) == 13
                and argv[3] == "-R"
                and argv[4]
                and argv[5] == "--head"
                and argv[6]
                and list(argv[7:11]) == ["--state", "open", "--limit", "100"]
                and argv[11] == "--json"
                and argv[12]
                == "number,url,headRefOid,headRefName,headRepositoryOwner,isCrossRepository,baseRefName"
            ):
                return
            raise WatchError("Refusing an unapproved pull-request discovery command")
        if list(argv[1:3]) == ["api", "graphql"]:
            command = list(argv)
            if len(command) == 15 and command[-2] == "--hostname":
                if not GITHUB_HOST.fullmatch(command[-1]):
                    raise WatchError("Refusing an unapproved GitHub API hostname")
                command = command[:-2]
            if (
                len(command) == 13
                and command[3:6] == ["--method", "POST", "-f"]
                and command[6] == f"query={REVIEW_QUERY}"
                and command[7] == "-f"
                and command[8].startswith("owner=")
                and GITHUB_PART.fullmatch(command[8].removeprefix("owner="))
                and command[9] == "-f"
                and command[10].startswith("name=")
                and GITHUB_PART.fullmatch(command[10].removeprefix("name="))
                and command[11] == "-F"
                and re.fullmatch(r"number=[1-9][0-9]*", command[12])
            ):
                return
            raise WatchError("Refusing a non-approved GraphQL operation")
        if len(argv) >= 3 and argv[1] == "api":
            command = list(argv)
            if len(command) == 7 and command[-2] == "--hostname":
                if not GITHUB_HOST.fullmatch(command[-1]):
                    raise WatchError("Refusing an unapproved GitHub API hostname")
                command = command[:-2]
            if (
                len(command) == 5
                and (REACTION_ENDPOINT.fullmatch(command[2]) or CHECK_ENDPOINT.fullmatch(command[2]))
                and command[3:] == ["--method", "GET"]
            ):
                return
            raise WatchError("Refusing a non-approved GitHub API request")
    raise WatchError(f"Refusing unapproved monitoring command: {argv[0]}")


def redact(text: str) -> str:
    return SECRET.sub("[REDACTED]", text)


def run_command(
    argv: Sequence[str],
    cwd: Path | None = None,
    *,
    optional: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    deadline: Deadline | None = None,
) -> str | None:
    ensure_read_only(argv)
    # Empty disables both hook-based fsmonitor on older Git and the daemon on
    # newer Git. Older versions interpret "false" as a hook pathname.
    command = ["git", "-c", "core.fsmonitor=", *argv[1:]] if argv[0] == "git" else list(argv)
    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    if list(argv[:2]) == ["git", "diff"]:
        # macOS can normalize argv into another index filename. Keep the exact
        # spelling for this child without changing repository configuration.
        command[3:3] = ["-c", "core.precomposeunicode=false"]
        # Inventory supplies explicit literal pathspecs. Inherited defaults can
        # disable that magic or add case folding, so normalize only this child.
        for name in ("GIT_LITERAL_PATHSPECS", "GIT_ICASE_PATHSPECS",
                     "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS"):
            environment.pop(name, None)
    log_output = list(argv[:3]) == ["gh", "run", "view"] and any(
        option in argv for option in ("--log", "--log-failed")
    )
    options = argv[2:argv.index("--")] if "--" in argv else argv[2:]
    nul_output = argv[0] == "git" and "-z" in options

    def invoke(arguments, env, *, tail=False):
        remaining = deadline.remaining() if deadline is not None else 60
        try:
            result = capture_command(
                arguments,
                cwd=str(cwd) if cwd else None,
                env=env,
                timeout=min(60, remaining),
                tail=tail,
                lossless_stdout=nul_output,
            )
        except FileNotFoundError as exc:
            raise WatchError(f"Required executable is unavailable: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            if deadline is not None and remaining <= 60:
                raise WatchTimeout("monitor timeout") from exc
            raise WatchError(f"Read-only command timed out: {' '.join(argv[:3])}") from exc
        except OSError as exc:
            raise WatchError(f"Cannot capture read-only command: {' '.join(argv[:3])}") from exc
        if deadline is not None:
            deadline.remaining()
        if getattr(result, "stderr_overflow", False) or (
            getattr(result, "stdout_overflow", False) and not tail
        ):
            raise WatchError(f"Read-only command output exceeds the capture limit: {' '.join(argv[:3])}")
        return result

    if argv[0] == "git" and any(name in environment for name in (*SELECTORS, "GIT_INDEX_FILE")):
        location = (cwd or Path.cwd()).resolve()

        def query_path(option, env):
            result = invoke(["git", "-c", "core.fsmonitor=", "rev-parse", option], env)
            if result.returncode != 0 or not result.stdout.rstrip("\r\n"):
                raise ValueError("inherited Git selectors conflict with or cannot verify the selected repository")
            return (location / result.stdout.rstrip("\r\n")).resolve()

        try:
            _, environment = repository_context(location, environment, query_path, constrain_index=True)
        except ValueError as exc:
            raise WatchError(str(exc)) from exc

    for attempt in range(3):
        result = invoke(command, environment, tail=log_output)
        output = result.stdout if nul_output else result.stdout.rstrip("\r\n")
        if getattr(result, "stdout_overflow", False):
            # A retained partial first line can start inside a credential,
            # beyond the prefix needed by redaction. Keep complete lines.
            output = output.partition("\n")[2]
            output = "[omitted earlier command output: capture limit exceeded]\n" + output
        if result.returncode == 0:
            return redact(output) if log_output else output
        detail = redact((result.stderr or output or "unknown error").strip())
        if optional:
            return None
        if argv[0] == "gh" and TRANSIENT.search(detail) and attempt < 2:
            delay = min(2**attempt, deadline.remaining()) if deadline is not None else 2**attempt
            sleep(delay)
            continue
        raise WatchError(f"{' '.join(argv[:3])} failed: {detail[:1200]}")
    raise AssertionError("retry loop exited unexpectedly")


Runner = Callable[..., str | None]


def github_repository(url: str, *, github_hosts: Sequence[str] = ()) -> str:
    if re.match(r"^[^@\s]+@[^:\s]+:", url):
        host, path = url.split("@", 1)[1].split(":", 1)
    else:
        parsed = urlparse(url)
        host, path = parsed.hostname or "", parsed.path.lstrip("/")
    path = path.removesuffix(".git").strip("/")
    parts = path.split("/")
    host = host.lower()
    if not GITHUB_HOST.fullmatch(host) or len(parts) != 2 or not all(GITHUB_PART.fullmatch(part) for part in parts):
        safe_location = f"{host or '<missing host>'}/{path or '<missing repository>'}"
        raise WatchError(f"Unsupported GitHub remote URL: {safe_location}")
    if host != "github.com" and host not in {item.lower() for item in github_hosts}:
        raise WatchError(
            f"Remote host {host} is not a verified GitHub host; use the provider's own adapter, "
            "or --github-host HOST only after verifying this is GitHub Enterprise"
        )
    return path if host == "github.com" else f"{host}/{path}"


def git_root(path: Path, runner: Runner, *, optional: bool = False) -> Path | None:
    output = runner(["git", "rev-parse", "--show-toplevel"], cwd=path, optional=optional)
    return Path(output).resolve() if output else None


def discover_roots(
    cwd: Path,
    explicit: Sequence[Path],
    runner: Runner,
    *,
    include_siblings: bool = False,
    on_error: Callable[[Path, WatchError], None] | None = None,
) -> list[Path]:
    def inspect(path: Path, *, optional: bool = False) -> Path | None:
        try:
            result = git_root(path, runner, optional=optional)
            if result is None and not optional:
                raise WatchError(f"No Git repository found at {path}")
            return result
        except WatchTimeout:
            raise
        except WatchError as exc:
            if on_error is None:
                raise
            on_error(path, exc)
            return None

    workspaces: list[Path] = []
    if explicit:
        candidates = [inspect(path.resolve()) for path in explicit]
        if include_siblings:
            workspaces = list(dict.fromkeys(path.parent for path in candidates if path))
    else:
        location = cwd.resolve()
        current = inspect(location, optional=True)
        candidates = [current] if current else []
        if include_siblings:
            workspaces = [current.parent if current else location]
    if include_siblings:
        for workspace in workspaces:
            try:
                directories = sorted(
                    (
                        candidate for candidate in workspace.iterdir()
                        if candidate.is_dir() and not candidate.is_symlink()
                    ),
                    key=lambda candidate: (candidate.name.casefold(), candidate.name),
                )
            except OSError as exc:
                error = WatchError(f"Cannot inspect repository workspace: {workspace}")
                if on_error is None:
                    raise error from exc
                on_error(workspace, error)
                continue
            for directory in directories:
                candidate = inspect(directory, optional=True)
                if candidate and candidate == directory.resolve():
                    candidates.append(candidate)
    roots = list(dict.fromkeys(path for path in candidates if path))
    if not roots and on_error is None:
        raise WatchError("No Git repository found; use --repo /path/to/repository")
    return roots


def parse_submodules(output: str, root: Path) -> list[Path]:
    paths: list[Path] = []
    for line in output.splitlines():
        match = re.match(rf"^([ +\-U])({FULL_SHA})\s+(.+?)(?:\s+\([^)]*\))?$", line)
        if not match:
            raise WatchError(f"Cannot parse submodule status: {line[:160]}")
        state, _, relative = match.groups()
        if state == "-":
            raise WatchError(f"Uninitialized submodule: {root / relative}")
        if state == "+":
            raise WatchError(f"Submodule does not match its pinned gitlink: {root / relative}")
        if state == "U":
            raise WatchError(f"Submodule has unresolved conflicts: {root / relative}")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise WatchError(f"Submodule escapes its owning repository: {relative}")
        paths.append(path)
    return paths


def build_target(path: Path, root: Path, runner: Runner, *, github_hosts: Sequence[str] = ()) -> Target:
    branch = runner(["git", "branch", "--show-current"], cwd=path)
    if not branch:
        raise WatchError(f"Detached HEAD cannot be monitored safely: {path}")
    head = runner(["git", "rev-parse", "HEAD"], cwd=path)
    selected_ref = f"refs/heads/{branch}"
    upstream = runner(
        ["git", "for-each-ref", "--count=2", f"--format={UPSTREAM_FORMAT}", selected_ref],
        cwd=path,
    )
    fields = upstream.split("\0") if upstream else []
    if len(fields) != 3 or fields[0] != selected_ref or any("\n" in field or "\r" in field for field in fields):
        raise WatchError(f"Missing or ambiguous upstream facts for {path}")
    _, remote, remote_ref = fields
    if bool(remote) != bool(remote_ref):
        raise WatchError(f"Incomplete upstream remote/ref facts for {path}")
    if not remote:
        raise WatchError(f"Missing upstream remote/ref facts for {path}; configure tracking first")
    if remote == "." or remote.startswith("-") or re.search(r"\s", remote):
        raise WatchError(f"Unsupported upstream remote identity for {path}")
    if not remote_ref.startswith("refs/heads/") or not remote_ref.removeprefix("refs/heads/"):
        raise WatchError(f"Upstream is not a remote branch for {path}")
    upstream_branch = remote_ref.removeprefix("refs/heads/")
    remote_url = runner(["git", "remote", "get-url", remote], cwd=path)
    if not head or not remote_url:
        raise WatchError(f"Missing Git metadata for {path}")
    if not re.fullmatch(FULL_SHA, head):
        raise WatchError(f"Invalid full commit SHA: {path}")
    return Target(path, root, github_repository(remote_url, github_hosts=github_hosts), branch, upstream_branch, head, remote)


def discover_targets(
    roots: Sequence[Path], runner: Runner, *, deduplicate: bool = True,
    github_hosts: Sequence[str] = (),
) -> list[Target]:
    targets: list[Target] = []
    seen: set[str] = set()
    for root in roots:
        output = runner(["git", "submodule", "status", "--recursive"], cwd=root) or ""
        for path in [root, *parse_submodules(output, root)]:
            target = build_target(path, root, runner, github_hosts=github_hosts)
            key = target.key
            if not deduplicate or key not in seen:
                seen.add(key)
                targets.append(target)
    return targets


def ordered_push_targets(targets: Iterable[Target]) -> list[Target]:
    return sorted(targets, key=lambda target: (-target.depth, str(target.path)))


def bounded_log(text: str, max_lines: int, max_chars: int = 10000) -> str:
    if max_lines < 1 or max_chars < 1:
        return ""
    lines = redact(text).splitlines()
    output = "\n".join(lines[-max_lines:])
    if len(lines) <= max_lines and len(output) <= max_chars:
        return output
    marker = "[omitted earlier output]"
    if max_chars <= len(marker):
        return "[omitted]" if max_chars >= len("[omitted]") else "…"
    # Tiny line budgets keep the marker inline so useful tail lines survive.
    separate_line = max_lines > 2
    separator = "\n" if separate_line else " "
    tail = "\n".join(lines[-(max_lines - int(separate_line)):])
    available = max_chars - len(marker) - len(separator)
    return marker + separator + (tail[-available:] if available else "")


def classify(run: dict[str, Any]) -> str:
    if run.get("status") != "completed":
        return "active"
    conclusion = run.get("conclusion") or "unknown"
    return "passed" if conclusion == "success" else "skipped" if conclusion in NON_FAILURE else "failed"
