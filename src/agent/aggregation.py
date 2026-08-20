from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.agent.models import EventDraft
from src.models import HotspotItem


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "how", "in", "into", "is", "it", "its", "new", "of", "on", "or", "our",
    "that", "the", "their", "this", "to", "using", "via", "was", "we", "what",
    "when", "where", "why", "with", "you", "your", "api", "app", "tool", "tools",
    "package", "project", "release", "released", "version", "build", "built",
}

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref",
    "source", "fbclid", "gclid",
}

TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI / Agent", (" ai ", "artificial intelligence", "llm", "language model", "agent", "openai", "anthropic", "claude", "gemini", "deepseek", "langchain", "rag", "embedding", "inference")),
    ("SaaS / 产品", ("saas", "startup", "pricing", "subscription", "product launch", "customer", "revenue", "acquisition", "workflow")),
    ("安全 / 风险", ("security", "malware", "vulnerability", "attack", "breach", "privacy", "risk", "exploit", "unlearning")),
    ("开源生态", ("open source", "github", "repository", "repo", "license", "fork", "community")),
    ("开发工具", ("developer", "sdk", "typescript", "javascript", "python", "rust", "golang", "terminal", "cli", "npm", "database", "sqlite", "framework")),
    ("数据 / 基础设施", ("database", "cloud", "infrastructure", "distributed", "pubsub", "data platform", "storage", "runtime")),
    ("互联网平台", ("internet", "platform", "social", "browser", "web", "mastodon", "creator")),
)


def _normalized_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        query = urlencode(
            [(key, value) for key, value in parse_qsl(parts.query) if key.lower() not in TRACKING_PARAMS]
        )
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))
    except ValueError:
        return url.strip()


def _normalize_text(value: str) -> str:
    value = value.lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\u4e00-\u9fff@+.#-]+", " ", value)).strip()


def _tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9+.#-]{1,}|[\u4e00-\u9fff]{2,}", _normalize_text(value))
    return {token for token in tokens if token not in STOPWORDS and len(token) > 1}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _npm_family(item: HotspotItem) -> str | None:
    if not item.source_name.startswith("npm Registry"):
        return None
    title = item.title.strip().lower()
    if title.startswith("@") and "/" in title:
        return title.split("/", 1)[0]
    return None


def _should_merge(left: HotspotItem, right: HotspotItem) -> bool:
    if _normalized_url(left.url) == _normalized_url(right.url):
        return True

    left_family = _npm_family(left)
    right_family = _npm_family(right)
    age_gap_hours = abs((left.published_at - right.published_at).total_seconds()) / 3600
    if left_family and left_family == right_family and age_gap_hours <= 36:
        return True

    left_title = _normalize_text(left.title)
    right_title = _normalize_text(right.title)
    title_tokens_left = _tokens(left.title)
    title_tokens_right = _tokens(right.title)
    all_tokens_left = _tokens(f"{left.title} {left.description[:260]}")
    all_tokens_right = _tokens(f"{right.title} {right.description[:260]}")
    title_overlap = _jaccard(title_tokens_left, title_tokens_right)
    content_overlap = _jaccard(all_tokens_left, all_tokens_right)
    sequence = SequenceMatcher(None, left_title, right_title).ratio()
    shared_specific = {
        token for token in title_tokens_left & title_tokens_right
        if len(token) >= 4 and token not in {"community", "content", "model"}
    }
    similarity = 0.48 * title_overlap + 0.27 * content_overlap + 0.25 * sequence

    if left.source_name != right.source_name:
        return similarity >= 0.50 or (len(shared_specific) >= 2 and similarity >= 0.40)
    return similarity >= 0.66 and len(shared_specific) >= 2


def _topic_labels(items: list[HotspotItem]) -> tuple[str, ...]:
    searchable = f" {_normalize_text(' '.join(f'{item.title} {item.description}' for item in items))} "
    scores: list[tuple[int, str]] = []
    for topic, phrases in TOPIC_RULES:
        matches = sum(1 for phrase in phrases if phrase in searchable)
        if matches:
            scores.append((matches, topic))
    if not scores:
        return ("综合科技",)
    scores.sort(key=lambda pair: (-pair[0], pair[1]))
    return tuple(topic for _, topic in scores[:3])


def _core_description(description: str) -> str:
    first = description.split(" · ", 1)[0].strip()
    if first.lower() in {"comments", "article", "软件包未提供简介", "仓库未提供简介"}:
        return ""
    return first


