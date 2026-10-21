#!/usr/bin/env python3
"""Watch exact-commit GitHub Actions with optional pull-request review monitoring."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from functools import partial
from pathlib import Path
from typing import Sequence

sys.dont_write_bytecode = True

_SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if _SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, _SCRIPT_DIRECTORY)

from pipeline_monitor import DEFAULT_TIMEOUT, Watcher, budget_event, monitor_deadline, watch_roots
from pipeline_support import (
    ACTIVE,
    NON_FAILURE,
    SECRET,
    TRANSIENT,
    VIEW_FILTER,
    Runner,
    Deadline,
    Target,
    WatchError,
    WatchTimeout,
    bounded_log,
    build_target,
    classify,
    discover_roots,
    discover_targets,
    ensure_read_only,
    git_root,
    github_repository,
    ordered_push_targets,
    parse_submodules,
    redact,
    run_command,
    validate_timings,
)


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--repo", type=Path, action="append", default=[], help="Monitor only explicitly selected repository roots")
    argument_parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Repository or explicitly selected workspace")
    argument_parser.add_argument("--include-siblings", action="store_true", help="Explicitly include all immediate sibling Git roots")
    argument_parser.add_argument("--github-host", action="append", default=[], help="Explicitly verified GitHub Enterprise hostname (repeatable)")
    argument_parser.add_argument("--review-provider", choices=("codex",), help="Also monitor this review adapter; default monitors CI only")
    argument_parser.add_argument("--once", action="store_true", help="Emit one compact current-state snapshot")
    argument_parser.add_argument("--interval", type=float, default=20, help="Seconds between active-workflow checks")
    argument_parser.add_argument("--max-interval", type=float, default=60, help="Maximum seconds between unchanged workflow checks")
    argument_parser.add_argument("--heartbeat", type=float, default=60, help="Seconds between compact progress heartbeats")
    argument_parser.add_argument("--rediscover", type=float, default=90, help="Seconds between late-workflow discovery passes")
    argument_parser.add_argument("--discovery-grace", type=float, default=120, help="Seconds allowed for an exact-commit workflow to appear")
    argument_parser.add_argument("--settle", type=float, default=120, help="Quiet seconds before a final exact-commit workflow discovery pass")
    argument_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Total budget in seconds including discovery and retries (default: 1800); explicitly use zero for indefinite monitoring")
    argument_parser.add_argument("--deadline", help="Original absolute ISO 8601 deadline with timezone when resuming; overrides --timeout")
    argument_parser.add_argument("--max-log-lines", type=int, default=40, help="Maximum lines emitted per failed job")
    argument_parser.add_argument("--max-log-chars", type=int, default=4000, help="Maximum characters emitted per failed job")
    argument_parser.add_argument("--max-failed-jobs", type=int, default=2, help="Maximum failed jobs inspected per workflow")
    argument_parser.add_argument("--max-runs", type=int, default=100, help="Workflow listing limit; reaching it blocks incomplete results")
    return argument_parser


def main(argv: Sequence[str] | None = None) -> int:
    options = parser().parse_args(argv)
    validate_timings(
        interval=options.interval, max_interval=options.max_interval, heartbeat=options.heartbeat,
        rediscover=options.rediscover, discovery_grace=options.discovery_grace,
        timeout=options.timeout, settle=options.settle,
    )
    if min(options.max_log_lines, options.max_log_chars, options.max_failed_jobs, options.max_runs) <= 0:
        raise WatchError("Workflow and failure-output limits must be positive")
    deadline = monitor_deadline(options.timeout, options.deadline, clock=time.monotonic, wall_clock=time.time)
    Watcher.print_event(budget_event(deadline))
    if deadline is not None:
        deadline.remaining()
    runner = deadline.bind(partial(run_command, deadline=deadline)) if deadline is not None else run_command
    blocked: dict[str, str] = {}

    def block(root: Path, error: WatchError) -> None:
        blocked[str(root)] = str(error)
        Watcher.print_event({"event": "root-blocked", "root": str(root), "reason": str(error)})

    roots = discover_roots(
        options.cwd, options.repo, runner, include_siblings=options.include_siblings, on_error=block,
    )
    if not roots and not blocked:
        block(options.cwd.resolve(), WatchError("No Git repository found; use --repo /path/to/repository"))
    watchers = []
    for root in roots:
        try:
            targets = discover_targets([root], runner, deduplicate=False, github_hosts=options.github_host)
        except WatchTimeout:
            raise
        except WatchError as error:
            block(root, error)
            continue
        watchers.append(Watcher(
            targets, runner=runner, deadline=deadline, timeout=0, clock=time.monotonic,
            interval=options.interval, max_interval=options.max_interval,
            heartbeat=options.heartbeat, rediscover=options.rediscover,
            discovery_grace=options.discovery_grace, settle=options.settle,
            max_log_lines=options.max_log_lines, max_log_chars=options.max_log_chars,
            max_failed_jobs=options.max_failed_jobs, max_runs=options.max_runs,
            monitor_reviews=options.review_provider == "codex",
        ))
    return watch_roots(
        watchers, blocked=blocked, once=options.once, emit=Watcher.print_event,
        clock=time.monotonic, sleep=time.sleep, deadline=deadline,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WatchError as error:
        Watcher.print_event({"event": "blocked", "reason": str(error)})
        raise SystemExit(2)
