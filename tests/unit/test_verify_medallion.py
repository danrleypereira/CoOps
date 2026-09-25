"""Unit tests for scripts/verify_medallion.py.

Two instruments, two questions — neither replaces the other:

* ``--self-test`` plants one defect per check and asserts rejection: it
  proves *the checks work*. It stays in the script and is run by hand.
* These tests assert the script's own contract — exit codes, precedence,
  registration: *the harness reports what it found.* Every defect the
  script has shipped with lived in that second category, and each was
  caught by a human re-running it, never by a test: rc 0 while checks
  were skipped for want of ``--reference``; a verdict text that denied
  record loss while the records really had vanished; a missing — then
  an empty — layer skipped into "all checks passed"; an early return
  that left ``no-record-vanished`` absent from the report rather than
  failing.

Do not delete one believing the other covers it.

The CLI tests drive ``main()`` over small synthetic corpora under
``tmp_path`` — never the frozen corpus — and assert exit CODES, never
message text, except where the contract itself is the message (the
precedence summary must name both findings). Every exit-code row runs
its clean twin in the same test, so a script stuck on one answer fails
every row: the arms-differ discipline ``--self-test`` already applies
to the checks, applied to the script itself.

Also pinned here: the staleness pair's reporting hole — an unusable
reference corpus (empty, partial, a wrong path, a different
organisation) made ``compared == 0`` and the early return left
``no-record-vanished`` out of the report entirely. A check that is
never emitted cannot fail, so the tests assert PRESENCE first:
asserting only "no failures" would also pass on the broken code.

And for gold-regenerated's ordering rule: equality must be settled on
the raw stamp strings BEFORE the 3h naive band is consulted, because a
copied seed is byte-identical, sits at delta 0 — inside the band — and
a band-first comparison passed it as inconclusive, certifying the exact
no-run the check exists to catch.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_medallion.py"
_SPEC = importlib.util.spec_from_file_location("verify_medallion", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
verify_medallion: ModuleType = importlib.util.module_from_spec(_SPEC)
# Registered before exec_module: the dataclasses in the script resolve their
# own module from sys.modules during class creation.
sys.modules["verify_medallion"] = verify_medallion
_SPEC.loader.exec_module(verify_medallion)


# --------------------------------------------------------------------------
# synthetic corpora — a handful of files under tmp_path, never the real one
# --------------------------------------------------------------------------

_REF_STAMP = "2026-09-24T00:00:00+00:00"  # the previous run, aware UTC
_ROOT_STAMP = "2026-09-25T06:00:00+00:00"  # this run: newer, exact compare
_STALE_STAMP = "2026-09-23T00:00:00+00:00"  # a day older than the reference

_COMMITS = [
    # A logged-in author with a hash: what every-author-hashed wants to see.
    {"sha": "c1", "commit": {"author": {"login": "alice",
                                        "author_email_hash": "h1"}}},
]
_ISSUES = [
    {"number": 1, "updated_at": "2026-09-20T00:00:00Z"},
    {"number": 2, "updated_at": "2026-09-21T00:00:00Z"},
]
_MEMBERS = [
    {"id": "m1", "name": "Alice"},
    {"id": "m2", "name": "Bob"},
]

_L_ALL = frozenset({"bronze", "silver", "gold"})
_L_NO_BRONZE = frozenset({"silver", "gold"})
_L_NO_SILVER = frozenset({"bronze", "gold"})
_L_NO_GOLD = frozenset({"bronze", "silver"})


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_bronze(bronze: Path, *, repos: tuple[str, ...] = ("r",)) -> None:
    for repo in repos:
        _write_json(bronze / f"commits_{repo}.json", _COMMITS)
        _write_json(bronze / f"issues_{repo}.json", _ISSUES)
    # The listing every per-repository file must correspond to (#216). The
    # _metadata first element mirrors what save_json_data writes; the check
    # reads the repo names out of the records after it.
    _write_json(
        bronze / "repositories_filtered.json",
        [{"_metadata": {"extracted_at": "2026-09-25T00:00:00Z"}},
         *[{"name": repo, "full_name": f"org/{repo}", "id": i}
           for i, repo in enumerate(repos, start=1)]],
    )


def _write_gold(gold: Path, stamp: str) -> None:
    """The five artifacts, each with its clock where the real writers keep it
    (see _stamp_text): generated_at, all_processed.updated_at, and the
    timelines' _metadata.extracted_at."""
    _write_json(gold / "executive_dashboard.json",
                {"kpis": {"total": 1}, "generated_at": stamp})
    _write_json(gold / "performance_tiers.json",
                {"tiers": [{"tier": "core"}], "generated_at": stamp})
    _write_json(gold / "registry.json",
                {"all_processed": {"updated_at": stamp}, "repos": [{"name": "r"}]})
    _write_json(gold / "timeline_last_7_days.json",
                [{"_metadata": {"extracted_at": stamp}},
                 {"day": "2026-09-25", "commits": 1}])
    _write_json(gold / "timeline_last_12_months.json",
                [{"_metadata": {"extracted_at": stamp}},
                 {"month": "2026-09", "commits": 1}])


