"""Bronze orchestration against the ports (issue #30).

:class:`BronzeService` is the extraction layer's *orchestration* — what to
fetch, in what order, with what watermarks, and where each result is written —
expressed against :class:`~coops.domain.ports.SourcePort` and
:class:`~coops.domain.ports.storage_port.StoragePort` only. It imports no
concrete GitHub client and none of the legacy JSON file helpers; a second
storage backend (or a second provider adapter) can be swapped in behind the
ports without touching this module. Since #30 wired the service onto the
live path, ``coops.etl.bronze_extract.run_extraction`` drives it for every
family the port can express; the byte-parity differential that verified the
service against the legacy extractors was retired with the redefinition of
#30 (a diff report, not a gate), and the wiring test in
``tests/integration/test_bronze_service_differential.py`` now pins the
wired path's tree and the known gap shapes.

Record content is **preserved, not redesigned**: every dataset this service
writes is the JSON the legacy path wrote over the same input, modulo the
generation-time timestamps (``_metadata.extracted_at`` and the structure
document's ``extracted_at``), which differ between any two runs including
two legacy runs, and modulo the port gaps the #30 wiring report names by
field (#240 committer name, #241 provider fields on repository records).
Where a record's shape is a provider-ism that survives the move (``method:
"rest"`` in structure files, the ``data/bronze/<entity>.json`` string in
``_metadata.file_path``), this module reproduces it deliberately rather than
cleaning it up — changing it is a different issue.

Coverage — what the CLI wires where
-----------------------------------

The service owns the write families the ports can express: repositories
(raw/filtered/detail), commits, issues, PRs and structures. Two families are
**deliberately absent**, because today's ``SourcePort`` cannot express their
content, and faking them would change published data; the CLI keeps the
legacy extractors for them on the same run (#238, #239):

1. ``issue_events_<repo>.json`` — the port has no
   ``fetch_issue_events`` method. The ``ActivityEvent`` model exists
   (:mod:`coops.domain.models`) but nothing yields it. Until the port grows
   that method, the events step cannot move.
2. ``members_basic.json`` / ``members_detailed.json`` — the ``Member`` model
   is a projection (identity, login, totals); today's member records carry
   the provider payload (``avatar_url``, ``type``, profile fields,
   ``profile_fetched``, ``data_source``, …) and a *numeric* ``id`` where the
   model stringifies. Not reconstructible without changing the model.

Also not expressible, with the consequence named:

- **The commit committer's name (#240).** The port yields domain models,
  never payloads (its own contract), so the GraphQL node's ``committer.name``
  — requested by the live history query and written by the legacy path on
  130,108 of 130,186 corpus records (measured, fga snapshot, the 486
  per-repository files — the retired ``commits_all.json`` aggregate is excluded
  because it repeats every record and doubles every figure; the other 78 are
  the deliberate ``_is_address`` blanks) — cannot cross it.
  ``_commit_record`` writes ``None``; every key set is otherwise identical
  at every level, so the defect is one value, not a shaping. Not fixable by
  widening ``Commit``: the model exists for the domain, not to envelope
  GitHub's schema. The fix is a payload-carrying seam on the port — a
  contract change, not a projection change. Pinned by the strict xfail in
  ``tests/unit/test_commit_projection_gap.py``.
- **Incremental fetch windows.** The port has no ``since`` (its docstring
  assigns watermarks to adapters; the GitHub adapter does not read them), so
  this service always fetches a full history and merges with what is stored
  (dedup by sha, merge by number). The *output* equals an incremental run;
  only the request volume is larger. The merge semantics — the part the
  issue assigns to the caller — live here.
- **The unchanged-tree skip.** The old structure step probes a branch head
  and reuses the previous file when it has not moved; there is no
  branch-head read on the port (the adapter was meant to own this skip and
  does not). The service re-fetches the tree and rewrites the file, which is
  byte-identical modulo the timestamp.
- **Deletion.** ``StoragePort`` has no delete, so the #216 reconciliation
  and the #170 retired-aggregate sweep cannot run through it; they stay with
  the caller that owns the filesystem (the CLI). The listing provenance the
  reconciliation depends on *is* written here (see :meth:`_save_records`).
- **Watermark persistence location.** ``watermarks.json`` deliberately lives
  outside ``data/`` (it must not be published), and the port's key space is
  ``(layer, entity)`` inside a tenant tree — there is no address for it.
  The *decisions* (what a watermark means for this run) are made here; the
  ``WatermarkStore`` remains the persisted-state adapter, passed in by the
  composition exactly like the two ports.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, cast

from coops.bronze.commits import _EMAIL_RE
from coops.bronze.watermarks import WatermarkStore, max_iso
from coops.domain.models import (
    Commit,
    FileEntry,
    FileTree,
    Issue,
    PullRequest,
    Repository,
)
from coops.domain.ports import SourceError, SourcePort
from coops.domain.ports.storage_port import JSONValue, StoragePort
from coops.domain.tenancy import TenantId

#: The CoOps repository blacklist, carried over from ``OrganizationConfig``.
#: Which repositories a run keeps is extraction policy (the adapter docstring
#: assigns it to this layer), so it belongs with the orchestration, not with
#: the provider.
DEFAULT_REPOSITORY_BLACKLIST: tuple[str, ...] = (
    "Hi.Events",
    "Qualifying-Software-Engineers-Undergraduates-in-DevOps",
)


def _now_iso() -> str:
    """The generation timestamp, in the exact form the legacy writer uses."""
    return datetime.now(timezone.utc).isoformat()


def _repository_record(repository: Repository) -> dict[str, Any]:
    """The stored repository record: today's field set, today's key order.

    Byte-parity with the legacy path requires the provider-shaped spelling
    (``private``/``fork``/``size``), including the numeric ``id`` the model
    stringifies as ``external_id``. The key order matches the listing
    payloads the corpus serves; real payloads carry further keys
    (``node_id``, ``owner``, ``license``, …) the model never sees — see the
    module docstring and the #30 report.
    """
    return {
        "id": int(repository.external_id) if repository.external_id else None,
        "name": repository.name,
        "full_name": repository.full_name,
        "private": repository.is_private,
        "fork": repository.is_fork,
        "archived": repository.is_archived,
        "description": repository.description,
        "default_branch": repository.default_branch,
        "language": repository.language,
        "html_url": repository.html_url,
        "size": repository.size_kb,
        "stargazers_count": repository.stargazers_count,
        "forks_count": repository.forks_count,
        "open_issues_count": repository.open_issues_count,
        "created_at": repository.created_at,
        "updated_at": repository.updated_at,
        "pushed_at": repository.pushed_at,
    }


def _actor_record(actor: Any) -> dict[str, Any] | None:
    """The stored actor: ``login``/``id``/``name``, keys only when present.

    Parity with ``ACTOR_FIELDS`` in the legacy issue projection: a field is
    written only when the source carried it, so a model ``None`` omits the
    key rather than publishing a null.
    """
    if actor is None:
        return None
    record: dict[str, Any] = {}
    if getattr(actor, "login", None):
        record["login"] = actor.login
    if getattr(actor, "account_id", None) is not None:
        record["id"] = actor.account_id
    if getattr(actor, "display_name", None) is not None:
        record["name"] = actor.display_name
    return record


def _conversation_record(item: Issue | PullRequest) -> dict[str, Any]:
    """The stored issue/PR record: the whitelist the legacy step applies."""
    return {
        "number": item.number,
        "state": item.state,
        "title": item.title,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "closed_at": item.closed_at,
        "user": _actor_record(item.author),
        "assignee": _actor_record(item.assignee),
        "repo_name": item.repo_name,
    }


def _commit_record(commit: Commit) -> dict[str, Any]:
    """The stored commit record: the sanitised shape the legacy step writes.

    The model arrives already pseudonymised — no raw address crosses the
    port, the author's name is blanked when it *is* an address, and the
    email survives only as its hash — so this projection rebuilds the
    post-scrub record directly. The one scrub rule that still has work to
    do here is free text: commit messages carry ``Co-authored-by:`` and
    ``Signed-off-by:`` trailers with real addresses, so the message is
    redacted with the very regex the legacy scrub uses (imported, not
    copied — a second copy could drift). ``html_url`` is ``None`` because
    the history query never requests a URL. The committer's *date* falls
    back to the commit date exactly as the legacy builder does. The
    committer's *name* is #240: the live query sends it, the model cannot
    carry it, and no seam transports the payload here — so this projection
    writes ``None`` where the legacy path writes a real name on 130,108 of
    130,186 corpus records, with every key set otherwise identical (see the
    module docstring and ``tests/unit/test_commit_projection_gap.py``).
    """
    author = commit.author
    author_data: dict[str, Any] = {"name": None, "date": commit.committed_at}
    if author is not None:
        author_data["name"] = author.display_name
        if author.login:
            author_data["login"] = author.login
        if author.account_id is not None:
            author_data["id"] = author.account_id
        if author.email_hash:
            author_data["author_email_hash"] = author.email_hash
    return {
        "sha": commit.sha,
        "html_url": None,
        "commit": {
            "author": author_data,
            "committer": {"name": None, "date": commit.committed_at},
            "message": _EMAIL_RE.sub("[email removed]", commit.message),
        },
        "parents": list(commit.parents),
        "additions": commit.additions,
        "deletions": commit.deletions,
        "total_changes": (
            (commit.additions or 0) + (commit.deletions or 0)
            if commit.additions is not None and commit.deletions is not None
            else None
        ),
        "repo_name": commit.repo_name,
    }


def _tree_entry_record(entry: FileEntry) -> dict[str, Any]:
    """One structure entry, in the standardised shape the tree step writes."""
    name = entry.path.split("/")[-1] if "/" in entry.path else entry.path
    if entry.kind == "blob":
        kind = "file"
    elif entry.kind == "tree":
        kind = "directory"
    else:
        kind = entry.kind
    node: dict[str, Any] = {
        "name": name,
        "path": entry.path,
        "type": kind,
        "sha": entry.sha or "",
        "mode": entry.mode or "",
    }
    if kind == "file":
        extension = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        node["extension"] = extension
        node["size"] = entry.size or 0
        node["is_binary"] = bool(entry.is_binary)
    elif kind == "directory":
        node["children"] = []
    return node


class BronzeService:
    """Bronze extraction orchestrated through ``SourcePort``/``StoragePort``.

    One instance serves one tenant. The watermark store is optional and,
    like the two ports, is handed in by the composition: the service makes
    the *decisions* watermarks feed (merge-or-replace, what to record) and
    persists them through the store, whose location the storage port cannot
    address (module docstring).
    """

    def __init__(
        self,
        source: SourcePort,
        storage: StoragePort,
        tenant: TenantId,
        *,
        watermarks: WatermarkStore | None = None,
        repo_blacklist: Sequence[str] = DEFAULT_REPOSITORY_BLACKLIST,
        offline: bool = False,
    ) -> None:
        self._source = source
        self._storage = storage
        self._tenant = tenant
        self._watermarks = watermarks
        self._repo_blacklist = tuple(repo_blacklist)
        # The port cannot express "this run is an offline replay", and a
        # replay must not claim a complete listing (#216: the guard travels
        # with the data, so the composition passes the flag in).
        self._offline = offline

    # -- repositories ------------------------------------------------------

    def extract_repositories(
        self,
        *,
        max_repos: int | None = None,
        repo_filter: list[str] | None = None,
    ) -> list[str]:
        """Fetch, filter and persist the organisation's repositories.

        Writes ``repositories_raw`` (everything the listing returned),
        ``repositories_filtered`` (the kept set, carrying the #216
        completeness provenance exactly when the enumeration was unbounded),
        one ``repo_<name>`` document per kept repository and the
        ``repositories_detailed`` listing. Returns the entity names written.

        ``max_repos`` caps the *kept* records; unlike the legacy step it
        cannot bound the listing fetch itself (the port has no page cap),
        so the output is identical and only the request volume differs.
        """
        repositories = list(self._source.fetch_repositories(self._tenant))
        if not repositories:
            print("ERROR: Failed to fetch repositories")
            return []

        kept: list[Repository] = []
        for repository in repositories:
            if self._should_skip(repository):
                print(
                    f"Skipping repository: {repository.name} (blacklisted/fork)"
                )
            else:
                kept.append(repository)

        if repo_filter:
            wanted = {name.lower() for name in repo_filter}
            available = {repo.full_name.lower() for repo in kept}
            missing = sorted(wanted - available)
            if missing:
                raise ValueError(
                    "--repo: not in the filtered repository set "
                    f"(unknown, blacklisted or fork): {', '.join(missing)}"
                )
            kept = [repo for repo in kept if repo.full_name.lower() in wanted]

        if max_repos is not None:
            kept = kept[:max_repos]

        print(f"Found {len(kept)} repositories (filtered from {len(repositories)})")

        listing_complete = (
            max_repos is None and repo_filter is None and not self._offline
        )

        entities = [
            self._save_records(
                "repositories_raw", [_repository_record(r) for r in repositories]
            )
        ]
        entities.append(
            self._save_records(
                "repositories_filtered",
                [_repository_record(r) for r in kept],
                complete=listing_complete,
            )
        )

        details: list[dict[str, Any]] = []
        for repository in kept:
            record = _repository_record(repository)
            details.append(record)
            entities.append(self._save_document(f"repo_{repository.name}", record))
        if details:
            entities.append(self._save_records("repositories_detailed", details))
        return entities

    def _should_skip(self, repository: Repository) -> bool:
        return repository.is_fork or repository.name in self._repo_blacklist

    # -- commits -----------------------------------------------------------

    def extract_commits(self, *, max_commits_per_repo: int | None = None) -> list[str]:
        """Fetch and persist each listed repository's commit history.

        Reads the filtered listing from storage (steps communicate through
        the layer, never in memory). With a watermark carrying ``last_run``
        the freshly fetched records are merged over the stored ones —
        prepend plus dedup by sha, the legacy semantics, which a full fetch
        makes equivalent to the legacy incremental run.
        """
        entities: list[str] = []
        for repo in self._filtered_repository_records():
            repo_name = repo.get("name", "unknown")
            full_name = repo.get("full_name") or repo_name
            wm = self._watermarks.get(full_name) if self._watermarks else None
            incremental = bool(wm and wm.last_run)

            print(f"Processing commits for: {repo_name}")
            commits = list(self._source.fetch_commits(self._tenant, repo_name))
            if max_commits_per_repo is not None:
                commits = commits[:max_commits_per_repo]
            records = [_commit_record(commit) for commit in commits]
            print(f"Found {len(records)} commits in {repo_name}")

            if incremental:
                prior = self._load_records(f"commits_{repo_name}")
                seen: set[str] = set()
                merged: list[dict[str, Any]] = []
                for record in records + prior:
                    sha = record.get("sha")
                    if sha and sha in seen:
                        continue
                    if sha:
                        seen.add(sha)
                    merged.append(record)
                records = merged

            if records:
                entities.append(self._save_records(f"commits_{repo_name}", records))

            if self._watermarks is not None:
                self._watermarks.update(full_name)
        return entities

    # -- issues and pull requests -------------------------------------------

    def extract_issues(
        self,
        *,
        max_issues: int | None = None,
        max_prs: int | None = None,
    ) -> list[str]:
        """Fetch and persist each listed repository's issues and PRs.

        Issue events are **not** extracted here: the source port has no
        ``fetch_issue_events`` (module docstring), so ``issue_events_<repo>``
        remains with the legacy step until the port grows the method.
        """
        entities: list[str] = []
        for repo in self._filtered_repository_records():
            repo_name = repo.get("name", "unknown")
            full_name = repo.get("full_name") or repo_name
            wm = self._watermarks.get(full_name) if self._watermarks else None
            last_updated_at = wm.last_updated_at if wm else None

            print(f"Processing issues for: {repo_name}")
            issues = list(self._source.fetch_issues(self._tenant, repo_name))
            pull_requests = list(
                self._source.fetch_pull_requests(self._tenant, repo_name)
            )
            issue_records = sorted(
                (_conversation_record(item) for item in issues),
                key=lambda item: item["number"],
            )
            pr_records = sorted(
                (_conversation_record(item) for item in pull_requests),
                key=lambda item: item["number"],
            )

            if last_updated_at:
                issue_records = self._merge_by_number(
                    self._load_records(f"issues_{repo_name}"), issue_records
                )
                pr_records = self._merge_by_number(
                    self._load_records(f"prs_{repo_name}"), pr_records
                )

            if max_issues is not None:
                issue_records = issue_records[:max_issues]
            if max_prs is not None:
                pr_records = pr_records[:max_prs]

            if issue_records:
                entities.append(self._save_records(f"issues_{repo_name}", issue_records))
            if pr_records:
                entities.append(self._save_records(f"prs_{repo_name}", pr_records))

            if self._watermarks is not None:
                newest_updated = None
                for item in issue_records + pr_records:
                    newest_updated = max_iso(newest_updated, item.get("updated_at"))
                self._watermarks.update(
                    full_name,
                    last_updated_at=max_iso(
                        wm.last_updated_at if wm else None, newest_updated
                    ),
                )
        return entities

    @staticmethod
    def _merge_by_number(
        prior: list[dict[str, Any]], fresh: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge by ``number``; a fresh record replaces its prior twin."""
        merged = {
            item["number"]: item
            for item in prior
            if isinstance(item, dict) and "number" in item
        }
        for item in fresh:
            if isinstance(item, dict) and "number" in item:
                merged[item["number"]] = item
        return sorted(merged.values(), key=lambda item: item["number"])

    # -- structures ---------------------------------------------------------

    def extract_structures(self) -> list[str]:
        """Fetch and persist each listed repository's default-branch tree.

        The record is the standardised structure document the legacy step
        writes, rebuilt from the ``FileTree``: the tree's own entry list,
        the repository metadata from the filtered listing, and the
        transport/total provenance fields. The branch-head skip the legacy
        step performs is not expressible here (module docstring), so every
        tree is fetched; the head sha is still recorded in the watermark
        store for whoever can use it.
        """
        entities: list[str] = []
        for repo in self._filtered_repository_records():
            repo_name = repo.get("name", "unknown")
            full_name = repo.get("full_name") or repo_name
            branch = repo.get("default_branch") or "main"

            print(f"Processing structure for: {repo_name}")
            try:
                tree = self._source.fetch_tree(self._tenant, repo_name)
            except SourceError:
                print(f"Failed to extract structure for {repo_name}")
                continue
            if not tree.entries:
                print(f"No files found in {repo_name}")
                continue

            record = self._structure_record(tree, repo)
            entities.append(self._save_plain_document(f"structure_{repo_name}", record))
            print(f"Saved structure for {repo_name} ({len(tree.entries)} entries)")

            if self._watermarks is not None and tree.sha:
                wm = self._watermarks.get(full_name)
                head_shas = dict((wm.head_shas or {}) if wm else {})
                head_shas[branch] = tree.sha
                self._watermarks.update(full_name, head_shas=head_shas)
        return entities

    @staticmethod
    def _structure_record(tree: FileTree, repo: dict[str, Any]) -> dict[str, Any]:
        """The stored structure document: today's shape, no ``_metadata``."""
        return {
            "owner": tree.account.org_id,
            "repository": tree.repo_name,
            "branch": tree.branch,
            "sha": tree.sha,
            "tree": [_tree_entry_record(entry) for entry in tree.entries],
            "truncated": False,
            "extracted_at": _now_iso(),
            # The port cannot say which transport served the tree; "rest" is
            # the value every non-truncated legacy record carries.
            "method": "rest",
            "total_items": len(tree.entries),
            "repository_metadata": {
                "id": repo.get("id"),
                "full_name": repo.get("full_name"),
                "description": repo.get("description"),
                "created_at": repo.get("created_at"),
                "updated_at": repo.get("updated_at"),
                "language": repo.get("language"),
                "size": repo.get("size"),
                "stars": repo.get("stargazers_count") or 0,
                "forks": repo.get("forks_count") or 0,
                "open_issues": repo.get("open_issues_count") or 0,
            },
        }

    # -- storage -------------------------------------------------------------

    def _save_records(
        self, entity: str, records: list[dict[str, Any]], *, complete: bool = False
    ) -> str:
        """Persist a record family with the legacy list envelope.

        The leading ``_metadata`` element is part of the record contract:
        ``file_path`` names the published location (``data/bronze/…``) the
        bytes have always carried, and ``complete`` is the #216 listing
        provenance — written only when positively asserted, absent means
        incomplete, so the reconciliation refuses narrowed listings.
        """
        metadata: dict[str, JSONValue] = {
            "extracted_at": _now_iso(),
            "file_path": f"data/bronze/{entity}.json",
            "record_count": len(records),
        }
        if complete:
            metadata["complete"] = True
        data: list[JSONValue] = [{"_metadata": metadata}, *records]
        self._storage.save(self._tenant, "bronze", entity, data)
        print(f"Saved data to: data/bronze/{entity}.json ({len(records)} records)")
        return entity

    def _save_document(self, entity: str, record: dict[str, Any]) -> str:
        """Persist a single document with the legacy dict envelope."""
        document: dict[str, JSONValue] = {
            **cast(dict[str, JSONValue], record),
            "_metadata": {
                "extracted_at": _now_iso(),
                "file_path": f"data/bronze/{entity}.json",
            },
        }
        self._storage.save(self._tenant, "bronze", entity, document)
        print(f"Saved data to: data/bronze/{entity}.json")
        return entity

    def _save_plain_document(self, entity: str, record: dict[str, Any]) -> str:
        """Persist a single document with no envelope at all.

        The structure family is written without the metadata element
        (``timestamp=False`` in the legacy writer), so its only timestamp
        is the record-level ``extracted_at`` the record itself carries.
        """
        self._storage.save(
            self._tenant, "bronze", entity, cast(dict[str, JSONValue], record)
        )
        print(f"Saved data to: data/bronze/{entity}.json")
        return entity

    def _load_records(self, entity: str) -> list[dict[str, Any]]:
        """Read back a stored record family, dropping the leading metadata."""
        dataset = self._storage.load(self._tenant, "bronze", entity)
        if dataset is None or not isinstance(dataset.data, list):
            return []
        records = list(dataset.data)
        if (
            records
            and isinstance(records[0], dict)
            and "_metadata" in records[0]
        ):
            records = records[1:]
        return [r for r in records if isinstance(r, dict)]

    def _filtered_repository_records(self) -> list[dict[str, Any]]:
        """The kept repository records, read back from the layer itself."""
        listing = self._storage.load(self._tenant, "bronze", "repositories_filtered")
        if listing is None or not isinstance(listing.data, list):
            print("No repositories found. Run repository extraction first.")
            return []
        records = list(listing.data)
        if (
            records
            and isinstance(records[0], dict)
            and "_metadata" in records[0]
        ):
            records = records[1:]
        return [r for r in records if isinstance(r, dict)]
