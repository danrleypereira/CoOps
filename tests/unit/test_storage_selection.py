"""Unit tests for coops.storage.selection — COOPS_STORAGE wiring (#42).

The selector is the one place configuration becomes a ``StoragePort``, so
these tests assert the behaviour the issue exists for:

- every accepted ``COOPS_STORAGE`` value yields a port that really stores
  and reads a dataset, **in the medium that value names** — files under
  ``./data`` for ``"data"``, documents in the collection for ``"mongo"``.
  A round-trip alone cannot tell the adapters apart (both pass it), so the
  side effect is asserted too, on the whole artifact;
- an unrecognised value raises, naming the value and the accepted set, and
  a typo leaves nothing written anywhere — the selector never falls back
  (the #129 wrong-org dashboard and #212 evergreen skips are this defect
  class);
- unset and empty behave as documented: ``Settings`` normalises both to the
  ``"data"`` default, and a value outside the accepted set reaching the
  factory — including an explicitly empty one — raises.

The MongoDB leg fakes the driver at the ``pymongo.MongoClient`` boundary,
the outermost edge: everything inboard — ``Settings``, the uri pass-through,
``MongoStorageAdapter``'s document writes — runs for real, and no network
is attempted. The in-memory collection is the one
``tests/unit/test_storage_datasets.py`` drives the adapter with directly.
"""

from __future__ import annotations

import json

import pytest

from coops.domain import TenantId
from coops.domain.ports import JSONValue, StoragePort
from coops.infrastructure.config import Settings
from coops.storage import select_storage
from coops.storage.selection import STORAGE_BACKENDS
from tests.unit.test_storage_datasets import FakeCollection

ORG = TenantId("org-a")
ENTITY = "issues_2099.1-Demo"
PAYLOAD: JSONValue = [{"number": 1, "title": "Ação"}]

MONGO_URI = "mongodb://fake.test:27017"


