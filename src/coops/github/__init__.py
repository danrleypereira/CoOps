"""The GitHub provider package: everything that knows GitHub's shapes.

The mapper (#25), the source-port adapter (#29) and the transport (#27)
live here; the raw capture (:mod:`coops.raw_capture`) and the Bronze
extractors (:mod:`coops.bronze`) predate them and are untouched.
"""

from typing import Any

from coops.github.mapper import (
    map_activity_event,
    map_commit_graphql,
    map_commit_rest,
    map_file_tree_graphql,
    map_file_tree_rest,
    map_issue,
    map_member,
    map_pull_request,
    map_repository,
)

__all__ = [
    "GitHubSourceAdapter",
    "map_activity_event",
    "map_commit_graphql",
    "map_commit_rest",
    "map_file_tree_graphql",
    "map_file_tree_rest",
    "map_issue",
    "map_member",
    "map_pull_request",
    "map_repository",
]


def __getattr__(name: str) -> Any:
    """Serve ``GitHubSourceAdapter`` on first request (#27).

    The adapter imports :class:`GitHubAPIClient` from
    ``coops.utils.github_api``, and since #27 that module imports this
    package's :mod:`coops.github.client` to inherit its transport — so an
    eager re-export here is a cycle in which every import order dies on a
    partially initialized module. Deferring the adapter until something
    actually asks for it breaks the cycle without changing any importer:
    ``from coops.github import GitHubSourceAdapter`` and
    ``from coops.github.adapter import GitHubSourceAdapter`` both keep
    working; the only thing that changes is that importing
    :mod:`coops.github` no longer imports the adapter as a side effect.
    """
    if name == "GitHubSourceAdapter":
        from coops.github.adapter import GitHubSourceAdapter

        return GitHubSourceAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
