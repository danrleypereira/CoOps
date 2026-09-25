"""The one contract suite every ``StoragePort`` adapter must pass (#55).

The per-adapter suites stay — ``test_file_storage_adapter.py`` and friends
prove each adapter does what its author thought. They cannot prove the
adapters **agree with each other**, and agreement is the property the port
exists to provide: the whole point of ``StoragePort`` is that a caller can
swap adapters and not care. This module is the runtime half of that
guarantee, next to the static half — the ``_conforms_to_storage_port``
anchors in ``file.py`` and ``datasets.py`` make *shape* drift a mypy
error, and the parametrised suite here makes *behaviour* drift a test
failure: a third adapter that answers ``[]`` where the others answer
``None`` cannot land green, months before a caller finds out.

Shape: **one** parametrised suite. Every contract below is written once
and runs once per adapter through the ``adapter`` fixture. A test written
per adapter is the thing this module replaces.

Anti-drift — the property that keeps this true after this PR, because a
suite that silently stops covering a new adapter is two test runs with
extra machinery:

- the fixture's parameters are **derived**:
  :func:`exported_storage_adapters` scans ``coops.storage.__all__`` at
  collection time — never a hand-written list of names — so exporting a
  new ``StoragePort`` implementation sweeps it into the suite;
- a parametrised adapter with no factory **fails** the run rather than
  skipping out of it;
- ``test_every_exported_adapter_is_in_the_suite_parameters`` re-scans the
  exports at test time and compares them with what the fixture was
  collected with, so the parameter list cannot quietly become stale or
  hand-written;
- ``test_the_run_exercised_the_file_adapter`` (last in this module: pytest
  runs tests in definition order) fails a run in which the file adapter
  never executed, so the suite cannot pass vacuously.

``MongoStorageAdapter`` needs a live database. It is skipped when
``MONGO_URI`` is unset or unreachable — every skip reason names the
variable — and the skip is reported, never silent:
``tests/unit/conftest.py`` prints, at the end of any run that collects
this module, which adapters were exercised and which skipped. No new
infrastructure is required; #57 tracks a containerised database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pymongo
import pytest
from pymongo.errors import PyMongoError

import coops.storage
from coops.domain import TenantId
from coops.domain.ports import JSONValue, StoragePort, StoredDataset

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

#: The environment variable that opts the Mongo adapter into this suite.
#: Every skip reason names it: a skip that does not say what would have
#: turned it on is how a suite comes to pass while testing fewer adapters
#: than anyone believes it does.
MONGO_URI_ENV = "MONGO_URI"


def exported_storage_adapters() -> list[type[StoragePort]]:
    """Every ``StoragePort`` implementation exported by ``coops.storage``.

    Derived from ``coops.storage.__all__`` at call time, so the scan — and
    with it the suite — changes the moment an adapter is exported. The
    raw-capture types sharing that ``__all__`` are filtered out
    structurally, not by name: ``RawStore``/``MongoRawStore`` answer
    ``save``/``get``, not ``load``/``list``, so ``issubclass`` cannot
    mistake them for dataset adapters — and a renamed or added raw type
    needs no edit here either.
    """
    adapters = [
        exported
        for name in coops.storage.__all__
        if isinstance(exported := getattr(coops.storage, name), type)
        and issubclass(exported, StoragePort)
    ]
    return sorted(adapters, key=lambda adapter_class: adapter_class.__name__)


#: What the ``adapter`` fixture is parametrised over — a snapshot of
#: :func:`exported_storage_adapters` taken when this module is collected.
#: Derived, never hand-written: the anti-drift test below compares a fresh
#: scan against it, which is only meaningful because neither side is a
#: literal list of adapter names.
SUITE_ADAPTERS: list[type[StoragePort]] = exported_storage_adapters()


@contextmanager
def _file_adapter(tmp_path: Path) -> Iterator[StoragePort]:
    """The plain adapter, rooted in the test's own scratch directory."""
    yield coops.storage.FileStorageAdapter(tmp_path / "contract-suite")


@contextmanager
def _mongo_adapter(tmp_path: Path) -> Iterator[StoragePort]:
    """The document adapter, against the live MongoDB named by ``MONGO_URI``.

    Each test gets its own throwaway database (dropped on teardown), so
    tests cannot see each other's tenants and the suite leaves nothing
    behind. ``MongoStorageAdapter`` connects and creates its index eagerly,
    so an unreachable server fails fast into the skip below.
    """
    uri = os.environ.get(MONGO_URI_ENV, "").strip()
    if not uri:
        pytest.skip(
            f"{MONGO_URI_ENV} is not set, so MongoStorageAdapter is NOT "
            "exercised — export MONGO_URI (see docker-compose.dev.yml) to "
            "include it in the contract suite"
        )
    database = f"coops_contract_suite_{uuid4().hex}"
    try:
        adapter = coops.storage.MongoStorageAdapter(uri, database=database)
    except PyMongoError as error:
        pytest.skip(
            f"{MONGO_URI_ENV} is set but MongoDB is unreachable, so "
            f"MongoStorageAdapter is NOT exercised: {error}"
        )
    try:
        yield adapter
    finally:
        adapter.close()
        cleanup = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
        try:
            cleanup.drop_database(database)
        finally:
            cleanup.close()


