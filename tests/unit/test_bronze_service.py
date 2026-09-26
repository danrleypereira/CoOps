"""Unit tests for the ported Bronze orchestration (#30).

The differential in ``tests/integration/test_bronze_service_differential.py``
proves byte-identity against the legacy extractors; these tests pin the
behaviours that must hold on their own: the #216 listing provenance, the
scrub on the service's write path, the watermark-driven merge decisions,
and the ports-only import discipline.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

import coops.bronze.bronze_service as bronze_service_module
from coops.bronze.bronze_service import BronzeService
from coops.bronze.watermarks import WatermarkStore
from coops.domain.models import (
    Actor,
    Commit,
    FileEntry,
    FileTree,
    Issue,
    PullRequest,
    Repository,
)
from coops.domain.tenancy import resolve_tenant
from coops.storage.file import FileStorageAdapter

TENANT = resolve_tenant("single", "test-org")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _repo(name: str, *, fork: bool = False, **over: Any) -> Repository:
    fields: dict[str, Any] = {
        "external_id": "101",
        "name": name,
        "full_name": f"test-org/{name}",
        "description": "A corpus repository",
        "default_branch": "main",
        "language": "Python",
        "html_url": f"https://github.com/test-org/{name}",
        "size_kb": 42,
        "stargazers_count": 3,
        "forks_count": 1,
        "open_issues_count": 2,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-06-01T00:00:00Z",
        "pushed_at": "2025-06-01T00:00:00Z",
    }
    fields.update(over)
    return Repository(
        tenant_id=TENANT.id, account=TENANT.accounts[0], is_fork=fork, **fields
    )


def _commit(
    sha: str,
    repo: str,
    *,
    message: str = "chore: work",
    login: str | None = None,
    account_id: int | None = None,
    name: str | None = None,
    email: str | None = None,
    committed_at: str = "2025-02-01T00:00:00Z",
    parents: tuple[str, ...] = (),
) -> Commit:
    email_hash = (
        hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        if email
        else None
    )
    author = (
        Actor.resolve(
            login=login, account_id=account_id, name=name, email_hash=email_hash
        )
        if (login or email_hash or name)
        else None
    )
    return Commit(
        tenant_id=TENANT.id,
        account=TENANT.accounts[0],
        external_id=sha,
        repo_name=repo,
        sha=sha,
        author=author,
        committed_at=committed_at,
        message=message,
        parents=parents,
        additions=1,
        deletions=0,
    )


def _issue(number: int, repo: str, *, state: str = "open") -> Issue:
    return Issue(
        tenant_id=TENANT.id,
        account=TENANT.accounts[0],
        external_id=str(9000 + number),
        repo_name=repo,
        number=number,
        state=state,
        title=f"Issue {number}",
        author=Actor.resolve(login="linked_user", account_id=4242),
        created_at="2025-02-01T00:00:00Z",
        updated_at="2025-02-02T00:00:00Z",
    )


def _pr(number: int, repo: str) -> PullRequest:
    return PullRequest(
        tenant_id=TENANT.id,
        account=TENANT.accounts[0],
        external_id=str(9100 + number),
        repo_name=repo,
        number=number,
        state="open",
        title=f"PR {number}",
        author=Actor.resolve(login="outsider", account_id=4245),
    )


def _tree(repo: str, entries: tuple[FileEntry, ...], sha: str = "tree-sha") -> FileTree:
    return FileTree(
        tenant_id=TENANT.id,
        account=TENANT.accounts[0],
        repo_name=repo,
        branch="main",
        sha=sha,
        external_id=sha,
        entries=entries,
    )


class StubSource:
    """A minimal in-memory source port serving hand-built models."""

    def __init__(
        self,
        *,
        repositories: tuple[Repository, ...] = (),
        commits: dict[str, list[Commit]] | None = None,
        issues: dict[str, list[Issue]] | None = None,
        pull_requests: dict[str, list[PullRequest]] | None = None,
        trees: dict[str, FileTree] | None = None,
    ) -> None:
        self._repositories = list(repositories)
        self._commits = commits or {}
        self._issues = issues or {}
        self._pull_requests = pull_requests or {}
        self._trees = trees or {}

    def fetch_repositories(self, tenant: Any) -> Any:
        return iter(list(self._repositories))

    def fetch_members(self, tenant: Any) -> Any:
        return iter(())

    def fetch_commits(self, tenant: Any, repo_name: str) -> Any:
        return iter(list(self._commits.get(repo_name, [])))

    def fetch_issues(self, tenant: Any, repo_name: str) -> Any:
        return iter(list(self._issues.get(repo_name, [])))

    def fetch_pull_requests(self, tenant: Any, repo_name: str) -> Any:
        return iter(list(self._pull_requests.get(repo_name, [])))

    def fetch_tree(self, tenant: Any, repo_name: str, branch: str | None = None) -> FileTree:
        return self._trees[repo_name]


def _service(
    source: StubSource,
    tmp_path: Path,
    *,
    watermarks: WatermarkStore | None = None,
    offline: bool = False,
) -> tuple[BronzeService, FileStorageAdapter]:
    storage = FileStorageAdapter(tmp_path / "store")
    return (
        BronzeService(
            source, storage, TENANT.id, watermarks=watermarks, offline=offline
        ),
        storage,
    )


def _stored(storage: FileStorageAdapter, entity: str) -> Any:
    dataset = storage.load(TENANT.id, "bronze", entity)
    assert dataset is not None, f"{entity} was not written"
    return dataset.data


def _seed_records(
    storage: FileStorageAdapter, entity: str, records: list[dict[str, Any]]
) -> None:
    """Write a prior run's file, envelope and all, the way the layer does."""
    storage.save(
        TENANT.id,
        "bronze",
        entity,
        [
            {
                "_metadata": {
                    "extracted_at": "2025-01-01T00:00:00Z",
                    "file_path": f"data/bronze/{entity}.json",
                    "record_count": len(records),
                }
            },
            *records,
        ],
    )


