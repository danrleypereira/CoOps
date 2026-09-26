"""Unit tests for the Bronze orphan reconciliation (#216).

Every fixture is built under ``tmp_path``: this module tests a routine
that DELETES files, so it never runs against a real corpus — the fenced
corpus is read only, and ``./data`` in the checkout is tracked pipeline
output.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import coops.bronze.reconcile as reconcile_module
from coops.bronze.files import bronze_files, bronze_files_raw
from coops.bronze.reconcile import reconcile_orphans
from coops.bronze.repositories import extract_repositories
from coops.utils.github_api import save_json_data

# The #216 fixture, exactly as the real corpus holds it: one repository,
# recased, with the old-case file beside the current one. Only ``x`` is
# in the filtered listing.
RECASED_CURRENT = "x"
RECASED_ORPHAN = "X"


@pytest.fixture()
def bronze(tmp_path: Path) -> Path:
    directory = tmp_path / "data" / "bronze"
    directory.mkdir(parents=True)
    return directory


def _listing(bronze: Path, names: tuple[str, ...], *, complete: bool = True) -> None:
    """Write a filtered listing the way the producer does.

    ``complete=False`` must leave the key ABSENT, never write
    ``complete: false`` — absent means incomplete, and no producer writes
    the false spelling, so the tests must not either.
    """
    records = [
        {"name": name, "full_name": f"unb-mds/{name}", "id": index}
        for index, name in enumerate(names, start=1)
    ]
    save_json_data(records, str(bronze / "repositories_filtered.json"), complete=complete)


def _family_file(bronze: Path, family: str, repo: str) -> Path:
    path = bronze / f"{family}_{repo}.json"
    path.write_text("[]", encoding="utf-8")
    return path


def _extraction_client(repos: list[dict], *, offline: bool = False) -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    client.offline = offline
    config = MagicMock()
    config.org_name = "unb-mds"
    config.should_skip_repo.return_value = False
    client.get_paginated.return_value = repos
    client.get_with_cache.return_value = repos[0] if repos else None
    return client, config


# --------------------------------------------------------------------------
# Acceptance 1: the reconciliation removes the orphan, keeps the current file
# --------------------------------------------------------------------------


def test_recase_orphan_removed_current_file_kept(bronze: Path, capsys) -> None:
    """The #216 fixture: commits_X.json and commits_x.json, only x listed."""
    _listing(bronze, (RECASED_CURRENT,))
    current = _family_file(bronze, "commits", RECASED_CURRENT)
    orphan = _family_file(bronze, "commits", RECASED_ORPHAN)

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is None
    assert not orphan.exists()
    assert current.is_file()
    assert result.deleted == [orphan]
    assert "APPLY" in capsys.readouterr().out


def test_full_rename_removes_old_files_across_families(bronze: Path) -> None:
    """A repository renamed outright (foo -> bar) orphans every family."""
    _listing(bronze, ("bar",))
    families = ("commits", "prs", "issues", "issue_events", "structure", "repo")
    for family in families:
        _family_file(bronze, family, "bar")
        _family_file(bronze, family, "foo")

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is None
    for family in families:
        assert not (bronze / f"{family}_foo.json").exists()
        assert (bronze / f"{family}_bar.json").is_file()


def test_dry_run_is_the_default_and_deletes_nothing(bronze: Path, capsys) -> None:
    """Dry run is the DEFAULT of the function; it names what would go and
    deletes nothing, and says which mode ran (deletion-safety #4)."""
    _listing(bronze, (RECASED_CURRENT,))
    _family_file(bronze, "commits", RECASED_CURRENT)
    orphan = _family_file(bronze, "commits", RECASED_ORPHAN)

    result = reconcile_orphans(bronze)  # no apply

    assert result.deleted == []
    assert result.orphans == [orphan]
    assert orphan.is_file()
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "nothing deleted" in out


# --------------------------------------------------------------------------
# Deletion-safety 1: the recase trap — never delete the only copy
# --------------------------------------------------------------------------


