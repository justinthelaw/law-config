"""Validate inherited Git selection without changing process-wide state."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping


SELECTORS = {"GIT_WORK_TREE": "--show-toplevel", "GIT_DIR": "--absolute-git-dir",
             "GIT_COMMON_DIR": "--git-common-dir"}


def repository_context(
    directory: Path, environment: Mapping[str, str],
    query_path: Callable[[str, Mapping[str, str]], Path], *,
    explicit: bool = True, constrain_index: bool = False,
) -> tuple[Path, dict[str, str]]:
    """Resolve the selected checkout and normalize matching hook selectors.

    The caller owns Git execution and any subsequent chdir. Explicit selection
    compares native discovery with inherited selectors before using their data.
    """
    inherited = dict(environment)
    selected_environment = dict(inherited)
    if explicit:
        for name in (*SELECTORS, "GIT_INDEX_FILE"):
            selected_environment.pop(name, None)
    selected = {name: query_path(option, selected_environment)
                for name, option in SELECTORS.items()}
    if explicit and any(name in inherited for name in SELECTORS):
        for name, option in SELECTORS.items():
            if query_path(option, inherited) != selected[name]:
                raise ValueError("inherited Git selectors conflict with the selected repository")
    for name, value in selected.items():
        if name in inherited:
            inherited[name] = str(value)
    if "GIT_INDEX_FILE" in inherited:
        index = (directory / inherited["GIT_INDEX_FILE"]).resolve()
        if constrain_index and not index.is_relative_to(selected["GIT_DIR"]):
            raise ValueError("explicit --repo requires an index inside its Git directory")
        inherited["GIT_INDEX_FILE"] = str(index)
    return selected["GIT_WORK_TREE"], inherited
