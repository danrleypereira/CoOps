"""Session-level hooks for the unit suite (fixtures live in tests/conftest.py)."""

from __future__ import annotations

import sys

import pytest

#: The module whose adapter coverage the terminal summary reports. Looked
#: up in ``sys.modules`` so the hook costs nothing on runs that do not
#: collect it.
_SUITE_MODULE = "tests.unit.test_storage_contract_suite"


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, exitstatus: int, config: pytest.Config
) -> None:
    """Name which StoragePort adapters the contract suite exercised.

    ``MongoStorageAdapter`` legitimately skips when ``MONGO_URI`` is unset,
    but the skip must stay visible: a suite that quietly narrows to one
    adapter while still passing is the defect class this project keeps
    finding (#55). The suite's own guard test fails a run where even the
    file adapter skipped; this line is the report that makes the narrower
    case legible in every run, including under ``-q``.
    """
    suite = sys.modules.get(_SUITE_MODULE)
    if suite is None:
        return  # the suite was not collected; nothing to report
    terminalreporter.write_sep("-", suite.coverage_line())
