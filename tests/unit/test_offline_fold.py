"""An offline replay must read the *newest cached version* of a record (#199).

The cache is keyed ``md5(full URL)``, so one logical record lives in several
entries — the unconditional listing and the ``?since=<watermark>`` ones. A
replay with no watermark asks only for the unconditional URL, whose body can
be months old; the newer records sit under keys nothing asks for, and a
regeneration on such a cache lost 55 records and reverted 34 others.

These tests drive the real extractors over a real offline client and a
materialised cache directory, so they exercise the whole path a corpus replay
takes: URL-keyed page reads, the content-indexed fold, the projection to the
stored record, and the written bronze file. The GraphQL page is seeded through
a faked ``requests.post`` (the network boundary) so the cache key is computed
by the real code, never hardcoded in a test.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from coops.bronze.commits import extract_commits
from coops.bronze.issues import extract_issues
from coops.utils.github_api import GitHubAPIClient, OrganizationConfig

ORG = "test-org"
FULL_NAME = f"{ORG}/repo1"

# Distinct body mtimes, oldest first. Real timestamps near 2026 so ISO
# rendering is realistic; the fold compares floats, so these can be arbitrary.
T0 = 1_789_000_000.0
T1 = 1_789_100_000.0
T2 = 1_789_200_000.0


def iso(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def key_sorting_after(anchor_key: str, label: str) -> str:
    """A cache key whose md5 filename sorts strictly after ``anchor_key``'s.

    The fold scans cache files in filename order and filenames are md5 of the
    key, so which body a test folds *first* must not be left to the hash: salt
    the fold-only body's key until its digest lands where the test needs it.
    """
    return key_sorting_after_digest(hashlib.md5(anchor_key.encode()).hexdigest(), label)


def key_sorting_after_digest(target_hex: str, label: str) -> str:
    """Same, anchored on a digest — for cache entries whose key the test
    cannot reconstruct (GraphQL keys hash the whole query text)."""
    index = 0
    while True:
        candidate = f"{label}#{index}"
        if hashlib.md5(candidate.encode()).hexdigest() > target_hex:
            return candidate
        index += 1


def cache_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, hashlib.md5(key.encode()).hexdigest() + ".json")


def write_body(cache_dir: str, key: str, body, mtime: float) -> str:
    """Write a cache entry exactly as ``_cache_set`` would, with a chosen mtime."""
    os.makedirs(cache_dir, exist_ok=True)
    path = cache_path(cache_dir, key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False)
    os.utime(path, (mtime, mtime))
    return path


def read_saved(path):
    """Read a bronze list file, dropping the leading ``_metadata`` entry."""
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    return [r for r in records if not (isinstance(r, dict) and "_metadata" in r)]


def seed_run(tmp_path, monkeypatch, repos=None):
    """chdir into a scratch working directory holding the filtered repo list."""
    monkeypatch.chdir(tmp_path)
    bronze = tmp_path / "data" / "bronze"
    bronze.mkdir(parents=True, exist_ok=True)
    with open(bronze / "repositories_filtered.json", "w", encoding="utf-8") as f:
        json.dump(repos or [{"name": "repo1", "full_name": FULL_NAME}], f)
    return OrganizationConfig(ORG)


def issue(number, updated_at, *, pr=False, repo=FULL_NAME):
    record = {
        "number": number,
        "title": f"issue {number}",
        "state": "open",
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": updated_at,
        "closed_at": None,
        "repository_url": f"https://api.github.com/repos/{repo}",
        "user": {"login": "alice", "id": 1},
    }
    if pr:
        record["pull_request"] = {
            "url": f"https://api.github.com/repos/{repo}/pulls/{number}"
        }
    return record


def event(event_id):
    return {
        "id": event_id,
        "event": "assigned",
        "created_at": "2026-09-20T00:00:00Z",
        "actor": {"login": "alice"},
        "issue": {"number": 1},
        "url": f"https://api.github.com/repos/{FULL_NAME}/issues/events/{event_id}",
    }


def event_page_url(page: int) -> str:
    return f"https://api.github.com/repos/{FULL_NAME}/issues/events?per_page=100&page={page}"


def issues_page_url(page: int) -> str:
    return f"https://api.github.com/repos/{FULL_NAME}/issues?state=all&per_page=100&page={page}"


# ---------------------------------------------------------------------------
# issues and pull requests
# ---------------------------------------------------------------------------


class TestOfflineIssueFold:
    def test_newest_version_wins_across_bodies(self, tmp_path, monkeypatch):
        """Two bodies hold the same number with different ``updated_at``.

        The replay must store the newer version. Before the fold it stored
        whichever body the unconditional URL holds — the older one.
        """
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(
            cache_dir,
            issues_page_url(1),
            [issue(1, "2026-09-01T00:00:00Z"), issue(2, "2026-09-02T00:00:00Z")],
            T0,
        )
        # A watermark run's ?since= body, fetched later: #2 moved, #1 did not.
        write_body(
            cache_dir,
            f"{issues_page_url(1)}&since=2026-09-10T00:00:00Z",
            [issue(2, "2026-09-22T00:00:00Z")],
            T1,
        )
        write_body(cache_dir, event_page_url(1), [event(10)], T0)

        extract_issues(client, config, use_cache=True)

        records = read_saved(tmp_path / "data" / "bronze" / "issues_repo1.json")
        by_number = {r["number"]: r for r in records}
        assert by_number[2]["updated_at"] == "2026-09-22T00:00:00Z"

    def test_record_only_in_incremental_body_is_recovered(self, tmp_path, monkeypatch):
        """The lost-55 defect: records created after the unconditional capture
        exist only under ``?since=`` keys, and a no-watermark replay dropped
        them."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(
            cache_dir, issues_page_url(1), [issue(1, "2026-09-01T00:00:00Z")], T0
        )
        write_body(
            cache_dir,
            f"{issues_page_url(1)}&since=2026-09-10T00:00:00Z",
            [issue(7, "2026-09-23T00:00:00Z")],
            T1,
        )
        write_body(cache_dir, event_page_url(1), [event(10)], T0)

        extract_issues(client, config, use_cache=True)

        records = read_saved(tmp_path / "data" / "bronze" / "issues_repo1.json")
        assert sorted(r["number"] for r in records) == [1, 7]

    def test_record_absent_from_newer_body_survives(self, tmp_path, monkeypatch):
        """Absence from a ``?since=`` body means "not changed", never "deleted".

        #1 sits in the old body only; the newer body must not delete it. This
        pins existing behaviour: it cannot fail before the fold exists, it
        exists to fail if the fold ever treats the union as
        "latest body wins".
        """
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(
            cache_dir,
            issues_page_url(1),
            [issue(1, "2026-09-01T00:00:00Z"), issue(2, "2026-09-02T00:00:00Z")],
            T0,
        )
        write_body(
            cache_dir,
            f"{issues_page_url(1)}&since=2026-09-10T00:00:00Z",
            [issue(2, "2026-09-22T00:00:00Z")],
            T1,
        )
        write_body(cache_dir, event_page_url(1), [event(10)], T0)

        extract_issues(client, config, use_cache=True)

        records = read_saved(tmp_path / "data" / "bronze" / "issues_repo1.json")
        by_number = {r["number"]: r for r in records}
        assert 1 in by_number
        assert by_number[1]["updated_at"] == "2026-09-01T00:00:00Z"

    def test_last_seen_at_is_the_newest_body_containing_the_record(
        self, tmp_path, monkeypatch
    ):
        """``last_seen_at`` = mtime of the newest cached response holding the
        record — whichever version's content won, and even when the newer body
        only repeats it."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(
            cache_dir,
            issues_page_url(1),
            [issue(1, "2026-09-01T00:00:00Z"), issue(2, "2026-09-02T00:00:00Z")],
            T0,
        )
        # Fetched later; #2 is newer here, #1 is repeated unchanged. The key
        # is salted to sort after the page body's, so the fold always folds
        # the older body first — the repeat is what must bump #1's stamp.
        write_body(
            cache_dir,
            key_sorting_after(issues_page_url(1), "since-query"),
            [issue(1, "2026-09-01T00:00:00Z"), issue(2, "2026-09-22T00:00:00Z")],
            T2,
        )
        write_body(cache_dir, event_page_url(1), [event(10), event(11)], T0)

        extract_issues(client, config, use_cache=True)

        by_number = {
            r["number"]: r
            for r in read_saved(tmp_path / "data" / "bronze" / "issues_repo1.json")
        }
        # #1's content came from the old body (nothing newer), but the record
        # was *seen* again in the T2 body.
        assert by_number[1]["last_seen_at"] == iso(T2)
        assert by_number[2]["last_seen_at"] == iso(T2)

        events = read_saved(tmp_path / "data" / "bronze" / "issue_events_repo1.json")
        assert {e["last_seen_at"] for e in events} == {iso(T0)}

    def test_single_body_control_matches_todays_output(self, tmp_path, monkeypatch):
        """The arms-differ control: with one cached body the fold must change
        nothing but the stamp.

        The records are asserted equal, field for field, to what today's code
        projects from that body — without this, a fold that mangles the simple
        case passes every test above.
        """
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(
            cache_dir,
            issues_page_url(1),
            [
                # Newest-first, as GitHub actually lists them: if the fold ever
                # returns body order instead of the sorted order today's code
                # produces, the assertion below must catch it.
                issue(3, "2026-09-03T00:00:00Z"),
                issue(2, "2026-09-02T00:00:00Z", pr=True),
                issue(1, "2026-09-01T00:00:00Z"),
            ],
            T0,
        )
        write_body(cache_dir, event_page_url(1), [event(10)], T0)

        extract_issues(client, config, use_cache=True)

        def projected(number, updated_at):
            return {
                "number": number,
                "state": "open",
                "title": f"issue {number}",
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": updated_at,
                "closed_at": None,
                "user": {"login": "alice", "id": 1},
                "assignee": None,
                "repo_name": "repo1",
                "last_seen_at": iso(T0),
            }

        # Field-for-field what today's code projects from that one body, with
        # the stamp as the only addition — and the issue/PR split unchanged.
        records = read_saved(tmp_path / "data" / "bronze" / "issues_repo1.json")
        assert records == [
            projected(1, "2026-09-01T00:00:00Z"),
            projected(3, "2026-09-03T00:00:00Z"),
        ]
        prs = read_saved(tmp_path / "data" / "bronze" / "prs_repo1.json")
        assert prs == [projected(2, "2026-09-02T00:00:00Z")]
        events = read_saved(tmp_path / "data" / "bronze" / "issue_events_repo1.json")
        assert events == [
            {
                "id": 10,
                "event": "assigned",
                "created_at": "2026-09-20T00:00:00Z",
                "repo_name": "repo1",
                "actor": {"login": "alice"},
                "issue": {"number": 1},
                "last_seen_at": iso(T0),
            }
        ]

    def test_other_repositories_bodies_do_not_leak(self, tmp_path, monkeypatch):
        """Content attribution must scope the fold to one repository: a
        neighbouring repository's issue body shares the cache directory."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(
            cache_dir, issues_page_url(1), [issue(1, "2026-09-01T00:00:00Z")], T0
        )
        write_body(
            cache_dir,
            f"https://api.github.com/repos/{ORG}/repo2/issues?state=all&per_page=100&page=1",
            [issue(99, "2026-09-24T00:00:00Z", repo=f"{ORG}/repo2")],
            T1,
        )
        write_body(cache_dir, event_page_url(1), [event(10)], T0)

        extract_issues(client, config, use_cache=True)

        records = read_saved(tmp_path / "data" / "bronze" / "issues_repo1.json")
        assert [r["number"] for r in records] == [1]


