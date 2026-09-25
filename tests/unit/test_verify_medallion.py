"""Unit tests for scripts/verify_medallion.py — the staleness pair.

Regression coverage for the reporting hole where an unusable reference corpus
(empty, partial, a wrong path, a different organisation) made ``compared == 0``
and the early return left ``no-record-vanished`` out of the report entirely.
A check that is never emitted cannot fail, so the tests assert PRESENCE first:
asserting only "no failures" would also pass on the broken code.
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
