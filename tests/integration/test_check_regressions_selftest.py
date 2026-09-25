"""Integration test: the regression gate's self-test, with the real tools.

`scripts/check_regressions.py --self-test` is the control that proves the
gate can fail: it plants a type error in a file the configured mypy scope
excludes (the exact Phase 1 blind spot), plants findings in a new file,
compares an unchanged tree, and checks that a file which improves is not
reported. A gate whose controls do not fire is decorative, so this test runs
them for real — pinned ruff and mypy from the venv, materialized arms of
this repository — and refuses a self-test that does not pass.

Slow by design (several cold mypy runs across materialized arms, ~1 minute);
it is the end-to-end counterpart to the fast unit tests, which use fakes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_regressions.py"


def test_self_test_all_four_controls_fire():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--self-test"],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    for control in ("control 1", "control 2", "control 3", "control 4"):
        assert control in proc.stdout, f"{control} did not run: {output}"
    assert "all four controls fired" in proc.stdout
    # the blind-spot control must show both sides: the configured scope
    # blind, the gate not
    assert "configured mypy scope does not report the file" in proc.stdout