def _build_corpus(root: Path, *, layers: frozenset[str] = _L_ALL,
                  gold_stamp: str = _ROOT_STAMP) -> None:
    data = root / "data"
    if "bronze" in layers:
        _write_bronze(data / "bronze")
    if "silver" in layers:
        _write_json(data / "silver" / "members_statistics.json", _MEMBERS)
    if "gold" in layers:
        _write_gold(data / "gold", gold_stamp)


def _build_reference(root: Path, *, disjoint: bool = False,
                     extra_issue: bool = False) -> None:
    """A previous run: same records, older gold stamps.

    disjoint=True holds a different repository, so no record key is shared
    and the staleness probe can compare nothing — the reference shape that
    once dropped no-record-vanished from the report entirely.
    """
    data = root / "data"
    _write_bronze(data / "bronze", repos=("q",) if disjoint else ("r",))
    if extra_issue:
        _write_json(data / "bronze" / "issues_r.json",
                    [*_ISSUES, {"number": 3, "updated_at": "2026-09-22T00:00:00Z"}])
    _write_gold(data / "gold", _REF_STAMP)


def _run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
         *argv: str) -> tuple[int, str, str]:
    """Drive main() the way the CLI does: argv in, exit code and output out."""
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), *argv])
    rc = verify_medallion.main()
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# --------------------------------------------------------------------------
# output rows — other tooling parses these lines, so the tests do too
# --------------------------------------------------------------------------

_ROW = re.compile(
    r"^  (?P<status>PASS|FAIL|SKIP|BROKEN)\s+"
    r"(?P<layer>bronze|silver|gold)\s+"
    r"(?P<name>\S+)"
    r"(?:\s{2,}(?P<detail>.*))?$"
)


def _parse_rows(out: str) -> list[re.Match[str]]:
    """Every stdout line before the summary's blank line, as a row match."""
    rows: list[re.Match[str]] = []
    for line in out.split("\n"):
        if not line.strip():
            break  # rows first, blank line, then the summary
        m = _ROW.match(line)
        assert m, f"row does not parse: {line!r}"
        rows.append(m)
    assert rows, "the script printed no rows"
    return rows


def _row_names(out: str) -> set[str]:
    """The set of check names in the report — registration, not verdicts.

    Uniqueness is asserted too: a check emitted twice is a report defect
    that set comparison alone would hide.
    """
    names = [m["name"] for m in _parse_rows(out)]
    assert len(names) == len(set(names)), f"a check is registered twice: {names}"
    return set(names)


_CONTROLS_RE = re.compile(r"(\d+) of (\d+) controls fired")


def _controls_fired(out: str) -> tuple[str, str]:
    m = _CONTROLS_RE.search(out)
    assert m, "self-test printed no control count"
    return m.group(1), m.group(2)


# --------------------------------------------------------------------------
# 1. the exit-code matrix — every row's opposite runs in the same test
# --------------------------------------------------------------------------

_MUTATOR = Callable[[Path, Path], None]


def _noop(root: Path, reference: Path) -> None:
    """The clean row: the opposite every other row is paired against."""


def _plant_duplicate_member_ids(root: Path, reference: Path) -> None:
    """One person counted twice — an invariant of the data, rc 1."""
    _write_json(
        root / "data" / "silver" / "members_statistics.json",
        [{"id": "m1", "name": "Alice"}, {"id": "m1", "name": "Alice again"}],
    )


def _plant_vanished_issue(root: Path, reference: Path) -> None:
    """The reference holds a record this run lost (#199's shape), rc 1."""
    _write_json(
        reference / "data" / "bronze" / "issues_r.json",
        [*_ISSUES, {"number": 3, "updated_at": "2026-09-22T00:00:00Z"}],
    )


def _plant_stale_gold(root: Path, reference: Path) -> None:
    """Gold a day older than the reference run: aware stamps, rc 1."""
    _write_gold(root / "data" / "gold", _STALE_STAMP)


def _plant_orphaned_bronze_file(root: Path, reference: Path) -> None:
    """#216's shape: the recase leftover beside the current-case file, rc 1.

    Both spellings are globbed downstream, so the repository is counted
    twice — a gain no falling-record check can see.
    """
    _write_json(root / "data" / "bronze" / "commits_R.json", _COMMITS)


def _plant_empty_filtered_listing(root: Path, reference: Path) -> None:
    """A listing that names no repositories makes every file an orphan.

    Not rc 2: the listing is readable and its content genuinely disagrees
    with the files beside it. The row must say so loudly either way.
    """
    _write_json(root / "data" / "bronze" / "repositories_filtered.json",
                [{"_metadata": {"extracted_at": "2026-09-25T00:00:00Z"}}])


def _plant_empty_gold_artifact(root: Path, reference: Path) -> None:
    """registry.json holds {} — gold-file-set cannot certify it, rc 2."""
    _write_json(root / "data" / "gold" / "registry.json", {})


def _plant_empty_silver_members(root: Path, reference: Path) -> None:
    """members_statistics.json holds [] — the probe sees no members, rc 2."""
    _write_json(root / "data" / "silver" / "members_statistics.json", [])


