from __future__ import annotations

import calendar
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup


UTC = timezone.utc
USER_AGENT = "X-Trend-Agent-Demo/0.1 (local Streamlit demo; public-source reader)"
DEFAULT_TIMEOUT = (15, 45)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/atom+xml, application/rss+xml, text/xml;q=0.9, */*;q=0.8",
        }
    )
    return session


def _request(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    """Retry only short-lived TLS/connection failures; timeouts fail fast per source."""
    for attempt in range(3):
        try:
            with build_session() as session:
                response = session.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
                if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
                    raise RuntimeError("公开接口的匿名访问额度暂时已用完，请稍后重试")
                response.raise_for_status()
                return response
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
            if attempt == 2:
                raise
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError("公开来源请求失败")


def fetch_bytes(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    return _request(url, params=params, headers=headers).content


def fetch_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    return _request(url, params=params, headers=headers).json()


def clean_text(raw: str | None, *, limit: int = 360) -> str:
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    shortened = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:，。；：")
    return f"{shortened}…"


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_feed_time(entry: Any) -> datetime:
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(field)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
    raise ValueError("来源条目缺少可解析的发布时间")
