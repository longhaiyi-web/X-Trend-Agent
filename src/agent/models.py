from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.models import HotspotItem


@dataclass(frozen=True, slots=True)
class EventDraft:
    event_id: str
    title: str
    summary: str
    published_at: datetime
    items: tuple[HotspotItem, ...]
    topics: tuple[str, ...]
    event_type: str
    merge_explanation: str


@dataclass(frozen=True, slots=True)
class ScoreFactor:
    name: str
    score: float
    max_score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class TopicPreference:
    topic: str
    adopted: int
    rejected: int
    streak_action: str | None
    streak_count: int
    adjustment: float
    evidence_titles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HotspotEvent:
    event_id: str
    rank: int
    title: str
    summary: str
    published_at: datetime
    items: tuple[HotspotItem, ...]
    topics: tuple[str, ...]
    event_type: str
    relevance_tier: str
    merge_explanation: str
    score: float
    base_score: float
    feedback_adjustment: float
    factors: tuple[ScoreFactor, ...]
    follow_up: str
    follow_reason: str
    content_angle: str | None
    candidate_post: str | None
    recommendation_reason: str | None


@dataclass(frozen=True, slots=True)
class AgentReport:
    generated_at: datetime
    raw_count: int
    event_count: int
    recommended_count: int
    grouped_event_count: int
    events: tuple[HotspotEvent, ...]
    preferences: tuple[TopicPreference, ...]
