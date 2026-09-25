"""Content-indexed reading of the URL-keyed HTTP cache (#199).

The cache on disk is keyed ``md5(full URL)`` — one file per URL, overwritten in
place — so the same logical record legitimately lives in **several** entries:
the unconditional listing (``issues?state=all&per_page=100&page=1``) and the
incremental ones (``...&since=<watermark>``). A reader that consults a single
URL therefore reads whichever *version* happened to be asked for, and with no
watermark that is the unconditional URL — whose body can be months old, because
most cached bodies carry no ETag and are served forever without revalidation.
The newer records sit under keys nothing asks for. A regeneration on such a
cache lost 55 records and reverted 34 others.

This module answers a different question than ``_cache_get``. Instead of "what
does this one URL hold", it answers "what does the **cache** hold for this
repository and record family": every cached response whose *content* contains
records for that repository and family, unioned, with the newest version of
each record kept.

Attribution is by content, because the URL cannot be recovered from an md5
filename:

* issues/PRs list bodies — each record carries ``repository_url``;
* issue-events bodies — each record carries a per-event ``url`` whose path
  names the repository;
* REST commit-list bodies — each record carries a per-commit ``url``;
* GraphQL commit-history bodies — the query requests no repository name, so
  the response carries none, and a body is attributed to a repository only by
  **commit-graph continuation**: it folds into a repository when its node and
  parent ``oid``s intersect the commits already known for that repository
  (seeded by the URLs the run itself asked for). Commit history is a chain, so
  a ``since`` body for a repository necessarily reaches into that repository's
  existing commits through the ``parents`` of its oldest node. Measured over
  the corpus this stays per-repository: 2,867 GraphQL bodies cluster into 449
  components (largest 39), with no component spanning two extracted
  repositories.

Offline mode only. Online runs revalidate (or should — the no-ETag staleness
of a live run is a separate defect), and a live full listing is authoritative
and complete on its own.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

#: Bounds only the cheap first-bytes prefilter that decides whether a cache
#: file is worth parsing at all; bodies are read whole after it.
_PREFILTER_BYTES = 4096

#: Internal fold state per record: the winning provider-shaped record, and the
#: mtime of the newest cached body the record was found in (float, because two
#: bodies can be written within the same second and the fold still has to
#: order them).
_Entry = List[Any]  # [record: Dict, max_mtime: float]


def _mtime_iso(mtime: float) -> str:
    """Render a cache file mtime as a second-resolution UTC ``Z`` timestamp.

    Same shape as the provider's own ``updated_at`` values, so the two can be
    read side by side in a bronze record.
    """
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse a GitHub-style ISO timestamp to an aware UTC datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _repo_from_api_url(url: Optional[str]) -> Optional[str]:
    """``https://api.github.com/repos/{owner}/{repo}/...`` → ``owner/repo``."""
    if not isinstance(url, str):
        return None
    marker = "/repos/"
    at = url.find(marker)
    if at == -1:
        return None
    parts = url[at + len(marker) :].split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def client_fold(client: Any) -> Optional["CacheFold"]:
    """The client's cache fold when it is genuinely in offline mode, else None.

    Strict about the flag (``is True``): the extractors are unit-tested with
    MagicMock clients, whose ``.offline`` attribute is a truthy Mock, and a
    loose truthiness check would route those tests through the fold and break
    on its return types instead of exercising what they set out to test.
    """
    if getattr(client, "offline", False) is not True:
        return None
    return client.offline_fold()


@dataclass
class FoldedRecord:
    """One record as the cache holds its newest version.

    ``record`` is the provider-shaped record: a raw issue or event, or a
    GraphQL history node (REST commit-list items are converted to that shape,
    so the commits family has one record shape). It carries the content of the
    version that won the fold. ``last_seen_at`` is when the record was last
    *confirmed*: the mtime of the newest cached response containing it,
    whichever version won — a record seen again in a later body is "still
    there as of then" even when the later body holds no newer version of it.

    A record present in an old body and absent from every newer one keeps both
    its old content and its old ``last_seen_at``: absence from a ``?since=``
    response means "not changed", never "deleted".
    """

    record: Dict[str, Any]
    last_seen_at: str