# ---------------------------------------------------------------------------
# commits
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.headers = {}

    def json(self):
        return self._body


def gql_node(sha, parents, *, message="commit", date="2026-09-20T00:00:00Z"):
    return {
        "oid": sha,
        "message": message,
        "messageHeadline": message,
        "committedDate": date,
        "author": {
            "name": "alice",
            "email": "alice@example.com",
            "user": {"login": "alice", "databaseId": 1},
        },
        "committer": {"name": "alice", "email": "alice@example.com", "date": date},
        "parents": {"nodes": [{"oid": parent} for parent in parents]},
        "additions": 1,
        "deletions": 1,
    }


def gql_page(nodes, has_next=False):
    return {
        "data": {
            "repository": {
                "defaultBranchRef": {
                    "name": "main",
                    "target": {
                        "history": {
                            "pageInfo": {"hasNextPage": has_next, "endCursor": None},
                            "nodes": nodes,
                        }
                    },
                }
            }
        }
    }


def seed_graphql_page(monkeypatch, cache_dir, nodes, page_mtime=None):
    """Populate the unconditional GraphQL page through the real online path.

    ``requests.post`` is faked at the network boundary and the *real*
    extraction method drives it, so the cache key is produced by the client's
    own query text and variables — exactly what the offline replay will ask
    for. The body is then served from the cache with the network removed.
    Returns the page's cache filename: GraphQL keys hash the whole query text,
    so the filename is the only handle a test has on the entry's sort order.
    """
    import coops.utils.github_api as github_api

    client = GitHubAPIClient("token", cache_dir=cache_dir)

    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse(200, gql_page(nodes))

    monkeypatch.setattr(github_api.requests, "post", fake_post)
    commits, _ = client.graphql_commit_history(owner=ORG, repo="repo1", page_size=50)
    assert [c["oid"] for c in commits] == [n["oid"] for n in nodes]

    pages = [
        os.path.join(cache_dir, name)
        for name in os.listdir(cache_dir)
        if name.endswith(".json")
    ]
    assert len(pages) == 1
    if page_mtime is not None:
        os.utime(pages[0], (page_mtime, page_mtime))

    # From here on, any network touch is a failure of offline mode itself.
    def no_network(*args, **kwargs):
        raise AssertionError("offline mode must not touch the network")

    monkeypatch.setattr(github_api.requests, "post", no_network)
    monkeypatch.setattr(github_api.requests, "get", no_network)
    return pages[0]