def _event_title(items: list[HotspotItem]) -> str:
    families = {_npm_family(item) for item in items}
    families.discard(None)
    if len(items) > 1 and len(families) == 1:
        family = next(iter(families))
        return f"{family} 软件包家族集中更新（{len(items)} 个原始条目）"
    return max(items, key=lambda item: (len(_tokens(item.title)), len(item.title))).title


def _event_summary(items: list[HotspotItem], title: str) -> str:
    snippets: list[str] = []
    for item in sorted(items, key=lambda value: value.published_at, reverse=True):
        snippet = _core_description(item.description)
        if snippet and snippet.lower() not in {value.lower() for value in snippets}:
            snippets.append(snippet)
        if len(snippets) == 2:
            break
    body = "；".join(snippets) if snippets else title
    body = body[:420].rstrip(" ,.;:，。；：")
    if len(items) > 1:
        return f"{len(items)} 条公开记录被聚合为同一事件。{body}"
    return body


def _event_type(items: list[HotspotItem], title: str, topics: tuple[str, ...]) -> str:
    """Classify an event for downstream editorial strategy using visible source text."""
    text = _normalize_text(" ".join(f"{item.title} {item.description}" for item in items))
    npm_families = {_npm_family(item) for item in items}
    npm_families.discard(None)

    if len(items) > 1 and (npm_families or len(items) >= 3):
        return "生态集中更新 / 软件包家族更新"
    if any(item.source_name.startswith("GitHub Search") for item in items):
        return "开源项目 / GitHub 工具"
    if re.search(
        r"\b(paper|research|study|benchmark|evaluation|dataset|architecture|training|"
        r"reasoning model|foundation model|new model|inference method)\b",
        text,
    ):
        return "研究 / 新技术进展"
    if re.search(
        r"\b(why|opinion|argument|debate|controversy|critique|trust|limitation|"
        r"should we|is it|the case against|thoughts on|doesn t|does not|what you think)\b",
        text,
    ):
        return "技术观点 / 争议文章"
    if re.search(
        r"\b(i built|we built|my experience|our experience|case study|postmortem|"
        r"lessons learned|how i|how we|what i learned|content journey|dev log|tutorial|guide)\b",
        text,
    ):
        return "开发者经验 / 案例分享"
    if re.search(
        r"\b(acquire|acquisition|funding|raised|company|partnership|layoff|ceo|"
        r"industry|market|policy|announces|announcement)\b",
        text,
    ):
        return "行业新闻 / 公司动态"
    if re.search(
        r"\b(launch|launched|release|released|ships|shipped|introducing|available|"
        r"sdk|api|platform|product|tool|plugin|extension|version|v\d+)\b",
        text,
    ) or "SaaS / 产品" in topics:
        return "产品 / 工具发布"
    if "开源生态" in topics:
        return "开源项目 / GitHub 工具"
    return "行业新闻 / 公司动态"


def aggregate_items(items: tuple[HotspotItem, ...]) -> list[EventDraft]:
    records = list(items)
    if not records:
        return []

    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            if _should_merge(records[left], records[right]):
                union(left, right)

    groups: dict[int, list[HotspotItem]] = defaultdict(list)
    for index, item in enumerate(records):
        groups[find(index)].append(item)

    events: list[EventDraft] = []
    for grouped_items in groups.values():
        grouped_items.sort(key=lambda item: item.published_at, reverse=True)
        title = _event_title(grouped_items)
        identity = "|".join(
            sorted(f"{_normalized_url(item.url)}::{_normalize_text(item.title)}" for item in grouped_items)
        )
        event_id = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
        distinct_sources = len({item.source_name for item in grouped_items})
        if len(grouped_items) == 1:
            merge_explanation = "相似度未达到聚合阈值，保留为独立事件"
        elif distinct_sources > 1:
            merge_explanation = f"通过相同原文或标题/内容相似度合并 {distinct_sources} 个来源"
        else:
            merge_explanation = f"通过相同原文、标题相似度或同一发布家族合并 {len(grouped_items)} 条记录"
        events.append(
            EventDraft(
                event_id=event_id,
                title=title,
                summary=_event_summary(grouped_items, title),
                published_at=grouped_items[0].published_at,
                items=tuple(grouped_items),
                topics=(topics := _topic_labels(grouped_items)),
                event_type=_event_type(grouped_items, title, topics),
                merge_explanation=merge_explanation,
            )
        )

    events.sort(key=lambda event: event.published_at, reverse=True)
    return events
