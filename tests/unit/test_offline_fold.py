"""An offline replay must read the *newest cached version* of a record (#199).

The cache is keyed ``md5(full URL)``, so one logical record can live in
several entries — the unconditional listing and the ``?since=<watermark>``
ones. A replay with no watermark asks only for the unconditional URL, whose
body can be months old; the newer records sit under keys nothing asks for,
and a regeneration on such a cache lost 55 records and reverted 34 others.

These tests drive the real extractor over a real offline client and a
materialised cache directory, so they exercise the whole path a corpus
replay takes: URL-keyed page reads, the content-indexed fold, the
projection to the stored record, and the written bronze file.

Scope note (#30 wiring): the **issues** fold — the union of cached issue
bodies, newest version per number — was retired with the legacy
``extract_issues`` it lived in. Issues and PRs are ``BronzeService``'s now,
and neither the service nor the GitHub adapter implements the fold, so an
offline replay of those families through the port sees only the
plain-URL page snapshot; a live run is unaffected (it re-fetches current
pages). That regression of the replay *diagnostic* is recorded in the #30
wiring report. What is still folded on the live path is **events** (and
the REST fallback of the kept commit extractor), so those are what this
file pins.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from coops.bronze.issues import extract_issue_events
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
    return key_sorting_after_digest(hashlib.md5(anchor_key.encode(), usedforsecurity=False).hexdigest(), label)


def key_sorting_after_digest(target_hex: str, label: str) -> str:
    """Same, anchored on a digest — for cache entries whose key the test
    cannot reconstruct (GraphQL keys hash the whole query text)."""
    index = 0
    while True:
        candidate = f"{label}#{index}"
        if hashlib.md5(candidate.encode(), usedforsecurity=False).hexdigest() > target_hex:
            return candidate
        index += 1


def cache_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, hashlib.md5(key.encode(), usedforsecurity=False).hexdigest() + ".json")


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


def event(event_id, repo=FULL_NAME):
    return {
        "id": event_id,
        "event": "assigned",
        "created_at": "2026-09-20T00:00:00Z",
        "actor": {"login": "alice"},
        "issue": {"number": 1},
        "url": f"https://api.github.com/repos/{repo}/issues/events/{event_id}",
    }


def event_page_url(page: int) -> str:
    return f"https://api.github.com/repos/{FULL_NAME}/issues/events?per_page=100&page={page}"


# ---------------------------------------------------------------------------
# issue events (the family still on the folded path — #239 keeps it legacy)
# ---------------------------------------------------------------------------


class TestOfflineEventFold:
    def test_single_body_control_matches_todays_output(self, tmp_path, monkeypatch):
        """The arms-differ control: with one cached body the fold must change
        nothing but the stamp.

        The record is asserted field for field to what the code projects from
        that body — without this, a fold that mangles the simple case passes
        every test below.
        """
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(cache_dir, event_page_url(1), [event(10), event(11)], T0)

        extract_issue_events(client, config, use_cache=True)

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
            },
            {
                "id": 11,
                "event": "assigned",
                "created_at": "2026-09-20T00:00:00Z",
                "repo_name": "repo1",
                "actor": {"login": "alice"},
                "issue": {"number": 1},
                "last_seen_at": iso(T0),
            },
        ]

    def test_event_only_in_a_later_body_is_recovered(self, tmp_path, monkeypatch):
        """The lost-records defect, events edition: an event whose id exists
        only under a key the unconditional replay does not ask for (an
        incremental page captured later) must still reach the output."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(cache_dir, event_page_url(1), [event(10)], T0)
        # Any other key holding this repository's events — the fold is
        # content-indexed, not URL-matched.
        write_body(
            cache_dir,
            key_sorting_after(event_page_url(1), "later-events"),
            [event(11)],
            T1,
        )

        extract_issue_events(client, config, use_cache=True)

        events = read_saved(tmp_path / "data" / "bronze" / "issue_events_repo1.json")
        assert [e["id"] for e in events] == [10, 11]

    def test_last_seen_at_is_the_newest_body_containing_the_event(
        self, tmp_path, monkeypatch
    ):
        """Events are immutable, so a later body cannot change the record —
        but seeing the id again refreshes ``last_seen_at``, which is the
        question that field exists to answer."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(cache_dir, event_page_url(1), [event(10)], T0)
        write_body(
            cache_dir,
            key_sorting_after(event_page_url(1), "repeat"),
            [event(10), event(11)],
            T2,
        )

        extract_issue_events(client, config, use_cache=True)

        events = {e["id"]: e for e in read_saved(tmp_path / "data" / "bronze" / "issue_events_repo1.json")}
        assert events[10]["last_seen_at"] == iso(T2)
        assert events[11]["last_seen_at"] == iso(T2)

    def test_other_repositories_event_bodies_do_not_leak(self, tmp_path, monkeypatch):
        """Content attribution must scope the fold to one repository: a
        neighbouring repository's event body shares the cache directory."""
        config = seed_run(tmp_path, monkeypatch)
        cache_dir = str(tmp_path / "cache")
        client = GitHubAPIClient("token", cache_dir=cache_dir, offline=True)
        write_body(cache_dir, event_page_url(1), [event(10)], T0)
        write_body(
            cache_dir,
            f"https://api.github.com/repos/{ORG}/repo2/issues/events?per_page=100&page=1",
            [event(99, repo=f"{ORG}/repo2")],
            T1,
        )

        extract_issue_events(client, config, use_cache=True)

        events = read_saved(tmp_path / "data" / "bronze" / "issue_events_repo1.json")
        assert [e["id"] for e in events] == [10]


# TestOfflineCommitFold removed with the commit fold it covered: commit-graph
# continuation attributed a successor repository history to its predecessor
# (2021.1-PC-GO1-Frontend 510 -> 818). TestOfflineIssueFold was removed with
# the #30 wiring: the legacy extract_issues that folded issue bodies is gone
# (see the module docstring), and the service path has no fold. The GraphQL
# seeding helpers went with them - the events family replays over plain REST
# pages, which write_body seeds directly.