class TestOfflineCommitFold:
    def test_since_body_commits_recovered_once_and_never_compared(
        self, tmp_path, monkeypatch
    ):
        """A watermark run's GraphQL body holds commits the unconditional page
        has never seen; they must be folded in. A sha present in two bodies is
        kept exactly once, with the version this run read — commits are
        immutable, so no timestamp is ever compared and no fold body can
        overwrite a commit the run itself fetched.

        The fold body here is the *older* one and carries different content
        for B, so "kept once with the run's version" is a real choice the code
        must make, not an accident of ordering."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir, exist_ok=True)
        A, B, C = "a" * 40, "b" * 40, "c" * 40
        page_file = seed_graphql_page(
            monkeypatch,
            cache_dir,
            [gql_node(A, [B], message="A"), gql_node(B, [], message="B")],
            page_mtime=T1,
        )
        # An older watermark run's chunked body: C extends A, and B appears
        # with different content — which must NOT overwrite the page's B.
        write_body(
            cache_dir,
            key_sorting_after_digest(
                os.path.basename(page_file)[:-5], "watermark-query"
            ),
            gql_page(
                [
                    gql_node(C, [A], message="C"),
                    gql_node(B, [], message="B REWRITTEN"),
                ]
            ),
            T0,
        )
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)

        extract_commits(client, config, use_cache=True, method="graphql", page_size=50)

        records = read_saved(tmp_path / "data" / "bronze" / "commits_repo1.json")
        shas = [r["sha"] for r in records]
        assert sorted(shas) == sorted([A, B, C])
        assert len(shas) == len(set(shas)), (
            "a sha present in two bodies must not duplicate"
        )
        by_sha = {r["sha"]: r for r in records}
        assert by_sha[B]["commit"]["message"] == "B", (
            "the run's own read wins; never compared"
        )
        assert by_sha[C]["commit"]["message"] == "C"
        assert by_sha[A]["last_seen_at"] == iso(T1)
        assert by_sha[B]["last_seen_at"] == iso(T1)
        assert by_sha[C]["last_seen_at"] == iso(T0)

    def test_commit_last_seen_at_and_unrelated_bodies_excluded(
        self, tmp_path, monkeypatch
    ):
        """``last_seen_at`` comes from the newest body containing the sha, and
        a body whose oids do not continue this repository's chain — another
        repository's history — does not attach."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir, exist_ok=True)
        A, B, Z = "a" * 40, "b" * 40, "z" * 40
        page_file = seed_graphql_page(
            monkeypatch, cache_dir, [gql_node(A, [B]), gql_node(B, [])], page_mtime=T0
        )
        write_body(
            cache_dir,
            "graphql:another-repos-history",
            gql_page([gql_node(Z, ["unrelated" + "0" * 32])]),
            T2,
        )
        # B re-observed by a later watermark run; salted to sort after the
        # page body so the repeat is folded second and must bump the stamp.
        write_body(
            cache_dir,
            key_sorting_after_digest(
                os.path.basename(page_file)[:-5], "watermark-reobserved"
            ),
            gql_page([gql_node(B, [])]),
            T1,
        )
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)

        extract_commits(client, config, use_cache=True, method="graphql", page_size=50)

        records = read_saved(tmp_path / "data" / "bronze" / "commits_repo1.json")
        by_sha = {r["sha"]: r for r in records}
        assert Z not in by_sha, "an unrelated chain must not attach to this repository"
        assert by_sha[A]["last_seen_at"] == iso(T0)
        assert by_sha[B]["last_seen_at"] == iso(T1), (
            "re-observed later: seen-as-of moves"
        )
