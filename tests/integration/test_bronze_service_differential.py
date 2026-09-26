"""Differential acceptance for the ported Bronze service (#30).

The claim under test is byte-identity: over one fixed corpus served by one
stub client, the legacy extractors and ``BronzeService`` (through
``GitHubSourceAdapter`` + ``FileStorageAdapter``) must produce the same
tree, file for file and byte for byte, modulo the generation timestamps.

Arms
----
Both arms read the *same* stub client, so the corpus — not the adapter —
is the only difference between them:

* legacy arm: ``extract_repositories`` → ``extract_issues`` →
  ``extract_commits`` (the CLI's default GraphQL method) →
  ``extract_members`` → ``extract_repository_structure``, run with the
  working directory inside ``tmp_path`` so the relative ``data/bronze``
  paths land there;
* service arm: the same step order through ``BronzeService``, writing
  through ``FileStorageAdapter`` into a separate root.

What the corpus deliberately does not carry (each is a reported finding,
not a hidden exemption)
----------------------------------------------------------------------
The stub's GraphQL commit nodes carry no ``committer``, because the
``Commit`` model has none: a node that had one would make the legacy arm
write ``commit.committer`` with real values the service cannot reproduce.
The stub's tree response reuses the branch-head sha as its own ``sha``,
because ``FileTree.sha`` (the tree response's sha) is not the value the
legacy structure record carries (the branch-head commit sha). And the
member payloads are minimal: members are not ported at all (see below).

``REPO_RECORDS`` carries the **99-key** shape a real ``repo_*.json`` payload
has (476 of the fga corpus's 486 files at 99, 10 at 100 with
``template_repository``), not the seventeen ``Repository`` reads. It used to
carry only those seventeen, which made every repository arm here unable to
fail — so the headline "byte-identical" count included families whose
comparison was decided by the fixture rather than by the code. #241.

With the real shape, **five** families cannot match, and that number was
measured rather than predicted: not only the two ``repo_*.json`` files but
all three ``repositories_*`` aggregates, which are built from the same
listing records. They are listed in ``PARITY_GAP_FILES``, still compared and
still reported, and pinned by the strict xfail
``test_repository_families_would_be_byte_identical`` — which flips to an
unexpected pass, loudly, the day #241 lands.

So the honest accounting of the sixteen families this corpus exercises is:

* **7** compared and byte-identical — the claim this file actually proves;
* **5** compared and pinned as parity gaps (``PARITY_GAP_FILES``, #241);
* **4** not written at all because the port cannot express them
  (``PORT_GAP_FILES``: both ``members_*``, both ``issue_events_*``).

``test_listing_fixture_carries_more_than_the_model_reads`` is the guard that
keeps this true: a fixture whose key set equals the model's field set fails
there, so the next family cannot be born vacuous.

Families the service does not write (pinned, not skipped)
---------------------------------------------------------
``members_basic.json``, ``members_detailed.json`` and
``issue_events_<repo>.json`` are produced by the legacy arm only: the
source port has no ``fetch_issue_events`` and the ``Member`` model cannot
express the member record. The comparison ASSERTS those files — and only
those files — are missing from the service arm, so any other file the
service failed to write fails this test rather than disappearing.

Timestamp normalisation (accounted, bounded)
--------------------------------------------
Exactly two generation-time fields are normalised before comparing:
``_metadata.extracted_at`` (list and document envelopes) and the structure
document's own ``extracted_at``. Both are ``now()``-at-write in both arms
and differ between any two runs, including two legacy runs. The count of
normalised fields is asserted, so a third exemption cannot be added
silently.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from coops.bronze.bronze_service import BronzeService
from coops.bronze.commits import extract_commits
from coops.bronze.issues import extract_issues
from coops.bronze.members import extract_members
from coops.bronze.repositories import extract_repositories
from coops.bronze.repository_structure import extract_repository_structure
from coops.domain.tenancy import resolve_tenant
from coops.github.adapter import GitHubSourceAdapter
from coops.storage.file import FileStorageAdapter
from coops.utils.github_api import GitHubAPIClient, OrganizationConfig

ORG = "test-org"
_API = "https://api.github.com"

# The repository listing, in listing order: two kept repositories, one
# fork and one blacklisted, so the filter runs in both arms. The key set
# is exactly what map_repository reads — see the module docstring.
#: A real ``repo_*.json`` payload carries **99** keys (476 of the fga corpus's 486
#: files; 100 on the other 10, adding ``template_repository``) where ``Repository``
#: reads **17**. A fixture carrying only those 17 makes the ``repo_*`` arms of this
#: differential unable to fail — the shaping #241 names. So the listing records
#: below carry the full 99-key shape.
#:
#: The key *names* are GitHub's repository schema, taken from the corpus. The
#: *values* are synthetic: what makes the comparison non-vacuous is that the
#: payload carries fields the projection must drop, not what those fields hold.
_PAYLOAD_FLAG_KEYS: tuple[str, ...] = (
    "allow_auto_merge", "allow_forking", "allow_merge_commit",
    "allow_rebase_merge", "allow_squash_merge", "allow_update_branch",
    "delete_branch_on_merge", "disabled", "has_discussions",
    "has_downloads", "has_issues", "has_pages",
    "has_projects", "has_pull_requests", "has_wiki",
    "is_template", "use_squash_pr_title_as_default", "web_commit_signoff_required",
)

_PAYLOAD_COUNT_KEYS: tuple[str, ...] = (
    "forks", "network_count", "open_issues",
    "subscribers_count", "watchers", "watchers_count",
)

_PAYLOAD_OBJECT_KEYS: tuple[str, ...] = (
    "custom_properties", "license", "organization",
    "owner", "permissions", "security_and_analysis",
)

_PAYLOAD_STRING_KEYS: tuple[str, ...] = (
    "archive_url", "assignees_url",
    "blobs_url", "branches_url",
    "clone_url", "collaborators_url",
    "comments_url", "commits_url",
    "compare_url", "contents_url",
    "contributors_url", "deployments_url",
    "downloads_url", "events_url",
    "forks_url", "git_commits_url",
    "git_refs_url", "git_tags_url",
    "git_url", "homepage",
    "hooks_url", "issue_comment_url",
    "issue_events_url", "issues_url",
    "keys_url", "labels_url",
    "languages_url", "merge_commit_message",
    "merge_commit_title", "merges_url",
    "milestones_url", "mirror_url",
    "node_id", "notifications_url",
    "pull_request_creation_policy", "pulls_url",
    "releases_url", "squash_merge_commit_message",
    "squash_merge_commit_title", "ssh_url",
    "stargazers_url", "statuses_url",
    "subscribers_url", "subscription_url",
    "svn_url", "tags_url",
    "teams_url", "temp_clone_token",
    "topics", "trees_url",
    "url", "visibility",
)


def _github_only_fields(full_name: str) -> dict[str, Any]:
    """The 82 payload keys ``Repository`` cannot carry, with synthetic values."""
    fields: dict[str, Any] = dict.fromkeys(_PAYLOAD_FLAG_KEYS, False)
    fields.update(dict.fromkeys(_PAYLOAD_COUNT_KEYS, 0))
    fields.update({key: {"schema": key} for key in _PAYLOAD_OBJECT_KEYS})
    for key in _PAYLOAD_STRING_KEYS:
        fields[key] = f"{_API}/repos/{full_name}/{key}"
    fields["mirror_url"] = None
    fields["topics"] = []
    return fields


def _rich(record: dict[str, Any]) -> dict[str, Any]:
    """A listing record in the payload's real shape: the 17 keys the model reads
    plus the 82 it drops, so a projection cannot compare equal by construction.
    """
    return {**_github_only_fields(record["full_name"]), **record}


REPO_RECORDS: list[dict[str, Any]] = [
    _rich({
        "id": 101,
        "name": "repo1",
        "full_name": "test-org/repo1",
        "private": False,
        "fork": False,
        "archived": False,
        "description": "First corpus repository",
        "default_branch": "main",
        "language": "Python",
        "html_url": "https://github.com/test-org/repo1",
        "size": 42,
        "stargazers_count": 3,
        "forks_count": 1,
        "open_issues_count": 2,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-06-01T00:00:00Z",
        "pushed_at": "2025-06-01T00:00:00Z",
    }),
    _rich({
        "id": 102,
        "name": "2026.1-App.Two",
        "full_name": "test-org/2026.1-App.Two",
        "private": False,
        "fork": False,
        "archived": False,
        "description": "Second corpus repository",
        "default_branch": "master",
        "language": "TypeScript",
        "html_url": "https://github.com/test-org/2026.1-App.Two",
        "size": 7,
        "stargazers_count": 0,
        "forks_count": 0,
        "open_issues_count": 1,
        "created_at": "2025-02-01T00:00:00Z",
        "updated_at": "2025-05-01T00:00:00Z",
        "pushed_at": "2025-05-01T00:00:00Z",
    }),
    _rich({
        "id": 103,
        "name": "somefork",
        "full_name": "test-org/somefork",
        "private": False,
        "fork": True,
        "archived": False,
        "description": "A fork, filtered out",
        "default_branch": "main",
        "language": "Python",
        "html_url": "https://github.com/test-org/somefork",
        "size": 1,
        "stargazers_count": 0,
        "forks_count": 0,
        "open_issues_count": 0,
        "created_at": "2025-03-01T00:00:00Z",
        "updated_at": "2025-03-01T00:00:00Z",
        "pushed_at": "2025-03-01T00:00:00Z",
    }),
    _rich({
        "id": 104,
        "name": "Hi.Events",
        "full_name": "test-org/Hi.Events",
        "private": False,
        "fork": False,
        "archived": False,
        "description": "Blacklisted, filtered out",
        "default_branch": "main",
        "language": "PHP",
        "html_url": "https://github.com/test-org/Hi.Events",
        "size": 9,
        "stargazers_count": 0,
        "forks_count": 0,
        "open_issues_count": 0,
        "created_at": "2025-04-01T00:00:00Z",
        "updated_at": "2025-04-01T00:00:00Z",
        "pushed_at": "2025-04-01T00:00:00Z",
    }),
]

_ISSUE_BASE = {
    "user": {"login": "linked_user", "id": 4242},
    "assignee": None,
}

ISSUES_BY_REPO: dict[str, list[dict[str, Any]]] = {
    # GitHub returns issues and PRs interleaved, newest first.
    "repo1": [
        {
            "id": 9003,
            "number": 3,
            "state": "open",
            "title": "Pull request one",
            "created_at": "2025-04-01T00:00:00Z",
            "updated_at": "2025-04-02T00:00:00Z",
            "closed_at": None,
            **_ISSUE_BASE,
            "user": {"login": "outsider", "id": 4245},
            "pull_request": {
                "url": f"{_API}/repos/test-org/repo1/pulls/3",
                "merged_at": None,
            },
        },
        {
            "id": 9002,
            "number": 2,
            "state": "open",
            "title": "Second issue",
            "created_at": "2025-03-01T00:00:00Z",
            "updated_at": "2025-03-02T00:00:00Z",
            "closed_at": None,
            **_ISSUE_BASE,
            "assignee": {"login": "linked_user", "id": 4242},
        },
        {
            "id": 9001,
            "number": 1,
            "state": "closed",
            "title": "First issue",
            "created_at": "2025-02-01T10:00:00Z",
            "updated_at": "2025-02-02T10:00:00Z",
            "closed_at": "2025-02-02T10:00:00Z",
            **_ISSUE_BASE,
        },
    ],
    # No PRs here on purpose: the legacy step writes no prs_<repo>.json
    # when there are none, and the service must agree.
    "2026.1-App.Two": [
        {
            "id": 9101,
            "number": 1,
            "state": "open",
            "title": "Only issue",
            "created_at": "2025-05-01T00:00:00Z",
            "updated_at": "2025-05-02T00:00:00Z",
            "closed_at": None,
            **_ISSUE_BASE,
        },
    ],
}

EVENTS_BY_REPO: dict[str, list[dict[str, Any]]] = {
    "repo1": [
        {
            "id": 502,
            "event": "assigned",
            "created_at": "2025-03-02T00:00:00Z",
            "actor": {"login": "linked_user", "id": 4242},
            "issue": {"number": 2},
        },
        {
            "id": 501,
            "event": "closed",
            "created_at": "2025-02-02T10:00:00Z",
            "actor": {"login": "linked_user", "id": 4242},
            "issue": {"number": 1},
        },
    ],
    "2026.1-App.Two": [],
}

# GraphQL history nodes, newest first, exactly the fields the history
# query requests (no url, no committer — see the module docstring).
COMMIT_NODES_BY_REPO: dict[str, list[dict[str, Any]]] = {
    "repo1": [
        {
            "oid": "ccc3",
            "message": (
                "feat: third change\n\n"
                "Co-authored-by: Pair Person <pair@personal.example.net>\n"
            ),
            "messageHeadline": "feat: third change",
            "committedDate": "2025-06-01T00:00:00Z",
            "author": {
                "name": "Linked Person",
                "email": "linked@example.com",
                "user": {"login": "linked_user", "databaseId": 4242},
            },
            "additions": 10,
            "deletions": 2,
            "parents": {"nodes": [{"oid": "bbb2"}]},
        },
        {
            "oid": "bbb2",
            "message": "fix: handle empty input",
            "messageHeadline": "fix: handle empty input",
            "committedDate": "2025-03-01T00:00:00Z",
            # git user.name set to the address: the known case the label
            # policy blanks (#132), exercised on both arms.
            "author": {
                "name": "unlinked@example.com",
                "email": "unlinked@example.com",
            },
            "additions": 4,
            "deletions": 0,
            "parents": {"nodes": [{"oid": "aaa1"}]},
        },
        {
            "oid": "aaa1",
            "message": "chore: initial commit",
            "messageHeadline": "chore: initial commit",
            "committedDate": "2025-02-01T00:00:00Z",
            "author": {
                "name": "Second Person",
                "email": "second@example.com",
                "user": {"login": "second_user", "databaseId": 4243},
            },
            "additions": 100,
            "deletions": 0,
            "parents": {"nodes": []},
        },
    ],
    "2026.1-App.Two": [
        {
            "oid": "ddd1",
            "message": "feat: seed project",
            "messageHeadline": "feat: seed project",
            "committedDate": "2025-05-01T00:00:00Z",
            "author": {
                "name": "Linked Person",
                "email": "linked@example.com",
                "user": {"login": "linked_user", "databaseId": 4242},
            },
            "additions": 12,
            "deletions": 3,
            "parents": {"nodes": []},
        },
    ],
}

# Branch heads and raw recursive-tree responses. The response sha mirrors
# the branch-head sha on purpose — see the module docstring.
BRANCHES: dict[tuple[str, str], dict[str, Any]] = {
    ("repo1", "main"): {"commit": {"sha": "sha-head-1"}},
    ("2026.1-App.Two", "master"): {"commit": {"sha": "sha-head-2"}},
}

TREES: dict[str, dict[str, Any]] = {
    "sha-head-1": {
        "sha": "sha-head-1",
        "truncated": False,
        "tree": [
            {
                "path": "README.md",
                "mode": "100644",
                "type": "blob",
                "sha": "blob-1",
                "size": 120,
            },
            {"path": "src", "mode": "040000", "type": "tree", "sha": "tree-1"},
            {
                "path": "src/main.py",
                "mode": "100644",
                "type": "blob",
                "sha": "blob-2",
                "size": 2048,
            },
        ],
    },
    "sha-head-2": {
        "sha": "sha-head-2",
        "truncated": False,
        "tree": [
            {
                "path": "notes.txt",
                "mode": "100644",
                "type": "blob",
                "sha": "blob-3",
                "size": 64,
            }
        ],
    },
}

# Members: the legacy arm only (the service does not extract members).
ORG_MEMBERS: list[dict[str, Any]] = [
    {"login": "linked_user", "id": 4242},
    {"login": "orgmate", "id": 4244},
]

CONTRIBUTORS_BY_REPO: dict[str, list[dict[str, Any]]] = {
    "repo1": [
        {
            "login": "linked_user",
            "id": 4242,
            "type": "User",
            "contributions": 7,
            "avatar_url": "https://avatars.example.com/linked_user",
            "html_url": "https://github.com/linked_user",
        },
        {
            "login": "outsider",
            "id": 4245,
            "type": "User",
            "contributions": 2,
            "avatar_url": "https://avatars.example.com/outsider",
            "html_url": "https://github.com/outsider",
        },
    ],
    "2026.1-App.Two": [
        {
            "login": "orgmate",
            "id": 4244,
            "type": "User",
            "contributions": 1,
            "avatar_url": "https://avatars.example.com/orgmate",
            "html_url": "https://github.com/orgmate",
        },
    ],
}


def _profile(login: str, account_id: int) -> dict[str, Any]:
    return {
        "login": login,
        "id": account_id,
        "name": f"Person {account_id}",
        "type": "User",
        "avatar_url": f"https://avatars.example.com/{login}",
        "html_url": f"https://github.com/{login}",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-06-01T00:00:00Z",
        "public_repos": 3,
        "followers": 1,
        "following": 1,
    }


PROFILES: dict[str, dict[str, Any]] = {
    login: _profile(login, record["id"]) for login, record in [
        ("linked_user", ORG_MEMBERS[0]),
        ("orgmate", ORG_MEMBERS[1]),
        ("outsider", {"id": 4245}),
    ]
}


class StubGitHubClient:
    """An in-memory ``GitHubAPIClient`` serving the fixed corpus.

    Routing is by exact URL (and ``(owner, repo)`` for GraphQL), the same
    URLs both arms build. ``get_repository_tree`` reuses the real client's
    own ``_standardize_tree_node`` so the legacy arm's structure records
    are produced by production code, not by a test copy of it.
    """

    offline = False

    def __init__(self) -> None:
        self.pages: dict[str, list[dict[str, Any]]] = {
            f"{_API}/orgs/{ORG}/repos": REPO_RECORDS,
            f"{_API}/orgs/{ORG}/members": ORG_MEMBERS,
        }
        self.single: dict[str, dict[str, Any] | list[dict[str, Any]]] = {}
        for record in REPO_RECORDS:
            name = record["name"]
            self.single[f"{_API}/repos/{record['full_name']}"] = record
            self.pages[f"{_API}/repos/{record['full_name']}/contributors"] = (
                CONTRIBUTORS_BY_REPO.get(name, [])
            )
            self.pages[f"{_API}/repos/{record['full_name']}/issues?state=all"] = (
                ISSUES_BY_REPO.get(name, [])
            )
            self.pages[f"{_API}/repos/{record['full_name']}/issues/events"] = (
                EVENTS_BY_REPO.get(name, [])
            )
        for (name, branch), payload in BRANCHES.items():
            self.single[f"{_API}/repos/{ORG}/{name}/branches/{branch}"] = payload
        for tree in TREES.values():
            sha = tree["sha"]
            self.single[f"{_API}/repos/{ORG}/repo1/git/trees/{sha}?recursive=1"] = tree
        self.single[f"{_API}/repos/{ORG}/2026.1-App.Two/git/trees/sha-head-2?recursive=1"] = (
            TREES["sha-head-2"]
        )
        for login, profile in PROFILES.items():
            self.single[f"{_API}/users/{login}"] = profile

    def get_paginated(
        self, url: str, use_cache: bool = True, per_page: int = 100, max_pages=None
    ) -> list[dict[str, Any]]:
        return self.pages.get(url, [])

    def get_with_cache(
        self, url: str, use_cache: bool = True, return_headers: bool = False, silent=False
    ):
        payload = self.single.get(url)
        if return_headers:
            return payload, {"X-RateLimit-Remaining": "5000"}
        return payload

    def graphql_commit_history(
        self,
        owner: str,
        repo: str,
        page_size: int = 50,
        max_pages=None,
        max_commits=None,
        since: str | None = None,
        until: str | None = None,
        use_cache: bool = True,
        branches=None,
        split_large_extractions: bool = True,
        time_chunks: int = 3,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return (list(COMMIT_NODES_BY_REPO.get(repo, [])), {})

    def get_active_unmerged_branches(
        self, owner: str, repo: str, days: int = 30, use_cache: bool = True
    ) -> list[str]:
        return []

    def get_repository_tree(
        self, owner: str, repo: str, branch: str = "main", use_cache: bool = True
    ) -> dict[str, Any]:
        branch_data = BRANCHES[(repo, branch)]
        tree_sha = branch_data["commit"]["sha"]
        tree_data = TREES[tree_sha]
        standardized = [
            node
            for node in (
                # The real standardizer, unbound: it reads only the item.
                GitHubAPIClient._standardize_tree_node(None, item)
                for item in tree_data["tree"]
            )
            if node is not None
        ]
        return {
            "owner": owner,
            "repository": repo,
            "branch": branch,
            "sha": tree_sha,
            "tree": standardized,
            "truncated": False,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "method": "rest",
            "total_items": len(standardized),
        }


def _run_legacy_arm(client: StubGitHubClient, workdir: Path) -> None:
    config = OrganizationConfig(ORG)
    extract_repositories(client, config)
    extract_issues(client, config)
    extract_commits(client, config, method="graphql")
    extract_members(client, config)
    extract_repository_structure(client, config)


def _run_service_arm(
    client: StubGitHubClient, root: Path, storage: Any = None
) -> None:
    tenant = resolve_tenant("single", ORG)
    service = BronzeService(
        GitHubSourceAdapter(client, tenant),
        storage if storage is not None else FileStorageAdapter(root),
        tenant.id,
    )
    service.extract_repositories()
    service.extract_issues()
    service.extract_commits()
    service.extract_structures()


def _bronze_files(directory: Path) -> dict[str, Path]:
    return {path.name: path for path in sorted(directory.glob("*.json"))}


#: Families the source port cannot express, so the service does not write
#: them (module docstring). Anything else missing from the service arm is
#: a failure, not a finding.
PORT_GAP_FILES = {
    "members_basic.json",
    "members_detailed.json",
    "issue_events_repo1.json",
    "issue_events_2026.1-App.Two.json",
}

#: The service-owned families this corpus exercises. Pinned: a smaller set
#: would quietly shrink what the differential measures.
EXPECTED_COMPARED = {
    "repositories_raw.json",
    "repositories_filtered.json",
    "repositories_detailed.json",
    "repo_repo1.json",
    "repo_2026.1-App.Two.json",
    "commits_repo1.json",
    "commits_2026.1-App.Two.json",
    "issues_repo1.json",
    "issues_2026.1-App.Two.json",
    "prs_repo1.json",
    "structure_repo1.json",
    "structure_2026.1-App.Two.json",
}

#: Families the service writes and this differential compares, but which
#: **cannot** match: the listing payload carries 99 keys and ``Repository`` reads
#: 17, so the projection drops 82 (#241). Named, not skipped — the comparison
#: still runs over them and the strict xfail below pins the result, so the day
#: #241 lands this file fails loudly instead of quietly starting to pass.
#:
#: Measured, not assumed: making ``REPO_RECORDS`` carry the real 99-key shape
#: turned **five** families red, not the two ``repo_*`` files alone — the three
#: ``repositories_*`` aggregates are built from the same listing records.
PARITY_GAP_FILES = {
    "repositories_raw.json",
    "repositories_filtered.json",
    "repositories_detailed.json",
    "repo_repo1.json",
    "repo_2026.1-App.Two.json",
}

#: The payload keys ``map_repository`` reads. A fixture carrying only these makes
#: every repository arm of this differential unable to fail; asserted against in
#: ``test_listing_fixture_carries_more_than_the_model_reads``.
MODEL_PAYLOAD_KEYS = frozenset({
    "id", "name", "full_name", "private", "fork", "archived", "description",
    "default_branch", "language", "html_url", "size", "stargazers_count",
    "forks_count", "open_issues_count", "created_at", "updated_at", "pushed_at",
})

#: One ``_metadata.extracted_at`` per envelope file (10) plus one record
#: ``extracted_at`` per structure document (2): the normalisation budget.
EXPECTED_NORMALISATIONS_PER_ARM = 12


def _strip_generation_timestamps(payload: Any, name: str, removed: list[str]) -> Any:
    """Remove exactly the two generation-time timestamps, accounting each."""
    if (
        isinstance(payload, list)
        and payload
        and isinstance(payload[0], dict)
        and "_metadata" in payload[0]
    ):
        removed.append(f"{name}: _metadata.extracted_at")
        payload[0]["_metadata"].pop("extracted_at", None)
    elif isinstance(payload, dict):
        if isinstance(payload.get("_metadata"), dict):
            removed.append(f"{name}: _metadata.extracted_at")
            payload["_metadata"].pop("extracted_at", None)
        if "extracted_at" in payload:
            removed.append(f"{name}: extracted_at")
            payload.pop("extracted_at")
    return payload


def _diff_json(path: str, old: Any, new: Any, diffs: list[str]) -> None:
    """Deep comparison that names the JSON path of every difference."""
    if isinstance(old, dict) and isinstance(new, dict):
        if list(old.keys()) != list(new.keys()):
            diffs.append(
                f"{path}: key order/set differs: "
                f"{list(old.keys())} != {list(new.keys())}"
            )
        for key in old.keys() | new.keys():
            if key not in new:
                diffs.append(f"{path}.{key}: legacy only ({old[key]!r})")
            elif key not in old:
                diffs.append(f"{path}.{key}: service only ({new[key]!r})")
            else:
                _diff_json(f"{path}.{key}", old[key], new[key], diffs)
        return
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            diffs.append(f"{path}: length {len(old)} != {len(new)}")
        # strict=False on purpose: a length mismatch is already reported
        # above, and the diff should still name the shared-prefix fields.
        for index, (old_item, new_item) in enumerate(zip(old, new, strict=False)):
            _diff_json(f"{path}[{index}]", old_item, new_item, diffs)
        return
    if old != new:
        diffs.append(f"{path}: {old!r} != {new!r}")


#: Masks timestamp values in the raw text so the two files can be compared
#: literally — the byte-level half of the comparison.
_TIMESTAMP_TEXT = re.compile(r'("extracted_at": ")[^"]*(")')


def _compare_trees(old_root: Path, new_root: Path) -> tuple[list[str], list[str]]:
    """Diff the two Bronze trees; return (differences, normalisations)."""
    old_files = _bronze_files(old_root)
    new_files = _bronze_files(new_root)
    shared = sorted(set(old_files) & set(new_files))
    old_only = set(old_files) - set(new_files)
    new_only = set(new_files) - set(old_files)

    diffs: list[str] = []
    normalisations: list[str] = []

    if new_only:
        diffs.append(f"files only in the service arm: {sorted(new_only)}")
    unexpected_missing = old_only - PORT_GAP_FILES
    if unexpected_missing:
        diffs.append(f"files only in the legacy arm: {sorted(unexpected_missing)}")

    for name in shared:
        old_payload = json.loads(old_files[name].read_text(encoding="utf-8"))
        new_payload = json.loads(new_files[name].read_text(encoding="utf-8"))
        old_payload = _strip_generation_timestamps(old_payload, name, normalisations)
        new_payload = _strip_generation_timestamps(new_payload, name, normalisations)
        _diff_json(name, old_payload, new_payload, diffs)

        # Byte-level: same text once the timestamp values are masked.
        old_text = _TIMESTAMP_TEXT.sub(r"\1<TS>\2", old_files[name].read_text(encoding="utf-8"))
        new_text = _TIMESTAMP_TEXT.sub(r"\1<TS>\2", new_files[name].read_text(encoding="utf-8"))
        if old_text != new_text:
            diffs.append(f"{name}: bytes differ beyond the timestamp values")

    diffs.append(f"compared {len(shared)} shared files: {shared}")
    return diffs, normalisations


class _FieldDroppingStorage:
    """A StoragePort wrapper that plants one difference on the way down.

    The arms-differ control: it drops a single field (``total_changes``)
    from the first commit record of ``commits_repo1``, the kind of change
    a comparison must catch and name.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def save(self, tenant: Any, layer: Any, entity: str, data: Any) -> None:
        if entity == "commits_repo1" and isinstance(data, list) and len(data) > 1:
            planted = [dict(item) if isinstance(item, dict) else item for item in data]
            planted[1].pop("total_changes", None)
            data = planted
        self._inner.save(tenant, layer, entity, data)

    def load(self, tenant: Any, layer: Any, entity: str) -> Any:
        return self._inner.load(tenant, layer, entity)

    def list(self, tenant: Any, layer: Any) -> Any:
        return self._inner.list(tenant, layer)


