#!/usr/bin/env python3
"""Watch exact-commit GitHub Actions with optional pull-request review monitoring."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.dont_write_bytecode = True

_SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if _SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, _SCRIPT_DIRECTORY)

from pipeline_monitor import Watcher
from pipeline_support import (
    ACTIVE,
    NON_FAILURE,
    SECRET,
    TRANSIENT,
    VIEW_FILTER,
    Runner,
    Target,
    WatchError,
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
    argument_parser.add_argument("--timeout", type=float, default=0, help="Optional monitoring deadline in seconds; zero waits until terminal")
    argument_parser.add_argument("--max-log-lines", type=int, default=40, help="Maximum lines emitted per failed job")
    argument_parser.add_argument("--max-log-chars", type=int, default=4000, help="Maximum characters emitted per failed job")
    argument_parser.add_argument("--max-failed-jobs", type=int, default=2, help="Maximum failed jobs inspected per workflow")
    argument_parser.add_argument("--max-runs", type=int, default=100, help="Workflow listing limit; reaching it blocks incomplete results")
    return argument_parser


def main(argv: Sequence[str] | None = None) -> int:
    options = parser().parse_args(argv)
    if min(
        options.interval, options.max_interval, options.heartbeat,
        options.rediscover, options.discovery_grace,
    ) <= 0:
        raise WatchError("Polling, heartbeat, rediscovery, and grace intervals must be positive")
    if min(options.max_log_lines, options.max_log_chars, options.max_failed_jobs, options.max_runs) <= 0:
        raise WatchError("Workflow and failure-output limits must be positive")
    if options.timeout < 0 or options.settle < 0:
        raise WatchError("Limits must be positive and timeout or settle windows cannot be negative")
    roots = discover_roots(
        options.cwd, options.repo, run_command, include_siblings=options.include_siblings
    )
    targets = discover_targets(roots, run_command, github_hosts=options.github_host)
    watcher = Watcher(
        targets,
        interval=options.interval,
        max_interval=options.max_interval,
        heartbeat=options.heartbeat,
        rediscover=options.rediscover,
        discovery_grace=options.discovery_grace,
        settle=options.settle,
        timeout=options.timeout,
        max_log_lines=options.max_log_lines,
        max_log_chars=options.max_log_chars,
        max_failed_jobs=options.max_failed_jobs,
        max_runs=options.max_runs,
        monitor_reviews=options.review_provider == "codex",
    )
    return watcher.watch(once=options.once)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except WatchError as error:
        Watcher.print_event({"event": "blocked", "reason": str(error)})
        raise SystemExit(2)