class CacheFold:
    """Read the cache by repository and family instead of by URL.

    One instance per run. Each family scans the cache directory once and keeps
    only what that family needs, so a scoped replay pays for the bodies it can
    use and no more.
    """

    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = cache_dir
        self._issues: Optional[Dict[str, Dict[Any, Any]]] = None
        self._events: Optional[Dict[str, Dict[Any, Any]]] = None
        self._commit_lists: Optional[
            Dict[str, List[Tuple[float, List[Dict[str, Any]]]]]
        ] = None
        self._graphql_bodies: Optional[
            List[Tuple[float, Set[str], List[Dict[str, Any]]]]
        ] = None

    # -- scanning -----------------------------------------------------------

    def _iter_files(self) -> Iterable[str]:
        try:
            names = os.listdir(self.cache_dir)
        except OSError:
            return
        for name in sorted(names):
            if name.endswith(".json"):
                yield os.path.join(self.cache_dir, name)

    def _load(self, path: str) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _list_body(self, path: str) -> Optional[Tuple[float, List[Dict[str, Any]]]]:
        """Parse ``path`` as a list-of-objects body, or None.

        The prefilter reads only the first bytes: the corpus holds thousands of
        cache files and most are not list bodies for the family being scanned.
        """
        try:
            with open(path, "rb") as f:
                head = f.read(_PREFILTER_BYTES)
        except OSError:
            return None
        if not head.lstrip().startswith(b"["):
            return None
        body = self._load(path)
        if not isinstance(body, list) or not body:
            return None
        if not all(isinstance(item, dict) for item in body):
            return None
        return os.path.getmtime(path), body

    @staticmethod
    def _fold(
        bucket: Dict[Any, Any],
        key: Any,
        record: Dict[str, Any],
        mtime: float,
        *,
        newer: Optional[Any] = None,
    ) -> None:
        """Fold one record occurrence into ``bucket``.

        ``newer``, when given, decides whether this occurrence's content
        replaces the folded winner (issues/PRs: the greater ``updated_at``).
        Families whose records are immutable (commits, events) pass no
        ``newer`` and keep the first version seen. In both cases the record's
        presence in a body at ``mtime`` refreshes ``last_seen`` — that is the
        question ``last_seen_at`` exists to answer, and it is independent of
        which version's content won.
        """
        prior = bucket.get(key)
        if prior is None:
            bucket[key] = [record, mtime]
            return
        if newer is not None and newer(record, mtime, prior):
            prior[0] = record
        if mtime > prior[1]:
            prior[1] = mtime

    # -- issues and pull requests --------------------------------------------

    def issues(self, full_name: str) -> Dict[Any, FoldedRecord]:
        """Newest cached version of every issue *and* PR of one repository.

        Keyed by ``number`` (issues and PRs share an endpoint and a number
        space). The winner is the greatest ``updated_at`` — the provider's own
        notion of recency, not the body's mtime, because a re-fetched
        unconditional body can be newer on disk while holding older record
        versions than an incremental body. A record missing from every newer
        body survives. The caller splits issues from PRs by the
        ``pull_request`` key, exactly as it does for a live response.
        """
        if self._issues is None:
            self._issues = {}
            for path in self._iter_files():
                parsed = self._list_body(path)
                if parsed is None:
                    continue
                mtime, body = parsed
                if not all(
                    "number" in item and "repository_url" in item for item in body
                ):
                    continue
                repo = _repo_from_api_url(body[0].get("repository_url"))
                if repo is None:
                    continue
                bucket = self._issues.setdefault(repo, {})
                for item in body:
                    if item.get("number") is not None:
                        self._fold(
                            bucket,
                            item["number"],
                            dict(item),
                            mtime,
                            newer=self._issue_newer,
                        )
        return {
            number: FoldedRecord(entry[0], _mtime_iso(entry[1]))
            for number, entry in self._issues.get(full_name, {}).items()
        }

    @staticmethod
    def _issue_newer(candidate: Dict[str, Any], mtime: float, prior: List[Any]) -> bool:
        """True when ``candidate`` is a newer version than the folded winner.

        Ties and missing timestamps fall back to the body mtime so the choice
        is still deterministic: a timestamp beats none, and of two equal
        timestamps the later-fetched body wins.
        """
        cand_dt = _parse_iso(candidate.get("updated_at"))
        prior_dt = _parse_iso(prior[0].get("updated_at"))
        if cand_dt is not None and prior_dt is not None and cand_dt != prior_dt:
            return cand_dt > prior_dt
        if (cand_dt is None) != (prior_dt is None):
            return prior_dt is None
        return mtime >= prior[1]

    # -- issue events ---------------------------------------------------------

    def events(self, full_name: str) -> Dict[Any, FoldedRecord]:
        """Every cached issue event of one repository, keyed by ``id``.

        Events are immutable and id-monotone, so versions are never compared:
        the first version seen is kept, and a later body containing the same
        id only refreshes ``last_seen_at``.
        """
        if self._events is None:
            self._events = {}
            for path in self._iter_files():
                parsed = self._list_body(path)
                if parsed is None:
                    continue
                mtime, body = parsed
                if not all(
                    "id" in item and "event" in item and "url" in item for item in body
                ):
                    continue
                first_url = str(body[0].get("url"))
                repo = _repo_from_api_url(body[0].get("url"))
                if repo is None or "/issues/events/" not in first_url:
                    continue
                bucket = self._events.setdefault(repo, {})
                for item in body:
                    if item.get("id") is not None:
                        self._fold(bucket, item["id"], dict(item), mtime)
        return {
            eid: FoldedRecord(entry[0], _mtime_iso(entry[1]))
            for eid, entry in self._events.get(full_name, {}).items()
        }

    # -- commits ---------------------------------------------------------------

    def commits(self, full_name: str, seed_oids: Set[str]) -> Dict[str, FoldedRecord]:
        """Every cached commit of one repository, keyed by ``sha``.

        Commits are immutable — a commit that differs by ``sha`` is a different
        record — so versions are never compared: the first version seen (in
        body-mtime order) is kept, and a later body containing the same sha
        only refreshes ``last_seen_at``.

        Sources are:

        * REST commit-list bodies attributed to the repository by content; and
        * GraphQL commit-history bodies attributed by commit-graph
          continuation: a body folds in when its node/parent oids intersect
          the repository's known commits. The seed is what the run itself read
          (plus the REST records above); attachment repeats to a fixpoint so a
          run's time-chunked pages chain onto one another.
        """
        attached: List[Tuple[float, List[Dict[str, Any]]]] = []
        known: Set[str] = set(seed_oids)

        for mtime, body in self._commit_lists_by_repo().get(full_name, []):
            attached.append((mtime, body))
            for item in body:
                if item.get("sha"):
                    known.add(item["sha"])
                for parent in item.get("parents") or []:
                    if isinstance(parent, dict) and parent.get("sha"):
                        known.add(parent["sha"])

        # Fixpoint: each attached body can pull in the next (a chunk's oldest
        # node parents onto the previous chunk's newest node). Bodies are
        # revisited per pass; passes are bounded by the longest attach chain,
        # which for a per-repository history is the number of its bodies.
        graphql = self._graphql_history_bodies()
        taken = set()
        changed = True
        while changed:
            changed = False
            for idx, (mtime, oids, nodes) in enumerate(graphql):
                if idx in taken or not (oids & known):
                    continue
                taken.add(idx)
                attached.append((mtime, nodes))
                known |= oids
                changed = True

        attached.sort(key=lambda entry: entry[0])  # first version seen = oldest body
        bucket: Dict[str, Any] = {}
        for mtime, records in attached:
            for record in records:
                sha = record.get("sha") or record.get("oid")
                if not sha:
                    continue
                node = _rest_item_to_node(record) if "sha" in record else dict(record)
                self._fold(bucket, sha, node, mtime)
        return {
            sha: FoldedRecord(entry[0], _mtime_iso(entry[1]))
            for sha, entry in bucket.items()
        }

    def commit_items(self, full_name: str) -> Dict[str, FoldedRecord]:
        """Raw REST commit-list items of one repository, keyed by ``sha``.

        The REST branch of ``extract_commits`` builds its stored record from
        the REST item shape, so it folds raw items rather than the GraphQL
        node shape ``commits`` returns. REST list bodies only — a REST replay
        needs them to exist anyway (its own first page must be cached or the
        run stops before any fold), and GraphQL bodies carry no repository
        name to attribute themselves by. Same fold semantics as ``commits``:
        immutable records, first version seen, ``last_seen_at`` from the
        newest body containing the sha.
        """
        bucket: Dict[str, Any] = {}
        for mtime, body in self._commit_lists_by_repo().get(full_name, []):
            for item in body:
                if item.get("sha"):
                    self._fold(bucket, item["sha"], dict(item), mtime)
        return {
            sha: FoldedRecord(entry[0], _mtime_iso(entry[1]))
            for sha, entry in bucket.items()
        }

    def _commit_lists_by_repo(
        self,
    ) -> Dict[str, List[Tuple[float, List[Dict[str, Any]]]]]:
        if self._commit_lists is not None:
            return self._commit_lists
        by_repo: Dict[str, List[Tuple[float, List[Dict[str, Any]]]]] = {}
        for path in self._iter_files():
            parsed = self._list_body(path)
            if parsed is None:
                continue
            mtime, body = parsed
            if not all(
                "sha" in item and "commit" in item and "url" in item for item in body
            ):
                continue
            first_url = str(body[0].get("url"))
            repo = _repo_from_api_url(body[0].get("url"))
            if repo is None or "/commits" not in first_url:
                continue
            by_repo.setdefault(repo, []).append((mtime, body))
        self._commit_lists = by_repo
        return by_repo

    def _graphql_history_bodies(
        self,
    ) -> List[Tuple[float, Set[str], List[Dict[str, Any]]]]:
        """Every GraphQL commit-history body: ``(mtime, oids, nodes)``.

        Nodes keep the GraphQL shape the extractor already maps to the stored
        record. ``oids`` are the nodes' own oids plus their parents' — the
        parents are what tie a ``since`` body to the chain it extends.
        """
        if self._graphql_bodies is not None:
            return self._graphql_bodies
        bodies: List[Tuple[float, Set[str], List[Dict[str, Any]]]] = []
        for path in self._iter_files():
            try:
                with open(path, "rb") as f:
                    head = f.read(_PREFILTER_BYTES)
            except OSError:
                continue
            if b'"repository"' not in head:
                continue
            body = self._load(path)
            if not isinstance(body, dict):
                continue
            repo_obj = (body.get("data") or {}).get("repository") or {}
            target = (repo_obj.get("defaultBranchRef") or {}).get("target")
            if target is None and isinstance(repo_obj.get("ref"), dict):
                target = repo_obj["ref"].get("target")
            history = (
                (target or {}).get("history") if isinstance(target, dict) else None
            )
            nodes = (history or {}).get("nodes") if isinstance(history, dict) else None
            if not isinstance(nodes, list) or not nodes:
                continue
            oids: Set[str] = set()
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("oid"):
                    oids.add(node["oid"])
                for parent in (node.get("parents") or {}).get("nodes") or []:
                    if isinstance(parent, dict) and parent.get("oid"):
                        oids.add(parent["oid"])
            if oids:
                bodies.append((os.path.getmtime(path), oids, nodes))
        self._graphql_bodies = bodies
        return bodies


