from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.fetchers.dev_community import fetch_dev_community
from src.fetchers.github import fetch_github
from src.fetchers.lobsters import fetch_lobsters
from src.fetchers.npm_registry import fetch_npm_registry
from src.models import HotspotItem


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_id: str
    display_name: str
    source_type: str
    fetcher: Callable[[int], list[HotspotItem]]


SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition("dev_community", "DEV Community", "开发者社区 API", fetch_dev_community),
    SourceDefinition("github", "GitHub 近期高星仓库", "开源趋势 API", fetch_github),
    SourceDefinition("npm_registry", "npm Registry AI Packages", "软件包生态 API", fetch_npm_registry),
    SourceDefinition("lobsters", "Lobsters", "科技社区 RSS", fetch_lobsters),
)


__all__ = ["SOURCES", "SourceDefinition"]
