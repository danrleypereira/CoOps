"""The wired Bronze path, end to end (#30).

This file was the byte-parity differential: a legacy arm and a
``BronzeService`` arm over one fixed corpus, compared file for file and
byte for byte. #30 was redefined — *wire the service in, accept that the
output changes, record what changed: a diff report, not a gate* — and the
legacy arm's extractors were removed with the wiring, so the differential
retired with the acceptance it measured. What this file pins now is what
remains load-bearing about the live path:

* ``coops.etl.bronze_extract.run_extraction`` — the composition ``main()``
  calls — writes **every family the pipeline has always produced**:
  the service-owned families (repositories, issues, PRs, commits,
  structures) *and* the two the source port cannot express, members
  (#238) and issue events (#239), which stay on the legacy extractors the
  composition keeps. Six Silver/Gold modules read those files; a wiring
  that silently dropped them would starve them a layer away, as empty
  analytics rather than as an error here. So the tree assertion requires
  exactly the published set — nothing missing, nothing extra.
* the known port-gap shapes, by name: the commit record's ``committer.name``
  is ``None`` and its ``html_url`` is ``None`` (#240 — the model cannot
  carry the committer's name, and the history query requests no URL), and
  the repository record is the ``Repository`` model's seventeen-key
  projection (#241 — real payloads carry ~99 provider fields the model
  never sees; the strict xfail in
  ``tests/unit/test_repository_projection_gap.py`` pins that gap).
* the scrub, on the live path: the corpus's commit message carries a
  ``Co-authored-by:`` trailer with a real address, and one author's git
  ``user.name`` *is* an address (#132) — neither may reach ``data/bronze``
  through the service arm. The control asserts the probe finds the
  address in the corpus first (the arms-differ spirit of the old
  differential: a clean result must not be able to mean a dead probe).
* the envelopes still name the published location
  (``_metadata.file_path == "data/bronze/<entity>.json"``), because the
  composition stores through ``PublishedLayoutStorage`` — the flat
  ``data/bronze`` tree Silver and Gold glob — rather than the port's own
  tenant-scoped layout.

The corpus is unchanged from the differential era (same
``StubGitHubClient``, same records), so the shapes pinned here are the
ones the #30 wiring report was measured against.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from coops.bronze.watermarks import WatermarkStore
from coops.domain.tenancy import resolve_tenant
from coops.etl import bronze_extract
from coops.utils.github_api import GitHubAPIClient, OrganizationConfig

ORG = "test-org"
_API = "https://api.github.com"

# The repository listing, in listing order: two kept repositories, one
# fork and one blacklisted, so the filter runs. The key set is exactly
# what map_repository reads — see #241 and the module docstring.
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


#: The payload keys ``map_repository`` reads. A fixture carrying only these makes
#: every repository arm of this differential unable to fail; asserted against in
#: ``test_listing_fixture_carries_more_than_the_model_reads``.
MODEL_PAYLOAD_KEYS = frozenset({
    "id", "name", "full_name", "private", "fork", "archived", "description",
    "default_branch", "language", "html_url", "size", "stargazers_count",
    "forks_count", "open_issues_count", "created_at", "updated_at", "pushed_at",
})

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
    # No PRs here on purpose: the run must write no prs_<repo>.json
    # when there are none.
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
# query requests (no url, no committer — see #240 and the module
# docstring).
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
            # policy blanks (#132), which must be blanked on the wired
            # path too, not only by the legacy scrub.
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

# Members: the legacy path the composition keeps (#238).
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
    URLs the wired path builds — the adapter's branch probe and tree read,
    the legacy members/events pages. ``get_repository_tree`` is unused
    here (the adapter reads the branch and tree endpoints itself) but is
    kept serving the corpus, as the differential's arms did.
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


def _run_live_arm(workdir: Path) -> WatermarkStore:
    """Run the composition ``main()`` calls, inside ``workdir``.

    The legacy steps read and write relative ``data/bronze`` paths, so the
    working directory owns the run's tree; the service writes through
    ``PublishedLayoutStorage`` onto the same tree.
    """
    tenant = resolve_tenant("single", ORG)
    store = WatermarkStore(str(workdir / "watermarks.json"))
    bronze_extract.run_extraction(
        StubGitHubClient(),
        tenant,
        OrganizationConfig(ORG),
        watermarks=store,
    )
    return store


def _bronze_files(directory: Path) -> dict[str, Path]:
    return {path.name: path for path in sorted(directory.glob("*.json"))}


#: The service-owned families this corpus exercises.
SERVICE_FILES = {
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

#: The families the source port cannot express (#238, #239), produced on
#: the live run by the legacy extractors the composition keeps. Downstream
#: starvation is what this half exists to make impossible.
PORT_GAP_FILES = {
    "members_basic.json",
    "members_detailed.json",
    "issue_events_repo1.json",
    "issue_events_2026.1-App.Two.json",
}

#: Pinned: a smaller set would quietly shrink what the tree assertion
#: measures. Exactly this tree and nothing else may come out of the run.
EXPECTED_TREE = SERVICE_FILES | PORT_GAP_FILES

#: The repository record's key set: exactly the ``Repository`` model's
#: seventeen-key projection (#241). The corpus's listing records carry
#: exactly these keys, so this asserts the projection did not invent or
#: drop any of them; the ~82 provider fields a real payload carries beyond
#: them are the gap, pinned by the strict xfail in
#: ``tests/unit/test_repository_projection_gap.py``.
REPOSITORY_RECORD_KEYS = {
    "id", "name", "full_name", "private", "fork", "archived", "description",
    "default_branch", "language", "html_url", "size", "stargazers_count",
    "forks_count", "open_issues_count", "created_at", "updated_at",
    "pushed_at",
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _records(payload: Any) -> list[dict[str, Any]]:
    """A bronze list file's records, without the leading ``_metadata``."""
    assert isinstance(payload, list)
    return [r for r in payload[1:] if isinstance(r, dict)]


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """One wired run inside ``tmp_path``; returns its outputs for inspection."""
    workdir = tmp_path / "run"
    workdir.mkdir()
    with monkeypatch.context() as isolated:
        isolated.chdir(workdir)
        store = _run_live_arm(workdir)
    files = _bronze_files(workdir / "data" / "bronze")
    payloads = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in files.items()
    }
    return {"workdir": workdir, "files": files, "payloads": payloads, "store": store}


