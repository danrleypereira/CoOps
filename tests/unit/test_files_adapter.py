"""FileStorageAdapter: the StoragePort contract, plus what only a filesystem promises.

The port behaviours (round-trip, replace-not-append, tenant scoping,
sorted ``list``, validator rejections) are the contract every
implementation must hold, so this module runs the whole of
``StoragePortContract`` against the filesystem adapter — the same suite
``test_storage_port.py`` runs against its in-memory reference. What only
a filesystem can promise is tested on top:

- the layout ``<root>/<tenant>/<layer>/<entity>.json``, tenant segment
  included, parents created on demand;
- the write is a same-directory temp file ``os.replace``d onto the
  target — no stray temporary survives a save, and a failed write leaves
  the previous dataset intact;
- validation happens *before* any disk effect: a traversal attempt such
  as ``../../etc/passwd`` raises and leaves the root empty, having
  written nothing anywhere beneath it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coops.domain import TenantId
from coops.domain.ports import StoragePort
from coops.storage.files_adapter import FileStorageAdapter
from tests.unit.test_storage_port import StoragePortContract

TENANT_A = TenantId("org-a")


def test_the_adapter_satisfies_the_protocol(tmp_path: Path) -> None:
    assert isinstance(FileStorageAdapter(tmp_path), StoragePort)


class TestFileStoragePort(StoragePortContract):
    """The full port contract, run against a real directory tree."""

    # The base suite instantiates the store through a no-argument
    # ``make_store``; this adapter needs a per-test root, so the fixture
    # itself is what is overridden — ``tmp_path`` is exactly the scratch
    # directory the sandbox allows.
    @pytest.fixture
    def store(self, tmp_path: Path) -> StoragePort:
        return FileStorageAdapter(tmp_path)


class TestLayout:
    """Where a dataset lands — and where it must not."""

    def test_dataset_lives_at_tenant_layer_entity(self, tmp_path: Path) -> None:
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "bronze", "issues_2099.1-Demo", [{"number": 1}])
        assert (tmp_path / "org-a" / "bronze" / "issues_2099.1-Demo.json").is_file()

    def test_two_tenants_never_share_a_path(self, tmp_path: Path) -> None:
        # Same (layer, entity), two tenants: two files in two directories.
        # A shared path here is one tenant overwriting another's dataset.
        store = FileStorageAdapter(tmp_path)
        store.save(TenantId("org-a"), "bronze", "issues_d", [{"who": "a"}])
        store.save(TenantId("org-b"), "bronze", "issues_d", [{"who": "b"}])
        assert (tmp_path / "org-a" / "bronze" / "issues_d.json").is_file()
        assert (tmp_path / "org-b" / "bronze" / "issues_d.json").is_file()

    def test_save_creates_the_parent_directories(self, tmp_path: Path) -> None:
        root = tmp_path / "storage"  # does not exist yet
        store = FileStorageAdapter(root)
        store.save(TENANT_A, "gold", "executive_dashboard", {"kpi": 1})
        assert (root / "org-a" / "gold" / "executive_dashboard.json").is_file()

    def test_construction_touches_nothing(self, tmp_path: Path) -> None:
        # A wrong root should fail on first write, not quietly create a
        # directory tree the moment the adapter is built.
        FileStorageAdapter(tmp_path / "nowhere")
        assert not (tmp_path / "nowhere").exists()


class TestAtomicReplace:
    """save replaces outright, atomically, and cleans up after itself."""

    def test_second_save_leaves_one_file_holding_the_second_content(
        self, tmp_path: Path
    ) -> None:
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "bronze", "issues_d", [{"n": 1}])
        store.save(TENANT_A, "bronze", "issues_d", [{"n": 2}])

        layer_dir = tmp_path / "org-a" / "bronze"
        assert sorted(path.name for path in layer_dir.iterdir()) == ["issues_d.json"]
        with open(layer_dir / "issues_d.json", encoding="utf-8") as handle:
            assert json.load(handle) == [{"n": 2}]

    def test_save_leaves_no_temp_file_behind(self, tmp_path: Path) -> None:
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "bronze", "issues_d", [{"n": 1}])
        layer_dir = tmp_path / "org-a" / "bronze"
        assert [path.name for path in layer_dir.iterdir()] == ["issues_d.json"]

    def test_a_failed_write_keeps_the_previous_dataset_and_cleans_up(
        self, tmp_path: Path
    ) -> None:
        # ``object()`` is not JSON-serialisable: the dump fails after the
        # temporary exists, which is the crash-mid-write shape. The target
        # must still hold the first save, and no temporary may survive.
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "bronze", "issues_d", [{"n": 1}])
        with pytest.raises(TypeError):
            store.save(TENANT_A, "bronze", "issues_d", {"bad": object()})

        layer_dir = tmp_path / "org-a" / "bronze"
        assert [path.name for path in layer_dir.iterdir()] == ["issues_d.json"]
        loaded = store.load(TENANT_A, "bronze", "issues_d")
        assert loaded is not None
        assert loaded.data == [{"n": 1}]


class TestValidationPrecedesDisk:
    """A rejected address must leave the root exactly as it was."""

    @pytest.mark.parametrize("method", ["save", "load", "list"])
    def test_the_raw_capture_tier_is_rejected_on_every_method(
        self, tmp_path: Path, method: str
    ) -> None:
        store = FileStorageAdapter(tmp_path)
        with pytest.raises(ValueError, match="unknown layer"):
            if method == "save":
                store.save(TENANT_A, "raw", "issues_d", [])
            elif method == "load":
                store.load(TENANT_A, "raw", "issues_d")
            else:
                store.list(TENANT_A, "raw")
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize(
        "entity",
        [
            # The traversal that would escape the layer directory if the
            # separator rule ever stopped holding.
            "../../etc/passwd",
            "issues_a/b",
            "issues_a\\b",
            "../issues_a",
            # The extension the adapter owns.
            "issues_d.json",
            # The publish aggregate the port refuses to address.
            "issues_all",
            # Blank after trimming.
            "",
            "   ",
        ],
    )
    def test_an_invalid_entity_is_rejected_writing_nothing(
        self, tmp_path: Path, entity: str
    ) -> None:
        store = FileStorageAdapter(tmp_path)
        with pytest.raises(ValueError):
            store.save(TENANT_A, "bronze", entity, [])
        # Nothing anywhere beneath the root — directories included, which
        # is what a traversal would have to create to get out.
        assert list(tmp_path.rglob("*")) == []

    @pytest.mark.parametrize(
        "entity", ["../../etc/passwd", "issues_a/b", "issues_d.json", "issues_all"]
    )
    def test_an_invalid_entity_is_rejected_on_load_too(
        self, tmp_path: Path, entity: str
    ) -> None:
        store = FileStorageAdapter(tmp_path)
        with pytest.raises(ValueError):
            store.load(TENANT_A, "bronze", entity)

    def test_a_rejected_save_leaves_existing_datasets_alone(self, tmp_path: Path) -> None:
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "bronze", "issues_d", [{"n": 1}])
        with pytest.raises(ValueError, match="path separator"):
            store.save(TENANT_A, "bronze", "../issues_d", [{"n": 2}])
        loaded = store.load(TENANT_A, "bronze", "issues_d")
        assert loaded is not None
        assert loaded.data == [{"n": 1}]
        assert store.list(TENANT_A, "bronze") == ["issues_d"]


class TestListOnTheRealLayout:
    """``list`` names only what this port could have written."""

    def test_a_publish_aggregate_beside_the_datasets_is_not_listed(
        self, tmp_path: Path
    ) -> None:
        # The publish step writes ``*_all.json`` into the layer directory
        # (outside this port); it must not surface as a dataset.
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "bronze", "issues_a", [])
        aggregate = tmp_path / "org-a" / "bronze" / "issues_all.json"
        aggregate.write_text("[]", encoding="utf-8")
        assert store.list(TENANT_A, "bronze") == ["issues_a"]

    def test_a_leftover_temp_file_is_not_listed(self, tmp_path: Path) -> None:
        # What an interrupted save leaves behind: hidden, ``.tmp``, never
        # a dataset.
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "bronze", "issues_a", [])
        leftover = tmp_path / "org-a" / "bronze" / ".issues_b.crash.tmp"
        leftover.write_text("[", encoding="utf-8")
        assert store.list(TENANT_A, "bronze") == ["issues_a"]

    def test_list_returns_stems_without_the_extension(self, tmp_path: Path) -> None:
        store = FileStorageAdapter(tmp_path)
        store.save(TENANT_A, "silver", "members_detailed", [])
        assert store.list(TENANT_A, "silver") == ["members_detailed"]

    def test_load_from_a_missing_tenant_directory_is_none(self, tmp_path: Path) -> None:
        # The tenant's directory was never created; that is a miss, not an
        # error.
        store = FileStorageAdapter(tmp_path)
        assert store.load(TenantId("nobody"), "bronze", "issues_d") is None
        assert store.list(TenantId("nobody"), "bronze") == []


class TestPayloadShapes:
    def test_non_ascii_payload_round_trips(self, tmp_path: Path) -> None:
        store = FileStorageAdapter(tmp_path)
        data = [{"name": "Aloísio-Nº-2099.1 — medição"}]
        store.save(TENANT_A, "silver", "members_detailed", data)
        loaded = store.load(TENANT_A, "silver", "members_detailed")
        assert loaded is not None
        assert loaded.data == data
