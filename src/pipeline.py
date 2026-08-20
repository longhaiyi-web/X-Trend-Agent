from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from time import perf_counter

from src.fetchers import SOURCES, SourceDefinition
from src.models import FetchReport, HotspotItem, SourceStatus


def _run_source(source: SourceDefinition, limit: int) -> tuple[list[HotspotItem], SourceStatus]:
    started = perf_counter()
    try:
        items = source.fetcher(limit)
        elapsed_ms = round((perf_counter() - started) * 1000)
        return items, SourceStatus(
            source_id=source.source_id,
            display_name=source.display_name,
            source_type=source.source_type,
            success=True,
            item_count=len(items),
            elapsed_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = round((perf_counter() - started) * 1000)
        message = str(exc).strip() or exc.__class__.__name__
        return [], SourceStatus(
            source_id=source.source_id,
            display_name=source.display_name,
            source_type=source.source_type,
            success=False,
            item_count=0,
            elapsed_ms=elapsed_ms,
            error=message,
        )


def fetch_all_sources(limit_per_source: int = 15) -> FetchReport:
    """Fetch all public sources concurrently while isolating every source failure."""
    items: list[HotspotItem] = []
    statuses_by_id: dict[str, SourceStatus] = {}

    # A small pool is friendlier to public endpoints and avoids local TLS bursts.
    with ThreadPoolExecutor(max_workers=min(2, len(SOURCES))) as executor:
        futures = {
            executor.submit(_run_source, source, limit_per_source): source
            for source in SOURCES
        }
        for future in as_completed(futures):
            source_items, status = future.result()
            items.extend(source_items)
            statuses_by_id[status.source_id] = status

    items.sort(key=lambda item: item.published_at, reverse=True)
    ordered_statuses = tuple(statuses_by_id[source.source_id] for source in SOURCES)
    return FetchReport(
        fetched_at=datetime.now(timezone.utc),
        items=tuple(items),
        sources=ordered_statuses,
    )