def test_the_wired_run_writes_exactly_the_published_tree(run) -> None:
    """Every family the pipeline has always produced, and nothing else.

    The port-gap half is the point: members and issue events are still
    written *by the same run*, on the legacy path — a wiring that dropped
    them would starve six Silver/Gold modules a layer away.
    """
    assert set(run["files"]) == EXPECTED_TREE, (
        f"missing: {sorted(EXPECTED_TREE - set(run['files']))}; "
        f"unexpected: {sorted(set(run['files']) - EXPECTED_TREE)}"
    )


def test_port_gap_families_carry_real_content(run) -> None:
    """The kept families are not empty husks: members carry the merged
    member/contributor population with profiles, events carry the
    projected Silver-facing records."""
    members_basic = _records(run["payloads"]["members_basic.json"])
    members_detailed = _records(run["payloads"]["members_detailed.json"])

    by_login = {member["login"]: member for member in members_basic}
    # org member + contributor, and the outside contributor: the union.
    assert set(by_login) == {"linked_user", "orgmate", "outsider"}
    assert by_login["linked_user"]["contributions_total"] == 7
    assert by_login["linked_user"]["is_org_member"] is True
    assert by_login["outsider"]["is_org_member"] is False

    detailed_by_login = {m["login"]: m for m in members_detailed}
    assert detailed_by_login["linked_user"]["profile_fetched"] is True
    assert detailed_by_login["linked_user"]["public_repos"] == 3

    events = _records(run["payloads"]["issue_events_repo1.json"])
    assert [event["id"] for event in events] == [501, 502]
    assert set(events[0]) == {
        "id", "event", "created_at", "repo_name", "actor", "issue",
    }

    # A repository with no events still writes its file — the family
    # exists for every repository, as the published corpus does.
    assert _records(run["payloads"]["issue_events_2026.1-App.Two.json"]) == []


