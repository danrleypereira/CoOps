"""Ports: the interfaces the pipeline depends on, not the drivers behind them.

A port is a structural (`typing.Protocol`) interface with the tenant scope
built into every method, so an implementation cannot be reached without it.
Implementations live elsewhere — ``coops.storage`` today, adapters per #39 —
and nothing under ``coops.domain`` imports a database library.
"""

from .source_port import (
    SourceAccessError,
    SourceError,
    SourceNotFoundError,
    SourcePort,
    SourceUnavailableError,
    validate_branch,
    validate_repo_name,
)
from .storage_port import (
    LAYERS,
    JSONValue,
    Layer,
    StoragePort,
    StoredDataset,
    validate_entity,
    validate_layer,
)

__all__ = [
    "LAYERS",
    "JSONValue",
    "Layer",
    "SourceAccessError",
    "SourceError",
    "SourceNotFoundError",
    "SourcePort",
    "SourceUnavailableError",
    "StoragePort",
    "StoredDataset",
    "validate_branch",
    "validate_entity",
    "validate_layer",
    "validate_repo_name",
]
