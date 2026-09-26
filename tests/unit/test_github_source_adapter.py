"""Unit tests for ``coops.github.adapter`` — the GitHub `SourcePort` (issue #29).

The adapter is glue over three existing things, so the tests stub the
one seam it composes — :class:`coops.utils.github_api.GitHubAPIClient`
— and assert the other two directly: every read calls the client at the
same URLs the Bronze extractors use, and every payload crosses
:mod:`coops.github.mapper` before it reaches the caller (proven by the
domain types and the mapper-only transforms: stringified ids, resolved
actors, the blob/tree vocabulary).

Every fixture is shaped like the provider's real response — the field
names and nesting the mapper reads, taken from the queries in
``coops.utils.github_api`` — and every value is invented, as in
``test_github_mapper.py``: synthetic logins, semester 2099, addresses
on the reserved example domains.

No network: the stub implements only the four client methods the
adapter calls, records every call, and answers from a URL-keyed dict.
"""

from __future__ import annotations

from typing import Any

import pytest

from coops.domain import (
    PROVIDER_GITHUB,
    Commit,
    FileTree,
    Issue,
    Member,
    ProviderAccount,
    PullRequest,
    Repository,
    Tenant,
    TenantId,
)
from coops.domain.ports import (
    SourceNotFoundError,
    SourcePort,
    SourceUnavailableError,
)
from coops.github import GitHubSourceAdapter

TENANT_ID = TenantId("org-a")
ACCOUNT = ProviderAccount(PROVIDER_GITHUB, "org-a")
TENANT = Tenant(id=TENANT_ID, accounts=(ACCOUNT,))
OTHER_TENANT = TenantId("org-b")

API = "https://api.github.com"
ORG_REPOS = f"{API}/orgs/org-a/repos"
ORG_MEMBERS = f"{API}/orgs/org-a/members"
REPO_NAME = "2099.1-Demo.App"
FULL_NAME = f"org-a/{REPO_NAME}"
REPO_DETAIL = f"{API}/repos/org-a/{REPO_NAME}"
ISSUES_URL = f"{API}/repos/{FULL_NAME}/issues?state=all"
CONTRIBUTORS_URL = f"{API}/repos/{FULL_NAME}/contributors"

MAIN_SHA = "c" * 40
BRANCH_MAIN = f"{API}/repos/org-a/{REPO_NAME}/branches/main"
BRANCH_RELEASE = f"{API}/repos/org-a/{REPO_NAME}/branches/release/2026.1"
TREE_MAIN = f"{API}/repos/org-a/{REPO_NAME}/git/trees/{MAIN_SHA}?recursive=1"
RELEASE_SHA = "d" * 40
TREE_RELEASE = f"{API}/repos/org-a/{REPO_NAME}/git/trees/{RELEASE_SHA}?recursive=1"

LOGIN = "rosa-almeida"
USER_ID = 1001
ADDRESS = "rosa.almeida@example.com"


