"""The filesystem ``StoragePort`` adapter: one JSON file per dataset.

Local development's implementation of
:class:`coops.domain.ports.storage_port.StoragePort` — the same on-disk
shape ``coops.bronze.files`` already enumerates, with one tenant segment
added above the layer::

    <root>/<tenant>/<layer>/<entity>.json

The tenant segment is the port's isolation promise made a filesystem
fact: two tenants that save the same ``(layer, entity)`` write two
different files, and a load for one has no path that reaches the other.
Dropping the segment would make every tenant share one dataset, which is
why the tenant-isolation tests in ``tests/unit/test_files_adapter.py``
(and the contract suite it runs) fail loudly if it is ever removed.

Writes are atomic. ``save`` serialises into a temporary file created
*beside* the target and ``os.replace``s it onto the target, so a crash
mid-write leaves either the previous dataset or a complete new one —
never a half-written file that a later ``load`` would parse as truncated
data. ``os.replace`` is only atomic within one filesystem, which is why
the temporary file lives in the target's directory rather than in the
system temp directory.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from coops.domain.ports.storage_port import (
    JSONValue,
    Layer,
    StoragePort,
    StoredDataset,
    validate_entity,
    validate_layer,
)
from coops.domain.tenancy import TenantId

__all__ = ["FileStorageAdapter"]

#: Extension this adapter owns (``storage_port._JSON_SUFFIX``); the entity
#: name is the file stem, so an entity carrying the extension would address
#: one dataset two ways.
_SUFFIX = ".json"

#: Suffix of the temporary file ``save`` builds before the ``os.replace``.
#: Never ``_SUFFIX``, so an interrupted write cannot be mistaken for a
#: dataset by ``list``.
_TEMP_SUFFIX = ".tmp"


class FileStorageAdapter:
    """``StoragePort`` over a directory tree — the local-development driver.

    The root directory is given at construction and created lazily by
    ``save``: constructing an adapter must not touch the filesystem, so a
    wrong root fails on first write rather than silently creating a
    directory somewhere it was never meant to exist.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def _dataset_path(self, tenant: TenantId, layer: Layer, entity: str) -> Path:
        """The one file ``(tenant, layer, entity)`` addresses.

        Every component comes back validated: the tenant slug from
        ``TenantId.__post_init__``, the layer and entity from the
        ``validate_*`` calls each public method makes before it gets here,
        so a path cannot leave its tenant's layer directory.
        """
        return self._root / str(tenant) / layer / f"{entity}{_SUFFIX}"

    def save(
        self,
        tenant: TenantId,
        layer: Layer,
        entity: str,
        data: JSONValue,
    ) -> None:
        """Store (or replace) the dataset, atomically.

        Validation runs before anything touches the disk, so a rejected
        address leaves no directory, no file and no temporary behind. The
        write itself replaces the target outright — there is no read of
        what is already there, so no call can append to or merge with a
        previous dataset.
        """
        layer = validate_layer(layer)
        entity = validate_entity(entity)
        target = self._dataset_path(tenant, layer, entity)
        target.parent.mkdir(parents=True, exist_ok=True)

        descriptor, temp_name = tempfile.mkstemp(
            dir=target.parent, prefix=f".{entity}.", suffix=_TEMP_SUFFIX
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            os.replace(temp_name, target)
        except BaseException:
            # A failed serialise or replace must not leave the temporary
            # file beside the datasets, where a later run would trip over
            # it; the previous dataset, if any, is still intact.
            Path(temp_name).unlink(missing_ok=True)
            raise

    def load(
        self,
        tenant: TenantId,
        layer: Layer,
        entity: str,
    ) -> StoredDataset | None:
        """Return the dataset at the address, or ``None`` if nothing is stored.

        A missing file is an answer, not an error: the ETL distinguishes
        "never captured" from "captured and corrupt", and only the second
        raises (``json.load``, on a file this adapter's atomic writes
        cannot produce).
        """
        layer = validate_layer(layer)
        entity = validate_entity(entity)
        path = self._dataset_path(tenant, layer, entity)
        if not path.is_file():
            return None
        with open(path, encoding="utf-8") as handle:
            data = cast(JSONValue, json.load(handle))
        return StoredDataset(tenant=tenant, layer=layer, entity=entity, data=data)

    def list(self, tenant: TenantId, layer: Layer) -> list[str]:
        """Entity names stored under ``(tenant, layer)``, sorted.

        Only files this port could have written count as datasets. The
        publish step writes ``*_all.json`` aggregates *beside* the
        per-repository files (the ``storage_port`` module docstring: they
        are not addressable through the port), and an interrupted ``save``
        leaves a ``.tmp`` behind — neither is listed, so enumeration never
        hands a caller something ``load`` would reject or double-count.
        """
        layer = validate_layer(layer)
        directory = self._root / str(tenant) / layer
        if not directory.is_dir():
            return []
        names: list[str] = []
        for path in directory.iterdir():
            if not path.is_file() or path.suffix != _SUFFIX:
                continue
            try:
                names.append(validate_entity(path.stem))
            except ValueError:
                # Not a dataset this port addresses — a publish aggregate
                # or a hand-placed file. Listed files and loadable files
                # must be the same set, so an unloadable name is skipped
                # rather than returned.
                continue
        return sorted(names)


if TYPE_CHECKING:
    # The static half of the port contract (the [tool.mypy] note in
    # pyproject.toml): a runtime ``isinstance`` check against a
    # @runtime_checkable Protocol verifies method *names* only, so this
    # assignment is what turns signature drift into a type error. The
    # branch never runs — coverage excludes it, and no adapter is built.
    _ADAPTER_IS_A_PORT: StoragePort = FileStorageAdapter(Path("."))