def test_only_copy_under_old_case_is_kept(bronze: Path) -> None:
    """A file matching the listing under a different case is the LIVE one
    when no current-case file sits beside it (the run skipped or has not
    yet written that family). Deleting it is the record loss every other
    guard in this codebase exists to prevent — so it stays, named."""
    _listing(bronze, (RECASED_CURRENT,))
    only_copy = _family_file(bronze, "commits", RECASED_ORPHAN)

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is None
    assert result.deleted == []
    assert only_copy.is_file()
    assert result.kept_variants == [only_copy]


# --------------------------------------------------------------------------
# Deletion-safety 2 and 6: empty or missing listing deletes nothing
# --------------------------------------------------------------------------


def test_missing_listing_refuses_and_deletes_nothing(bronze: Path, capsys) -> None:
    live = _family_file(bronze, "commits", RECASED_CURRENT)

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is not None
    assert "absent" in result.refused
    assert result.deleted == []
    assert live.is_file()
    assert "REFUSED" in capsys.readouterr().out


def test_empty_listing_deletes_nothing(bronze: Path) -> None:
    """A listing of [] carries no _metadata at all — save_json_data
    prepends it only for non-empty lists — so the most destructive
    possible input is the one with the least evidence. It must refuse,
    as a test and not an inference."""
    (bronze / "repositories_filtered.json").write_text("[]", encoding="utf-8")
    live = _family_file(bronze, "commits", RECASED_CURRENT)

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is not None
    assert "complete" in result.refused
    assert result.deleted == []
    assert live.is_file()


def test_metadata_bearing_listing_with_no_names_refuses(bronze: Path) -> None:
    """Provenance alone is not enough: a listing that asserts completeness
    but names no repositories still deletes nothing."""
    (bronze / "repositories_filtered.json").write_text(
        json.dumps([{"_metadata": {"extracted_at": "2026-09-25T00:00:00Z", "complete": True}}]),
        encoding="utf-8",
    )
    live = _family_file(bronze, "commits", RECASED_CURRENT)

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is not None
    assert result.deleted == []
    assert live.is_file()


# --------------------------------------------------------------------------
# Deletion-safety 5: the guard is in the file, not in argv
# --------------------------------------------------------------------------


def test_capped_run_does_not_reconcile_its_own_subset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """Same-run shape (@curupira's gate): --max-repos 1 against a scratch
    corpus, reconciled at the end of that same run — 0 deletions, explicit
    refusal. The cap truncates BEFORE the write, so the listing on disk is
    a subset, and the subset carries no completeness provenance."""
    monkeypatch.chdir(tmp_path)
    repos = [{"name": f"repo{index}", "full_name": f"unb-mds/repo{index}"} for index in range(3)]
    client, config = _extraction_client(repos)
    extract_repositories(client, config, max_repos=1)

    bronze = tmp_path / "data" / "bronze"
    for index in (1, 2):  # files of the repositories the cap excluded
        _family_file(bronze, "commits", f"repo{index}")

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is not None
    assert "complete" in result.refused
    assert result.deleted == []
    for index in (1, 2):
        assert (bronze / f"commits_repo{index}.json").is_file()
    assert "REFUSED" in capsys.readouterr().out