class StubGitHubClient:
    """A ``GitHubAPIClient`` stand-in: URL-keyed answers, no network.

    Implements only the four methods the adapter calls, accepts the
    exact keyword arguments the adapter passes, and records every call
    so the tests can assert what the adapter asked the provider for —
    which URL, which owner/repo, which page size.
    """

    def __init__(self) -> None:
        self.by_url: dict[str, Any] = {}
        self.commit_history: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
        self.graphql_responses: list[Any] = []
        self.urls_called: list[str] = []
        self.history_called: list[dict[str, Any]] = []
        self.graphql_called: list[dict[str, Any]] = []
        #: outage injection: raised from every ``get_with_cache`` call,
        #: simulating a provider library exception escaping the client.
        self.get_with_cache_error: Exception | None = None

    def get_with_cache(self, url: str, *args: Any, **kwargs: Any) -> Any:
        self.urls_called.append(url)
        if self.get_with_cache_error is not None:
            raise self.get_with_cache_error
        return self.by_url.get(url)

    def get_paginated(self, base_url: str, *args: Any, **kwargs: Any) -> list[Any]:
        self.urls_called.append(base_url)
        return list(self.by_url.get(base_url) or [])

    def graphql(
        self, query: str, variables: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        self.graphql_called.append({"query": query, "variables": variables or {}})
        return self.graphql_responses.pop(0) if self.graphql_responses else None

    def graphql_commit_history(
        self, owner: str, repo: str, page_size: int, **kwargs: Any
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.history_called.append(
            {"owner": owner, "repo": repo, "page_size": page_size}
        )
        return self.commit_history.pop(0) if self.commit_history else ([], {})


# --- fixture builders: provider shapes, invented values ---------------------


def repo_payload(**over: Any) -> dict[str, Any]:
    """One item of ``/orgs/{org}/repos``, with the fields the mapper reads."""
    payload = {
        "id": 901,
        "name": REPO_NAME,
        "full_name": FULL_NAME,
        "private": False,
        "fork": False,
        "archived": False,
        "description": "demo api",
        "default_branch": "main",
        "language": "Python",
        "html_url": f"https://github.com/{FULL_NAME}",
        "size": 120,
        "stargazers_count": 3,
        "forks_count": 1,
        "open_issues_count": 2,
        "created_at": "2026-01-10T08:00:00Z",
        "updated_at": "2026-02-01T08:00:00Z",
        "pushed_at": "2026-02-02T08:00:00Z",
    }
    payload.update(over)
    return payload


def org_member(login: str, user_id: int) -> dict[str, Any]:
    """One item of ``/orgs/{org}/members``: a login and an id, no name."""
    return {"login": login, "id": user_id, "type": "User"}


def contributor(login: str, user_id: int, total: int) -> dict[str, Any]:
    """One item of ``/repos/{full}/contributors``: carries ``contributions``."""
    return {"login": login, "id": user_id, "type": "User", "contributions": total}


def commit_node(sha: str, **over: Any) -> dict[str, Any]:
    """One GraphQL ``history`` node, as ``graphql_commit_history`` requests it."""
    node = {
        "oid": sha,
        "message": "Refactor the capture loop",
        "messageHeadline": "Refactor the capture loop",
        "committedDate": "2026-03-04T10:00:00Z",
        "author": {
            "name": "Rosa Almeida",
            "email": ADDRESS,
            "user": {"login": LOGIN, "databaseId": USER_ID},
        },
        "committer": {
            "name": "Rosa Almeida",
            "email": ADDRESS,
            "date": "2026-03-04T10:00:00Z",
        },
        "additions": 12,
        "deletions": 4,
        "parents": {"nodes": [{"oid": "b" * 40}]},
    }
    node.update(over)
    return node


def issue_payload(number: int = 1, **over: Any) -> dict[str, Any]:
    """One item of the shared issues endpoint, without a PR object."""
    payload = {
        "id": 9000 + number,
        "number": number,
        "state": "open",
        "title": "Fix the parser",
        "user": {"login": LOGIN, "id": USER_ID},
        "assignee": None,
        "created_at": "2026-03-01T08:00:00Z",
        "updated_at": "2026-03-02T08:00:00Z",
        "closed_at": None,
    }
    payload.update(over)
    return payload


def pr_payload(number: int = 2, **over: Any) -> dict[str, Any]:
    """The same endpoint's PR shape: an issue payload plus the marker."""
    payload = issue_payload(
        number,
        state="closed",
        title="Rewrite the parser",
        closed_at="2026-03-02T09:00:00Z",
        pull_request={
            "url": f"{API}/repos/{FULL_NAME}/pulls/{number}",
            "merged_at": "2026-03-02T09:00:00Z",
        },
    )
    payload.update(over)
    return payload


def branch_payload(sha: str) -> dict[str, Any]:
    """One ``/repos/{full}/branches/{branch}`` response: name plus head."""
    return {"name": "main", "commit": {"sha": sha}}


def tree_payload(**over: Any) -> dict[str, Any]:
    """One REST Git Trees response (``?recursive=1``), not truncated."""
    payload = {
        "sha": "t" * 40,
        "truncated": False,
        "tree": [
            {
                "path": "README.md",
                "type": "blob",
                "mode": "100644",
                "sha": "b" * 40,
                "size": 42,
            }
        ],
    }
    payload.update(over)
    return payload


def graphql_blob(path: str, oid: str, size: int) -> dict[str, Any]:
    """One GraphQL tree entry for a blob: blob facts under ``object``."""
    return {
        "type": "blob",
        "mode": "100644",
        "path": path,
        "object": {"oid": oid, "byteSize": size, "isBinary": False},
    }


def graphql_level(*entries: dict[str, Any]) -> dict[str, Any]:
    """One ``graphql()`` response holding a level of the tree walk."""
    return {"data": {"repository": {"object": {"entries": list(entries)}}}}


def make_adapter(stub: StubGitHubClient) -> GitHubSourceAdapter:
    return GitHubSourceAdapter(stub, TENANT)


def drain(
    adapter: GitHubSourceAdapter,
    kind: str,
    tenant: TenantId = TENANT_ID,
    repo_name: str = REPO_NAME,
    branch: str | None = None,
) -> list[Any]:
    """Drain one fetch completely, so a lazy adapter's errors surface."""
    if kind == "commits":
        return list(adapter.fetch_commits(tenant, repo_name))
    if kind == "issues":
        return list(adapter.fetch_issues(tenant, repo_name))
    if kind == "pull_requests":
        return list(adapter.fetch_pull_requests(tenant, repo_name))
    if kind == "tree":
        return [adapter.fetch_tree(tenant, repo_name, branch)]
    raise ValueError(f"unknown kind {kind!r}")


REPO_KINDS = ("commits", "issues", "pull_requests", "tree")


# --- construction and conformance -------------------------------------------


def test_the_adapter_is_exported_from_the_provider_package():
    from coops.github.adapter import GitHubSourceAdapter as direct

    assert GitHubSourceAdapter is direct


def test_the_adapter_satisfies_the_port_protocol_at_runtime():
    # runtime_checkable checks method presence; the static half is the
    # TYPE_CHECKING anchor in adapter.py, proven by mutation.
    assert isinstance(make_adapter(StubGitHubClient()), SourcePort)


def test_two_github_accounts_for_one_tenant_are_refused():
    other = ProviderAccount(PROVIDER_GITHUB, "org-a-elsewhere")
    with pytest.raises(ValueError, match="exactly one GitHub account"):
        GitHubSourceAdapter(StubGitHubClient(), Tenant(id=TENANT_ID, accounts=(ACCOUNT, other)))


def test_a_tenant_without_a_github_account_is_refused():
    gitlab = ProviderAccount("gitlab", "org-a")
    with pytest.raises(ValueError, match="exactly one GitHub account"):
        GitHubSourceAdapter(StubGitHubClient(), Tenant(id=TENANT_ID, accounts=(gitlab,)))


# --- fetch_repositories ------------------------------------------------------


def test_fetch_repositories_calls_the_org_endpoint_and_maps_the_payloads():
    stub = StubGitHubClient()
    stub.by_url[ORG_REPOS] = [
        repo_payload(),
        repo_payload(
            id=902, name="2098.2-Demo_backend", full_name="org-a/2098.2-Demo_backend"
        ),
    ]
    adapter = make_adapter(stub)

    repositories = list(adapter.fetch_repositories(TENANT_ID))

    assert ORG_REPOS in stub.urls_called
    assert all(isinstance(repo, Repository) for repo in repositories)
    assert sorted(repo.name for repo in repositories) == [
        "2098.2-Demo_backend",
        REPO_NAME,
    ]
    first = repositories[0]
    assert first.tenant_id == TENANT_ID
    assert first.account == ACCOUNT
    # mapper-only transforms: the numeric id stringified, the flag bools.
    assert first.external_id == "901"
    assert first.full_name == FULL_NAME
    assert first.default_branch == "main"
    assert first.stargazers_count == 3
    assert first.is_fork is False


def test_fetch_repositories_yields_nothing_for_an_unserved_tenant():
    stub = StubGitHubClient()
    stub.by_url[ORG_REPOS] = [repo_payload()]
    adapter = make_adapter(stub)

    assert list(adapter.fetch_repositories(OTHER_TENANT)) == []
    assert stub.urls_called == []


# --- fetch_members -----------------------------------------------------------


def test_fetch_members_unions_org_members_with_contributors():
    stub = StubGitHubClient()
    stub.by_url[ORG_MEMBERS] = [
        org_member(LOGIN, USER_ID),
        org_member("teresa-lopes", 1003),
    ]
    stub.by_url[ORG_REPOS] = [repo_payload()]
    stub.by_url[CONTRIBUTORS_URL] = [
        contributor(LOGIN, USER_ID, 5),
        contributor("joao-silva", 2002, 17),
    ]
    adapter = make_adapter(stub)

    members = list(adapter.fetch_members(TENANT_ID))

    assert ORG_MEMBERS in stub.urls_called
    assert CONTRIBUTORS_URL in stub.urls_called
    assert all(isinstance(member, Member) for member in members)
    assert all(member.tenant_id == TENANT_ID for member in members)
    by_login = {member.login: member for member in members}
    # the org member who also contributed: flagged, contributions summed
    assert by_login[LOGIN].is_org_member is True
    assert by_login[LOGIN].contributions_total == 5
    # the contributor who is not an org member
    assert by_login["joao-silva"].is_org_member is False
    assert by_login["joao-silva"].contributions_total == 17
    assert by_login["joao-silva"].external_id == "2002"
    # the org member who never contributed: zero, not absent
    assert by_login["teresa-lopes"].is_org_member is True
    assert by_login["teresa-lopes"].contributions_total == 0


def test_fetch_members_sums_contributions_across_repositories():
    stub = StubGitHubClient()
    second = "2099.1-Demo.Web"
    stub.by_url[ORG_MEMBERS] = []
    stub.by_url[ORG_REPOS] = [
        repo_payload(),
        repo_payload(id=902, name=second, full_name=f"org-a/{second}"),
    ]
    stub.by_url[CONTRIBUTORS_URL] = [contributor(LOGIN, USER_ID, 5)]
    stub.by_url[f"{API}/repos/org-a/{second}/contributors"] = [
        contributor(LOGIN, USER_ID, 9)
    ]
    adapter = make_adapter(stub)

    members = list(adapter.fetch_members(TENANT_ID))

    assert [member.contributions_total for member in members] == [14]
    assert members[0].is_org_member is False


def test_fetch_members_yields_nothing_for_an_unserved_tenant():
    stub = StubGitHubClient()
    stub.by_url[ORG_MEMBERS] = [org_member(LOGIN, USER_ID)]
    adapter = make_adapter(stub)

    assert list(adapter.fetch_members(OTHER_TENANT)) == []
    assert stub.urls_called == []


# --- fetch_commits -----------------------------------------------------------


def test_fetch_commits_calls_the_history_query_and_maps_the_nodes():
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.commit_history.append(
        (
            [commit_node("a" * 40), commit_node("e" * 40)],
            {"remaining": 4999},
        )
    )
    adapter = make_adapter(stub)

    commits = list(adapter.fetch_commits(TENANT_ID, REPO_NAME))

    assert stub.history_called == [
        {"owner": "org-a", "repo": REPO_NAME, "page_size": 50}
    ]
    assert all(isinstance(commit, Commit) for commit in commits)
    assert sorted(commit.sha for commit in commits) == ["a" * 40, "e" * 40]
    first = commits[0]
    assert first.tenant_id == TENANT_ID
    assert first.repo_name == REPO_NAME
    assert first.external_id == first.sha == "a" * 40
    assert first.parents == ("b" * 40,)
    assert first.additions == 12
    # the mapper ran: the author resolved through the account link
    assert first.author is not None
    assert first.author.login == LOGIN
    assert first.author.account_id == USER_ID


def test_fetch_commits_is_lazy_until_consumed():
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.commit_history.append(([commit_node("a" * 40)], {}))
    adapter = make_adapter(stub)

    adapter.fetch_commits(TENANT_ID, REPO_NAME)

    # the port permits laziness; an unconsumed iterator must cost nothing
    assert stub.urls_called == []
    assert stub.history_called == []


# --- fetch_issues / fetch_pull_requests --------------------------------------


def shared_endpoint_stub() -> StubGitHubClient:
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.by_url[ISSUES_URL] = [issue_payload(1), pr_payload(2)]
    return stub


def test_fetch_issues_calls_the_shared_endpoint_and_yields_only_issues():
    stub = shared_endpoint_stub()
    adapter = make_adapter(stub)

    issues = list(adapter.fetch_issues(TENANT_ID, REPO_NAME))

    assert ISSUES_URL in stub.urls_called
    assert [issue.number for issue in issues] == [1]
    assert all(isinstance(issue, Issue) for issue in issues)
    assert not any(isinstance(issue, PullRequest) for issue in issues)
    first = issues[0]
    assert first.repo_name == REPO_NAME
    assert first.external_id == "9001"  # the provider id, stringified
    assert first.state == "open"
    assert first.author is not None and first.author.login == LOGIN


def test_fetch_pull_requests_yields_only_the_pr_payloads():
    stub = shared_endpoint_stub()
    adapter = make_adapter(stub)

    pull_requests = list(adapter.fetch_pull_requests(TENANT_ID, REPO_NAME))

    assert ISSUES_URL in stub.urls_called
    assert [pr.number for pr in pull_requests] == [2]
    assert all(isinstance(pr, PullRequest) for pr in pull_requests)
    first = pull_requests[0]
    assert first.title == "Rewrite the parser"
    assert first.state == "closed"
    # PR-only facts crossed the port through the mapper
    assert first.merged_at == "2026-03-02T09:00:00Z"
    assert first.draft is False


def test_pull_request_facts_cross_the_port():
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.by_url[ISSUES_URL] = [
        pr_payload(2),  # merged, not a draft
        pr_payload(4, draft=True, pull_request={"url": "x"}),  # an open draft
    ]
    adapter = make_adapter(stub)

    pull_requests = list(adapter.fetch_pull_requests(TENANT_ID, REPO_NAME))

    assert [pr.merged_at for pr in pull_requests] == [
        "2026-03-02T09:00:00Z",
        None,
    ]
    assert [pr.draft for pr in pull_requests] == [False, True]


# --- fetch_tree ---------------------------------------------------------------


def stubbed_tree(stub: StubGitHubClient) -> None:
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.by_url[BRANCH_MAIN] = branch_payload(MAIN_SHA)
    stub.by_url[TREE_MAIN] = tree_payload()


def test_fetch_tree_none_branch_selects_the_default_branch():
    stub = StubGitHubClient()
    stubbed_tree(stub)
    adapter = make_adapter(stub)

    tree = adapter.fetch_tree(TENANT_ID, REPO_NAME)

    assert isinstance(tree, FileTree)
    assert BRANCH_MAIN in stub.urls_called
    assert TREE_MAIN in stub.urls_called
    assert tree.tenant_id == TENANT_ID
    assert tree.repo_name == REPO_NAME
    assert tree.branch == "main"
    assert tree.sha == "t" * 40
    assert tree.external_id == "t" * 40
    # the mapper ran: git's own vocabulary, blob facts kept
    assert [entry.path for entry in tree.entries] == ["README.md"]
    assert tree.entries[0].kind == "blob"
    assert tree.entries[0].sha == "b" * 40
    assert tree.entries[0].size == 42


def test_fetch_tree_returns_the_named_branch():
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.by_url[BRANCH_RELEASE] = {"name": "release/2026.1", "commit": {"sha": RELEASE_SHA}}
    stub.by_url[TREE_RELEASE] = tree_payload(
        tree=[{"path": "CHANGELOG.md", "type": "blob", "mode": "100644", "sha": "e" * 40, "size": 7}]
    )
    adapter = make_adapter(stub)

    tree = adapter.fetch_tree(TENANT_ID, REPO_NAME, "release/2026.1")

    assert BRANCH_RELEASE in stub.urls_called
    assert tree.branch == "release/2026.1"
    assert [entry.path for entry in tree.entries] == ["CHANGELOG.md"]


def test_a_truncated_rest_tree_is_finished_by_the_graphql_walk():
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.by_url[BRANCH_MAIN] = branch_payload(MAIN_SHA)
    stub.by_url[TREE_MAIN] = tree_payload(truncated=True)
    stub.graphql_responses = [
        graphql_level(
            {"type": "tree", "mode": "040000", "path": "src", "object": {}},
            graphql_blob("README.md", "b" * 40, 42),
        ),
        graphql_level(graphql_blob("src/main.py", "e" * 40, 100)),
    ]
    adapter = make_adapter(stub)

    tree = adapter.fetch_tree(TENANT_ID, REPO_NAME)

    expressions = [call["variables"]["expression"] for call in stub.graphql_called]
    assert expressions == ["main:", "main:src"]
    # both levels present: the walk composed them, never skipped one
    assert sorted(entry.path for entry in tree.entries) == [
        "README.md",
        "src",
        "src/main.py",
    ]
    by_path = {entry.path: entry for entry in tree.entries}
    assert by_path["README.md"].kind == "blob"
    assert by_path["README.md"].sha == "b" * 40
    assert by_path["README.md"].size == 42
    assert by_path["README.md"].is_binary is False
    assert by_path["src"].kind == "tree"
    assert tree.branch == "main"


# --- the port's error and address contract ------------------------------------


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_unknown_repository_raises_source_not_found(kind):
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = None
    adapter = make_adapter(stub)

    with pytest.raises(SourceNotFoundError):
        drain(adapter, kind)


@pytest.mark.parametrize("kind", REPO_KINDS)
def test_repository_reads_for_an_unserved_tenant_are_not_found(kind):
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    adapter = make_adapter(stub)

    with pytest.raises(SourceNotFoundError):
        drain(adapter, kind, tenant=OTHER_TENANT)
    # and nothing was asked of the provider on that tenant's behalf
    assert stub.urls_called == []


def test_blank_repository_name_is_a_caller_bug():
    adapter = make_adapter(StubGitHubClient())
    with pytest.raises(ValueError, match="non-empty"):
        list(adapter.fetch_commits(TENANT_ID, "   "))


def test_the_owner_slash_repo_form_is_a_caller_bug():
    adapter = make_adapter(StubGitHubClient())
    with pytest.raises(ValueError, match="path separator"):
        adapter.fetch_tree(TENANT_ID, FULL_NAME)


def test_blank_branch_is_a_caller_bug():
    stub = StubGitHubClient()
    stubbed_tree(stub)
    adapter = make_adapter(stub)

    with pytest.raises(ValueError, match="non-empty"):
        adapter.fetch_tree(TENANT_ID, REPO_NAME, "   ")
    assert stub.urls_called == []


def test_unknown_branch_raises_source_not_found():
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.by_url[BRANCH_MAIN] = None
    adapter = make_adapter(stub)

    with pytest.raises(SourceNotFoundError):
        adapter.fetch_tree(TENANT_ID, REPO_NAME, "no-such-branch")


def test_a_provider_library_error_surfaces_as_the_ports_unavailable_error():
    stub = StubGitHubClient()
    stub.by_url[REPO_DETAIL] = repo_payload()
    stub.get_with_cache_error = RuntimeError(
        "connection reset — a provider library error"
    )
    stub.commit_history.append(([commit_node("a" * 40)], {}))
    adapter = make_adapter(stub)

    with pytest.raises(SourceUnavailableError) as excinfo:
        list(adapter.fetch_commits(TENANT_ID, REPO_NAME))
    # the provider library's own exception must not cross the port
    assert not isinstance(excinfo.value, RuntimeError)
