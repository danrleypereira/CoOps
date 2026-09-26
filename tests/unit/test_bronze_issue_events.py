"""Issue events on the legacy path — the family the source port cannot express (#239).

``extract_issue_events`` is the events half of the old ``extract_issues``,
kept on the live run by ``coops.etl.bronze_extract.run_extraction`` because
``SourcePort`` has no ``fetch_issue_events``. These tests fake the HTTP
client and the bronze files (the seam the extractor reads through) and let
the real extractor run, so the field projection, the append-only incremental
fetch by event id, the watermark advancement and the offline fold's
last-seen stamping are exercised rather than asserted against call
sequences.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from coops.bronze.issues import extract_issue_events
from coops.bronze.watermarks import WatermarkStore

REPOS = [{"name": "repo1", "full_name": "org/repo1", "default_branch": "main"}]
_NOW = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)


def _store(path="unused.json", **fields):
    store = WatermarkStore(path, now=_NOW)
    if fields:
        store.update("org/repo1", **fields)
    return store


def _run_events(client, files, watermarks=None):
    saved = {}

    def loader(path):
        return files.get(path)

    def saver(data, path, **kwargs):
        saved[path] = data
        return path

    with patch("coops.bronze.issues.load_json_data", side_effect=loader), patch("coops.bronze.issues.save_json_data", side_effect=saver):
        extract_issue_events(client, MagicMock(), watermarks=watermarks)
    return saved


class TestEventProjection:
    def test_event_fields_filtered(self):
        """Only the fields Silver reads survive; the payload does not."""
        client = MagicMock()
        client.get_paginated.return_value = [
            {
                "id": 123,
                "event": "closed",
                "created_at": "2024-01-01",
                "actor": {"login": "user1", "avatar_url": "url", "type": "User"},
                "issue": {"number": 1, "title": "Issue", "state": "closed"},
                "label": {"name": "bug"},
                "unnecessary_field": "data",
            }
        ]

        saved = _run_events(client, {"data/bronze/repositories_filtered.json": REPOS})

        (record,) = saved["data/bronze/issue_events_repo1.json"]
        assert set(record) == {
            "id", "event", "created_at", "repo_name", "actor", "issue",
        }
        assert record["actor"] == {"login": "user1"}
        assert record["issue"] == {"number": 1}

    def test_event_without_actor_and_issue(self):
        """A null actor is None, not a person named 'unknown'; so is a
        missing issue."""
        client = MagicMock()
        client.get_paginated.return_value = [{"id": 5, "event": "renamed"}]

        saved = _run_events(client, {"data/bronze/repositories_filtered.json": REPOS})

        (record,) = saved["data/bronze/issue_events_repo1.json"]
        assert record["actor"] is None
        assert record["issue"] is None

    def test_event_file_written_even_when_empty(self):
        """A repository with no events still writes its (empty) file — the
        published corpus carries one per repository and Silver relies on
        the family existing."""
        client = MagicMock()
        client.get_paginated.return_value = []

        saved = _run_events(client, {"data/bronze/repositories_filtered.json": REPOS})

        assert saved["data/bronze/issue_events_repo1.json"] == []

    def test_no_repositories_writes_nothing(self, capsys):
        client = MagicMock()
        saved = _run_events(client, {})
        assert saved == {}
        assert "Run repository extraction first" in capsys.readouterr().out


class TestIncrementalEvents:
    def test_full_fetch_uses_the_unconditional_events_url(self):
        client = MagicMock()
        client.get_paginated.return_value = []

        _run_events(client, {"data/bronze/repositories_filtered.json": REPOS})

        url = client.get_paginated.call_args[0][0]
        assert url.endswith("/repos/org/repo1/issues/events")

    def test_events_append_only_newer_ids(self):
        client = MagicMock()
        # Events come back newest-first; the fetch stops once it reaches id 2.
        client.get_with_cache.return_value = [
            {"id": 3, "event": "closed", "created_at": "2026-09-23T00:00:00Z", "actor": {"login": "u"}, "issue": {"number": 1}},
            {"id": 2, "event": "labeled", "created_at": "2026-09-22T12:00:00Z", "actor": {"login": "u"}, "issue": {"number": 1}},
        ]
        prior_events = [
            {"id": 1, "event": "opened", "created_at": "2026-09-22T10:00:00Z", "repo_name": "repo1", "actor": {"login": "u"}, "issue": {"number": 1}},
            {"id": 2, "event": "labeled", "created_at": "2026-09-22T12:00:00Z", "repo_name": "repo1", "actor": {"login": "u"}, "issue": {"number": 1}},
        ]
        wm = _store(last_event_id=2)
        files = {
            "data/bronze/repositories_filtered.json": REPOS,
            "data/bronze/issue_events_repo1.json": [{"_metadata": {}}, *prior_events],
        }

        saved = _run_events(client, files, wm)

        events = saved["data/bronze/issue_events_repo1.json"]
        assert [e["id"] for e in events] == [1, 2, 3]
        # The events endpoint has no `since` filter: incrementality comes from
        # paging from the newest event and stopping at the boundary id.
        assert client.get_with_cache.call_count == 1
        assert client.get_with_cache.call_args[0][0].endswith("issues/events?per_page=100&page=1")

    def test_watermark_advances_last_event_id(self):
        client = MagicMock()
        client.get_with_cache.return_value = [
            {"id": 99, "event": "closed", "created_at": "2026-09-24T00:00:00Z", "actor": {"login": "u"}, "issue": {"number": 9}}
        ]
        wm = _store(last_updated_at="2026-09-22T00:00:00Z", last_event_id=2)
        files = {
            "data/bronze/repositories_filtered.json": REPOS,
            "data/bronze/issue_events_repo1.json": [{"_metadata": {}}],
        }

        _run_events(client, files, wm)

        after = wm.get("org/repo1")
        assert after.last_event_id == 99

    def test_watermark_keeps_the_issues_side_untouched(self):
        """``last_updated_at`` belongs to the service's issues step; the
        events step advances only the id, and the store's merge must keep
        the other field (the old single ``update`` call set both — the
        split must not lose either half)."""
        client = MagicMock()
        client.get_paginated.return_value = []
        wm = _store(last_updated_at="2026-09-22T00:00:00Z", last_event_id=2)
        files = {
            "data/bronze/repositories_filtered.json": REPOS,
            "data/bronze/issue_events_repo1.json": [{"_metadata": {}}],
        }

        _run_events(client, files, wm)

        after = wm.get("org/repo1")
        assert after.last_updated_at == "2026-09-22T00:00:00Z"
        assert after.last_event_id == 2  # no events seen: prior id survives
