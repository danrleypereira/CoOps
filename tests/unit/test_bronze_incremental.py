"""Incremental-extraction behaviour (issue #110) at the Bronze extractor boundary.

These tests fake the HTTP client (the port) and the watermark store, and let
the real ``extract_commits`` run, so the watermark-bounded ``since`` fetch
and the prepend-plus-dedup merge are exercised for real rather than asserted
against call sequences.

Scope note (#30 wiring): the issues and structure halves of this file were
retired with their extractors. Issues and PRs are ``BronzeService``'s now —
its merge-by-number is pinned in ``tests/unit/test_bronze_service.py`` and
the port has no ``since`` window to test — and the structure extractor's
unchanged-head skip is gone outright (no branch-head read on the port; the
service re-fetches the tree, byte-identical modulo the timestamp — see the
service module docstring). ``extract_commits`` itself stays in the tree as
the function the #111 raw-read scrub guard
(``tests/unit/test_github_client_raw_layer.py::TestRawReadPathScrub``)
pins, so its incremental behaviour is still live to pin too.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from coops.bronze.commits import extract_commits
from coops.bronze.watermarks import WatermarkStore

REPOS = [{"name": "repo1", "full_name": "org/repo1", "default_branch": "main"}]
_NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _store(path="unused.json", **fields):
    store = WatermarkStore(path, now=_NOW)
    if fields:
        store.update("org/repo1", **fields)
    return store


def _run_commits(client, files, **kwargs):
    saved = {}

    def loader(path):
        return files.get(path)

    def saver(data, path, **kw):
        saved[path] = data
        return path

    with patch("coops.bronze.commits.load_json_data", side_effect=loader), patch("coops.bronze.commits.save_json_data", side_effect=saver):
        extract_commits(client, MagicMock(), **kwargs)
    return saved


class TestIncrementalCommits:
    def test_watermark_since_bounds_graphql_and_disables_chunking(self):
        client = MagicMock()
        client.graphql_commit_history.return_value = ([], {})
        client.get_paginated.return_value = []
        wm = _store(last_run="2026-09-21T00:00:00Z")

        _run_commits(
            client,
            {"data/bronze/repositories_filtered.json": REPOS},
            method="graphql",
            watermarks=wm,
        )

        kwargs = client.graphql_commit_history.call_args[1]
        assert kwargs["since"] == "2026-09-21T00:00:00Z"
        # A short incremental window must not be split into time chunks.
        assert kwargs["split_large_extractions"] is False

    def test_new_commits_prepended_and_duplicates_dropped(self):
        client = MagicMock()
        client.get_paginated.return_value = [
            {
                "sha": "new1",
                "author": {"login": "a", "id": 1},
                "commit": {"author": {"name": "A", "email": "a@x.com", "date": "2026-09-23T00:00:00Z"}, "message": "new"},
            },
            {
                "sha": "old1",
                "author": {"login": "a", "id": 1},
                "commit": {"author": {"name": "A", "email": "a@x.com", "date": "2026-09-22T00:00:00Z"}, "message": "old"},
            },
        ]
        client.get_with_cache.return_value = {"stats": {"additions": 1, "deletions": 0, "total": 1}}
        prior = [
            {"sha": "old1", "author": {"login": "a", "id": 1}, "commit": {"author": {"name": "A", "date": "2026-09-22T00:00:00Z"}, "message": "old"}, "repo_name": "repo1", "parents": [], "additions": 1, "deletions": 0, "total_changes": 1},
            {"sha": "old2", "author": {"login": "b", "id": 2}, "commit": {"author": {"name": "B", "date": "2026-09-21T00:00:00Z"}, "message": "old2"}, "repo_name": "repo1", "parents": [], "additions": 1, "deletions": 0, "total_changes": 1},
        ]
        wm = _store(last_run="2026-09-23T00:00:00Z")
        files = {
            "data/bronze/repositories_filtered.json": REPOS,
            "data/bronze/commits_repo1.json": [{"_metadata": {}}, *prior],
        }

        saved = _run_commits(client, files, method="rest", watermarks=wm)

        merged = saved["data/bronze/commits_repo1.json"]
        assert [c["sha"] for c in merged] == ["new1", "old1", "old2"]
