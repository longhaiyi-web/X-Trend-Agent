from __future__ import annotations

from src.fetchers.common import clean_text, fetch_json, parse_iso_datetime
from src.models import HotspotItem


DEV_ARTICLES_API = "https://dev.to/api/articles"


def fetch_dev_community(limit: int = 15) -> list[HotspotItem]:
    articles = fetch_json(
        DEV_ARTICLES_API,
        params={
            "tag": "ai",
            "top": 7,
            "per_page": max(1, min(limit, 30)),
        },
    )
    if not isinstance(articles, list) or not articles:
        raise RuntimeError("DEV Community API 未返回 AI 热门文章")

    items: list[HotspotItem] = []
    for article in articles:
        title = article.get("title")
        url = article.get("url")
        published_at = article.get("published_timestamp") or article.get("published_at")
        if not title or not url or not published_at:
            continue
        author = (article.get("user") or {}).get("name") or "DEV author"
        summary = clean_text(article.get("description"), limit=280) or "文章未提供简介"
        description = (
            f"{summary} · 作者 {author} · "
            f"{article.get('public_reactions_count', 0)} reactions · "
            f"{article.get('comments_count', 0)} comments"
        )
        items.append(
            HotspotItem(
                title=clean_text(title, limit=200),
                source_name="DEV Community",
                source_type="开发者社区 API",
                published_at=parse_iso_datetime(published_at),
                url=url,
                description=description,
            )
        )

    if not items:
        raise RuntimeError("DEV Community 条目缺少必要字段")
    return items[:limit]

