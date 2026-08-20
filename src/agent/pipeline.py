from __future__ import annotations

from datetime import datetime, timezone

from src.agent.aggregation import aggregate_items
from src.agent.models import AgentReport
from src.agent.scoring import rank_events
from src.models import FetchReport
from src.review_store import build_preference_profile


def run_agent(fetch_report: FetchReport, history: list[dict]) -> AgentReport:
    preferences = build_preference_profile(history)
    drafts = aggregate_items(fetch_report.items)
    events = rank_events(drafts, preferences, now=fetch_report.fetched_at)
    return AgentReport(
        generated_at=datetime.now(timezone.utc),
        raw_count=len(fetch_report.items),
        event_count=len(events),
        recommended_count=sum(event.follow_up == "建议跟进" for event in events),
        grouped_event_count=sum(len(event.items) > 1 for event in events),
        events=tuple(events),
        preferences=tuple(sorted(preferences.values(), key=lambda item: (-abs(item.adjustment), item.topic))),
    )