#: How to build one adapter per parametrised test. A new exported
#: implementation with no entry here fails the run (see the ``adapter``
#: fixture): it must be exercised, not skipped.
_ADAPTER_FACTORIES: dict[str, Callable[[Path], AbstractContextManager[StoragePort]]] = {
    coops.storage.FileStorageAdapter.__name__: _file_adapter,
    coops.storage.MongoStorageAdapter.__name__: _mongo_adapter,
}

#: Names of the adapters whose contract tests actually executed in this
#: run — what the terminal summary reports and the suite-level guard
#: asserts against. An adapter that skipped never lands here.
_EXERCISED: set[str] = set()


@pytest.fixture(params=SUITE_ADAPTERS, ids=lambda adapter_class: adapter_class.__name__)
def adapter(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[StoragePort]:
    """One fresh ``StoragePort`` per exported adapter, per test.

    Parametrised over :data:`SUITE_ADAPTERS` — the derived list, so adding
    an adapter and exporting it subjects it to every test in this module
    with no edit here. A missing factory is a failure, not a skip.
    """
    adapter_class = request.param
    factory = _ADAPTER_FACTORIES.get(adapter_class.__name__)
    if factory is None:
        pytest.fail(
            f"{adapter_class.__name__} is exported by coops.storage as a "
            "StoragePort implementation but has no factory in the contract "
            "suite (tests/unit/test_storage_contract_suite.py) — add one, "
            "or the suite has stopped covering it",
            pytrace=False,
        )
    with factory(tmp_path) as instance:
        _EXERCISED.add(adapter_class.__name__)
        yield instance


# ---------------------------------------------------------------------------
# the contract — written once, asserted of every adapter
# ---------------------------------------------------------------------------


def test_save_then_load_round_trips_the_dataset(adapter: StoragePort) -> None:
    data: JSONValue = {
        "name": "Ação & Café",
        "count": 42,
        "nested": {"ids": [1, 2, 3], "flag": True, "note": None},
    }
    adapter.save(TenantId("org-a"), "bronze", "issues_2099.1-Demo.App", data)
    loaded = adapter.load(TenantId("org-a"), "bronze", "issues_2099.1-Demo.App")
    # Whole-value equality: address and payload both, not just truthiness.
    assert loaded == StoredDataset(
        tenant=TenantId("org-a"),
        layer="bronze",
        entity="issues_2099.1-Demo.App",
        data=data,
    )


def test_load_of_an_address_never_written_returns_none(adapter: StoragePort) -> None:
    # `is None`, not falsiness: an adapter answering [] or {} for an absent
    # read is exactly the silent divergence this suite exists to catch, and
    # it must fail here on every adapter it appears in.
    tenant = TenantId("org-a")
    adapter.save(tenant, "bronze", "issues_written", [])
    assert adapter.load(tenant, "bronze", "issues_never_written") is None
    # A tenant nothing was ever written under answers the same way — the
    # same answer from every adapter, not one only when the tenant exists.
    assert adapter.load(TenantId("org-b"), "bronze", "issues_written") is None


def test_list_returns_the_tenants_entity_names_sorted(adapter: StoragePort) -> None:
    tenant = TenantId("org-a")
    written = [
        "issues_zeta",
        "issues_2099.1-Demo.App",
        "issues_alpha",
        "members_detailed",
    ]
    for entity in written:
        adapter.save(tenant, "bronze", entity, [])
    assert adapter.list(tenant, "bronze") == sorted(written)


def test_list_of_an_unknown_tenant_is_an_empty_sequence(adapter: StoragePort) -> None:
    assert adapter.list(TenantId("never-written"), "gold") == []


def test_second_save_replaces_the_dataset_not_appends(adapter: StoragePort) -> None:
    tenant = TenantId("org-a")
    adapter.save(tenant, "silver", "members_detailed", [{"n": 1}])
    adapter.save(tenant, "silver", "members_detailed", [{"n": 2}, {"n": 3}])
    loaded = adapter.load(tenant, "silver", "members_detailed")
    assert loaded is not None
    assert loaded.data == [{"n": 2}, {"n": 3}]
    # One dataset at the address, not two: enumeration is the witness that
    # no second copy accumulated anywhere the tenant can see.
    assert adapter.list(tenant, "silver") == ["members_detailed"]


def test_tenant_isolation_on_load(adapter: StoragePort) -> None:
    # The headline. Tenant B is not empty — it has its own dataset — so a
    # None here is scope, not absence-of-anything.
    tenant_a = TenantId("org-a")
    tenant_b = TenantId("org-b")
    adapter.save(tenant_a, "bronze", "issues_secret", [{"author": "a"}])
    adapter.save(tenant_b, "bronze", "issues_of_b", [{"author": "b"}])
    assert adapter.load(tenant_b, "bronze", "issues_secret") is None


def test_tenant_isolation_on_list(adapter: StoragePort) -> None:
    # The other read path: invisible to `load` AND not named by `list`.
    # An adapter that scopes one method but not the other fails here.
    tenant_a = TenantId("org-a")
    tenant_b = TenantId("org-b")
    adapter.save(tenant_a, "bronze", "issues_secret", [])
    adapter.save(tenant_b, "bronze", "issues_of_b", [])
    listed = adapter.list(tenant_b, "bronze")
    assert "issues_secret" not in listed
    assert listed == ["issues_of_b"]


def test_the_layer_is_part_of_the_address(adapter: StoragePort) -> None:
    # bronze/members_detailed and silver/members_detailed are two datasets
    # that must coexist — the collision the Mongo compound index exists to
    # prevent, asserted here of every adapter alike.
    tenant = TenantId("org-a")
    adapter.save(tenant, "bronze", "members_detailed", [{"src": "bronze"}])
    adapter.save(tenant, "silver", "members_detailed", [{"src": "silver"}])
    bronze = adapter.load(tenant, "bronze", "members_detailed")
    silver = adapter.load(tenant, "silver", "members_detailed")
    assert bronze is not None and bronze.data == [{"src": "bronze"}]
    assert silver is not None and silver.data == [{"src": "silver"}]
    assert adapter.list(tenant, "gold") == []


# ---------------------------------------------------------------------------
# anti-drift: what keeps the contract above true of every adapter
# ---------------------------------------------------------------------------


def test_every_exported_adapter_is_in_the_suite_parameters() -> None:
    """The keystone: the suite's parameters track ``coops.storage``.

    Re-scans the exports *now* and compares with what the ``adapter``
    fixture was collected with (:data:`SUITE_ADAPTERS`). Both directions
    matter: an exported implementation the suite never parametrised over
    is coverage silently lost, and a parameter that is not an export is a
    hand-written list — the thing this suite replaces — going stale.
    """
    exported = {cls.__name__ for cls in exported_storage_adapters()}
    parametrised = {cls.__name__ for cls in SUITE_ADAPTERS}
    missing = sorted(exported - parametrised)
    assert not missing, (
        f"StoragePort implementation(s) {missing} are exported by "
        "coops.storage but are not in the contract suite's parameters — "
        "the suite has drifted; parametrise over them"
    )
    stale = sorted(parametrised - exported)
    assert not stale, (
        f"contract-suite parameter(s) {stale} are not exported by "
        "coops.storage — derive the parameters from "
        "coops.storage.__all__, not a hand-written list"
    )


def coverage_line() -> str:
    """One line naming which adapters this run exercised and skipped.

    Printed by the ``pytest_terminal_summary`` hook in
    ``tests/unit/conftest.py``, so a run that skips an adapter says so
    even under ``-q``.
    """
    exported = {cls.__name__ for cls in exported_storage_adapters()}
    exercised = sorted(_EXERCISED)
    skipped = sorted(exported - _EXERCISED)
    return (
        f"StoragePort contract suite — exercised: {exercised or 'none'}; "
        f"skipped: {skipped or 'none'}"
    )


def test_the_run_exercised_the_file_adapter() -> None:
    """No vacuous passes: the file adapter actually executed.

    Must stay **last** in this module: it reads :data:`_EXERCISED`, which
    the ``adapter`` fixture fills as tests run. If every adapter skipped
    (an environment where even the filesystem adapter cannot run), the
    suite's green would mean nothing — this fails instead, and says what
    ran and what did not.
    """
    assert "FileStorageAdapter" in _EXERCISED, (
        "the contract suite passed without exercising the file adapter — "
        f"exercised: {sorted(_EXERCISED) or 'none'}; "
        f"not exercised: {sorted({cls.__name__ for cls in exported_storage_adapters()} - _EXERCISED) or 'none'}"
    )
