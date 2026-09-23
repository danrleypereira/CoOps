"""Provider-agnostic domain entities (issue #21).

Additive in this PR: nothing consumes these yet by design — they are the
first step of Phase 1 (#20), and the GitHub mapper (#25,
:mod:`coops.github.mapper`) is the proof that they fit real data. All of
them are frozen, slotted dataclasses that validate in ``__post_init__``
with ``ValueError``, matching :mod:`coops.domain.tenancy`.

Every entity carries a :class:`~coops.domain.TenantId`, never a bare
organization string: the raw store already scopes on ``TenantId`` and the
models must not weaken that boundary.
"""

from coops.domain.models.activity_event import ActivityEvent
from coops.domain.models.actor import Actor, display_name_of, identity_key
from coops.domain.models.commit import Commit
from coops.domain.models.file_tree import ENTRY_KINDS, FileEntry, FileTree
from coops.domain.models.issue import Issue
from coops.domain.models.member import Member
from coops.domain.models.pull_request import PullRequest
from coops.domain.models.repository import Repository

__all__ = [
    "ENTRY_KINDS",
    "ActivityEvent",
    "Actor",
    "Commit",
    "FileEntry",
    "FileTree",
    "Issue",
    "Member",
    "PullRequest",
    "Repository",
    "display_name_of",
    "identity_key",
]
