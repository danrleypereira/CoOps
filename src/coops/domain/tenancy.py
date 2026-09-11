from __future__ import annotations
from dataclasses import dataclass
from uuid import uuid4

@dataclass(frozen=True, slots=True)
class TenantId:

    org_id:str

    def __post_init__(self) -> None:
        if not self.org_id or not self.org_id.strip():
            raise ValueError("TenantId requires a non-empty org_id")

    def __str__(self) -> str:
        return self.org_id
    
@dataclass(frozen=True, slots=True)
class CorrelationId:

    value:str

    @classmethod
    def new(cls) -> CorrelationId:
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value