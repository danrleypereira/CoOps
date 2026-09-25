"""The GitHub provider package: everything that knows GitHub's shapes.

The mapper (#25) and the source-port adapter (#29) live here; the raw
capture (:mod:`coops.raw_capture`) and the Bronze extractors
(:mod:`coops.bronze`) predate them and are untouched.
"""

from coops.github.adapter import GitHubSourceAdapter
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
