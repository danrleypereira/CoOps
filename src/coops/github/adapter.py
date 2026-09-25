"""The GitHub adapter for the source port (issue #29).

Glue, and only glue. This module composes three things that already
exist and owns none of them:

- :class:`coops.utils.github_api.GitHubAPIClient` — the transport:
  REST and GraphQL, caching, ETags, retries, pagination;
- :mod:`coops.github.mapper` — every rule that turns a GitHub payload
  into a domain model (nothing here reads a provider field the mapper
  does not);
- the domain's own :class:`~coops.domain.Tenant` — which tenant to
  serve, and which GitHub account to read it through.

:class:`~coops.domain.ports.SourcePort` fixes what may cross the
boundary; this file decides only *which existing client calls* answer
each port read. When the GitLab adapter arrives (#49) it writes its own
twin of this file and nothing above the port changes.

What the adapter does own, because the port assigns it to adapters:

- **The provider policies** the port leaves deliberately open. Commits
  are the default branch's history, fetched by
  ``graphql_commit_history`` — the union-with-dedup the port docstring
  names as this adapter's policy, REST fallback included. Issues and
  pull requests are read with ``state=all`` from the endpoint GitHub
  serves them both from, and split behind the port exactly as the
  Bronze extractor splits them today (a ``pull_request`` object on the
  payload). The tree is the REST recursive response, finished by the
  GraphQL level walk when GitHub truncates it — the fallback the port
  makes the adapter's problem. Repositories and members are yielded as
  the provider lists them: fork and blacklist filtering is extraction
  policy, which stays with the caller Bronze becomes (#26), not with
  the provider adapter.
- **The error vocabulary.** The client swallows provider faults and
  answers ``None``; a repository probe that comes back ``None`` is the
  port's `SourceNotFoundError` (the client collapses 404, 403 and
  exhaustion into ``None``, so "cannot read it" is the strongest honest
  claim the adapter can make). Any exception that does escape the
  client is translated to `SourceUnavailableError` before it can reach
  a caller — a provider library's own exception crossing this boundary
  would leak the provider exactly as an ``etag`` parameter would —
  except ``OfflineCacheMiss``, which passes through untranslated: an
  offline replay (#199) must stop the run, and surfacing it as a
  retryable condition would invite exactly the partial answer that
  error exists to prevent.

Tenant scoping is structural, as in the reference implementation in
``tests/unit/test_source_port.py``: one adapter instance serves exactly
one tenant through exactly one GitHub account, so a call naming any
other tenant has nothing to read. Organization-wide reads answer empty
and touch no provider; repository-addressed reads raise
`SourceNotFoundError`, the loud form of the same rule.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from coops.domain import (
    PROVIDER_GITHUB,
    Commit,
    FileEntry,
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
    SourceError,
    SourceNotFoundError,
    SourcePort,
    SourceUnavailableError,
    validate_branch,
    validate_repo_name,
)
from coops.github.mapper import (
    map_commit_graphql,
    map_file_tree_graphql,
    map_file_tree_rest,
    map_issue,
    map_member,
    map_pull_request,
    map_repository,
)
from coops.utils.github_api import GitHubAPIClient, OfflineCacheMiss

#: The REST root every extractor in :mod:`coops.bronze` builds URLs from.
_API_ROOT = "https://api.github.com"

#: Page size for every listing, the ``per_page=100`` the extractors use.
_LIST_PAGE_SIZE = 100

#: Commit-history page size: ``extract_commits``' own default
#: (``coops/bronze/commits.py``), kept so the adapter asks for pages the
#: same size the pipeline always has.
_COMMIT_PAGE_SIZE = 50

#: Safety bound on the GraphQL tree walk, the ``max_depth`` of the
#: client's own ``graphql_repository_tree``.
_MAX_TREE_LEVELS = 100

#: One level of the GraphQL tree walk: the same fields
#: ``graphql_repository_tree`` requests, so the ``entries`` arrays
#: arriving here are exactly the shape :func:`map_file_tree_graphql`
#: reads — ``path``/``type``/``mode`` on the entry, ``oid``/
#: ``byteSize``/``isBinary`` under ``object`` for blobs.
_TREE_LEVEL_QUERY = """
query($owner: String!, $name: String!, $expression: String!) {
  repository(owner: $owner, name: $name) {
    object(expression: $expression) {
      ... on Tree {
        entries {
          type
          mode
          path
          object {
            ... on Blob {
              byteSize
              isBinary
              oid
            }
          }
        }
      }
    }
  }
}
"""

_T = TypeVar("_T")


class GitHubSourceAdapter:
    """`SourcePort` answered by GitHub, for one tenant and one account.

    Constructed from a :class:`~coops.domain.Tenant` (the same object
    :func:`coops.domain.resolve_tenant` builds) so the tenant served and
    the account read through can never disagree; the account's
    normalised ``org_id`` is the organisation every URL addresses. The
    client arrives already configured — token, cache, raw layer — since
    those are transport concerns this adapter composes, not ones it
    re-decides. ``use_cache`` is threaded to every client call so a
    caller keeps the ``--no-cache`` ability the extractors have.
    """

    def __init__(
        self,
        client: GitHubAPIClient,
        tenant: Tenant,
        *,
        use_cache: bool = True,
    ) -> None:
        github_accounts = [
            account for account in tenant.accounts
            if account.provider == PROVIDER_GITHUB
        ]
        if len(github_accounts) != 1:
            raise ValueError(
                "GitHubSourceAdapter reads exactly one GitHub account:"
                " construct one adapter per (tenant, GitHub account) pair"
            )
        self._client = client
        self._tenant_id = tenant.id
        self._account = github_accounts[0]
        self._use_cache = use_cache

    # -- SourcePort ------------------------------------------------------

    def fetch_repositories(self, tenant: TenantId) -> Iterator[Repository]:
        """Yield the organisation's repositories as the provider lists them.

        Unfiltered: which repositories a *run* keeps (forks, the
        blacklist) is extraction policy that stays with the caller, not
        a property of the provider. Yields nothing, and touches no
        provider, for a tenant this adapter does not serve.
        """
        if self._account_for(tenant) is None:
            return iter(())
        return self._provider_stream(self._iter_repositories)

    def fetch_members(self, tenant: TenantId) -> Iterator[Member]:
        """Yield the member/contributor union the `Member` model describes.

        Assembled exactly as Bronze assembles it: the organisation
        member list, plus the contributors of every repository the org
        listing returns, one record per login with contributions summed
        across repositories and ``is_org_member`` marking the members
        endpoint's population.
        """
        if self._account_for(tenant) is None:
            return iter(())
        return self._provider_stream(self._iter_members)

    def fetch_commits(self, tenant: TenantId, repo_name: str) -> Iterator[Commit]:
        """Yield the repository's default-branch history.

        ``graphql_commit_history`` performs the provider policy the port
        docstring names for this method — the union-with-dedup, with its
        REST fallback — and its nodes are GraphQL-shaped whichever transport
        served them, so every record maps through
        :func:`map_commit_graphql`.
        """
        name = validate_repo_name(repo_name)
        self._require_tenant(tenant, name)
        return self._provider_stream(lambda: self._iter_commits(name))

    def fetch_issues(self, tenant: TenantId, repo_name: str) -> Iterator[Issue]:
        """Yield the repository's issues: the conversations that are not PRs."""
        name = validate_repo_name(repo_name)
        self._require_tenant(tenant, name)
        return self._provider_stream(lambda: self._iter_issues(name))

    def fetch_pull_requests(
        self, tenant: TenantId, repo_name: str
    ) -> Iterator[PullRequest]:
        """Yield the repository's pull requests, split behind the port.

        GitHub serves issues and PRs from one endpoint and marks the
        difference with a ``pull_request`` object; the split happens
        here, never in front of the port, so a PR can never arrive as
        an `Issue` or the reverse.
        """
        name = validate_repo_name(repo_name)
        self._require_tenant(tenant, name)
        return self._provider_stream(lambda: self._iter_pull_requests(name))

    def fetch_tree(
        self,
        tenant: TenantId,
        repo_name: str,
        branch: str | None = None,
    ) -> FileTree:
        """Return the repository's file tree on one branch, complete.

        ``branch=None`` selects the default branch the repository detail
        names. The REST recursive response is the primary read; a
        truncated one is finished by the GraphQL level walk, because a
        partial tree mapped as a whole one is silent data loss and
        :func:`map_file_tree_rest` refuses it for exactly that reason.
        """
        name = validate_repo_name(repo_name)
        selected = None if branch is None else validate_branch(branch)
        self._require_tenant(tenant, name)
        return self._provider_call(lambda: self._read_tree(name, selected))

    # -- tenant scope ----------------------------------------------------

    def _account_for(self, tenant: TenantId) -> ProviderAccount | None:
        """The account to read for ``tenant``, or ``None`` if not this one.

        One adapter serves one tenant, so a call naming another tenant
        has nothing to read — the same answer the reference
        implementation in ``tests/unit/test_source_port.py`` gives an
        unknown tenant. Slugs compare exactly (#92):
        ``TenantId("ORG-A")`` is a different tenant from
        ``TenantId("org-a")``.
        """
        return self._account if tenant == self._tenant_id else None

    def _require_tenant(self, tenant: TenantId, repo_name: str) -> None:
        if self._account_for(tenant) is None:
            raise SourceNotFoundError(
                f"no repository {repo_name!r} for this tenant"
            )

    # -- error translation -------------------------------------------------

    def _provider_call(self, read: Callable[[], _T]) -> _T:
        """Run one eager read inside the port's error vocabulary."""
        try:
            return read()
        except (SourceError, OfflineCacheMiss):
            raise
        except Exception as exc:
            raise SourceUnavailableError(
                "the GitHub client could not serve the read right now"
            ) from exc

    def _provider_stream(
        self, read: Callable[[], Iterator[_T]]
    ) -> Iterator[_T]:
        """Relay one lazy read, translating faults that surface mid-iteration.

        A generator, so provider conditions raise while the caller is
        consuming the iterator — within the port's contract — and still
        cross the boundary as `SourceError`, never as the transport's
        own exception. The port's own errors pass through untranslated:
        turning a `SourceNotFoundError` into "unavailable" would make a
        deleted repository look like a transient fault.
        """
        try:
            yield from read()
        except (SourceError, OfflineCacheMiss):
            raise
        except Exception as exc:
            raise SourceUnavailableError(
                "the GitHub client could not serve the read right now"
            ) from exc

    # -- the reads, each a composition of client calls and mapper calls ----

    def _iter_repositories(self) -> Iterator[Repository]:
        url = f"{_API_ROOT}/orgs/{self._account.org_id}/repos"
        raw_repos: list[Mapping[str, Any]] = self._client.get_paginated(
            url, use_cache=self._use_cache, per_page=_LIST_PAGE_SIZE
        )
        for raw in raw_repos:
            yield map_repository(raw, self._tenant_id, self._account)

    def _iter_members(self) -> Iterator[Member]:
        members_url = f"{_API_ROOT}/orgs/{self._account.org_id}/members"
        org_members: list[Mapping[str, Any]] = self._client.get_paginated(
            members_url, use_cache=self._use_cache, per_page=_LIST_PAGE_SIZE
        )
        org_logins: set[str] = set()
        payloads: dict[str, Mapping[str, Any]] = {}
        for raw in org_members:
            login = raw.get("login")
            if not login:
                continue
            org_logins.add(login)
            payloads.setdefault(login, dict(raw))
        # One record per login, contributions summed across the
        # repositories the org listing returns — the union the Member
        # model documents. Payloads are assembled, then mapped: the
        # mapping itself stays the mapper's.
        totals: dict[str, int] = {}
        for repository in self._iter_repositories():
            contributors_url = (
                f"{_API_ROOT}/repos/{repository.full_name}/contributors"
            )
            contributors: list[Mapping[str, Any]] = self._client.get_paginated(
                contributors_url, use_cache=self._use_cache, per_page=_LIST_PAGE_SIZE
            )
            for contributor in contributors:
                login = contributor.get("login")
                if not login:
                    continue
                totals[login] = (
                    totals.get(login, 0) + (contributor.get("contributions") or 0)
                )
                payloads.setdefault(
                    login, {"login": login, "id": contributor.get("id")}
                )
        for login in sorted(payloads):
            payload = dict(payloads[login])
            if login in totals:
                payload["contributions"] = totals[login]
            yield map_member(
                payload,
                self._tenant_id,
                self._account,
                is_org_member=login in org_logins,
            )

    def _require_repository(self, repo_name: str) -> Mapping[str, Any]:
        """The repository detail, or `SourceNotFoundError`.

        The client answers ``None`` for a repository it cannot read —
        deleted, renamed away, or unreadable with this token — and the
        port requires the loud form of that answer rather than an empty
        iterator. The detail is the same request Bronze makes for
        ``repositories_detailed.json``, so a cached run pays nothing.
        """
        url = f"{_API_ROOT}/repos/{self._account.org_id}/{repo_name}"
        detail: Mapping[str, Any] = self._client.get_with_cache(
            url, use_cache=self._use_cache
        )
        if not detail:
            raise SourceNotFoundError(
                f"no repository {repo_name!r} for this tenant"
            )
        return detail

    def _iter_commits(self, repo_name: str) -> Iterator[Commit]:
        self._require_repository(repo_name)
        nodes, _rate_meta = self._client.graphql_commit_history(
            owner=self._account.org_id,
            repo=repo_name,
            page_size=_COMMIT_PAGE_SIZE,
            use_cache=self._use_cache,
        )
        for node in nodes:
            yield map_commit_graphql(
                node, self._tenant_id, self._account, repo_name
            )

    def _iter_issue_payloads(self, repo_name: str) -> Iterator[Mapping[str, Any]]:
        """Page the endpoint GitHub serves issues and PRs from, unmapped."""
        detail = self._require_repository(repo_name)
        full_name = detail.get("full_name") or (
            f"{self._account.org_id}/{repo_name}"
        )
        url = f"{_API_ROOT}/repos/{full_name}/issues?state=all"
        payloads: list[Mapping[str, Any]] = self._client.get_paginated(
            url, use_cache=self._use_cache, per_page=_LIST_PAGE_SIZE
        )
        yield from payloads

    def _iter_issues(self, repo_name: str) -> Iterator[Issue]:
        for raw in self._iter_issue_payloads(repo_name):
            if raw.get("pull_request"):
                continue
            yield map_issue(raw, self._tenant_id, self._account, repo_name)

    def _iter_pull_requests(self, repo_name: str) -> Iterator[PullRequest]:
        for raw in self._iter_issue_payloads(repo_name):
            if not raw.get("pull_request"):
                continue
            yield map_pull_request(
                raw, self._tenant_id, self._account, repo_name
            )

    def _read_tree(self, repo_name: str, branch: str | None) -> FileTree:
        detail = self._require_repository(repo_name)
        selected: str = (
            branch
            if branch is not None
            else (detail.get("default_branch") or "main")
        )
        branch_url = (
            f"{_API_ROOT}/repos/{self._account.org_id}/{repo_name}"
            f"/branches/{selected}"
        )
        branch_data: Mapping[str, Any] = self._client.get_with_cache(
            branch_url, use_cache=self._use_cache
        )
        if not branch_data:
            raise SourceNotFoundError(
                f"no branch {selected!r} on repository {repo_name!r}"
            )
        tree_sha = branch_data["commit"]["sha"]
        tree_url = (
            f"{_API_ROOT}/repos/{self._account.org_id}/{repo_name}"
            f"/git/trees/{tree_sha}?recursive=1"
        )
        tree_data: Mapping[str, Any] = self._client.get_with_cache(
            tree_url, use_cache=self._use_cache
        )
        if not tree_data:
            raise SourceUnavailableError(
                "the GitHub client could not serve the read right now"
            )
        if tree_data.get("truncated"):
            return self._read_tree_graphql(repo_name, selected)
        return map_file_tree_rest(
            tree_data, self._tenant_id, self._account, repo_name, selected
        )

    def _read_tree_graphql(self, repo_name: str, branch: str) -> FileTree:
        """Finish a truncated REST tree with the GraphQL level walk.

        ``map_file_tree_graphql`` maps one level of ``... on Tree
        { entries }`` and its docstring assigns level *composition* to
        the caller, which is this method: each directory the walk meets
        is one GraphQL query whose entries map independently, and the
        levels are concatenated into the one `FileTree` the port
        returns. A level that fails to arrive is never skipped — a
        partial tree mapped as a whole one is the silent data loss the
        fallback exists to prevent — so a missing root is the branch not
        being there (`SourceNotFoundError`) and a missing deeper level
        is the provider failing mid-walk (`SourceUnavailableError`).
        The tree's own ``sha``/``external_id`` stay ``None``, as the
        model documents for GraphQL-walked trees.
        """
        entries: list[FileEntry] = []
        visited: set[str] = set()
        pending = [""]
        while pending:
            path = pending.pop()
            if path in visited or len(visited) >= _MAX_TREE_LEVELS:
                continue
            visited.add(path)
            expression = f"{branch}:{path}"
            data: Mapping[str, Any] | None = self._client.graphql(
                _TREE_LEVEL_QUERY,
                {
                    "owner": self._account.org_id,
                    "name": repo_name,
                    "expression": expression,
                },
                use_cache=self._use_cache,
            )
            if not data or "data" not in data:
                raise SourceUnavailableError(
                    "the GitHub client could not serve the read right now"
                )
            tree_object = (
                (data.get("data") or {}).get("repository") or {}
            ).get("object")
            if not isinstance(tree_object, Mapping):
                if not path:
                    raise SourceNotFoundError(
                        f"no branch {branch!r} on repository {repo_name!r}"
                    )
                raise SourceUnavailableError(
                    "the GitHub client could not serve the read right now"
                )
            level_entries = tree_object.get("entries") or []
            level = map_file_tree_graphql(
                level_entries, self._tenant_id, self._account, repo_name, branch
            )
            entries.extend(level.entries)
            for raw in level_entries:
                if raw.get("type") == "tree" and raw.get("path"):
                    pending.append(raw["path"])
        return FileTree(
            tenant_id=self._tenant_id,
            account=self._account,
            repo_name=repo_name,
            branch=branch,
            entries=tuple(entries),
        )


if TYPE_CHECKING:
    #: Static conformance anchor, the twin of the ones in
    #: ``coops/storage/file.py`` and ``coops/storage/datasets.py``. mypy
    #: reading this module does not by itself assert that the adapter
    #: satisfies ``SourcePort`` — measured on the storage pair, renaming
    #: an adapter method so it no longer implements the port left mypy
    #: reporting "Success: no issues found" where the anchored file
    #: failed. Binding the adapter to the port here makes any signature
    #: drift — a dropped ``tenant`` parameter, a retyped return — a type
    #: error under ``strict = true`` now, rather than a silent drift
    #: until a runtime caller assigns the adapter to a ``SourcePort``
    #: in #26. A function rather than an instance assignment because
    #: constructing the adapter needs a client and a tenant, neither of
    #: which exists for free at import time.
    def _conforms_to_source_port(adapter: GitHubSourceAdapter) -> SourcePort:
        return adapter