@pytest.fixture(autouse=True)
def _clean_env(tmp_path, monkeypatch):
    """No COOPS_STORAGE/MONGO_URI from the machine, and a cwd whose ./data
    is the test's own — the selector roots the file adapter at ./data, so
    the checkout's data/ must be unreachable (tests never write into it)."""
    for var in ("COOPS_STORAGE", "MONGO_URI"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    yield


class _FakeDatabase:
    def __init__(self, collection):
        self._collection = collection

    def __getitem__(self, key):
        return self._collection


class FakeMongoClient:
    """``pymongo.MongoClient`` stand-in: records how it was built and serves
    one in-memory collection, so the uri the selector passed is assertable."""

    def __init__(self, uri, **kwargs):
        self.uri = uri
        self.kwargs = kwargs
        self.collection = FakeCollection()

    def __getitem__(self, database):
        return _FakeDatabase(self.collection)

    def close(self):
        pass


@pytest.fixture
def mongo_clients(monkeypatch):
    """Every MongoClient the selector builds lands here, fully functional."""
    import pymongo

    built = []

    def _fake_client(uri, **kwargs):
        client = FakeMongoClient(uri, **kwargs)
        built.append(client)
        return client

    monkeypatch.setattr(pymongo, "MongoClient", _fake_client)
    return built


def _corpus_json(data: JSONValue) -> str:
    """The exact bytes the ETL's JSON writers produce (indent=2, non-ASCII
    kept) — the whole artifact, not a prefix."""
    return json.dumps(data, indent=2, ensure_ascii=False)


class TestDataBackend:
    def test_the_documented_default_round_trips_through_files(self, tmp_path):
        settings = Settings()  # COOPS_STORAGE unset: the documented default
        assert settings.coops_storage == "data"

        store = select_storage(settings)

        assert isinstance(store, StoragePort)
        store.save(ORG, "bronze", ENTITY, PAYLOAD)
        loaded = store.load(ORG, "bronze", ENTITY)
        assert loaded is not None
        assert loaded.data == PAYLOAD
        assert loaded.tenant == ORG
        # The medium is the filesystem, and the bytes are the corpus format:
        # this is what pins the value "data" to the file adapter.
        written = tmp_path / "data" / "org-a" / "bronze" / f"{ENTITY}.json"
        assert written.read_text(encoding="utf-8") == _corpus_json(PAYLOAD)

    def test_an_empty_env_value_selects_the_default(self, monkeypatch, tmp_path):
        # An undefined Actions secret expands to "" — documented to count as
        # unset — so a workflow template cannot fail the run by existing.
        monkeypatch.setenv("COOPS_STORAGE", "")
        assert Settings().coops_storage == "data"

        store = select_storage(Settings())

        store.save(ORG, "gold", "executive_dashboard", {"v": 1})
        assert (tmp_path / "data" / "org-a" / "gold" / "executive_dashboard.json").is_file()


class TestMongoBackend:
    def test_round_trips_through_documents_from_the_configured_uri(
        self, mongo_clients
    ):
        settings = Settings(coops_storage="mongo", mongo_uri=MONGO_URI)

        store = select_storage(settings)

        assert isinstance(store, StoragePort)
        store.save(ORG, "silver", ENTITY, PAYLOAD)
        loaded = store.load(ORG, "silver", ENTITY)
        assert loaded is not None
        assert loaded.data == PAYLOAD
        # The medium is the collection, and the client was built from the
        # configured uri — this is what pins "mongo" to the Mongo adapter.
        assert len(mongo_clients) == 1
        assert mongo_clients[0].uri == MONGO_URI
        assert (
            mongo_clients[0].collection.count_documents(
                {"tenant_id": "org-a", "layer": "silver", "entity": ENTITY}
            )
            == 1
        )

    def test_mongo_without_a_uri_raises_naming_the_setting_and_stores_nothing(
        self, mongo_clients, tmp_path
    ):
        settings = Settings(coops_storage="mongo")
        assert settings.mongo_uri is None

        with pytest.raises(ValueError, match="MONGO_URI"):
            select_storage(settings)

        # A guard is proven by what did not happen: no client was built and
        # no file adapter ran in the Mongo branch's place.
        assert mongo_clients == []
        assert not (tmp_path / "data").exists()


class TestUnknownValues:
    @pytest.mark.parametrize(
        "bad",
        [
            "mongoo",   # the typo from the issue text
            "Mongo",    # no case folding
            " mongo",   # no trimming
            "mongo ",   # no trimming
            "data/",    # a path is not a selector
            "files",    # a plausible synonym is still unknown
            "raw",      # the raw tier has its own port, not a backend
            "",         # only a directly-built Settings can carry this
        ],
    )
    def test_raises_naming_the_value_and_the_accepted_set(self, bad):
        with pytest.raises(ValueError) as excinfo:
            select_storage(Settings(coops_storage=bad))

        message = str(excinfo.value)
        assert bad in message, message
        for accepted in sorted(STORAGE_BACKENDS):
            assert accepted in message, message

    def test_a_typo_writes_nowhere_rather_than_defaulting(self, tmp_path):
        # The effect, not the raise: a selector that quietly fell back to
        # files would leave a data/ tree behind and report success.
        with pytest.raises(ValueError):
            select_storage(Settings(coops_storage="mongoo"))

        assert not (tmp_path / "data").exists()

    def test_the_accepted_set_is_exactly_the_documented_pair(self):
        # What the Settings docstring documents, pinned: adding a backend
        # means changing both this set and the branch, deliberately.
        assert sorted(STORAGE_BACKENDS) == ["data", "mongo"]


class TestExports:
    def test_both_adapters_and_the_selector_come_from_coops_storage(self):
        import coops.storage as package
        from coops.storage.datasets import MongoStorageAdapter
        from coops.storage.file import FileStorageAdapter

        assert package.FileStorageAdapter is FileStorageAdapter
        assert package.MongoStorageAdapter is MongoStorageAdapter
        assert callable(package.select_storage)
