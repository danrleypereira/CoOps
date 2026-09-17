from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class TenantId:
    """Identifies a tenant by its organization.

    Organization names are case-insensitive on GitHub, so the id is trimmed
    and lower-cased: `TenantId("UNB-MDS ") == TenantId("unb-mds")`.
    """

    org_id: str

    def __post_init__(self) -> None:
        normalized = (self.org_id or "").strip().lower()
        if not normalized:
            raise ValueError("TenantId requires a non-empty org_id")
        object.__setattr__(self, "org_id", normalized)

    def __str__(self) -> str:
        return self.org_id


@dataclass(frozen=True, slots=True)
class CorrelationId:
    """Ties together the logs and records produced by one pipeline run."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("CorrelationId requires a non-empty value")

    @classmethod
    def new(cls) -> CorrelationId:
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value
