from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class HotspotItem:
    """Normalized record shared by every public source."""

    title: str
    source_name: str
    source_type: str
    published_at: datetime
    url: str
    description: str


@dataclass(frozen=True, slots=True)
class SourceStatus:
    source_id: str
    display_name: str
    source_type: str
    success: bool
    item_count: int
    elapsed_ms: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FetchReport:
    fetched_at: datetime
    items: tuple[HotspotItem, ...]
    sources: tuple[SourceStatus, ...]

