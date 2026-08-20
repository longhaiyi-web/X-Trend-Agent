from __future__ import annotations

from src.fetchers.common import clean_text, fetch_json, parse_iso_datetime
from src.models import HotspotItem


NPM_SEARCH_API = "https://registry.npmjs.org/-/v1/search"


def fetch_npm_registry(limit: int = 15) -> list[HotspotItem]:
    payload = fetch_json(
        NPM_SEARCH_API,
        params={
            "text": "keywords:ai",
            "size": max(1, min(limit, 30)),
            "from": 0,
        },
    )
    records = payload.get("objects", []) if isinstance(payload, dict) else []
    if not records:
        raise RuntimeError("npm Registry Search 未返回 AI 相关软件包")

    items: list[HotspotItem] = []
    for record in records:
        package = record.get("package") or {}
        name = package.get("name")
        published_at = package.get("date")
        url = (package.get("links") or {}).get("npm")
        if not name or not published_at or not url:
            continue
        summary = clean_text(package.get("description"), limit=280) or "软件包未提供简介"
        publisher = (package.get("publisher") or {}).get("username") or "unknown"
        score = float((record.get("score") or {}).get("final") or 0)
        description = (
            f"{summary} · v{package.get('version', '?')} · publisher: {publisher} · "
            f"search score: {score:.3f}"
        )
        items.append(
            HotspotItem(
                title=name,
                source_name="npm Registry（AI packages）",
                source_type="软件包生态 API",
                published_at=parse_iso_datetime(published_at),
                url=url,
                description=description,
            )
        )

    if not items:
        raise RuntimeError("npm Registry 条目缺少必要字段")
    return items[:limit]

