from __future__ import annotations

import feedparser

from src.fetchers.common import clean_text, fetch_bytes, parse_feed_time
from src.models import HotspotItem


LOBSTERS_FEED = "https://lobste.rs/rss"


def fetch_lobsters(limit: int = 15) -> list[HotspotItem]:
    payload = fetch_bytes(LOBSTERS_FEED)
    feed = feedparser.parse(payload)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Lobsters RSS 解析失败：{feed.bozo_exception}")

    items: list[HotspotItem] = []
    for entry in feed.entries[:limit]:
        title = clean_text(entry.get("title"), limit=200)
        url = entry.get("link")
        if not title or not url:
            continue
        author = entry.get("author") or "Lobsters community"
        summary = clean_text(entry.get("summary") or entry.get("description"), limit=330)
        description = f"{summary} · submitted by {author}" if summary else f"submitted by {author}"
        items.append(
            HotspotItem(
                title=title,
                source_name="Lobsters",
                source_type="科技社区 RSS",
                published_at=parse_feed_time(entry),
                url=url,
                description=description,
            )
        )

    if not items:
        raise RuntimeError("Lobsters RSS 未返回可用文章")
    return items

