"""Storage adapters.

The raw layer keeps a clean boundary so it can sit behind its port without
rewriting callers; the dataset adapters (#39 Mongo, #41 files) are the
``StoragePort`` drivers, and :func:`select_storage` (#42) is where
configuration chooses between them.
"""

from .datasets import MongoStorageAdapter
from .file import FileStorageAdapter
from .raw import (
    PROVIDER_GITHUB,
    MongoRawStore,
    RawDocument,
    RawStore,
    is_fresh,
    raw_params_hash,
)
from .selection import select_storage

__all__ = [
    "PROVIDER_GITHUB",
    "FileStorageAdapter",
    "MongoRawStore",
    "MongoStorageAdapter",
    "RawDocument",
    "RawStore",
    "is_fresh",
    "raw_params_hash",
    "select_storage",
]
