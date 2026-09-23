"""GitHub REST/GraphQL payloads -> domain models (issue #25).

This module is the only place outside the extractors that knows about
GitHub: it reads the provider's own shapes and builds
:class:`~coops.domain` models from **named fields**, never by spreading a
response. ``data/bronze/`` is a publish boundary downstream of this mapper,
and a whitelist is bounded by what we use while a denylist is bounded by
what we have noticed (``docs/definition-of-done.md``; the projection pattern
is ``_project_issue``/``ISSUE_FIELDS`` in :mod:`coops.bronze.issues`).
Building a dataclass from named keyword arguments makes spreading
impossible by construction: a provider field nobody whitelisted raises
``TypeError`` instead of leaking onto the model.

Commit authors arrive in two shapes, and both are mapped here from the
*provider* representation rather than from the REST-like intermediate that
:mod:`coops.bronze.commits` normalises into — so the GitHub knowledge stays
in one place:

- GraphQL ``history`` nodes, as requested by
  ``GitHubAPIClient.graphql_commit_history``::

      {oid, message, committedDate,
       author {name email user {login databaseId}},
       parents {nodes {oid}}, additions, deletions}

- REST commit objects (list items of ``/repos/{full_name}/commits`` or the
  commit detail)::

      {sha, commit {author {name email date}, committer {date}, message},
       author {login id} | null, parents [{sha}], stats {additions deletions}}

An email address never reaches a model. As in
:func:`coops.bronze.commits._sanitize_commit`, the address is reduced to its
SHA-256 (``_hash_email`` below, twin of the Bronze helper) and only the hash
travels, as ``Actor.email_hash``; the raw name survives only as
``display_name``, blanked when it is itself an address (#132).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from coops.domain import (
    ActivityEvent,
    Actor,
    Commit,
    FileEntry,
    FileTree,
    Issue,
    Member,
    PullRequest,
    Repository,
    TenantId,
    display_name_of,
    identity_key,
)


def _hash_email(email: str) -> str:
    """SHA-256 of a trimmed, lower-cased address.

    Twin of ``coops.bronze.commits._hash_email``: same input normalisation,
    so an identity derived here matches one derived by the Bronze scrub.
    Pseudonymization, not anonymization — the point is that no raw address
    crosses onto a domain model.
    """
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _author_actor(
    *,
    login: str | None = None,
    account_id: int | None = None,
    name: str | None = None,
    email: str | None = None,
) -> Actor:
    """Resolve a commit author from the provider's three identity channels.

    The email is hashed here and only the hash is passed on, and — matching
    ``_sanitize_commit`` — the hash is kept only when there is no account
    link: a linked author is keyed by ``login``, an unlinked one (5.8% of
    the corpus) by the hash of an email that is their only identifier.
    ``Actor.resolve`` applies the precedence (login -> email_hash -> name)
    and blanks an address-shaped name.
    """
    unlinked = not login and account_id is None
    return Actor.resolve(
        login=login,
        account_id=account_id,
        name=name,
        email_hash=_hash_email(email) if email and unlinked else None,
    )


def _conversation_actor(raw_user: Any) -> Actor | None:
    """A user object on an issue/PR/event payload, or ``None``.

    ``None`` (JSON ``null``, a deleted account) stays ``None``: an absent
    actor is not a person named "unknown" — measured, 957 event actors in
    the corpus are literally ``null``.
    """
    if not isinstance(raw_user, Mapping) or not raw_user.get("login"):
        return None
    return Actor.resolve(
        login=raw_user.get("login"),
        account_id=raw_user.get("id"),
    )


def map_repository(raw: Mapping[str, Any], tenant: TenantId) -> Repository:
    """Map a REST repository object (``/orgs/{org}/repos`` item)."""
    return Repository(
        tenant=tenant,
        repo_id=raw.get("id") or 0,
        name=raw.get("name") or "",
        full_name=raw.get("full_name") or "",
        is_private=bool(raw.get("private")),
        is_fork=bool(raw.get("fork")),
        is_archived=bool(raw.get("archived")),
        description=raw.get("description"),
        default_branch=raw.get("default_branch"),
        language=raw.get("language"),
        html_url=raw.get("html_url"),
        size_kb=raw.get("size"),
        stargazers_count=raw.get("stargazers_count"),
        forks_count=raw.get("forks_count"),
        open_issues_count=raw.get("open_issues_count"),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
        pushed_at=raw.get("pushed_at"),
    )


def map_member(
    raw: Mapping[str, Any],
    tenant: TenantId,
    *,
    is_org_member: bool = False,
) -> Member:
    """Map a REST user payload to a Member.

    Accepts the shapes that make up the member population, all of which
    carry ``login`` and ``id``: the organization member list item, the
    contributor list item (whose ``contributions`` total is picked up here)
    and the ``/users/{login}`` profile (the only one carrying ``name`` —
    list items yield ``display_name=None``, which is normal). Whether the
    person is an organization member is caller knowledge (which endpoint
    produced the payload), hence the keyword-only flag.
    """
    login = raw.get("login") or None
    display_name = display_name_of(raw.get("name"))
    identity = identity_key(login, None, display_name)
    if identity is None:
        raise ValueError(
            "member payload carries no login and no legible name;"
            " nothing to key a Member on"
        )
    return Member(
        tenant=tenant,
        identity=identity,
        display_name=display_name,
        login=login,
        account_id=raw.get("id"),
        is_org_member=is_org_member,
        contributions_total=raw.get("contributions") or 0,
    )


def map_commit_graphql(
    node: Mapping[str, Any],
    tenant: TenantId,
    repo_name: str,
) -> Commit:
    """Map one GraphQL ``history`` node to a Commit.

    The node shape is what ``graphql_commit_history`` requests (see module
    docstring); ``additions``/``deletions`` are always requested but kept
    optional so a degraded node still maps.
    """
    author = node.get("author") or {}
    user = author.get("user") or {}
    parent_nodes = (node.get("parents") or {}).get("nodes") or []
    return Commit(
        tenant=tenant,
        repo_name=repo_name,
        sha=node.get("oid") or "",
        author=_author_actor(
            login=user.get("login"),
            account_id=user.get("databaseId"),
            name=author.get("name"),
            email=author.get("email"),
        ),
        committed_at=node.get("committedDate") or "",
        message=node.get("message") or "",
        parents=tuple(
            p["oid"] for p in parent_nodes if isinstance(p, Mapping) and p.get("oid")
        ),
        additions=node.get("additions"),
        deletions=node.get("deletions"),
    )


def map_commit_rest(
    raw: Mapping[str, Any],
    tenant: TenantId,
    repo_name: str,
) -> Commit:
    """Map one REST commit object (list item or detail) to a Commit.

    The account link lives in the top-level ``author`` (``null`` for the
    5.8% of authors with no GitHub account); the git identity lives in
    ``commit.author``. ``stats`` is only present on the detail payload, so
    additions/deletions are ``None`` for list items.
    """
    top_author = raw.get("author") or {}
    git_author = (raw.get("commit") or {}).get("author") or {}
    git_committer = (raw.get("commit") or {}).get("committer") or {}
    stats = raw.get("stats") or {}
    return Commit(
        tenant=tenant,
        repo_name=repo_name,
        sha=raw.get("sha") or "",
        author=_author_actor(
            login=top_author.get("login"),
            account_id=top_author.get("id"),
            name=git_author.get("name"),
            email=git_author.get("email"),
        ),
        committed_at=git_committer.get("date") or "",
        message=(raw.get("commit") or {}).get("message") or "",
        authored_at=git_author.get("date"),
        parents=tuple(
            p["sha"]
            for p in raw.get("parents") or []
            if isinstance(p, Mapping) and p.get("sha")
        ),
        additions=stats.get("additions"),
        deletions=stats.get("deletions"),
    )


def map_issue(raw: Mapping[str, Any], tenant: TenantId, repo_name: str) -> Issue:
    """Map a REST issue payload (no ``pull_request`` object) to an Issue.

    Built from named fields only: ``body`` and ``milestone`` are never read,
    so they cannot reach the model whatever the provider sends.
    """
    if raw.get("pull_request"):
        raise ValueError(
            f"payload #{raw.get('number')} is a pull request; use map_pull_request"
        )
    return Issue(
        tenant=tenant,
        repo_name=repo_name,
        number=raw.get("number") or 0,
        state=raw.get("state") or "",
        title=raw.get("title") or "",
        author=_conversation_actor(raw.get("user")),
        assignee=_conversation_actor(raw.get("assignee")),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
        closed_at=raw.get("closed_at"),
    )


def map_pull_request(
    raw: Mapping[str, Any],
    tenant: TenantId,
    repo_name: str,
) -> PullRequest:
    """Map a REST issue payload that carries a ``pull_request`` object."""
    pr = raw.get("pull_request")
    if not pr:
        raise ValueError(
            f"payload #{raw.get('number')} has no pull_request object; use map_issue"
        )
    return PullRequest(
        tenant=tenant,
        repo_name=repo_name,
        number=raw.get("number") or 0,
        state=raw.get("state") or "",
        title=raw.get("title") or "",
        author=_conversation_actor(raw.get("user")),
        assignee=_conversation_actor(raw.get("assignee")),
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
        closed_at=raw.get("closed_at"),
        merged_at=pr.get("merged_at"),
        draft=bool(raw.get("draft")),
    )


def map_activity_event(
    raw: Mapping[str, Any],
    tenant: TenantId,
    repo_name: str,
) -> ActivityEvent:
    """Map a REST issue-event payload to an ActivityEvent."""
    issue = raw.get("issue")
    return ActivityEvent(
        tenant=tenant,
        repo_name=repo_name,
        event_id=raw.get("id") or 0,
        event_type=raw.get("event") or "",
        created_at=raw.get("created_at") or "",
        actor=_conversation_actor(raw.get("actor")),
        issue_number=issue.get("number") if isinstance(issue, Mapping) else None,
    )


def map_file_tree_rest(
    raw: Mapping[str, Any],
    tenant: TenantId,
    repo_name: str,
    branch: str | None = None,
) -> FileTree:
    """Map a REST Git Trees response (``?recursive=1``) to a FileTree.

    Refuses a response with ``truncated: true``: a partial tree mapped as a
    whole one is silent data loss, and the extraction layer falls back to
    GraphQL precisely so that never reaches storage.
    """
    if raw.get("truncated"):
        raise ValueError("refusing to map a truncated REST tree; fall back to GraphQL")
    entries = tuple(
        FileEntry(
            path=item.get("path") or "",
            kind=item.get("type") or "",
            sha=item.get("sha"),
            mode=item.get("mode"),
            size=item.get("size"),
        )
        for item in raw.get("tree") or []
        if isinstance(item, Mapping)
    )
    return FileTree(
        tenant=tenant,
        repo_name=repo_name,
        branch=branch,
        sha=raw.get("sha"),
        entries=entries,
    )


def map_file_tree_graphql(
    entries: Any,
    tenant: TenantId,
    repo_name: str,
    branch: str | None = None,
) -> FileTree:
    """Map one level of GraphQL ``... on Tree { entries { ... } }``.

    The GraphQL walk fetches each directory with its own query, and
    ``TreeEntry.path`` is the full path from the repository root, so every
    level maps independently and the caller composes them. Blob facts
    (``oid``, ``byteSize``, ``isBinary``) sit under ``object`` and exist for
    blobs only, so a directory entry maps with ``sha``/``size``/``is_binary``
    all ``None``. There is no tree sha at this level.
    """
    mapped = []
    for entry in entries or []:
        if not isinstance(entry, Mapping):
            continue
        blob = entry.get("object") or {}
        mapped.append(
            FileEntry(
                path=entry.get("path") or "",
                kind=entry.get("type") or "",
                sha=blob.get("oid"),
                mode=entry.get("mode"),
                size=blob.get("byteSize"),
                is_binary=blob.get("isBinary"),
            )
        )
    return FileTree(
        tenant=tenant,
        repo_name=repo_name,
        branch=branch,
        entries=tuple(mapped),
    )
