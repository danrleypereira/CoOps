"""A commit, provider-neutral, with its author resolved to an Actor.

Commits arrive from GitHub in two shapes and this model is the one place
they meet (the mapper in :mod:`coops.github.mapper` reads both).

``author`` is ``None`` when no channel identifies the author — no login,
no account, no name, no email (measured, 2,076 commits in the corpus,
#154: a deleted account, or author metadata that never resolved). An
absent author is not an ``Actor`` carrying a blank field: a shared empty
identity would merge distinct people, the defect #151 exists to prevent.
The same treatment the null event actors get.

Two fields exist because the two shapes disagree:

- ``committed_at`` — when the commit entered the history it was fetched
  from. Always present: GraphQL's ``committedDate``, or the REST committer
  date. This is the timestamp analytics order by.
- ``authored_at`` — when the change was originally written; it differs from
  ``committed_at`` after a rebase or cherry-pick. ``None`` when the source
  shape does not carry it (the GraphQL history query does not request
  ``authoredDate``; REST list items carry it as ``commit.author.date``).

``additions``/``deletions`` are ``None`` when the source carries no stats
(a REST list item without the detail fetch). ``message`` may be empty: git
permits empty commit messages, so there is no guard on it.
"""

from __future__ import annotations

from dataclasses import dataclass

from coops.domain.models.actor import Actor
from coops.domain.tenancy import TenantId


@dataclass(frozen=True, slots=True)
class Commit:
    """One commit on one repository's history."""

    tenant: TenantId
    repo_name: str
    sha: str
    author: Actor | None
    committed_at: str
    message: str
    authored_at: str | None = None
    parents: tuple[str, ...] = ()
    additions: int | None = None
    deletions: int | None = None

    def __post_init__(self) -> None:
        if not (self.repo_name or "").strip():
            raise ValueError("Commit requires a non-empty repo_name")
        if not (self.sha or "").strip():
            raise ValueError("Commit requires a non-empty sha")
        if not (self.committed_at or "").strip():
            raise ValueError("Commit requires a non-empty committed_at")
