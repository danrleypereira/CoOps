"""A source repository, provider-neutral.

Fields mirror what the pipeline already derives from a repository payload
(the ``repository_metadata`` block of ``data/bronze/structure_*.json`` and
the repository selectors), minus everything provider-shaped that no consumer
reads. ``is_fork``/``is_archived``/``is_private`` are the classification the
Bronze filter needs; ``pushed_at`` is the activity signal; the counts are the
repository metrics Silver publishes.
"""

from __future__ import annotations

from dataclasses import dataclass

from coops.domain.tenancy import TenantId


@dataclass(frozen=True, slots=True)
class Repository:
    """One repository owned by the tenant's organization."""

    tenant: TenantId
    repo_id: int
    name: str
    full_name: str
    is_private: bool = False
    is_fork: bool = False
    is_archived: bool = False
    description: str | None = None
    default_branch: str | None = None
    language: str | None = None
    html_url: str | None = None
    size_kb: int | None = None
    stargazers_count: int | None = None
    forks_count: int | None = None
    open_issues_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    pushed_at: str | None = None

    def __post_init__(self) -> None:
        if self.repo_id < 1:
            raise ValueError(f"Repository.repo_id must be >= 1, got {self.repo_id}")
        if not (self.name or "").strip():
            raise ValueError("Repository requires a non-empty name")
        if not (self.full_name or "").strip():
            raise ValueError("Repository requires a non-empty full_name")