def _run_both_arms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, storage: Any = None):
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    ported_root = tmp_path / "ported"

    with monkeypatch.context() as isolated:
        isolated.chdir(legacy_root)
        _run_legacy_arm(StubGitHubClient(), legacy_root)

    _run_service_arm(StubGitHubClient(), ported_root, storage=storage)

    old_bronze = legacy_root / "data" / "bronze"
    new_bronze = ported_root / ORG / "bronze"
    return _compare_trees(old_bronze, new_bronze)


def test_service_output_matches_legacy_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The differential: identical trees modulo the accounted timestamps."""
    diffs, normalisations = _run_both_arms(tmp_path, monkeypatch)

    compared = [line for line in diffs if line.startswith("compared ")]
    failures = [line for line in diffs if not line.startswith("compared ")]

    assert len(compared) == 1

    # The parity gaps are compared, reported, and excluded from *this* assertion
    # only — pinned by ``test_repository_families_would_be_byte_identical``.
    gaps = [line for line in failures if any(name in line for name in PARITY_GAP_FILES)]
    unexplained = [line for line in failures if line not in gaps]
    assert unexplained == [], "differences:\n" + "\n".join(unexplained)

    count = int(compared[0].split()[1])
    assert count == len(EXPECTED_COMPARED), (
        f"compared {count} files, expected {len(EXPECTED_COMPARED)}: "
        "the corpus or the writers changed shape"
    )
    assert count > 0, "a comparison over zero files passes vacuously"

    # The normalisation budget: exactly the two generation-time fields, in
    # exactly the expected files. A third exemption fails here, loudly.
    assert len(normalisations) == 2 * EXPECTED_NORMALISATIONS_PER_ARM, (
        f"normalised {len(normalisations)} timestamps, expected "
        f"{2 * EXPECTED_NORMALISATIONS_PER_ARM} (both arms): {normalisations}"
    )


def test_arms_differ_control_fails_and_names_the_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: a comparison that says "identical" must be able to see.

    One field dropped from one record in the service arm must fail the
    comparison *and* be named — file and field — or the green run above
    measures nothing.
    """
    storage = _FieldDroppingStorage(FileStorageAdapter(tmp_path / "ported"))
    diffs, _ = _run_both_arms(tmp_path, monkeypatch, storage=storage)

    failures = [line for line in diffs if not line.startswith("compared ")]
    assert failures, "the planted difference was not caught"
    named = [line for line in failures if "total_changes" in line]
    assert named, f"the difference was seen but not named: {failures}"
    assert any("commits_repo1.json" in line for line in named), named