def _remove_layer(layer: str) -> _MUTATOR:
    def plant(root: Path, reference: Path) -> None:
        shutil.rmtree(root / "data" / layer)

    return plant


def _empty_layer(layer: str) -> _MUTATOR:
    def plant(root: Path, reference: Path) -> None:
        d = root / "data" / layer
        shutil.rmtree(d)
        d.mkdir()

    return plant


_EXIT_MATRIX = [
    # the universal opposite: everything below differs from this row by
    # exactly one mutation (or one argument) and must not return its code.
    pytest.param(_noop, 0, id="clean-corpus-with-reference"),
    # rc 1 — the data broke an invariant (three different invariants,
    # so no single check's idea of "broken" can satisfy the matrix).
    pytest.param(_plant_duplicate_member_ids, 1,
                 id="invariant-broken-duplicate-member-ids"),
    pytest.param(_plant_vanished_issue, 1,
                 id="invariant-broken-record-vanished"),
    pytest.param(_plant_stale_gold, 1,
                 id="invariant-broken-gold-not-regenerated"),
    pytest.param(_plant_orphaned_bronze_file, 1,
                 id="invariant-broken-orphaned-bronze-file"),
    pytest.param(_plant_empty_filtered_listing, 1,
                 id="invariant-broken-empty-filtered-listing"),
    # rc 2 — the instrument could not see (control_fired=False).
    pytest.param(_plant_empty_gold_artifact, 2,
                 id="control-silent-gold-artifact-holds-nothing"),
    pytest.param(_plant_empty_silver_members, 2,
                 id="control-silent-silver-holds-no-members"),
    # rc 2 — absence is the one state that used to skip into a pass.
    pytest.param(_remove_layer("bronze"), 2, id="layer-absent-bronze"),
    pytest.param(_remove_layer("silver"), 2, id="layer-absent-silver"),
    pytest.param(_remove_layer("gold"), 2, id="layer-absent-gold"),
    # rc 2 — an empty layer is a distinct state with the same silence.
    pytest.param(_empty_layer("bronze"), 2, id="layer-empty-bronze"),
    pytest.param(_empty_layer("silver"), 2, id="layer-empty-silver"),
    pytest.param(_empty_layer("gold"), 2, id="layer-empty-gold"),
]


