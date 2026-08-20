from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.fetchers.common import clean_text, fetch_json, parse_iso_datetime
from src.models import HotspotItem


GITHUB_SEARCH_API = "https://api.github.com/search/repositories"


def fetch_github(limit: int = 15) -> list[HotspotItem]:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    payload = fetch_json(
        GITHUB_SEARCH_API,
        params={
            "q": f"created:>={since}",
            "sort": "stars",
            "order": "desc",
            "per_page": max(1, min(limit, 30)),
        },
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    repositories = payload.get("items", []) if isinstance(payload, dict) else []
    if not repositories:
        raise RuntimeError("GitHub Search 未返回近期仓库")

    items: list[HotspotItem] = []
    for repository in repositories:
        title = repository.get("full_name")
        url = repository.get("html_url")
        created_at = repository.get("created_at")
        if not title or not url or not created_at:
            continue
        summary = clean_text(repository.get("description"), limit=270) or "仓库未提供简介"
        language = repository.get("language") or "语言未标注"
        description = (
            f"{summary} · ★ {repository.get('stargazers_count', 0):,} · "
            f"{language} · 最近 7 天新建仓库"
        )
        items.append(
            HotspotItem(
                title=title,
                source_name="GitHub Search（近期高星仓库）",
                source_type="开源趋势 API",
                published_at=parse_iso_datetime(created_at),
                url=url,
                description=description,
            )
        )

    if not items:
        raise RuntimeError("GitHub 仓库条目缺少必要字段")
    return items[:limit]

