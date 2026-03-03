"""Tests for src/silver/members_statistics.py — process_members_statistics."""

import silver.members_statistics as ms


def _make_helpers(monkeypatch, *, commits=None, issues=None, prs=None, events=None):
    """Wire up fake load/save for the module under test."""
    commits = commits or []
    issues = issues or []
    prs = prs or []
    events = events or []

    def fake_load(path):
        if "commits_all" in path:
            return commits
        if "issues_all" in path:
            return issues
        if "prs_all" in path:
            return prs
        if "issue_events_all" in path:
            return events
        return []

    saved = {}

    def fake_save(data, path, timestamp=True):
        saved[path] = data
        return path

    monkeypatch.setattr(ms, "load_json_data", fake_load)
    monkeypatch.setattr(ms, "save_json_data", fake_save)
    return saved


# ---------------------------------------------------------------------------
# Empty / trivial data
# ---------------------------------------------------------------------------

class TestEmptyData:
    def test_all_empty(self, monkeypatch):
        saved = _make_helpers(monkeypatch)
        files = ms.process_members_statistics()
        assert any("members_statistics" in f for f in files)
        assert saved["data/silver/members_statistics.json"] == []

    def test_commits_only_no_date(self, monkeypatch):
        """Commits without a parseable date should be skipped."""
        saved = _make_helpers(monkeypatch, commits=[
            {"commit": {"author": {"name": "alice"}}, "author": {"login": "alice"}}
        ])
        ms.process_members_statistics()
        assert saved["data/silver/members_statistics.json"] == []


# ---------------------------------------------------------------------------
# Commit processing
# ---------------------------------------------------------------------------