@pytest.mark.parametrize(("mutate", "expected"), _EXIT_MATRIX)
def test_exit_code_matrix(mutate: _MUTATOR, expected: int, tmp_path: Path,
                          monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:
    """One mutation, and the clean twin run first: the arms must differ.

    Without the twin, a `rc == 0` row passes a script that can only ever
    return 0, and a `rc == 2` row passes one stuck on 2. This is the same
    discipline --self-test applies to the checks, pointed at the script.
    """
    clean_root, defect_root = tmp_path / "clean", tmp_path / "defect"
    clean_ref, defect_ref = tmp_path / "ref-clean", tmp_path / "ref-defect"
    _build_corpus(clean_root)
    _build_reference(clean_ref)
    _build_corpus(defect_root)
    _build_reference(defect_ref)
    mutate(defect_root, defect_ref)

    rc_clean, _, _ = _run(monkeypatch, capsys, "--root", str(clean_root),
                          "--reference", str(clean_ref))
    rc_defect, _, _ = _run(monkeypatch, capsys, "--root", str(defect_root),
                           "--reference", str(defect_ref))

    assert rc_clean == 0
    assert rc_defect == expected
    # the arms differ exactly when a defect was planted — the clean row's
    # opposite is every other row of this matrix, not its own twin
    assert (rc_defect != rc_clean) == (expected != 0)


def test_skipped_checks_exit_2_not_0(tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    """Without --reference the staleness checks are SKIP rows, and the run
    is not a pass.

    The historical defect: rc 0 with an honest "a phase gate needs
    --reference" printed above it — right message, wrong gate. The arms
    differ by the argument alone: same corpus, with and without.
    """
    root, reference = tmp_path / "root", tmp_path / "reference"
    _build_corpus(root)
    _build_reference(reference)

    rc_with, _, _ = _run(monkeypatch, capsys, "--root", str(root),
                         "--reference", str(reference))
    rc_without, out, _ = _run(monkeypatch, capsys, "--root", str(root))

    assert rc_with == 0
    assert rc_without == 2
    assert rc_without != rc_with
    # skipped checks still register — as SKIP rows, never as absent rows
    assert _row_names(out) == _ALL_CHECKS


def test_root_without_data_dir_exits_2(tmp_path: Path,
                                       monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    """A --root holding no data/ is not a corpus: rc 2, nothing on stdout.

    The opposite arm is the clean corpus, which must return 0 from the
    same test.
    """
    nowhere = tmp_path / "nowhere"
    rc_missing, out, err = _run(monkeypatch, capsys, "--root", str(nowhere))
    assert rc_missing == 2
    assert out == ""
    assert err.strip() != ""  # the complaint goes to stderr, never stdout

    root, reference = tmp_path / "root", tmp_path / "reference"
    _build_corpus(root)
    _build_reference(reference)
    rc_clean, _, _ = _run(monkeypatch, capsys, "--root", str(root),
                          "--reference", str(reference))
    assert rc_clean == 0
    assert rc_missing != rc_clean


# --------------------------------------------------------------------------
# 2. precedence — rc 2 dominates rc 1, and the summary says both
# --------------------------------------------------------------------------

def test_rc2_outranks_rc1_and_the_summary_names_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing layer AND real record loss: rc 2, both findings named.

    This regressed once already: the verdict text said "not the data"
    while records had vanished. Three arms, one corpus — both defects
    (rc 2, both named), the data failure alone (rc 1), the instrument
    failure alone (rc 2, and no claim about the data).
    """
    root = tmp_path / "root"
    _build_corpus(root, layers=_L_NO_SILVER)  # the instrument is incomplete
    ref_loss = tmp_path / "ref-loss"
    _build_reference(ref_loss, extra_issue=True)  # issue #3 really vanished
    ref_clean = tmp_path / "ref-clean"
    _build_reference(ref_clean)

    rc_both, out_both, _ = _run(monkeypatch, capsys, "--root", str(root),
                                "--reference", str(ref_loss))
    assert rc_both == 2
    # the one place the contract IS text: the summary must name both halves
    assert ("the instrument is incomplete AND 1 check(s) failed on the data"
            in out_both)
    assert "no-record-vanished" in out_both  # the data half is named
    assert "silver-present" in out_both  # the instrument half is named

    # arm 2: silver restored, the loss stays — the data failure alone is rc 1
    _write_json(root / "data" / "silver" / "members_statistics.json", _MEMBERS)
    rc_data, out_data, _ = _run(monkeypatch, capsys, "--root", str(root),
                                "--reference", str(ref_loss))
    assert rc_data == 1
    assert "the instrument is incomplete AND" not in out_data

    # arm 3: silver absent again, the loss removed — instrument alone, and
    # the summary must not claim the data failed when nothing did
    shutil.rmtree(root / "data" / "silver")
    rc_instrument, out_instrument, _ = _run(monkeypatch, capsys,
                                            "--root", str(root),
                                            "--reference", str(ref_clean))
    assert rc_instrument == 2
    assert "the instrument is incomplete AND" not in out_instrument
    assert rc_both != rc_data


def test_disjoint_reference_is_the_instrument_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A --reference sharing no record with the corpus cannot certify it.

    The registration hole lived exactly here: the early return left
    no-record-vanished out of the report, and a run with an absent row
    looks like a clean run to anything reading verdicts. Opposite arm:
    a usable reference on the same corpus returns 0.
    """
    root, disjoint = tmp_path / "root", tmp_path / "disjoint"
    _build_corpus(root)
    _build_reference(disjoint, disjoint=True)
    usable = tmp_path / "usable"
    _build_reference(usable)

    rc_disjoint, out, _ = _run(monkeypatch, capsys, "--root", str(root),
                               "--reference", str(disjoint))
    assert rc_disjoint == 2
    assert {"no-record-reverted", "no-record-vanished"} <= _row_names(out)

    rc_usable, _, _ = _run(monkeypatch, capsys, "--root", str(root),
                           "--reference", str(usable))
    assert rc_usable == 0
    assert rc_disjoint != rc_usable


# --------------------------------------------------------------------------
# 3. registration — which checks exist in the report, per argument
#    combination. Asserted on NAMES, never on verdicts: the
#    no-record-vanished hole was an absent row, not a wrong row.
# --------------------------------------------------------------------------

_PRESENCE_CHECKS = frozenset({"bronze-present", "silver-present", "gold-present"})
_BRONZE_CHECKS = frozenset({"aggregates-removed", "every-author-hashed",
                            "no-orphaned-bronze-files",
                            "no-record-reverted", "no-record-vanished"})
# The unknown-labels check registers as unknown-labels-not-growing on EVERY
# branch. Until #233 its absent/empty branches emitted the same check under a
# second name, no-unknown-labels, which --self-test had never heard of; this
# file used to pin both spellings as observed behaviour.
_SILVER_CHECKS = frozenset({"member-ids-distinct", "every-member-identified",
                            "unknown-labels-not-growing", "hash-never-a-label"})
_GOLD_CHECKS = frozenset({"gold-file-set", "gold-regenerated"})
_ALL_CHECKS = _PRESENCE_CHECKS | _BRONZE_CHECKS | _SILVER_CHECKS | _GOLD_CHECKS

_E_NONE: frozenset[str] = frozenset()

_REGISTRATION_MATRIX = [
    # a full corpus registers everything under every reference argument,
    # including none at all (the staleness trio arrive as SKIP rows) and
    # the two reference shapes that compare nothing (BROKEN rows, the
    # registration hole's exact world).
    pytest.param(_L_ALL, _E_NONE, "usable", _ALL_CHECKS,
                 id="full-usable-reference"),
    pytest.param(_L_ALL, _E_NONE, "none", _ALL_CHECKS,
                 id="full-no-reference"),
    pytest.param(_L_ALL, _E_NONE, "empty", _ALL_CHECKS,
                 id="full-empty-reference"),
    pytest.param(_L_ALL, _E_NONE, "disjoint", _ALL_CHECKS,
                 id="full-disjoint-reference"),
    # a layer that is absent takes its checks with it, but the presence
    # row for it must still be there naming the absence.
    pytest.param(_L_NO_BRONZE, _E_NONE, "usable", _ALL_CHECKS - _BRONZE_CHECKS,
                 id="no-bronze-usable-reference"),
    pytest.param(_L_NO_BRONZE, _E_NONE, "none", _ALL_CHECKS - _BRONZE_CHECKS,
                 id="no-bronze-no-reference"),
    pytest.param(_L_NO_SILVER, _E_NONE, "usable", _ALL_CHECKS - _SILVER_CHECKS,
                 id="no-silver-usable-reference"),
    pytest.param(_L_NO_SILVER, _E_NONE, "none", _ALL_CHECKS - _SILVER_CHECKS,
                 id="no-silver-no-reference"),
    pytest.param(_L_NO_GOLD, _E_NONE, "usable", _ALL_CHECKS - _GOLD_CHECKS,
                 id="no-gold-usable-reference"),
    pytest.param(_L_NO_GOLD, _E_NONE, "none", _ALL_CHECKS - _GOLD_CHECKS,
                 id="no-gold-no-reference"),
    # an EMPTY layer keeps its checks — the dir exists, so they run and
    # report what they cannot see — except every-member-identified, which
    # its sibling member-ids-distinct already covers with a BROKEN row.
    pytest.param(_L_ALL, frozenset({"gold"}), "usable", _ALL_CHECKS,
                 id="empty-gold-usable-reference"),
    pytest.param(_L_ALL, frozenset({"bronze"}), "usable", _ALL_CHECKS,
                 id="empty-bronze-usable-reference"),
    # empty silver: every check still registers. Before #233,
    # every-member-identified was ABSENT here (its early return preceded the
    # row) and unknown-labels-not-growing appeared under a second name — so
    # this row used to subtract two names and add one.
    pytest.param(_L_ALL, frozenset({"silver"}), "usable", _ALL_CHECKS,
                 id="empty-silver-usable-reference"),
]


@pytest.mark.parametrize(("layers", "empty", "ref_kind", "expected"),
                         _REGISTRATION_MATRIX)
def test_check_registration(layers: frozenset[str], empty: frozenset[str],
                            ref_kind: str, expected: frozenset[str],
                            tmp_path: Path,
                            monkeypatch: pytest.MonkeyPatch,
                            capsys: pytest.CaptureFixture[str]) -> None:
    """The report holds exactly the checks the argument combination owes.

    A dropped row reads as success to anything that checks verdicts, so
    this asserts the SET of names and nothing else.
    """
    root = tmp_path / "root"
    _build_corpus(root, layers=layers)
    for layer in empty:
        d = root / "data" / layer
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    argv = ["--root", str(root)]
    reference = tmp_path / "reference"
    if ref_kind == "usable":
        _build_reference(reference)
        argv += ["--reference", str(reference)]
    elif ref_kind == "empty":
        (reference / "data" / "bronze").mkdir(parents=True)
        (reference / "data" / "gold").mkdir(parents=True)
        argv += ["--reference", str(reference)]
    elif ref_kind == "disjoint":
        _build_reference(reference, disjoint=True)
        argv += ["--reference", str(reference)]

    rc, out, _ = _run(monkeypatch, capsys, *argv)
    assert 0 <= rc <= 2  # registration is the subject; the matrix owns codes
    assert _row_names(out) == set(expected)


# --------------------------------------------------------------------------
# 4. --self-test — 16 of 16, and the harness notices a silent control
# --------------------------------------------------------------------------

def test_self_test_fires_all_controls_and_exits_0(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """The count is part of the contract: 16 controls, all firing."""
    rc, out, _ = _run(monkeypatch, capsys, "--self-test")
    assert rc == 0
    assert _controls_fired(out) == ("17", "17")


def test_self_test_detects_a_control_that_stops_firing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """The opposite arm: a check that cannot fail makes its control SILENT,
    the count drops to 15 of 16, and the exit code is 2 — not 0."""
    def always_passes(bronze: Path, rep: verify_medallion.Report) -> None:
        rep.add(verify_medallion.Result("aggregates-removed", "bronze", True,
                                        "sabotaged: this check never fails"))

    monkeypatch.setattr(verify_medallion, "check_no_aggregates", always_passes)
    rc, out, _ = _run(monkeypatch, capsys, "--self-test")
    assert rc == 2
    assert _controls_fired(out) == ("16", "17")


# --------------------------------------------------------------------------
# 5. the row format — other tooling parses these lines
# --------------------------------------------------------------------------

def test_every_row_parses_and_every_status_occurs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One corpus engineered to print PASS, FAIL, SKIP and BROKEN — and
    every line before the summary parses as a row."""
    root, reference = tmp_path / "root", tmp_path / "reference"
    _build_corpus(root)
    _build_reference(reference)
    _plant_duplicate_member_ids(root, reference)  # a FAIL row
    _plant_empty_gold_artifact(root, reference)  # a BROKEN row
    # no --reference: the staleness trio arrives as SKIP rows

    rc, out, _ = _run(monkeypatch, capsys, "--root", str(root))
    rows = _parse_rows(out)
    statuses = {m["status"] for m in rows}
    assert statuses == {"PASS", "FAIL", "SKIP", "BROKEN"}
    assert rc == 2  # the run as a whole is the instrument, and says so


# --------------------------------------------------------------------------
# regressions — the staleness pair and the gold stamp ordering rule
# --------------------------------------------------------------------------


def _write_issues(root: Path, repo: str, records: list[dict]) -> None:
    (root / f"issues_{repo}.json").write_text(json.dumps(records), encoding="utf-8")


def _by_name(rep: verify_medallion.Report, name: str) -> list[verify_medallion.Result]:
    return [r for r in rep.results if r.name == name]


_NAIVE_OLD = "2026-09-24T00:00:00"  # pre-#143 local time, no offset


def _gold_report(
    tmp_path: Path,
    root_stamps: dict[str, str],
    ref_stamps: dict[str, str],
    drop: str | None = None,
) -> tuple[verify_medallion.Report, list[verify_medallion.Result]]:
    """Run check_gold_regenerated on two seeded gold trees, all five artifacts."""
    root, reference = tmp_path / "gold", tmp_path / "reference"
    for directory, stamps in ((root, root_stamps), (reference, ref_stamps)):
        directory.mkdir(parents=True, exist_ok=True)
        for name, stamp in stamps.items():
            payload = {"x": 1} if name == drop else {"x": 1, "generated_at": stamp}
            (directory / name).write_text(json.dumps(payload), encoding="utf-8")
    rep = verify_medallion.Report()
    verify_medallion.check_gold_regenerated(root, reference, rep)
    results = _by_name(rep, "gold-regenerated")
    assert results, "gold-regenerated missing from the report"
    return rep, results


def test_copied_seed_with_naive_stamps_fails_the_gate(tmp_path: Path) -> None:
    """Regression (#201): a byte-identical naive copy must FAIL, not pass.

    The naive flavour is the one that matters — it is the only stamp format
    the frozen corpora carry — and it is the one a band-first comparison
    passed: delta 0 lands inside "up to 3h older, or equal".
    """
    all_naive = dict.fromkeys(verify_medallion.EXPECTED_GOLD, _NAIVE_OLD)
    rep, results = _gold_report(tmp_path, dict(all_naive), dict(all_naive))

    assert not results[0].passed
    assert results[0].control_fired is None  # a data failure gates as rc 1
    assert "copied, not regenerated" in results[0].detail
    assert rep.exit_code == 1


def test_naive_seed_shifted_back_two_hours_is_inconclusive(tmp_path: Path) -> None:
    """The band's purpose: -2h on naive local stamps is ambiguity, not staleness.

    Guarding the other edge of the ordering rule: only a strictly different
    stamp may reach the band, and inside it the row reports inconclusive
    rather than failing.
    """
    all_naive = dict.fromkeys(verify_medallion.EXPECTED_GOLD, _NAIVE_OLD)
    shifted = dict.fromkeys(verify_medallion.EXPECTED_GOLD, "2026-09-23T22:00:00")
    rep, results = _gold_report(tmp_path, shifted, all_naive)

    assert results[0].passed
    assert "inconclusive" in results[0].detail
    assert rep.exit_code == 0


def test_unreadable_generated_at_is_the_instrument(tmp_path: Path) -> None:
    """A stamp that cannot be read is neither a pass nor a fail: rc 2.

    Four of the five artifacts carry no generated_at in the frozen corpora,
    so this is the verdict a real run gets today until the writers stamp
    all five.
    """
    ref = dict.fromkeys(verify_medallion.EXPECTED_GOLD, "2026-09-24T00:00:00+00:00")
    root = dict.fromkeys(verify_medallion.EXPECTED_GOLD, "2026-09-25T06:00:00+00:00")
    rep, results = _gold_report(tmp_path, root, ref, drop="registry.json")

    assert not results[0].passed
    assert results[0].control_fired is False  # the instrument, not the data
    assert "registry.json" in results[0].detail
    assert rep.exit_code == 2


def test_empty_reference_emits_both_staleness_checks_as_failures(tmp_path: Path) -> None:
    """Regression: an unusable reference must not drop no-record-vanished.

    With `compared == 0` the old code returned after adding only
    no-record-reverted, so no-record-vanished was absent from the report —
    not passing, not failing, just missing.
    """
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    _write_issues(bronze, "r", [{"number": 1, "updated_at": "2026-09-01T00:00:00Z"}])
    reference = tmp_path / "reference"
    reference.mkdir()  # empty tree — the probe cannot measure anything

    rep = verify_medallion.Report()
    verify_medallion.check_no_record_reverted(bronze, reference, rep)

    reverted = _by_name(rep, "no-record-reverted")
    vanished = _by_name(rep, "no-record-vanished")
    assert reverted, "no-record-reverted missing from the report"
    assert vanished, "no-record-vanished missing from the report"
    assert not reverted[0].passed
    assert not vanished[0].passed
    # An unusable reference is an instrument failure, not clean data.
    assert reverted[0].control_fired is False
    assert vanished[0].control_fired is False
    assert rep.exit_code == 2


def test_vanished_record_fails_while_reverted_passes(tmp_path: Path) -> None:
    """A usable reference where a record really vanished: only vanished fails."""
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    _write_issues(bronze, "r", [{"number": 2, "updated_at": "2026-09-02T00:00:00Z"}])
    reference = tmp_path / "reference"
    reference.mkdir()
    _write_issues(
        reference,
        "r",
        [
            {"number": 2, "updated_at": "2026-09-02T00:00:00Z"},
            {"number": 3, "updated_at": "2026-09-03T00:00:00Z"},
        ],
    )

    rep = verify_medallion.Report()
    verify_medallion.check_no_record_reverted(bronze, reference, rep)

    reverted = _by_name(rep, "no-record-reverted")
    vanished = _by_name(rep, "no-record-vanished")
    assert reverted, "no-record-reverted missing from the report"
    assert vanished, "no-record-vanished missing from the report"
    assert reverted[0].passed  # the one shared record did not move backwards
    assert not vanished[0].passed


def test_identical_corpora_both_staleness_checks_pass(tmp_path: Path) -> None:
    """A usable reference with nothing lost and nothing stale: both pass."""
    records = [
        {"number": 1, "updated_at": "2026-09-01T00:00:00Z"},
        {"number": 2, "updated_at": "2026-09-02T00:00:00Z"},
    ]
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    _write_issues(bronze, "r", records)
    reference = tmp_path / "reference"
    reference.mkdir()
    _write_issues(reference, "r", records)

    rep = verify_medallion.Report()
    verify_medallion.check_no_record_reverted(bronze, reference, rep)

    reverted = _by_name(rep, "no-record-reverted")
    vanished = _by_name(rep, "no-record-vanished")
    assert reverted, "no-record-reverted missing from the report"
    assert vanished, "no-record-vanished missing from the report"
    assert reverted[0].passed
    assert vanished[0].passed


# --------------------------------------------------------------------------
# no-orphaned-bronze-files (#216) — the gain-side check. Every other check
# here asserts records must not FALL; the orphan ADDS records, so it was
# invisible to all of them. The fixture mirrors the real case: one
# repository, recased, listing only the current spelling.
# --------------------------------------------------------------------------


def _write_listing(bronze: Path, *repos: str) -> None:
    _write_json(
        bronze / "repositories_filtered.json",
        [{"_metadata": {"extracted_at": "2026-09-25T00:00:00Z"}},
         *[{"name": repo, "full_name": f"unb-mds/{repo}", "id": 957040204}
           for repo in repos]],
    )


def test_recase_leftover_fails_the_gate_naming_the_file(tmp_path: Path) -> None:
    """The #216 shape: commits_X.json beside commits_x.json, only x listed.

    Both arms in one test — the same corpus with the orphan removed must
    pass, because a check that fails on everything certifies nothing.
    """
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    _write_listing(bronze, "x")
    for name in ("commits_x.json", "commits_X.json"):
        _write_json(bronze / name, _COMMITS)

    rep = verify_medallion.Report()
    verify_medallion.check_no_orphaned_files(bronze, rep)
    orphaned = _by_name(rep, "no-orphaned-bronze-files")
    assert orphaned, "no-orphaned-bronze-files missing from the report"
    assert not orphaned[0].passed
    assert orphaned[0].control_fired is None  # bad data gates as rc 1
    assert "commits_X.json" in orphaned[0].detail  # the file is named
    assert rep.exit_code == 1

    (bronze / "commits_X.json").unlink()
    rep = verify_medallion.Report()
    verify_medallion.check_no_orphaned_files(bronze, rep)
    clean = _by_name(rep, "no-orphaned-bronze-files")
    assert clean[0].passed
    assert rep.exit_code == 0


def test_missing_filtered_listing_is_the_instrument_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without repositories_filtered.json the check cannot see, rc 2 —
    it must not silently pass, and its row must still register."""
    root, reference = tmp_path / "root", tmp_path / "reference"
    _build_corpus(root)
    _build_reference(reference)
    (root / "data" / "bronze" / "repositories_filtered.json").unlink()

    rc, out, _ = _run(monkeypatch, capsys, "--root", str(root),
                      "--reference", str(reference))

    names = {m["name"] for m in _parse_rows(out)}
    assert "no-orphaned-bronze-files" in names, (
        f"no-orphaned-bronze-files vanished — {sorted(names)}")
    assert rc == 2, f"an unreadable listing is an instrument failure, got {rc}"


def test_unreadable_filtered_listing_is_the_instrument(tmp_path: Path) -> None:
    """Present but not JSON is the same blindness as absent: rc 2.

    'Absent' and 'present but useless' take different branches, and only
    the first is covered above — the degenerate-branch discipline.
    """
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    _write_listing(bronze, "x")
    _write_json(bronze / "commits_x.json", _COMMITS)
    (bronze / "repositories_filtered.json").write_text("{not json", encoding="utf-8")

    rep = verify_medallion.Report()
    verify_medallion.check_no_orphaned_files(bronze, rep)
    result = _by_name(rep, "no-orphaned-bronze-files")
    assert result, "no-orphaned-bronze-files missing from the report"
    assert not result[0].passed
    assert result[0].control_fired is False
    assert rep.exit_code == 2


def test_only_copy_case_variant_is_not_an_orphan(tmp_path: Path) -> None:
    """An old-case file with no current-case file beside it is the only
    copy the corpus has (the run skipped or has not yet written that
    family), and the reconciler keeps it — flagging it here would demand
    deleting an only copy, which is the record loss every other check in
    the script exists to prevent.
    """
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    _write_listing(bronze, "x")
    _write_json(bronze / "commits_X.json", _COMMITS)  # and only this one

    rep = verify_medallion.Report()
    verify_medallion.check_no_orphaned_files(bronze, rep)
    result = _by_name(rep, "no-orphaned-bronze-files")
    assert result, "no-orphaned-bronze-files missing from the report"
    assert result[0].passed
    assert rep.exit_code == 0


def test_repository_absent_from_the_listing_is_an_orphan(tmp_path: Path) -> None:
    """A file whose repository matches nothing — renamed away or deleted —
    is stale whatever its case, and the row names it."""
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    _write_listing(bronze, "x")
    _write_json(bronze / "commits_x.json", _COMMITS)
    _write_json(bronze / "issues_gone.json", _ISSUES)

    rep = verify_medallion.Report()
    verify_medallion.check_no_orphaned_files(bronze, rep)
    result = _by_name(rep, "no-orphaned-bronze-files")
    assert result, "no-orphaned-bronze-files missing from the report"
    assert not result[0].passed
    assert "issues_gone.json" in result[0].detail
    assert rep.exit_code == 1


# --------------------------------------------------------------------------
# degenerate branches: the file is PRESENT but useless
#
# Added after @curupira ran 67 AST mutants over this module: 52 killed, 11
# equivalent, and 4 that survived. All four are the same shape — a check whose
# row VANISHES on a branch where the file exists but carries nothing usable:
#
#   verify_medallion.py:273  members present, none carrying an id
#   verify_medallion.py:306  members file with zero records
#   verify_medallion.py:333  members file with zero records
#   verify_medallion.py:399  a gold artifact present but not valid JSON
#
# test_check_registration covers the file-ABSENT branches only, so a mutation
# deleting one of these rows changed nothing any test observed. A missing row
# reads as success to anything inspecting verdicts, which is the defect this
# whole module exists to catch — so it is asserted here by NAME, plus rc 2,
# since each of these is control_fired=False and therefore an instrument
# failure rather than a data one.
# --------------------------------------------------------------------------


def _corpus_with_silver(root: Path, members: list[dict[str, object]]) -> None:
    """A complete corpus whose members_statistics.json is what the test says."""
    _build_corpus(root)
    _write_json(root / "data" / "silver" / "members_statistics.json", members)


@pytest.mark.parametrize(
    ("case", "members", "owed"),
    [
        pytest.param(
            "members-without-ids",
            [{"name": "someone"}, {"name": "another"}],
            "member-ids-distinct",
            id="members present but none carries an id (L273)",
        ),
        pytest.param(
            "no-member-records",
            [],
            "unknown-labels-not-growing",
            id="members file with zero records (L306)",
        ),
        pytest.param(
            "no-member-records",
            [],
            "hash-never-a-label",
            id="members file with zero records (L333)",
        ),
    ],
)
def test_degenerate_silver_still_registers_its_row(
    case: str, members: list[dict[str, object]], owed: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A silver file that exists but is useless still names its check."""
    root = tmp_path / "root"
    _corpus_with_silver(root, members)
    ref = tmp_path / "ref"
    _build_reference(ref)

    rc, out, _ = _run(monkeypatch, capsys, "--root", str(root), "--reference", str(ref))

    names = {m.group("name") for m in _parse_rows(out)}
    assert owed in names, f"{case}: {owed} vanished from the report — {sorted(names)}"
    assert rc == 2, f"{case}: an instrument that could not run must exit 2, got {rc}"


def test_unreadable_gold_artifact_still_registers_its_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A gold artifact present but unparseable still names gold-file-set (L399).

    The distinction that matters: 'absent' and 'present but not JSON' take
    different branches, and only the first was covered. A mutation deleting
    the second branch's row left every test green.
    """
    root = tmp_path / "root"
    _build_corpus(root)
    (root / "data" / "gold" / "registry.json").write_text("{not json", encoding="utf-8")
    ref = tmp_path / "ref"
    _build_reference(ref)

    rc, out, _ = _run(monkeypatch, capsys, "--root", str(root), "--reference", str(ref))

    names = {m.group("name") for m in _parse_rows(out)}
    assert "gold-file-set" in names, f"gold-file-set vanished — {sorted(names)}"
    assert rc == 2, f"an unreadable artifact is an instrument failure, got {rc}"
