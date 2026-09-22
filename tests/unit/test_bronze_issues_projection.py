"""The stored issue/PR record is built from named fields, not copied.

`data/bronze/` is a publish boundary — fork-and-forget commits it to a public
branch — so these tests assert the SHAPE of the record (only whitelisted keys
survive) rather than the absence of particular bad fields. A shape assertion
still holds when the provider adds a field nobody has seen yet; an absence
assertion does not.
"""
import json
import re
from unittest.mock import MagicMock, patch

from coops.bronze.issues import (
    extract_issues,
    ACTOR_FIELDS,
    ISSUE_FIELDS,
    _project_actor,
    _project_issue,
)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Shaped like a real REST issue, including the fields that carried every
# address found in published data.
RAW_ISSUE = {
    "number": 42,
    "state": "closed",
    "title": "Fix the thing",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-02T00:00:00Z",
    "closed_at": "2026-01-03T00:00:00Z",
    "body": "Ping me at dev@example.com if this breaks",
    "milestone": {"title": "v1", "description": "owner: lead@example.com"},
    "labels": [{"name": "bug"}],
    "html_url": "https://github.com/o/r/issues/42",
    "user": {
        "login": "octocat",
        "id": 1,
        "gravatar_id": "205e460b479e2e5b48aec07710c08d50",
        "url": "https://api.github.com/users/octocat",
    },
    "assignee": {"login": "hubber", "id": 2, "gravatar_id": ""},
}


def test_record_contains_only_whitelisted_keys():
    record = _project_issue(RAW_ISSUE, "acme/widget")
    assert set(record) <= set(ISSUE_FIELDS) | {"user", "assignee", "repo_name"}


def test_no_address_survives_projection():
    # Control: the probe must find the addresses before projection, or a clean
    # result afterwards would prove nothing.
    assert len(EMAIL.findall(json.dumps(RAW_ISSUE))) == 2

    record = _project_issue(RAW_ISSUE, "acme/widget")
    assert EMAIL.findall(json.dumps(record)) == []


def test_fields_every_consumer_reads_are_preserved():
    record = _project_issue(RAW_ISSUE, "acme/widget")
    assert record["number"] == 42
    assert record["state"] == "closed"
    assert record["title"] == "Fix the thing"           # ai_analysis reads this
    assert record["created_at"] == "2026-01-01T00:00:00Z"
    assert record["updated_at"] == "2026-01-02T00:00:00Z"
    assert record["closed_at"] == "2026-01-03T00:00:00Z"
    assert record["user"]["login"] == "octocat"
    assert record["assignee"]["login"] == "hubber"
    assert record["repo_name"] == "acme/widget"


def test_actor_is_trimmed_one_level_down():
    # gravatar_id is historically md5(email); a top-level-only whitelist would
    # leave the same class of problem nested inside the user object.
    actor = _project_actor(RAW_ISSUE["user"])
    assert set(actor) <= set(ACTOR_FIELDS)
    assert "gravatar_id" not in actor


def test_missing_optional_fields_do_not_invent_values():
    # An open issue has closed_at absent, and an unassigned one has no
    # assignee. Neither may become a fabricated value.
    record = _project_issue({"number": 7, "state": "open"}, "acme/widget")
    assert "closed_at" not in record
    assert record["assignee"] is None


def test_unassigned_is_none_not_empty_dict():
    # collaboration_networks and contribution_metrics branch on assignee being
    # falsy; an empty dict is falsy too, but None is what the provider sends
    # and what the consumers were written against.
    record = _project_issue({**RAW_ISSUE, "assignee": None}, "acme/widget")
    assert record["assignee"] is None


def test_pull_request_split_survives_the_projection():
    """The issues/PRs split keys on `pull_request`, which the whitelist drops.

    That works only because the classification reads the RAW object before
    projecting. If a refactor ever projects first and classifies second, every
    pull request files as an issue: no exception, no empty field, two wrong
    datasets.

    This drives `extract_issues` end to end, so it fails under that reversal.
    An earlier version of this test asserted only that the raw object carries
    `pull_request` and the projected record does not — which pins the DROP and
    passes happily under the very mutation it claimed to guard.
    """
    raw = [
        {"number": 1, "state": "open", "title": "an issue",
         "user": {"login": "a"}, "created_at": "2026-01-01T00:00:00Z"},
        {"number": 2, "state": "open", "title": "a pull request",
         "user": {"login": "b"}, "created_at": "2026-01-02T00:00:00Z",
         "pull_request": {"url": "https://api.github.com/..."}},
    ]

    client = MagicMock()
    client.get_paginated.side_effect = [list(raw), []]  # issues, then events
    saved = {}

    def capture_save(data, path):
        saved[path] = data
        return path

    with patch("coops.bronze.issues.load_json_data",
               return_value=[{"name": "repo1", "full_name": "acme/repo1"}]):
        with patch("coops.bronze.issues.save_json_data", side_effect=capture_save):
            extract_issues(client, MagicMock())

    issues = saved["data/bronze/issues_repo1.json"]
    prs = saved["data/bronze/prs_repo1.json"]

    assert [i["number"] for i in issues] == [1], "the issue must not be filed as a PR"
    assert [p["number"] for p in prs] == [2], "the pull request must not be filed as an issue"

    # And the discriminator itself is still dropped from what gets published.
    assert all("pull_request" not in r for r in issues + prs)
