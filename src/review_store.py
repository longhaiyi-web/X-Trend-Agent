from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.models import HotspotEvent, TopicPreference


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = PROJECT_ROOT / "data" / "review_state.json"
_STATE_LOCK = threading.Lock()
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "pool": [], "history": []}


def _normalize_legacy_candidate(record: Any) -> Any:
    """Keep old review decisions intact while fixing legacy mixed-language X drafts."""
    if not isinstance(record, dict):
        return record
    candidate = record.get("candidate_post", "")
    if not isinstance(candidate, str) or not _CJK_PATTERN.search(candidate):
        return record

    normalized = dict(record)
    sources = normalized.get("sources", [])
    if normalized.get("event_type") == "生态集中更新 / 软件包家族更新" and sources:
        source_title = str(sources[0].get("title", ""))
        family = source_title.split("/", 1)[0] if source_title.startswith("@") else "AI ecosystem"
        count = len(sources)
        link = str(sources[0].get("url", ""))
        normalized["candidate_post"] = (
            f"One signal worth paying attention to: A coordinated {family} update across {count} related packages. "
            f"{count} related updates moved together—a stronger ecosystem signal than an isolated patch. {link}"
        )
    else:
        cleaned = _CJK_PATTERN.sub(" ", candidate)
        normalized["candidate_post"] = re.sub(r"\s+", " ", cleaned).strip()
    return normalized


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    if not isinstance(payload, dict):
        return _empty_state()
    pool = payload.get("pool", []) if isinstance(payload.get("pool", []), list) else []
    history = payload.get("history", []) if isinstance(payload.get("history", []), list) else []
    return {
        "version": 1,
        "pool": [_normalize_legacy_candidate(record) for record in pool],
        "history": [_normalize_legacy_candidate(record) for record in history],
    }


def load_state(path: Path | None = None) -> dict[str, Any]:
    return _read_state(path or DEFAULT_STATE_PATH)


def _write_state(state: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _event_record(event: HotspotEvent) -> dict[str, Any]:
    return {
        "id": event.event_id,
        "title": event.title,
        "event_summary": event.summary,
        "topics": list(event.topics),
        "event_type": event.event_type,
        "score": event.score,
        "content_angle": event.content_angle,
        "candidate_post": event.candidate_post,
        "recommendation_reason": event.recommendation_reason,
        "sources": [
            {"title": item.title, "source_name": item.source_name, "url": item.url}
            for item in event.items
        ],
    }


def add_to_pool(event: HotspotEvent, path: Path | None = None) -> tuple[bool, str]:
    target = path or DEFAULT_STATE_PATH
    with _STATE_LOCK:
        state = _read_state(target)
        if any(record.get("id") == event.event_id for record in state["pool"]):
            return False, "该候选已在待审核内容池中"
        if any(record.get("id") == event.event_id for record in state["history"]):
            return False, "该事件已经完成过采用/驳回审核"
        record = _event_record(event)
        record["added_at"] = datetime.now(timezone.utc).isoformat()
        state["pool"].append(record)
        _write_state(state, target)
    return True, "已加入待审核内容池"


def decide_candidate(candidate_id: str, action: str, path: Path | None = None) -> tuple[bool, str]:
    if action not in {"采用", "驳回"}:
        raise ValueError("action must be 采用 or 驳回")
    target = path or DEFAULT_STATE_PATH
    with _STATE_LOCK:
        state = _read_state(target)
        candidate = next((record for record in state["pool"] if record.get("id") == candidate_id), None)
        if candidate is None:
            return False, "候选内容不存在或已处理"
        state["pool"] = [record for record in state["pool"] if record.get("id") != candidate_id]
        history_record = dict(candidate)
        history_record["action"] = action
        history_record["decided_at"] = datetime.now(timezone.utc).isoformat()
        state["history"].append(history_record)
        _write_state(state, target)
    return True, f"已{action}该候选内容"


def build_preference_profile(history: list[dict]) -> dict[str, TopicPreference]:
    topics = sorted({topic for record in history for topic in record.get("topics", []) if isinstance(topic, str)})
    profile: dict[str, TopicPreference] = {}
    for topic in topics:
        relevant = [record for record in history if topic in record.get("topics", [])]
        adopted = sum(record.get("action") == "采用" for record in relevant)
        rejected = sum(record.get("action") == "驳回" for record in relevant)
        streak_action: str | None = None
        streak_count = 0
        for record in reversed(relevant):
            action = record.get("action")
            if action not in {"采用", "驳回"}:
                continue
            if streak_action is None:
                streak_action = action
            if action != streak_action:
                break
            streak_count += 1
        base = (adopted - rejected) * 1.5
        streak_bonus = 0.0
        if streak_count >= 2:
            streak_bonus = min(4.0, (streak_count - 1) * 2.0)
            if streak_action == "驳回":
                streak_bonus *= -1
        adjustment = round(max(-8.0, min(8.0, base + streak_bonus)), 1)
        evidence_titles = tuple(record.get("title", "未命名事件") for record in relevant[-3:])
        profile[topic] = TopicPreference(
            topic=topic,
            adopted=adopted,
            rejected=rejected,
            streak_action=streak_action,
            streak_count=streak_count,
            adjustment=adjustment,
            evidence_titles=evidence_titles,
        )
    return profile
