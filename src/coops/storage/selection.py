"""Choosing the dataset adapter from configuration (#42).

:func:`select_storage` is the composition point where ``COOPS_STORAGE``
becomes a :class:`coops.domain.ports.storage_port.StoragePort`: the ETL
layers (#30/#33/#34) will ask for the port here and never see a concrete
adapter — which is the whole point of #26.

Why an unknown value raises instead of defaulting
-------------------------------------------------

This repository has a documented history of silent fallbacks that produce a
plausible wrong answer: the dashboard renders a complete, believable
dashboard of the *wrong* organisation when its org is unset (#129), and
integration tests that turn every exception into a skip are green forever
(#212). A selector that quietly defaults on a typo is the same defect in a
worse place: ``COOPS_STORAGE=mongoo`` would write a whole run to somewhere
nobody intended and report success. So the accepted values are matched
exactly — no trimming, no case folding, no aliases, which only multiply the
typo space — and anything else stops the run naming both the bad value and
the accepted set (the :func:`coops.domain.ports.storage_port.validate_layer`
message shape).

Empty and unset
---------------

``Settings`` owns the documented default: ``env_ignore_empty`` makes an
empty ``COOPS_STORAGE`` count as unset, and unset runs as ``"data"`` — the
filesystem adapter over ``./data``, the corpus the pipeline writes today
(the ETL reads and writes ``./data`` relative to the current directory).
The factory re-decides nothing: a value outside the accepted set reaching
it — including an explicitly empty one, which only a directly-constructed
``Settings`` can carry — raises like any other unknown value. No layer
invents a default twice.
"""

from __future__ import annotations

from coops.domain.ports.storage_port import StoragePort
from coops.infrastructure.config import Settings
from coops.storage.datasets import MongoStorageAdapter
from coops.storage.file import FileStorageAdapter

#: ``COOPS_STORAGE=data`` — the filesystem adapter over ``./data``; the
#: ``Settings`` default, so an unset or empty value runs here.
DATA_BACKEND = "data"

#: ``COOPS_STORAGE=mongo`` — the MongoDB adapter, which also needs
#: ``MONGO_URI`` (see :func:`select_storage`).
MONGO_BACKEND = "mongo"

#: Every accepted ``COOPS_STORAGE`` value — the set the error message names.
STORAGE_BACKENDS: frozenset[str] = frozenset({DATA_BACKEND, MONGO_BACKEND})


def select_storage(settings: Settings) -> StoragePort:
    """Return the ``StoragePort`` the configuration asks for — or raise.

    The return type is the port, never a concrete adapter: callers depend
    on the contract and stay interchangeable behind it (#26).

    Raises ``ValueError`` — never a fallback — when ``coops_storage`` is not
    one of :data:`STORAGE_BACKENDS`, naming the value and the accepted set,
    and when ``mongo`` is selected without a ``mongo_uri`` (the run cannot
    reach the adapter it was configured for, and the message says which
    setting to check).
    """
    backend = settings.coops_storage
    if backend == DATA_BACKEND:
        return FileStorageAdapter("data")
    if backend == MONGO_BACKEND:
        if not settings.mongo_uri:
            raise ValueError(f"COOPS_STORAGE={MONGO_BACKEND!r} requires MONGO_URI to be set")
        return MongoStorageAdapter(settings.mongo_uri)
    raise ValueError(
        f"unknown COOPS_STORAGE {backend!r}: expected one of {sorted(STORAGE_BACKENDS)}"
    )