class TestCommitProcessing:
    def test_basic_commit(self, monkeypatch):
        saved = _make_helpers(monkeypatch, commits=[
            {
                "commit": {"author": {"date": "2024-01-01T10:00:00Z", "name": "Alice"}},
                "author": {"login": "alice"},
                "repo_name": "repo1",
            },
            {
                "commit": {"author": {"date": "2024-01-15T10:00:00Z", "name": "Alice"}},
                "author": {"login": "alice"},
                "repo_name": "repo1",
            },
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert len(stats) == 1
        assert stats[0]["name"] == "alice"
        assert stats[0]["total_commits"] == 2
        assert stats[0]["repos"] == ["repo1"]

    def test_commit_author_login_fallback(self, monkeypatch):
        """When commit.author has no login, fall back to top-level author.login."""
        saved = _make_helpers(monkeypatch, commits=[
            {
                "commit": {"author": {"date": "2024-03-01T00:00:00Z"}},
                "author": {"login": "bob"},
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert len(stats) == 1
        assert stats[0]["name"] == "bob"

    def test_commit_name_fallback(self, monkeypatch):
        """Fall back to commit.author.name when no login available."""
        saved = _make_helpers(monkeypatch, commits=[
            {
                "commit": {"author": {"date": "2024-03-01T00:00:00Z", "name": "Charlie"}},
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert len(stats) == 1
        assert stats[0]["name"] == "Charlie"


# ---------------------------------------------------------------------------
# Bot filtering
# ---------------------------------------------------------------------------

class TestBotFiltering:
    def test_bot_user_filtered_from_commits(self, monkeypatch):
        saved = _make_helpers(monkeypatch, commits=[
            {
                "commit": {"author": {"date": "2024-01-01T00:00:00Z"}},
                "author": {"login": "dependabot[bot]"},
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        assert saved["data/silver/members_statistics.json"] == []

    def test_bot_user_filtered_from_issues(self, monkeypatch):
        saved = _make_helpers(monkeypatch, issues=[
            {
                "user": {"login": "renovate[bot]"},
                "created_at": "2024-01-01T00:00:00Z",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        assert saved["data/silver/members_statistics.json"] == []

    def test_bot_user_filtered_from_prs(self, monkeypatch):
        saved = _make_helpers(monkeypatch, prs=[
            {
                "user": {"login": "github-actions[bot]"},
                "created_at": "2024-01-01T00:00:00Z",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        assert saved["data/silver/members_statistics.json"] == []

    def test_bot_user_filtered_from_events(self, monkeypatch):
        saved = _make_helpers(monkeypatch, events=[
            {
                "actor": {"login": "codecov[bot]"},
                "created_at": "2024-01-01T00:00:00Z",
                "event": "commented",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        assert saved["data/silver/members_statistics.json"] == []


# ---------------------------------------------------------------------------
# Unknown user handling
# ---------------------------------------------------------------------------

class TestUnknownUser:
    def test_unknown_commit_author_skipped(self, monkeypatch):
        """Commits where no identifier can be resolved → 'unknown' → skipped."""
        saved = _make_helpers(monkeypatch, commits=[
            {
                "commit": {"author": {"date": "2024-01-01T00:00:00Z"}},
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        assert saved["data/silver/members_statistics.json"] == []

    def test_unknown_issue_user_skipped(self, monkeypatch):
        saved = _make_helpers(monkeypatch, issues=[
            {"user": {}, "created_at": "2024-01-01T00:00:00Z", "repo_name": "r1"}
        ])
        ms.process_members_statistics()
        assert saved["data/silver/members_statistics.json"] == []


# ---------------------------------------------------------------------------
# Issue processing
# ---------------------------------------------------------------------------

class TestIssueProcessing:
    def test_issue_created_and_closed(self, monkeypatch):
        saved = _make_helpers(monkeypatch, issues=[
            {
                "user": {"login": "alice"},
                "created_at": "2024-01-01T00:00:00Z",
                "state": "closed",
                "closed_at": "2024-01-10T00:00:00Z",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert len(stats) == 1
        assert stats[0]["total_issues_created"] == 1
        assert stats[0]["total_issues_closed"] == 1

    def test_closed_issue_uses_updated_at_fallback(self, monkeypatch):
        """When closed_at is missing, updated_at is used."""
        saved = _make_helpers(monkeypatch, issues=[
            {
                "user": {"login": "alice"},
                "created_at": "2024-01-01T00:00:00Z",
                "state": "closed",
                "updated_at": "2024-01-05T00:00:00Z",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["total_issues_closed"] == 1


# ---------------------------------------------------------------------------
# PR processing
# ---------------------------------------------------------------------------

class TestPRProcessing:
    def test_pr_created_and_closed(self, monkeypatch):
        saved = _make_helpers(monkeypatch, prs=[
            {
                "user": {"login": "bob"},
                "created_at": "2024-02-01T00:00:00Z",
                "state": "closed",
                "closed_at": "2024-02-15T00:00:00Z",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["total_prs_created"] == 1
        assert stats[0]["total_prs_closed"] == 1


# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------

class TestEventProcessing:
    def test_comment_event_counted(self, monkeypatch):
        saved = _make_helpers(monkeypatch, events=[
            {
                "actor": {"login": "alice"},
                "created_at": "2024-03-01T00:00:00Z",
                "event": "commented",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["total_comments"] == 1

    def test_non_comment_event_not_counted(self, monkeypatch):
        saved = _make_helpers(monkeypatch, events=[
            {
                "actor": {"login": "alice"},
                "created_at": "2024-03-01T00:00:00Z",
                "event": "labeled",
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["total_comments"] == 0
        assert stats[0]["total_events"] == 1

    def test_repos_deduplicated_across_events(self, monkeypatch):
        saved = _make_helpers(monkeypatch, events=[
            {"actor": {"login": "alice"}, "created_at": "2024-03-01T00:00:00Z",
             "event": "commented", "repo_name": "r1"},
            {"actor": {"login": "alice"}, "created_at": "2024-03-02T00:00:00Z",
             "event": "commented", "repo_name": "r1"},
            {"actor": {"login": "alice"}, "created_at": "2024-03-03T00:00:00Z",
             "event": "labeled", "repo_name": "r2"},
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["repos_count"] == 2
        assert set(stats[0]["repos"]) == {"r1", "r2"}


# ---------------------------------------------------------------------------
# Activity period & weekly averages
# ---------------------------------------------------------------------------

class TestActivityPeriod:
    def test_zero_activity_period_clamped(self, monkeypatch):
        """When first == last activity the period clamps to 0.1 weeks."""
        saved = _make_helpers(monkeypatch, commits=[
            {
                "commit": {"author": {"date": "2024-06-01T12:00:00Z"}},
                "author": {"login": "alice"},
                "repo_name": "r1",
            }
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["activity_period"]["weeks"] == 0.1
        assert stats[0]["avg_weekly_activity"] == 10.0  # 1 event / 0.1

    def test_multi_week_period(self, monkeypatch):
        saved = _make_helpers(monkeypatch, commits=[
            {"commit": {"author": {"date": "2024-01-01T00:00:00Z"}},
             "author": {"login": "alice"}, "repo_name": "r1"},
            {"commit": {"author": {"date": "2024-01-15T00:00:00Z"}},
             "author": {"login": "alice"}, "repo_name": "r1"},
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["activity_period"]["days"] == 14
        assert stats[0]["activity_period"]["weeks"] == 2.0
        assert stats[0]["avg_weekly_activity"] == 1.0  # 2 events / 2 weeks


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

class TestSorting:
    def test_sorted_by_avg_weekly_activity_desc(self, monkeypatch):
        """Members are sorted by avg_weekly_activity descending."""
        saved = _make_helpers(monkeypatch, commits=[
            # alice: 1 event in 0.1 weeks → 10.0
            {"commit": {"author": {"date": "2024-01-01T00:00:00Z"}},
             "author": {"login": "alice"}, "repo_name": "r1"},
            # bob: 2 events in 2 weeks → 1.0
            {"commit": {"author": {"date": "2024-01-01T00:00:00Z"}},
             "author": {"login": "bob"}, "repo_name": "r1"},
            {"commit": {"author": {"date": "2024-01-15T00:00:00Z"}},
             "author": {"login": "bob"}, "repo_name": "r1"},
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert stats[0]["name"] == "alice"
        assert stats[1]["name"] == "bob"
        assert stats[0]["avg_weekly_activity"] > stats[1]["avg_weekly_activity"]


# ---------------------------------------------------------------------------
# Metadata stripping
# ---------------------------------------------------------------------------

class TestMetadataStripping:
    def test_metadata_stripped_from_inputs(self, monkeypatch):
        saved = _make_helpers(monkeypatch, commits=[
            {"_metadata": {"ts": "2024-01-01"}},  # should be stripped
            {"commit": {"author": {"date": "2024-06-01T00:00:00Z"}},
             "author": {"login": "alice"}, "repo_name": "r1"},
        ])
        ms.process_members_statistics()
        stats = saved["data/silver/members_statistics.json"]
        assert len(stats) == 1
        assert stats[0]["name"] == "alice"
