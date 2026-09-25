"""Unit tests for scripts/verify_medallion.py.

Regression coverage for the staleness pair's reporting hole: an unusable
reference corpus (empty, partial, a wrong path, a different organisation)
made ``compared == 0`` and the early return left ``no-record-vanished`` out
of the report entirely. A check that is never emitted cannot fail, so the
tests assert PRESENCE first: asserting only "no failures" would also pass
on the broken code.

And for gold-regenerated's ordering rule: equality must be settled on the
raw stamp strings BEFORE the 3h naive band is consulted, because a copied
seed is byte-identical, sits at delta 0 — inside the band — and a band-first
comparison passed it as inconclusive, certifying the exact no-run the check
exists to catch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
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
    all_naive = {n: _NAIVE_OLD for n in verify_medallion.EXPECTED_GOLD}
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
    all_naive = {n: _NAIVE_OLD for n in verify_medallion.EXPECTED_GOLD}
    shifted = {n: "2026-09-23T22:00:00" for n in verify_medallion.EXPECTED_GOLD}
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
    ref = {n: "2026-09-24T00:00:00+00:00" for n in verify_medallion.EXPECTED_GOLD}
    root = {n: "2026-09-25T06:00:00+00:00" for n in verify_medallion.EXPECTED_GOLD}
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
