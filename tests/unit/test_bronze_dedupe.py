"""Dedupe by repository id at the reader (#248).

Every fixture is built under ``tmp_path``. The measured case this module
exists for is the live pair — ``repo_2025-1-NoFluxoUNB.json`` and
``repo_2025-1-NoFluxoUnB.json``, both carrying repository id ``957040204``,
7 days apart in ``_metadata.extracted_at``, with published totals doubled
(commits 1,239 + 1,219, issues 117 + 109, prs 70 + 61,
issue_events 1,414 + 1,336) — and the fixtures below reproduce its shape,
including the mixed naive/aware stamps the winner rule has to survive.

Fixture discipline: the ``repo_`` fixtures are built at the width a real
GitHub repository object carries (100 keys, of which the dedupe reads one —
``id``). A fixture whose key set were only what the code under test reads
could not disagree with it: that exact trap made two of #30's twelve
"byte-identical" families green by construction. Field NAMES come from the
provider schema; every VALUE is a dummy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from coops.bronze.dedupe import (
    REASON_NO_SIBLING,
    REASON_SIBLING_NO_ID,
    write_report,
)
from coops.bronze.files import bronze_dedupe_report, bronze_files, bronze_records

# --------------------------------------------------------------------------
# The live pair, as measured (#248).
# --------------------------------------------------------------------------

#: The repository id both spellings of the recased repository carry.
LIVE_ID = 957040204

#: What the pipeline writes today (current case), and what it stopped
#: writing when the repository was recased (the orphan, never rewritten).
CURRENT = "2025-1-NoFluxoUnB"
ORPHAN = "2025-1-NoFluxoUNB"

#: The stamps exactly as the live pair holds them: the current file was
#: written by the post-#143 UTC-aware writer, the orphan by the pre-#143
#: naive one — 7 days apart.
CURRENT_STAMP = "2026-09-25T09:53:03.135878+00:00"
ORPHAN_STAMP = "2026-09-18T09:15:46.896528"

#: What each copy of the live pair contributes (current / orphan).
LIVE_COUNTS = {"commits": 1239, "issues": 117, "prs": 70, "issue_events": 1414}
ORPHAN_COUNTS = {"commits": 1219, "issues": 109, "prs": 61, "issue_events": 1336}


@pytest.fixture()
def bronze(tmp_path: Path) -> Path:
    directory = tmp_path / "data" / "bronze"
    directory.mkdir(parents=True)
    return directory


# --------------------------------------------------------------------------
# Fixture builders: the producer's shapes, not the reader's vocabulary.
# --------------------------------------------------------------------------


def _repo_document(repository_id: int, name: str) -> dict[str, Any]:
    """A GitHub repository object at its real width: 100 keys.

    The dedupe reads one of them (``id``). Building the fixture from only
    the keys the code reads is the trap this builder exists to avoid — see
    the module docstring — so the width is asserted where it is used.
    """
    full_name = f"unb-mds/{name}"
    api = f"https://api.github.com/repos/{full_name}"
    return {
        "id": repository_id,
        "node_id": "R_kgDONxPlcw",
        "name": name,
        "full_name": full_name,
        "private": False,
        "owner": {
            "login": "unb-mds",
            "id": 555_555_001,
            "node_id": "MDEyOk9yZ2FuaXphdGlvbjU1NQ",
            "type": "Organization",
            "site_admin": False,
        },
        "html_url": f"https://github.com/{full_name}",
        "description": "dummy description for the fixture",
        "fork": False,
        "url": api,
        "forks_url": f"{api}/forks",
        "keys_url": f"{api}/keys{{/key_id}}",
        "collaborators_url": f"{api}/collaborators{{/collaborator}}",
        "teams_url": f"{api}/teams",
        "hooks_url": f"{api}/hooks",
        "issue_events_url": f"{api}/issues/events{{/number}}",
        "events_url": f"{api}/events",
        "assignees_url": f"{api}/assignees{{/user}}",
        "branches_url": f"{api}/branches{{/branch}}",
        "tags_url": f"{api}/tags",
        "blobs_url": f"{api}/git/blobs{{/sha}}",
        "git_tags_url": f"{api}/git/tags{{/sha}}",
        "git_refs_url": f"{api}/git/refs{{/sha}}",
        "trees_url": f"{api}/git/trees{{/sha}}",
        "statuses_url": f"{api}/statuses/{{sha}}",
        "languages_url": f"{api}/languages",
        "stargazers_url": f"{api}/stargazers",
        "contributors_url": f"{api}/contributors",
        "subscribers_url": f"{api}/subscribers",
        "subscription_url": f"{api}/subscription",
        "commits_url": f"{api}/commits{{/sha}}",
        "git_commits_url": f"{api}/git/commits{{/sha}}",
        "comments_url": f"{api}/comments{{/number}}",
        "issue_comment_url": f"{api}/issues/comments{{/number}}",
        "contents_url": f"{api}/contents/{{+path}}",
        "compare_url": f"{api}/compare/{{base}}...{{head}}",
        "merges_url": f"{api}/merges",
        "archive_url": f"{api}/{{archive_format}}{{/ref}}",
        "downloads_url": f"{api}/downloads",
        "issues_url": f"{api}/issues{{/number}}",
        "pulls_url": f"{api}/pulls{{/number}}",
        "milestones_url": f"{api}/milestones{{/number}}",
        "notifications_url": f"{api}/notifications{{?since,all,participating}}",
        "labels_url": f"{api}/labels{{/name}}",
        "releases_url": f"{api}/releases{{/id}}",
        "deployments_url": f"{api}/deployments",
        "created_at": "2025-03-01T12:00:00Z",
        "updated_at": "2026-09-01T12:00:00Z",
        "pushed_at": "2026-09-20T12:00:00Z",
        "git_url": f"git://github.com/{full_name}.git",
        "ssh_url": f"git@github.com:{full_name}.git",
        "clone_url": f"https://github.com/{full_name}.git",
        "svn_url": f"https://github.com/{full_name}",
        "homepage": "",
        "size": 1234,
        "stargazers_count": 2,
        "watchers_count": 2,
        "language": "Python",
        "has_issues": True,
        "has_projects": True,
        "has_downloads": True,
        "has_wiki": True,
        "has_pages": False,
        "has_discussions": False,
        "forks_count": 1,
        "mirror_url": None,
        "archived": False,
        "disabled": False,
        "open_issues_count": 3,
        "license": {
            "key": "gpl-3.0",
            "name": "GNU General Public License v3.0",
            "spdx_id": "GPL-3.0-or-later",
            "url": "https://api.github.com/licenses/gpl-3.0",
            "node_id": "MDc6TGljZW5zZTA=",
        },
        "allow_forking": True,
        "is_template": False,
        "web_commit_signoff_required": False,
        "topics": ["education", "github-api"],
        "visibility": "public",
        "forks": 1,
        "open_issues": 3,
        "watchers": 2,
        "default_branch": "main",
        "permissions": {
            "admin": False,
            "maintain": False,
            "push": False,
            "triage": False,
            "pull": True,
        },
        "allow_squash_merge": True,
        "allow_merge_commit": True,
        "allow_rebase_merge": True,
        "allow_auto_merge": False,
        "allow_update_branch": False,
        "delete_branch_on_merge": False,
        "squash_merge_commit_title": "PR_TITLE",
        "squash_merge_commit_message": "COMMIT_MESSAGES",
        "merge_commit_title": "MERGE_MESSAGE",
        "merge_commit_message": "PR_TITLE",
        "required_linear_history": False,
        "enable_automated_security_fixes": True,
        "enable_vulnerability_alerts": True,
        "security_and_analysis": {
            "advanced_security": {"status": "disabled"},
            "secret_scanning": {"status": "disabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
        },
        "code_of_conduct": {
            "key": "gpl-3.0",
            "name": "GNU General Public License v3.0",
            "url": f"{api}/community/code_of_conduct",
            "node_id": "MDc6Q29kZU9mQ29uZHVjdGdmZQ",
        },
        "role_name": None,
        "network_count": 3,
        "temp_clone_token": None,
        "organization": {
            "login": "unb-mds",
            "id": 555_555_001,
            "node_id": "MDEyOk9yZ2FuaXphdGlvbjU1NQ",
            "url": "https://api.github.com/orgs/unb-mds",
            "repos_url": "https://api.github.com/orgs/unb-mds/repos",
            "avatar_url": "https://avatars.githubusercontent.com/u/555555001?v=4",
        },
        "custom_properties": {"semester": "2025-1"},
    }


def _write_repo_file(
    bronze: Path, repo: str, repository_id: int | str | None, stamp: str
) -> Path:
    """A ``repo_<name>.json`` as ``save_json_data`` writes it: the provider
    object with ``_metadata`` merged in."""
    path = bronze / f"repo_{repo}.json"
    document = _repo_document(0, repo)
    document["id"] = repository_id
    payload = {
        **document,
        "_metadata": {"extracted_at": stamp, "file_path": str(path)},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_records_file(
    bronze: Path, family: str, repo: str, records: list[dict], stamp: str
) -> Path:
    """A record-family file as ``save_json_data`` writes it: the
    ``_metadata`` sidecar prepended, records after it."""
    path = bronze / f"{family}_{repo}.json"
    payload = [
        {
            "_metadata": {
                "extracted_at": stamp,
                "file_path": str(path),
                "record_count": len(records),
            }
        },
        *records,
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_empty_records_file(bronze: Path, family: str, repo: str) -> Path:
    """An empty record file: ``save_json_data`` prepends no ``_metadata`` to
    an empty list, so it carries no stamp at all."""
    path = bronze / f"{family}_{repo}.json"
    path.write_text("[]", encoding="utf-8")
    return path


def _write_structure_file(bronze: Path, repo: str, stamp: str) -> Path:
    """A ``structure_<name>.json`` document, carrying both the writer's own
    ``extracted_at`` field and the ``_metadata`` sidecar; the rule reads the
    sidecar's, so the fixture must hold both to be honest."""
    path = bronze / f"structure_{repo}.json"
    payload = {
        "owner": "unb-mds",
        "repository": repo,
        "branch": "main",
        "sha": "0" * 40,
        "tree": [{"path": f"file{index}.py", "type": "blob"} for index in range(2)],
        "truncated": False,
        "extracted_at": stamp,
        "method": "rest",
        "total_items": 2,
        "_metadata": {"extracted_at": stamp, "file_path": str(path)},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _records_for(family: str, count: int) -> list[dict]:
    """Records of ``family``, with the family's identifying key present."""
    if family == "commits":
        return [
            {
                "sha": f"{index:040x}",
                "commit": {
                    "author": {
                        "name": f"author{index % 5}",
                        "date": "2026-09-01T12:00:00Z",
                    }
                },
                "author": {"login": f"user{index % 5}"},
            }
            for index in range(count)
        ]
    if family in {"issues", "prs"}:
        return [
            {
                "number": index,
                "state": "open",
                "user": {"login": f"user{index % 5}"},
                "created_at": "2026-09-01T12:00:00Z",
            }
            for index in range(1, count + 1)
        ]
    if family == "issue_events":
        return [
            {
                "id": 10_000 + index,
                "event": "commented",
                "actor": {"login": f"user{index % 5}"},
            }
            for index in range(count)
        ]
    raise ValueError(f"no record fixture for {family!r}")


def _live_pair(bronze: Path) -> None:
    """The measured corpus shape: one repository, recased, in every family."""
    for family in LIVE_COUNTS:
        _write_records_file(
            bronze, family, CURRENT, _records_for(family, LIVE_COUNTS[family]),
            CURRENT_STAMP,
        )
        _write_records_file(
            bronze, family, ORPHAN, _records_for(family, ORPHAN_COUNTS[family]),
            ORPHAN_STAMP,
        )
    _write_repo_file(bronze, CURRENT, LIVE_ID, CURRENT_STAMP)
    _write_repo_file(bronze, ORPHAN, LIVE_ID, ORPHAN_STAMP)
    _write_structure_file(bronze, CURRENT, CURRENT_STAMP)
    _write_structure_file(bronze, ORPHAN, ORPHAN_STAMP)


# --------------------------------------------------------------------------
# Acceptance 1: the live pair — the newer copy wins, one set is counted.
# --------------------------------------------------------------------------


def test_the_repo_fixture_is_at_a_realistic_width() -> None:
    """The fixture discipline, asserted: a real ``repo_<name>.json`` payload
    carries 99 or 100 keys, of which the dedupe reads one. A fixture built
    only from the keys the code reads cannot disagree with the code — that
    trap made two of #30's twelve "byte-identical" families green by
    construction."""
    assert len(_repo_document(LIVE_ID, CURRENT)) == 100


@pytest.mark.parametrize("family,expected", sorted(LIVE_COUNTS.items()))
def test_the_live_pair_counts_each_family_once(bronze: Path, family, expected) -> None:
    """Two files, same id, 7 days apart: the newer wins, the totals are the
    current copy's alone — 1,239 commits, 117 issues, 70 prs, 1,414 events,
    not the doubled 2,458 / 226 / 131 / 2,750."""
    _live_pair(bronze)

    records = list(bronze_records(bronze, family))

    assert len(records) == expected
    assert {repo for repo, _ in records} == {CURRENT}


def test_the_live_pair_dedupes_the_document_families_on_their_own_payload(
    bronze: Path,
) -> None:
    """The repo family maps through the file itself, so the recased
    ``repo_`` pair and the ``structure_`` pair dedupe like the rest."""
    _live_pair(bronze)

    assert [p.name for p in bronze_files(bronze, "repo")] == [f"repo_{CURRENT}.json"]
    assert [p.name for p in bronze_files(bronze, "structure")] == [
        f"structure_{CURRENT}.json"
    ]


def test_the_live_pair_report_names_the_winner_and_asserts_nothing_is_unmapped(
    bronze: Path,
) -> None:
    """Six deduped groups (four record families + repo + structure), each
    naming its winner — and, explicitly, NOTHING unmapped: a zero that is
    never asserted is indistinguishable from never having looked."""
    _live_pair(bronze)

    report = bronze_dedupe_report(bronze)

    assert len(report.deduped) == 6
    assert report.refused == ()
    by_family = {group.family: group for group in report.deduped}
    for family in (*LIVE_COUNTS, "repo", "structure"):
        assert by_family[family].repository_id == LIVE_ID
        assert by_family[family].winner == f"{family}_{CURRENT}.json"
    # The orphan's copy of every family is named as superseded, so the
    # report says which file stopped being read.
    superseded = {
        facts.name
        for group in report.deduped
        for facts in group.files
        if facts.name != group.winner
    }
    assert superseded == {f"{family}_{ORPHAN}.json" for family in (*LIVE_COUNTS, "repo", "structure")}
    # EXPLICIT zero: every file in this tree maps to an id.
    assert report.unmapped == ()
    assert report.as_dict()["unmapped"]["count"] == 0


# --------------------------------------------------------------------------
# Acceptance 2: a young pair refuses — both kept, the pair reported.
# --------------------------------------------------------------------------


def _young_pair(bronze: Path, older: str, newer: str) -> None:
    """One repository, two spellings, an hour apart — the shape concurrent
    duplicate generation would leave behind."""
    _write_repo_file(bronze, newer, 4242, "2026-09-25T10:00:00+00:00")
    _write_repo_file(bronze, older, 4242, "2026-09-25T09:00:00+00:00")
    _write_records_file(
        bronze, "issues", newer, _records_for("issues", 5), "2026-09-25T10:00:00+00:00"
    )
    _write_records_file(
        bronze, "issues", older, _records_for("issues", 3), "2026-09-25T09:00:00+00:00"
    )


def test_a_pair_one_hour_apart_refuses_and_keeps_both(bronze: Path) -> None:
    """An orphan that young is indistinguishable from concurrent duplicate
    generation: no winner is picked, the double count persists — visibly."""
    _young_pair(bronze, "Beta", "beta")

    found = [p.name for p in bronze_files(bronze, "issues")]

    assert found == ["issues_Beta.json", "issues_beta.json"]
    assert len(list(bronze_records(bronze, "issues"))) == 8  # both, on purpose


def test_a_refused_pair_is_reported_with_its_totals(bronze: Path) -> None:
    """The refusal reaches the OUTPUT: the run-report lines and the
    published shape both name the repository id and the totals each copy
    contributes — a double-counted total must never travel unlabelled."""
    _young_pair(bronze, "Beta", "beta")

    report = bronze_dedupe_report(bronze, families=["issues"])

    (group,) = report.refused
    assert group.repository_id == 4242
    assert group.winner is None
    assert [f.name for f in group.files] == ["issues_Beta.json", "issues_beta.json"]
    assert [f.records for f in group.files] == [3, 5]

    run_report = "\n".join(report.format_lines())
    assert "REFUSED — BOTH KEPT AND DOUBLE-COUNTED" in run_report
    assert "issues" in run_report and "4242" in run_report
    assert "issues_Beta.json" in run_report and "issues_beta.json" in run_report
    assert "3 record(s)" in run_report and "5 record(s)" in run_report

    published = report.as_dict()
    assert published["refused_duplicates"]["count"] == 1
    (entry,) = published["refused_duplicates"]["groups"]
    assert entry["repository_id"] == 4242
    assert sorted(f["records"] for f in entry["files"]) == [3, 5]


def test_a_pair_47h_apart_with_mixed_naive_and_aware_stamps_refuses(
    bronze: Path,
) -> None:
    """The precondition's hard case: a naive stamp (its writer's zone)
    against an aware one. Subtracting them directly raises ``TypeError``;
    compared on UTC wall times the gap is 47h — at most 48h, so REFUSES."""
    _write_repo_file(bronze, "gamma", 7, "2026-09-25T11:00:00+00:00")
    _write_repo_file(bronze, "Gamma", 7, "2026-09-27T10:00:00")  # naive, 47h later
    _write_records_file(
        bronze, "commits", "gamma", _records_for("commits", 2), "2026-09-25T11:00:00+00:00"
    )
    _write_records_file(
        bronze, "commits", "Gamma", _records_for("commits", 4), "2026-09-27T10:00:00"
    )

    found = [p.name for p in bronze_files(bronze, "commits")]

    assert found == ["commits_Gamma.json", "commits_gamma.json"]
    report = bronze_dedupe_report(bronze, families=["commits"])
    (group,) = report.refused
    assert group.gap is not None and group.gap.total_seconds() == 47 * 3600


def test_a_pair_49h_apart_picks_the_latest(bronze: Path) -> None:
    """Just past the threshold, the winner rule fires — and the latest copy
    wins whatever its awareness: here the naive stamp is the newer one."""
    _write_repo_file(bronze, "delta", 11, "2026-09-25T11:00:00+00:00")
    _write_repo_file(bronze, "Delta", 11, "2026-09-27T12:00:00")  # naive, 49h later
    _write_records_file(
        bronze, "prs", "delta", _records_for("prs", 6), "2026-09-25T11:00:00+00:00"
    )
    _write_records_file(
        bronze, "prs", "Delta", _records_for("prs", 9), "2026-09-27T12:00:00"
    )

    found = [p.name for p in bronze_files(bronze, "prs")]

    assert found == ["prs_Delta.json"]
    report = bronze_dedupe_report(bronze, families=["prs"])
    (group,) = report.deduped
    assert group.winner == "prs_Delta.json"
    assert len(list(bronze_records(bronze, "prs"))) == 9


def test_a_duplicate_whose_gap_cannot_be_established_refuses(bronze: Path) -> None:
    """An empty record file carries no ``_metadata`` at all. The winner
    rule's precondition cannot be established, so it refuses — an
    unprovable gap must not become a guessed winner."""
    _write_repo_file(bronze, "epsilon", 12, "2026-09-25T11:00:00+00:00")
    _write_repo_file(bronze, "Epsilon", 12, "2026-09-20T11:00:00+00:00")
    _write_records_file(
        bronze, "commits", "epsilon", _records_for("commits", 2),
        "2026-09-25T11:00:00+00:00",
    )
    _write_empty_records_file(bronze, "commits", "Epsilon")

    found = [p.name for p in bronze_files(bronze, "commits")]

    assert found == ["commits_Epsilon.json", "commits_epsilon.json"]
    report = bronze_dedupe_report(bronze, families=["commits"])
    (group,) = report.refused
    assert group.gap is None
    assert group.files[0].name == "commits_Epsilon.json"
    assert group.files[0].records == 0  # an empty file still counts its zero


# --------------------------------------------------------------------------
# Acceptance 3: unmapped files — counted, kept, reported.
# --------------------------------------------------------------------------


def test_a_family_file_with_no_repo_sibling_is_counted_kept_and_reported(
    bronze: Path,
) -> None:
    """No ``repo_<name>.json`` sibling means no id: the file cannot be
    keyed. Dropping it under-counts and merging it guesses; both are wrong,
    so it is counted and named."""
    _write_repo_file(bronze, "zeta", 21, "2026-09-25T11:00:00+00:00")
    _write_records_file(
        bronze, "commits", "zeta", _records_for("commits", 4), "2026-09-25T11:00:00+00:00"
    )
    _write_records_file(
        bronze, "commits", "lost-sibling", _records_for("commits", 6),
        "2026-09-25T11:00:00+00:00",
    )

    found = [p.name for p in bronze_files(bronze, "commits")]

    assert found == ["commits_lost-sibling.json", "commits_zeta.json"]
    assert len(list(bronze_records(bronze, "commits"))) == 10

    report = bronze_dedupe_report(bronze, families=["commits"])
    (item,) = report.unmapped
    assert item.name == "commits_lost-sibling.json"
    assert item.reason == REASON_NO_SIBLING.format(name="lost-sibling")
    run_report = "\n".join(report.format_lines())
    assert "unmapped — counted and kept" in run_report
    assert "commits_lost-sibling.json" in run_report


def test_a_sibling_without_a_readable_id_is_unmapped(bronze: Path) -> None:
    """The sibling exists but its payload carries no usable ``id`` (here a
    provider response with ``id: null``): unmapped, not guessed."""
    _write_repo_file(bronze, "eta", None, "2026-09-25T11:00:00+00:00")
    _write_records_file(
        bronze, "issues", "eta", _records_for("issues", 2), "2026-09-25T11:00:00+00:00"
    )

    assert [p.name for p in bronze_files(bronze, "issues")] == ["issues_eta.json"]

    report = bronze_dedupe_report(bronze, families=["issues"])
    (item,) = report.unmapped
    assert item.name == "issues_eta.json"
    assert item.reason == REASON_SIBLING_NO_ID.format(name="eta")


def test_a_digit_string_id_and_an_int_id_are_one_repository(bronze: Path) -> None:
    """``957040204`` and ``"957040204"`` are the same repository id spelled
    by hand and by the provider; they must land in one group, not pass each
    other by."""
    _write_repo_file(bronze, "theta", 501, "2026-09-25T11:00:00+00:00")
    _write_repo_file(bronze, "Theta", "501", "2026-09-18T11:00:00+00:00")
    _write_records_file(
        bronze, "prs", "theta", _records_for("prs", 3), "2026-09-25T11:00:00+00:00"
    )
    _write_records_file(
        bronze, "prs", "Theta", _records_for("prs", 5), "2026-09-18T11:00:00+00:00"
    )

    assert [p.name for p in bronze_files(bronze, "prs")] == ["prs_theta.json"]

    report = bronze_dedupe_report(bronze, families=["prs"])
    (group,) = report.deduped
    assert group.repository_id == 501
    assert group.winner == "prs_theta.json"


# --------------------------------------------------------------------------
# The published artifact.
# --------------------------------------------------------------------------


def test_write_report_publishes_the_refusal_with_its_totals(bronze: Path) -> None:
    """``data/bronze/dedupe.json``: the whole report as data, stamped aware
    UTC (#143), asserted over the whole artifact rather than an excerpt."""
    _young_pair(bronze, "Beta", "beta")

    report = bronze_dedupe_report(bronze)
    target = write_report(bronze, report)

    assert target == bronze / "dedupe.json"
    published = json.loads(target.read_text(encoding="utf-8"))

    assert published["generated_at"].endswith("+00:00")
    assert published["unmapped"]["count"] == 0
    refused = published["refused_duplicates"]
    assert refused["count"] == 2  # the issues pair and the repo pair itself
    issues_entry = next(g for g in refused["groups"] if g["family"] == "issues")
    assert issues_entry["repository_id"] == 4242
    assert sorted(f["records"] for f in issues_entry["files"]) == [3, 5]


def test_the_clean_corpus_report_is_written_and_says_zero(bronze: Path) -> None:
    """The zero case ships too: an artifact that appears only on failure is
    indistinguishable from a check that never ran."""
    _write_repo_file(bronze, "iota", 77, "2026-09-25T11:00:00+00:00")
    _write_records_file(
        bronze, "commits", "iota", _records_for("commits", 1), "2026-09-25T11:00:00+00:00"
    )

    report = bronze_dedupe_report(bronze)
    target = write_report(bronze, report)

    published = json.loads(target.read_text(encoding="utf-8"))
    assert published["refused_duplicates"]["count"] == 0
    assert published["deduped"]["count"] == 0
    assert published["unmapped"]["count"] == 0
    header = "\n".join(report.format_lines())
    assert "0 duplicate id(s) deduped, 0 REFUSED" in header
    assert "0 unmapped file(s)" in header
