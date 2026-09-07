"""Resolve repository paths that tests read, in the two layouts those tests run in.

Locally the suite runs from a checkout, so `Path(__file__).parents[3]` is the repository root.
In CI it runs inside the api container, where only `app`, `tests`, `scripts` and the mounted
contract and data directories exist — there is no repository root above `/code`, and the eager
`parents[3]` those tests used raised `IndexError` at import. Four modules failed collection that
way, which is why `python-unit` has been red: the assertions were not failing, they were never
running.

Nothing here degrades to a skip. A test that quietly stops checking a migration is worse than
one that fails, because a green run then means nothing about the thing it claims to cover.
"""

from __future__ import annotations

import os
from pathlib import Path


# A directory is the repository root when it holds both of these. Either alone appears in the
# container image, so both are required.
_ROOT_MARKERS = ("infrastructure/database/migrations", "packages/shared/src")


def repository_root() -> Path | None:
    """The checkout root, or None when the tests run without one (the container)."""
    for candidate in Path(__file__).resolve().parents:
        if all((candidate / marker).is_dir() for marker in _ROOT_MARKERS):
            return candidate
    return None


def _directory(environment_variable: str, *relative: str) -> Path:
    override = os.environ.get(environment_variable)
    if override:
        return Path(override)
    root = repository_root()
    if root is None:
        raise RuntimeError(
            f"{environment_variable} is unset and no repository root was found above "
            f"{Path(__file__).resolve()}. Mount the directory into the container or set the "
            "variable; do not skip the test, which would drop the assertion silently."
        )
    return root.joinpath(*relative)


def migrations_directory() -> Path:
    return _directory("STACKGRAPH_MIGRATIONS_DIR", "infrastructure", "database", "migrations")


def fixtures_directory() -> Path:
    return _directory("STACKGRAPH_FIXTURES_DIR", "packages", "shared", "src", "fixtures")