# --------------------------------------------------------------------------
# The seam: no concrete client, no legacy JSON helpers
# --------------------------------------------------------------------------


def test_module_imports_no_concrete_io() -> None:
    """The service module binds none of the legacy I/O names.

    AST for the imports (a docstring mentioning a name must not pass or
    fail this) plus a text-level sweep as the belt: the identifiers do not
    appear in the file at all.
    """
    source = Path(bronze_service_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all("coops.utils" not in alias.name for alias in node.names), (
                f"concrete import: {[a.name for a in node.names]}"
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module != "coops.utils.github_api", ast.dump(node)
    for forbidden in ("GitHubAPIClient", "save_json_data", "load_json_data"):
        assert forbidden not in source, f"{forbidden} appears in the module"


# --------------------------------------------------------------------------
# Listing provenance (#216) — the guard the reconciliation depends on
# --------------------------------------------------------------------------


def test_provenance_written_on_unbounded_listing(tmp_path: Path) -> None:
    service, storage = _service(StubSource(repositories=(_repo("repo1"), _repo("repo2"))), tmp_path)
    service.extract_repositories()

    data = _stored(storage, "repositories_filtered")
    assert data[0]["_metadata"]["complete"] is True
    assert data[0]["_metadata"]["record_count"] == 2
    assert data[0]["_metadata"]["file_path"] == "data/bronze/repositories_filtered.json"


def test_max_repos_leaves_listing_unprovenanced(tmp_path: Path) -> None:
    service, storage = _service(StubSource(repositories=(_repo("repo1"), _repo("repo2"))), tmp_path)
    service.extract_repositories(max_repos=1)

    data = _stored(storage, "repositories_filtered")
    assert "complete" not in data[0]["_metadata"]
    assert data[0]["_metadata"]["record_count"] == 1


def test_repo_filter_leaves_listing_unprovenanced(tmp_path: Path) -> None:
    service, storage = _service(StubSource(repositories=(_repo("repo1"), _repo("repo2"))), tmp_path)
    service.extract_repositories(repo_filter=["test-org/repo2"])

    data = _stored(storage, "repositories_filtered")
    assert "complete" not in data[0]["_metadata"]
    assert [record["name"] for record in data[1:]] == ["repo2"]


def test_offline_run_leaves_listing_unprovenanced(tmp_path: Path) -> None:
    """An offline replay must not claim completeness (#216 rule 4)."""
    service, storage = _service(
        StubSource(repositories=(_repo("repo1"),)), tmp_path, offline=True
    )
    service.extract_repositories()

    data = _stored(storage, "repositories_filtered")
    assert "complete" not in data[0]["_metadata"]


def test_repo_filter_unknown_name_raises(tmp_path: Path) -> None:
    service, _ = _service(StubSource(repositories=(_repo("repo1"),)), tmp_path)
    with pytest.raises(ValueError, match="not in the filtered repository set"):
        service.extract_repositories(repo_filter=["test-org/nope"])


def test_repo_filter_matches_case_insensitively(tmp_path: Path) -> None:
    """GitHub repository names are case-insensitive, and so is the filter —
    the rule the legacy ``--repo`` tests pinned at the extractor, restated
    here now that the filter is the service's."""
    service, storage = _service(
        StubSource(repositories=(_repo("repo1"), _repo("repo2"))), tmp_path
    )

    service.extract_repositories(repo_filter=["Test-Org/REPO1"])

    kept = _stored(storage, "repositories_filtered")
    assert [record["name"] for record in kept[1:]] == ["repo1"]


def test_forks_and_blacklist_filtered_from_kept_set(tmp_path: Path) -> None:
    service, storage = _service(
        StubSource(
            repositories=(_repo("repo1"), _repo("somefork", fork=True), _repo("Hi.Events"))
        ),
        tmp_path,
    )
    service.extract_repositories()

    raw = _stored(storage, "repositories_raw")
    kept = _stored(storage, "repositories_filtered")
    assert [record["name"] for record in raw[1:]] == [
        "repo1",
        "somefork",
        "Hi.Events",
    ]
    assert [record["name"] for record in kept[1:]] == ["repo1"]


def test_empty_listing_writes_nothing(tmp_path: Path) -> None:
    service, storage = _service(StubSource(repositories=()), tmp_path)
    assert service.extract_repositories() == []
    assert storage.list(TENANT.id, "bronze") == []


# --------------------------------------------------------------------------
# The scrub on the service's write path
# --------------------------------------------------------------------------


def test_commit_message_address_never_reaches_storage(tmp_path: Path) -> None:
    """Free text is the one channel the model still carries raw.

    Control first: the address is present in the model's message, so its
    absence from storage is the scrub working, not a dead probe.
    """
    message = "feat: pair\n\nCo-authored-by: Pair <pair@personal.example.net>\n"
    service, storage = _service(
        StubSource(
            repositories=(_repo("repo1"),),
            commits={"repo1": [_commit("aaa1", "repo1", message=message)]},
        ),
        tmp_path,
    )
    service.extract_repositories()
    service.extract_commits()

    assert "pair@personal.example.net" in message  # the control
    stored = json.dumps(_stored(storage, "commits_repo1"))
    assert not _EMAIL_RE.search(stored)
    # Credit survives: the attributed name and the trailer stay.
    assert "Co-authored-by: Pair" in stored
    assert "[email removed]" in stored


# --------------------------------------------------------------------------
# Watermark decisions: merge semantics on the caller's side of the port
# --------------------------------------------------------------------------


def test_commits_merge_with_prior_by_sha_on_incremental(tmp_path: Path) -> None:
    watermarks = WatermarkStore(path=str(tmp_path / "watermarks.json"))
    watermarks.update("test-org/repo1", last_run="2025-01-01T00:00:00Z")
    service, storage = _service(
        StubSource(
            repositories=(_repo("repo1"),),
            commits={
                "repo1": [
                    _commit("new1", "repo1", message="fresh"),
                    _commit("new2", "repo1"),
                ]
            },
        ),
        tmp_path,
        watermarks=watermarks,
    )
    _seed_records(
        storage,
        "commits_repo1",
        [
            {"sha": "old1", "repo_name": "repo1"},
            {"sha": "new1", "repo_name": "repo1", "commit": {"message": "stale"}},
        ],
    )

    service.extract_repositories()
    service.extract_commits()

    records = _stored(storage, "commits_repo1")[1:]
    # Fresh first (commits are immutable, so merge is a prepend), the
    # prior-only record kept, the fresh twin replacing its stale twin.
    assert [record["sha"] for record in records] == ["new1", "new2", "old1"]
    fresh = records[0]
    assert fresh["commit"]["message"] == "fresh"


def test_issues_merge_by_number_on_incremental(tmp_path: Path) -> None:
    watermarks = WatermarkStore(path=str(tmp_path / "watermarks.json"))
    watermarks.update("test-org/repo1", last_updated_at="2025-01-01T00:00:00Z")
    service, storage = _service(
        StubSource(
            repositories=(_repo("repo1"),),
            issues={"repo1": [_issue(1, "repo1", state="closed"), _issue(3, "repo1")]},
        ),
        tmp_path,
        watermarks=watermarks,
    )
    _seed_records(
        storage,
        "issues_repo1",
        [
            {"number": 1, "state": "open", "repo_name": "repo1"},
            {"number": 2, "state": "open", "repo_name": "repo1"},
        ],
    )

    service.extract_repositories()
    service.extract_issues()

    records = _stored(storage, "issues_repo1")[1:]
    assert [record["number"] for record in records] == [1, 2, 3]
    assert records[0]["state"] == "closed"  # the fresh record replaced its twin
    wm = watermarks.get("test-org/repo1")
    assert wm.last_updated_at == "2025-02-02T00:00:00Z"


def test_issues_without_prs_write_no_prs_file(tmp_path: Path) -> None:
    service, storage = _service(
        StubSource(repositories=(_repo("repo1"),), issues={"repo1": [_issue(1, "repo1")]}),
        tmp_path,
    )
    service.extract_repositories()
    service.extract_issues()

    assert storage.load(TENANT.id, "bronze", "issues_repo1") is not None
    assert storage.load(TENANT.id, "bronze", "prs_repo1") is None


# --------------------------------------------------------------------------
# Structures
# --------------------------------------------------------------------------


def test_structure_document_shape_and_head_sha_watermark(tmp_path: Path) -> None:
    watermarks = WatermarkStore(path=str(tmp_path / "watermarks.json"))
    entries = (
        FileEntry(path="README.md", kind="blob", sha="blob-1", mode="100644", size=120),
        FileEntry(path="src", kind="tree", sha="tree-1", mode="040000"),
    )
    service, storage = _service(
        StubSource(repositories=(_repo("repo1"),), trees={"repo1": _tree("repo1", entries)}),
        tmp_path,
        watermarks=watermarks,
    )
    service.extract_repositories()
    assert service.extract_structures() == ["structure_repo1"]

    document = _stored(storage, "structure_repo1")
    assert list(document.keys()) == [
        "owner",
        "repository",
        "branch",
        "sha",
        "tree",
        "truncated",
        "extracted_at",
        "method",
        "total_items",
        "repository_metadata",
    ]
    assert document["tree"][0] == {
        "name": "README.md",
        "path": "README.md",
        "type": "file",
        "sha": "blob-1",
        "mode": "100644",
        "extension": ".md",
        "size": 120,
        "is_binary": False,
    }
    assert document["tree"][1]["children"] == []
    assert document["repository_metadata"]["stars"] == 3
    assert watermarks.get("test-org/repo1").head_shas == {"main": "tree-sha"}


def test_structure_empty_tree_not_written(tmp_path: Path) -> None:
    service, storage = _service(
        StubSource(repositories=(_repo("repo1"),), trees={"repo1": _tree("repo1", ())}),
        tmp_path,
    )
    service.extract_repositories()
    assert service.extract_structures() == []
    assert storage.load(TENANT.id, "bronze", "structure_repo1") is None