def test_commit_scrub_runs_on_the_wired_path(run) -> None:
    """No address reaches data/bronze through the service arm (#111's
    binding, restated for the path that is now live).

    CONTROL: the probe must find the address in the corpus before the
    run, or a clean result afterwards would prove nothing — the
    arms-differ discipline the byte-parity differential enforced.
    """
    corpus = json.dumps(COMMIT_NODES_BY_REPO["repo1"])
    assert _EMAIL_RE.search(corpus), "the corpus no longer carries an address"

    commits = _records(run["payloads"]["commits_repo1.json"])
    serialized = json.dumps(commits)
    assert not _EMAIL_RE.search(serialized)
    # Credit survives: the trailer and the human names stay.
    assert "Co-authored-by: Pair Person" in serialized
    by_sha = {commit["sha"]: commit for commit in commits}
    # git user.name set to the address: blanked (#132), not published.
    assert by_sha["bbb2"]["commit"]["author"]["name"] is None
    # The email survives only as its hash — for the linked author too.
    assert by_sha["ccc3"]["commit"]["author"]["author_email_hash"]


def test_commit_gap_shapes_are_the_service_shapes(run) -> None:
    """#240, named: the committer's name and the html_url are ``None``.

    The legacy GraphQL path wrote a real committer name on records whose
    node carried one (and the live query requests it); the model cannot
    carry it across the port, so ``None`` is the wired path's shape. The
    day #240 lands a payload-carrying seam, this test changes
    deliberately — that is why it exists.
    """
    commits = _records(run["payloads"]["commits_repo1.json"])
    for commit in commits:
        assert commit["commit"]["committer"]["name"] is None
        assert commit["html_url"] is None
    # Everything else the legacy record carried is intact.
    assert commits[0]["parents"] == ["bbb2"]
    assert commits[0]["total_changes"] == 12


def test_repository_record_is_the_model_projection(run) -> None:
    """#241, named: the stored repository record is exactly the
    ``Repository`` model's seventeen keys — the provider payload does not
    survive the port."""
    listing = _records(run["payloads"]["repositories_filtered.json"])
    assert {record["name"] for record in listing} == {"repo1", "2026.1-App.Two"}
    for record in listing:
        assert set(record) == REPOSITORY_RECORD_KEYS

    document = run["payloads"]["repo_repo1.json"]
    assert set(document) - {"_metadata"} == REPOSITORY_RECORD_KEYS


def test_envelopes_name_the_published_location(run) -> None:
    """The service writes through the port, but the published contract —
    ``_metadata.file_path`` naming ``data/bronze/<entity>.json`` — is what
    the tree and its readers key on."""
    listing = run["payloads"]["repositories_filtered.json"]
    assert listing[0]["_metadata"]["file_path"] == (
        "data/bronze/repositories_filtered.json"
    )
    # The #216 listing provenance: an unbounded, online run asserts it.
    assert listing[0]["_metadata"]["complete"] is True
    assert listing[0]["_metadata"]["record_count"] == 2

    document = run["payloads"]["repo_repo1.json"]
    assert document["_metadata"]["file_path"] == "data/bronze/repo_repo1.json"


def test_structure_document_shape(run) -> None:
    """The structure family keeps its document shape: no ``_metadata``
    envelope, the standardised tree, and the repository metadata block
    Silver's language analysis reads."""
    structure = run["payloads"]["structure_repo1.json"]
    assert "_metadata" not in structure
    assert structure["method"] == "rest"
    assert structure["total_items"] == 3
    assert [entry["path"] for entry in structure["tree"]] == [
        "README.md", "src", "src/main.py",
    ]
    assert structure["repository_metadata"]["full_name"] == "test-org/repo1"
    assert structure["repository_metadata"]["stars"] == 3


def test_watermarks_recorded_across_both_paths(run) -> None:
    """The service records head shas; the kept events extractor records
    the event id; one store carries both (the composition threads it
    through the two halves of what was one step)."""
    store: WatermarkStore = run["store"]

    wm = store.get("test-org/repo1")
    assert wm.head_shas == {"main": "sha-head-1"}
    assert wm.last_event_id == 502

    wm_two = store.get("test-org/2026.1-App.Two")
    assert wm_two.head_shas == {"master": "sha-head-2"}


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