def test_capped_listing_refuses_a_later_clean_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two-run shape (@curupira's gate): run A truncates and EXITS; run B
    reconciles with a completely clean argv — no --max-repos, no --repo,
    no --offline — and must still delete nothing, because the FILE says
    the listing is not known to be complete. An argv guard passes every
    other condition and wipes the corpus here."""
    run_a = tmp_path / "run-a"
    run_a.mkdir()
    monkeypatch.chdir(run_a)
    repos = [{"name": f"repo{index}", "full_name": f"unb-mds/repo{index}"} for index in range(3)]
    client, config = _extraction_client(repos)
    extract_repositories(client, config, max_repos=1)  # run A exits here
    monkeypatch.chdir(tmp_path)  # run B starts with nothing carried over

    bronze = run_a / "data" / "bronze"
    listing = json.loads((bronze / "repositories_filtered.json").read_text())
    # What run A left: one entry, provenance that does not assert completeness.
    assert len(listing) == 2  # _metadata + the single kept repository
    assert "complete" not in listing[0]["_metadata"]

    result = reconcile_orphans(bronze, apply=True)  # run B, clean argv

    assert result.refused is not None
    assert "complete" in result.refused
    assert result.deleted == []


def test_provenance_not_size_guards_the_delete(bronze: Path) -> None:
    """The arms differ on provenance, never on size: a COMPLETE listing of
    five repositories reconciles (an orphan is removed), while record_count
    — the same five after a cap — cannot tell a genuine small organisation
    from a truncated listing, and is never consulted."""
    _listing(bronze, tuple(f"repo{index}" for index in range(5)))
    _family_file(bronze, "commits", "repo0")
    orphan = _family_file(bronze, "commits", "gone")

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is None
    assert not orphan.exists()


def test_repo_filter_run_leaves_listing_unprovenanced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--repo writes a subset too, and it refuses exactly like the cap."""
    monkeypatch.chdir(tmp_path)
    repos = [
        {"name": "keep", "full_name": "unb-mds/keep"},
        {"name": "other", "full_name": "unb-mds/other"},
    ]
    client, config = _extraction_client(repos)
    extract_repositories(client, config, repo_filter=["unb-mds/keep"])

    bronze = tmp_path / "data" / "bronze"
    listing = json.loads((bronze / "repositories_filtered.json").read_text())
    assert "complete" not in listing[0]["_metadata"]

    result = reconcile_orphans(bronze, apply=True)
    assert result.refused is not None
    assert result.deleted == []


def test_offline_replay_leaves_listing_unprovenanced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An offline replay reads only what the cache holds, so its listing
    is a claim about the provider the run has no evidence for — the same
    rule that keeps an offline run from persisting watermarks."""
    monkeypatch.chdir(tmp_path)
    repos = [{"name": "keep", "full_name": "unb-mds/keep"}]
    client, config = _extraction_client(repos, offline=True)
    extract_repositories(client, config)

    bronze = tmp_path / "data" / "bronze"
    listing = json.loads((bronze / "repositories_filtered.json").read_text())
    assert "complete" not in listing[0]["_metadata"]

    result = reconcile_orphans(bronze, apply=True)
    assert result.refused is not None
    assert result.deleted == []


def test_pre_provenance_listing_refuses(bronze: Path) -> None:
    """Fail closed on absent: every listing already on disk — including
    the whole corpus as it exists today — has no provenance, and must
    refuse rather than be read as complete."""
    (bronze / "repositories_filtered.json").write_text(
        json.dumps(
            [
                {
                    "_metadata": {
                        "extracted_at": "2026-09-23T16:43:16.417673",
                        "file_path": "data/bronze/repositories_filtered.json",
                        "record_count": 486,
                    }
                },
                {"name": RECASED_CURRENT, "full_name": f"unb-mds/{RECASED_CURRENT}"},
            ]
        ),
        encoding="utf-8",
    )
    live = _family_file(bronze, "commits", RECASED_CURRENT)

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is not None
    assert result.deleted == []
    assert live.is_file()


# --------------------------------------------------------------------------
# Deletion-safety 3: nothing outside data/bronze is touched
# --------------------------------------------------------------------------


def test_nothing_outside_bronze_is_touched(tmp_path: Path) -> None:
    data = tmp_path / "data"
    bronze = data / "bronze"
    bronze.mkdir(parents=True)
    silver = data / "silver"
    silver.mkdir()
    _listing(bronze, (RECASED_CURRENT,))
    _family_file(bronze, "commits", RECASED_CURRENT)
    _family_file(bronze, "commits", RECASED_ORPHAN)
    silver_orphan = silver / "commits_gone.json"
    silver_orphan.write_text("[]", encoding="utf-8")

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is None
    assert silver_orphan.is_file()


def test_refuses_when_enumeration_reaches_outside_bronze(
    bronze: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outside-directory guard must be shown capable of firing: an
    enumeration that ever yields a path outside bronze_dir makes the whole
    reconciliation refuse, deleting nothing (here forced by stubbing the
    enumeration, which is the only way to produce the state)."""
    _listing(bronze, (RECASED_CURRENT,))
    _family_file(bronze, "commits", RECASED_CURRENT)
    outside = bronze.parent / "commits_X.json"
    outside.write_text("[]", encoding="utf-8")

    # bronze_files_raw, not bronze_files: #258 repointed the reconciler at the
    # raw enumeration, and patching the old name silently stopped stubbing
    # anything — the guard then never saw an outside path and this test failed,
    # which is the seam doing its job.
    real_enumerate = reconcile_module.bronze_files_raw

    def stubbed(bronze_dir, family):
        files = real_enumerate(bronze_dir, family)
        return sorted([*files, outside]) if family == "commits" else files

    monkeypatch.setattr(reconcile_module, "bronze_files_raw", stubbed)

    result = reconcile_orphans(bronze, apply=True)

    assert result.refused is not None
    assert "outside" in result.refused
    assert result.deleted == []
    assert outside.is_file()


# --------------------------------------------------------------------------
# #258: the reader and the reconciler need different enumerations
# --------------------------------------------------------------------------


def _recased_pair_corpus(tmp_path: Path) -> Path:
    """The live NoFluxo shape: a recased pair sharing one repository id.

    This is the only shape in which the dedupe hides anything from the
    reconciler, and nothing exercised it before #258 — each feature was tested
    alone. The `repo_` siblings are what give both copies the same id.
    """
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    old, new = "2026-09-18T09:15:46.896528", "2026-09-25T09:53:03.135878+00:00"

    def write(name: str, payload: object) -> None:
        (bronze / name).write_text(json.dumps(payload), encoding="utf-8")

    write("repo_2025-1-NoFluxoUNB.json",
          {"id": 957040204, "name": "2025-1-NoFluxoUNB", "_metadata": {"extracted_at": old}})
    write("repo_2025-1-NoFluxoUnB.json",
          {"id": 957040204, "name": "2025-1-NoFluxoUnB", "_metadata": {"extracted_at": new}})
    for family in ("commits", "issues"):
        write(f"{family}_2025-1-NoFluxoUNB.json", [{"_metadata": {"extracted_at": old}}, {"n": 1}])
        write(f"{family}_2025-1-NoFluxoUnB.json", [{"_metadata": {"extracted_at": new}}, {"n": 1}])
    write("repositories_filtered.json",
          [{"_metadata": {"extracted_at": new, "complete": True}},
           {"name": "2025-1-NoFluxoUnB", "full_name": "unb-mds/2025-1-NoFluxoUnB", "id": 957040204}])
    return bronze


def test_the_reader_dedupes_and_the_reconciler_still_sees_the_orphan(tmp_path: Path) -> None:
    """#258: they must disagree, and that disagreement is the point.

    Between #248 and #258 `reconcile_orphans` enumerated through the deduped
    `bronze_files`, so the superseded copy it exists to delete was the very
    thing the dedupe had hidden: three orphans on disk, zero found.
    """
    bronze = _recased_pair_corpus(tmp_path)

    # the reader: one copy per family, the newer name
    assert [p.name for p in bronze_files(bronze, "commits")] == ["commits_2025-1-NoFluxoUnB.json"]

    # the reconciler: still sees all three superseded files on disk
    report = reconcile_orphans(bronze, apply=False)
    assert sorted(p.name for p in report.orphans) == [
        "commits_2025-1-NoFluxoUNB.json",
        "issues_2025-1-NoFluxoUNB.json",
        "repo_2025-1-NoFluxoUNB.json",
    ]
    assert report.deleted == []


def test_the_raw_enumeration_is_not_deduped(tmp_path: Path) -> None:
    """The control for the distinction itself.

    If `bronze_files_raw` ever starts deduping, the test above would pass for
    the wrong reason — the reconciler would find nothing and the assertion
    would be about an empty list. This pins the two apart.
    """
    bronze = _recased_pair_corpus(tmp_path)
    raw = [p.name for p in bronze_files_raw(bronze, "commits")]
    deduped = [p.name for p in bronze_files(bronze, "commits")]
    assert raw == ["commits_2025-1-NoFluxoUNB.json", "commits_2025-1-NoFluxoUnB.json"]
    assert deduped == ["commits_2025-1-NoFluxoUnB.json"]
    assert len(raw) > len(deduped), "the raw enumeration must not be deduped"
