"""The stored issue/PR/event record is built from named fields, not copied.

`data/bronze/` is a publish boundary — fork-and-forget commits it to a public
branch — so these tests assert the SHAPE of the record (only whitelisted keys
survive) rather than the absence of particular bad fields. A shape assertion
still holds when the provider adds a field nobody has seen yet; an absence
assertion does not.

Since the #30 wiring, the issue/PR record is built in two whitelisted steps
on the live path: the GitHub mapper (`map_issue`/`map_pull_request`, named
fields only — `body` and `milestone` are never read) and
`BronzeService._conversation_record`. The event record is still projected by
`coops.bronze.issues._project_event`, the family the source port cannot
express (#239). Both halves are pinned here, at the same boundary the old
extractor-level tests pinned.
"""
import json
import re
from unittest.mock import patch

from coops.bronze.bronze_service import _conversation_record
from coops.bronze.issues import _load_prior_records, _project_event
from coops.domain.tenancy import resolve_tenant
from coops.github.mapper import map_issue, map_pull_request

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_TENANT = resolve_tenant("single", "acme")
_ACCOUNT = _TENANT.accounts[0]

# Shaped like a real REST issue, including the fields that carried every
# address found in published data.
RAW_ISSUE = {
    "id": 424242,
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


def _record(raw):
    """The stored record for ``raw``, through the live two-step projection."""
    if raw.get("pull_request"):
        model = map_pull_request(raw, _TENANT.id, _ACCOUNT, "acme/widget")
    else:
        model = map_issue(raw, _TENANT.id, _ACCOUNT, "acme/widget")
    return _conversation_record(model)


def test_record_contains_only_whitelisted_keys():
    record = _record(RAW_ISSUE)
    assert set(record) == {
        "number", "state", "title", "created_at", "updated_at", "closed_at",
        "user", "assignee", "repo_name",
    }


def test_no_address_survives_projection():
    # Control: the probe must find the addresses before projection, or a clean
    # result afterwards would prove nothing.
    assert len(EMAIL.findall(json.dumps(RAW_ISSUE))) == 2

    assert EMAIL.findall(json.dumps(_record(RAW_ISSUE))) == []


def test_fields_every_consumer_reads_are_preserved():
    record = _record(RAW_ISSUE)
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
    actor = _record(RAW_ISSUE)["user"]
    assert set(actor) <= {"login", "id", "name"}
    assert "gravatar_id" not in actor


def test_missing_optional_fields_do_not_invent_values():
    # An open issue has closed_at absent, and an unassigned one has no
    # assignee. Neither may become a fabricated value.
    record = _record({"id": 8, "number": 7, "state": "open"})
    assert record["closed_at"] is None
    assert record["assignee"] is None


def test_unassigned_is_none_not_empty_dict():
    # collaboration_networks and contribution_metrics branch on assignee being
    # falsy; an empty dict is falsy too, but None is what the provider sends
    # and what the consumers were written against.
    record = _record({**RAW_ISSUE, "assignee": None})
    assert record["assignee"] is None


def test_issue_and_pr_projections_carry_the_same_whitelist():
    """The split lives behind the port; both halves must publish the same
    shape, or a PR looks like a different kind of record to Silver."""
    pr = _record({**RAW_ISSUE,
                  "pull_request": {"url": "https://api.github.com/o/r/pulls/42",
                                   "merged_at": None}})
    issue = _record(RAW_ISSUE)
    assert set(pr) == set(issue)


# ---------------------------------------------------------------------------
# events — still projected by the legacy module (#239)
# ---------------------------------------------------------------------------


RAW_EVENT = {
    "id": 5,
    "event": "assigned",
    "created_at": "2026-01-02T00:00:00Z",
    "actor": {"login": "octocat", "id": 1, "gravatar_id": ""},
    "issue": {"number": 42, "title": "Fix the thing"},
    "url": "https://api.github.com/repos/acme/widget/issues/events/5",
}


def test_event_record_contains_only_whitelisted_keys():
    record = _project_event(RAW_EVENT, "acme/widget")
    assert set(record) == {"id", "event", "created_at", "repo_name", "actor", "issue"}
    assert record["actor"] == {"login": "octocat"}
    assert record["issue"] == {"number": 42}


def test_prior_event_records_are_reprojected_on_load():
    """A stale record already on disk is re-projected when read back.

    Without this, the whitelist is only a guarantee about *writes*: an
    incremental run appends prior records after re-projection today, but a
    refactor that stops passing the projector would keep whatever shape a
    record was first written with.
    """
    stale = [
        {"_metadata": {"generated_at": "2026-01-01T00:00:00Z"}},
        {
            "id": 7,
            "event": "closed",
            "created_at": "2026-01-01T00:00:00Z",
            "repo_name": "repoA",
            # Fields the projection must strip on the next read:
            "label": {"name": "bug"},
            "actor": {"login": "alice", "gravatar_id": "d41d8cd9"},
            "issue": {"number": 1, "title": "extra"},
        },
    ]
    with patch("coops.bronze.issues.load_json_data", return_value=stale):
        out = _load_prior_records("data/bronze/issue_events_repoA.json", _project_event)

    assert len(out) == 1, "the _metadata sidecar must not survive as a record"
    record = out[0]
    assert set(record) == {"id", "event", "created_at", "repo_name", "actor", "issue"}
    assert record["actor"] == {"login": "alice"}
    assert record["issue"] == {"number": 1}


def test_prior_records_load_verbatim_without_a_projector():
    """`project=None` keeps the old behaviour, so the parameter is what changes it."""
    stale = [{"id": 7, "label": "kept", "repo_name": "repoA"}]
    with patch("coops.bronze.issues.load_json_data", return_value=stale):
        out = _load_prior_records("data/bronze/issue_events_repoA.json")
    assert out[0]["label"] == "kept"