@pytest.mark.xfail(
    strict=True,
    reason=(
        "#241: Repository is a 17-field projection of a 99-key payload, so the "
        "five repository families cannot be byte-identical. Flips to an "
        "unexpected pass the day the gap closes — at which point remove this "
        "test and PARITY_GAP_FILES."
    ),
)
def test_repository_families_would_be_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pin: what the differential would assert if #241 were fixed.

    Kept separate from the main differential so that the other seven compared
    families still gate on real byte-identity while this one records the gap.
    """
    diffs, _ = _run_both_arms(tmp_path, monkeypatch)
    gaps = [
        line
        for line in diffs
        if not line.startswith("compared ")
        and any(name in line for name in PARITY_GAP_FILES)
    ]
    assert gaps == [], "repository parity gaps:\n" + "\n".join(gaps)


def test_listing_fixture_carries_more_than_the_model_reads() -> None:
    """A fixture shaped by the model cannot detect what the model drops.

    This is the guard that stops the next family being born vacuous: if someone
    trims ``REPO_RECORDS`` back to the keys ``map_repository`` reads, the
    repository arms silently become unable to fail, which is exactly the state
    #241 was hiding in. Assert the shape, not the count alone.
    """
    assert REPO_RECORDS, "no listing records: every repository arm would be vacuous"
    for record in REPO_RECORDS:
        keys = set(record)
        assert keys >= MODEL_PAYLOAD_KEYS, (
            f"{record['name']}: fixture is missing keys the mapper reads: "
            f"{sorted(MODEL_PAYLOAD_KEYS - keys)}"
        )
        assert keys != MODEL_PAYLOAD_KEYS, (
            f"{record['name']}: fixture carries exactly the model's key set, so "
            "the repository arms of the differential cannot fail (#241)"
        )
        payload_only = keys - MODEL_PAYLOAD_KEYS
        assert len(payload_only) == 82, (
            f"{record['name']}: expected the 82 payload-only keys a real "
            f"repo_*.json carries, found {len(payload_only)}"
        )
        assert len(keys) == 99, f"{record['name']}: expected 99 keys, found {len(keys)}"
