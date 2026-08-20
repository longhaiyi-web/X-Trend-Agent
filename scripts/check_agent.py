from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import run_agent  # noqa: E402
from src.pipeline import fetch_all_sources  # noqa: E402
from src.review_store import load_state  # noqa: E402


def factor_score(event, name: str) -> float:
    return next(factor.score for factor in event.factors if factor.name == name)


def main() -> int:
    fetch_report = fetch_all_sources(limit_per_source=15)
    state = load_state()
    agent_report = run_agent(fetch_report, state["history"])
    recommendations = [event for event in agent_report.events if event.follow_up == "建议跟进"]
    grouped = [event for event in agent_report.events if len(event.items) > 1]
    single_github = [
        event
        for event in agent_report.events
        if len(event.items) == 1
        and event.items[0].source_name.startswith("GitHub Search")
        and "AI / Agent" in event.topics
    ]
    successful_sources = [source for source in fetch_report.sources if source.success]

    print(f"Successful real sources: {len(successful_sources)} / {len(fetch_report.sources)}")
    print(f"Raw items: {agent_report.raw_count}")
    print(f"Aggregated events: {agent_report.event_count}")
    print(f"Events with multiple raw records: {len(grouped)}")
    print(f"Dynamic recommended follow-ups: {len(recommendations)}")
    print(f"Pending review items: {len(state['pool'])}")
    print(f"Feedback history: {len(state['history'])}")
    print()

    for event in agent_report.events[:20]:
        print(
            f"#{event.rank:02d} {event.score:>5.1f} {event.follow_up:<7} "
            f"{event.relevance_tier:<4} {len(event.items)} raw "
            f"[{event.event_type}] {event.title}"
        )
        print("     " + " | ".join(f"{factor.name}={factor.score:g}" for factor in event.factors))

    print("\nTrend-signal example:")
    if grouped:
        example = max(grouped, key=lambda event: factor_score(event, "趋势形成信号"))
        print(
            f"  {example.title}: {len(example.items)} raw, "
            f"trend {factor_score(example, '趋势形成信号'):.1f}/20, rank #{example.rank}, {example.follow_up}"
        )
    else:
        print("  none")

    print("Single AI GitHub downgrade example:")
    if single_github:
        example = single_github[0]
        print(
            f"  {example.title}: trend {factor_score(example, '趋势形成信号'):.1f}/20, "
            f"rank #{example.rank}, {example.follow_up} — {example.follow_reason}"
        )
    else:
        print("  none")

    print("\nRecommended event types and differentiated drafts:")
    for event in recommendations[:5]:
        print(f"  [{event.event_type}] {event.content_angle}")
        print(f"    {event.candidate_post}")

    print("\nTOP recommendation reasons:")
    for event in recommendations[:3]:
        print(f"  TOP {event.rank}: {event.recommendation_reason}")

    errors: list[str] = []
    if len(successful_sources) < 3:
        errors.append("fewer than three real public sources succeeded")
    if agent_report.raw_count == 0:
        errors.append("no real raw items were fetched")
    if agent_report.event_count == 0:
        errors.append("no aggregated events were produced")
    if not recommendations:
        errors.append("no event crossed the dynamic recommendation thresholds")
    if any(not event.factors or not event.follow_reason for event in agent_report.events):
        errors.append("an event is missing explainable scoring or a follow-up reason")
    if any(f"总分 {event.score:.1f}" not in event.follow_reason for event in agent_report.events):
        errors.append("an event decision reason does not explicitly explain its total score")
    if any(
        event.follow_up == "观察" and ("但" not in event.follow_reason or "门槛" not in event.follow_reason)
        for event in agent_report.events
    ):
        errors.append("an observation does not name the key failed threshold")
    if any(not event.candidate_post or not event.content_angle for event in recommendations):
        errors.append("a recommended event is missing candidate content")
    if any(len(event.candidate_post or "") > 280 for event in recommendations):
        errors.append("a candidate X post exceeds 280 characters")
    candidate_texts = [event.candidate_post or "" for event in recommendations]
    candidate_texts += [
        record.get("candidate_post", "")
        for record in state["pool"] + state["history"]
    ]
    if any(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", text) for text in candidate_texts):
        errors.append("a current or persisted English X candidate contains Chinese characters")
    if any(not item.url.startswith(("http://", "https://")) for event in agent_report.events for item in event.items):
        errors.append("an event contains a non-public source URL")
    if not grouped:
        errors.append("no multi-record event exists for the trend-signal check")
    if not single_github or all(event.follow_up == "建议跟进" for event in single_github):
        errors.append("no single AI GitHub repository was visibly downgraded")
    if len({event.event_type for event in recommendations}) < 3:
        errors.append("fewer than three event types reached the recommendation set")
    if len({(event.candidate_post or "").split(":", 1)[0] for event in recommendations}) < 3:
        errors.append("fewer than three distinct X hook structures were generated")
    if len({event.recommendation_reason for event in recommendations[:3]}) < min(3, len(recommendations)):
        errors.append("TOP recommendation reasons are still duplicated")
    scoring_source = (PROJECT_ROOT / "src" / "agent" / "scoring.py").read_text(encoding="utf-8")
    if "target_count" in scoring_source or "selected_ids" in scoring_source:
        errors.append("a fixed recommendation quota is still present")
    if load_state() != state:
        errors.append("local review state changed or failed to reload consistently")

    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print("\n[OK] Real sources, event types, dynamic thresholds, differentiated drafts and persistence passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