def _rest_item_to_node(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a REST commit-list item to the GraphQL node shape.

    The commits family has one consumer (``extract_commits``) and it maps
    GraphQL nodes to the stored record; folding a REST list item through that
    same shape keeps one code path. Stats live in per-sha detail bodies, not
    in list items, so additions/deletions default to 0 exactly as
    ``graphql_commit_history`` defaults missing stats — the REST branch of the
    extractor enriches them from the detail bodies when it reads them.
    """
    commit_obj = item.get("commit") or {}
    top_author = item.get("author") or {}
    author_obj = commit_obj.get("author") or {}
    committer_obj = commit_obj.get("committer") or {}
    message = commit_obj.get("message") or ""
    parents = [
        {"oid": parent.get("sha")}
        for parent in (item.get("parents") or [])
        if isinstance(parent, dict) and parent.get("sha")
    ]
    return {
        "oid": item.get("sha"),
        "message": message,
        "messageHeadline": message.split("\n")[0] if message else "",
        "committedDate": author_obj.get("date"),
        "author": {
            "name": author_obj.get("name"),
            "email": author_obj.get("email"),
            "user": {
                "login": top_author.get("login"),
                "databaseId": top_author.get("id"),
            },
        },
        "committer": {
            "name": committer_obj.get("name"),
            "email": committer_obj.get("email"),
            "date": committer_obj.get("date"),
        },
        "parents": {"nodes": parents},
        "additions": 0,
        "deletions": 0,
    }
