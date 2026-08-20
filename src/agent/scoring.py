from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from src.agent.content import candidate_post, content_angle
from src.agent.models import EventDraft, HotspotEvent, ScoreFactor, TopicPreference


HIGH_RELEVANCE_SIGNALS: tuple[tuple[str, str], ...] = (
    (r"\b(ai agent|ai agents|agentic|multi-agent)\b", "AI Agent"),
    (r"\b(ai assistant|ai copilot|copilot)\b", "AI 应用 / 助手"),
    (r"\b(llm|large language model|foundation model)\b", "LLM / 基础模型"),
    (r"\b(openai|anthropic|claude|gemini|deepseek|langchain)\b", "主流 AI 模型或生态"),
    (r"\b(rag|retrieval augmented|embedding|vector search|inference)\b", "AI 应用基础设施"),
    (r"\b(model capability|reasoning model|multimodal|fine-tun|machine learning)\b", "模型能力 / 训练"),
    (r"\b(model context protocol|mcp server|mcp client|ai sdk|agent sdk)\b", "AI 开发者工具"),
)

MEDIUM_RELEVANCE_SIGNALS: tuple[tuple[str, str], ...] = (
    (r"\b(developer|sdk|api|cli|framework|software engineering|devtool)\b", "开发工具 / 软件工程"),
    (r"\b(saas|startup|subscription|workflow|product)\b", "SaaS / 产品"),
    (r"\b(open source|github|repository|package|npm)\b", "开源生态"),
    (r"\b(cloud|database|data platform|infrastructure|runtime|storage)\b", "云 / 数据基础设施"),
)

PACKAGE_SOURCE_TYPES = {"软件包生态 API", "开源趋势 API"}
COMMUNITY_SOURCE_TYPES = {"开发者社区 API", "科技社区 RSS"}


def _event_text(event: EventDraft) -> str:
    return " ".join(
        [event.title, event.summary]
        + [f"{item.title} {item.description}" for item in event.items]
    ).lower()


def _is_package_or_repo_event(event: EventDraft) -> bool:
    return bool(event.items) and all(item.source_type in PACKAGE_SOURCE_TYPES for item in event.items)


def _is_clear_ecosystem_trend(event: EventDraft) -> bool:
    """Registry/repository updates need breadth or independent corroboration to count as a trend."""
    if len(event.items) < 2 or not _is_package_or_repo_event(event):
        return False
    source_count = len({item.source_name for item in event.items})
    type_count = len({item.source_type for item in event.items})
    return type_count >= 2 or source_count >= 2 or len(event.items) >= 5


def _has_community_source(event: EventDraft) -> bool:
    return any(item.source_type in COMMUNITY_SOURCE_TYPES for item in event.items)


def _recency(event: EventDraft, now: datetime) -> tuple[float, str]:
    age_hours = max(0.0, (now - event.published_at).total_seconds() / 3600)
    if age_hours <= 6:
        score = 25
    elif age_hours <= 24:
        score = 22
    elif age_hours <= 72:
        score = 18
    elif age_hours <= 168:
        score = 13
    elif age_hours <= 720:
        score = 6
    else:
        score = 2
    detail = f"约 {age_hours:.1f} 小时前发布" if age_hours < 24 else f"约 {age_hours / 24:.1f} 天前发布"
    return float(score), detail


def _trend_signal(event: EventDraft) -> tuple[float, str]:
    raw_count = len(event.items)
    source_count = len({item.source_name for item in event.items})
    type_count = len({item.source_type for item in event.items})

    weak_registry_cluster = (
        raw_count > 1
        and _is_package_or_repo_event(event)
        and not _is_clear_ecosystem_trend(event)
    )

    if weak_registry_cluster:
        score = 2.0 if raw_count == 2 else 4.0
    elif type_count >= 3:
        score = 20.0
    elif type_count == 2:
        score = min(20.0, 17.0 + min(3, raw_count - 2))
    elif source_count >= 2:
        score = min(17.0, 14.0 + min(3, raw_count - 2))
    elif raw_count >= 8:
        score = 16.0
    elif raw_count >= 5:
        score = 14.0
    elif raw_count >= 3:
        score = 12.0
    elif raw_count == 2:
        score = 9.0
    else:
        score = 1.0 if _is_package_or_repo_event(event) else 3.0

    if weak_registry_cluster:
        detail = (
            f"同一 npm/GitHub 来源只有 {raw_count} 条相关更新，缺少跨来源印证且规模不足；"
            "不按明显生态趋势计分"
        )
    elif type_count > 1:
        detail = f"{raw_count} 条原始记录覆盖 {source_count} 个来源、{type_count} 种来源类型，形成跨类型趋势信号"
    elif source_count > 1:
        detail = f"{raw_count} 条原始记录来自 {source_count} 个独立来源，已有交叉印证"
    elif raw_count > 1:
        detail = f"同一公开来源的 {raw_count} 条相关记录集中出现，形成发布簇；尚缺跨来源印证"
    else:
        detail = "仅 1 条原始记录，尚未形成多条目或多来源趋势信号"
    return score, detail


def _relevance(event: EventDraft) -> tuple[float, str, str]:
    text = _event_text(event)
    high_matches = [label for pattern, label in HIGH_RELEVANCE_SIGNALS if re.search(pattern, text)]
    medium_matches = [label for pattern, label in MEDIUM_RELEVANCE_SIGNALS if re.search(pattern, text)]
    lone_ai = bool(re.search(r"\bai\b", text))
    ai_builder_context = bool(
        re.search(r"\b(developer|sdk|api|agent|model|inference|workflow|platform|infrastructure)\b", text)
    )

    if len(high_matches) >= 3:
        tier, score = "高相关", 25.0
    elif len(high_matches) == 2:
        tier, score = "高相关", 23.0
    elif len(high_matches) == 1 and (ai_builder_context or len(event.items) > 1):
        tier, score = "高相关", 21.0
    elif len(high_matches) == 1:
        tier, score = "中相关", 18.0
    elif lone_ai and ai_builder_context and medium_matches:
        tier, score = "中相关", 17.0
    elif lone_ai:
        tier, score = "中相关", 14.0
    elif len(medium_matches) >= 2:
        tier, score = "中相关", 16.0
    elif len(medium_matches) == 1:
        tier, score = "中相关", 13.0
    elif any(topic in event.topics for topic in ("互联网平台", "安全 / 风险", "综合科技")):
        tier, score = "低相关", 8.0
    else:
        tier, score = "无关", 3.0

    if event.event_type == "生态集中更新 / 软件包家族更新" and high_matches:
        score = min(25.0, score + 2.0)
        tier = "高相关"

    signals = high_matches[:3] or medium_matches[:3]
    if signals:
        evidence = "、".join(signals)
    elif lone_ai:
        evidence = "仅出现单一 AI 词，缺少更具体的模型、Agent 或基础设施语义"
    else:
        evidence = "未识别到与 AI/Agent 账号直接相关的具体语义"
    detail = f"{tier}：结合标题、描述和主题标签识别到 {evidence}；不是按单个 AI 关键词直接给满分"
    return score, detail, tier


def _engagement_numbers(text: str) -> tuple[int, int, int]:
    reactions = sum(int(value.replace(",", "")) for value in re.findall(r"([\d,]+)\s+reactions?", text, re.I))
    comments = sum(int(value.replace(",", "")) for value in re.findall(r"([\d,]+)\s+comments?", text, re.I))
    stars = sum(int(value.replace(",", "")) for value in re.findall(r"★\s*([\d,]+)", text))
    return reactions, comments, stars


def _discussion(event: EventDraft) -> tuple[float, str]:
    text = _event_text(event)
    reactions, comments, stars = _engagement_numbers(text)
    community_signal = min(8.0, math.log10(1 + reactions + comments * 2) * 2.6)
    star_signal = min(3.0, math.log10(1 + stars) * 0.9)
    debate_terms = (
        "why", "how", " vs ", "risk", "security", "benchmark", "pricing",
        "future", "limitation", "trust", "tradeoff", "controversy", "lessons",
    )
    matched = [term.strip() for term in debate_terms if term in text]
    registry_only = _is_package_or_repo_event(event)
    clear_ecosystem_trend = _is_clear_ecosystem_trend(event)
    type_bonus = {
        "技术观点 / 争议文章": 4.0,
        "开发者经验 / 案例分享": 2.5,
        "研究 / 新技术进展": 2.5,
        "生态集中更新 / 软件包家族更新": 2.0 if clear_ecosystem_trend else 0.0,
        "行业新闻 / 公司动态": 3.5 if not registry_only else 1.0,
        "产品 / 工具发布": 3.5 if not registry_only else 0.0,
        "开源项目 / GitHub 工具": 0.5,
    }[event.event_type]
    score = min(20.0, 4.0 + community_signal + star_signal + type_bonus + min(5.0, len(matched) * 1.25))

    signals: list[str] = [f"{event.event_type}提供 {type_bonus:g} 分讨论基础"]
    if reactions or comments:
        signals.append(f"公开互动 {reactions} reactions / {comments} comments，作为社区讨论优先信号")
    if stars:
        signals.append(f"GitHub stars 仅折算 {star_signal:.1f} 分，不单独决定推荐")
    if matched:
        signals.append(f"可展开议题：{', '.join(matched[:4])}")
    return round(score, 1), "；".join(signals)


def _content_value(event: EventDraft, discussion_score: float) -> tuple[float, str]:
    score = 2.0
    reasons: list[str] = []
    registry_only = _is_package_or_repo_event(event)
    clear_ecosystem_trend = _is_clear_ecosystem_trend(event)
    if len(event.summary) >= 80:
        score += 1.5
        reasons.append("原始描述提供足够上下文")
    if len(event.items) > 1 and (not registry_only or clear_ecosystem_trend):
        score += 1.5
        reasons.append("有多条可追溯记录可形成判断")
    if len({item.source_type for item in event.items}) > 1:
        score += 1.0
        reasons.append("跨来源类型便于交叉验证")
    type_value = {
        "产品 / 工具发布": 3.5 if not registry_only else 0.5,
        "开源项目 / GitHub 工具": 1.0,
        "生态集中更新 / 软件包家族更新": 2.5 if clear_ecosystem_trend else 0.0,
        "行业新闻 / 公司动态": 3.0 if not registry_only else 1.0,
        "技术观点 / 争议文章": 2.5,
        "开发者经验 / 案例分享": 2.5,
        "研究 / 新技术进展": 2.0,
    }[event.event_type]
    score += type_value
    reasons.append(f"{event.event_type}可形成专属内容结构")
    if _has_community_source(event) and discussion_score >= 10:
        score += 1.5
        reasons.append("公开互动达到社区高讨论优先级")
    if re.search(r"\b(why|how|launch|release|benchmark|risk|lessons|case study)\b", _event_text(event)):
        score += 1.0
        reasons.append("存在明确叙事或判断抓手")
    return round(min(10.0, score), 1), "；".join(reasons)


def _feedback(event: EventDraft, preferences: dict[str, TopicPreference]) -> tuple[float, str]:
    matched = [preferences[topic] for topic in event.topics if topic in preferences]
    if not matched:
        return 0.0, "没有同主题历史采用/驳回记录，本次不调整"
    matched.sort(key=lambda item: abs(item.adjustment), reverse=True)
    selected = matched[:2]
    adjustment = max(-10.0, min(10.0, sum(item.adjustment for item in selected) / len(selected)))
    details = [
        f"{item.topic} {item.adjustment:+.1f}（采用 {item.adopted} / 驳回 {item.rejected}）"
        for item in selected
    ]
    return round(adjustment, 1), "；".join(details)


def _is_single_github(event: EventDraft) -> bool:
    return len(event.items) == 1 and event.items[0].source_name.startswith("GitHub Search")


def _failed_thresholds(row: dict, thresholds: tuple[tuple[str, bool], ...]) -> str:
    failed = [label for label, passed in thresholds if not passed]
    return "、".join(failed) if failed else "对应事件类型的综合条件"


def _recommendation_decision(row: dict) -> tuple[str, str]:
    event: EventDraft = row["draft"]
    single_github = _is_single_github(event)
    registry_cluster = len(event.items) > 1 and _is_package_or_repo_event(event)
    clear_ecosystem_trend = _is_clear_ecosystem_trend(event)
    grouped_trend = len(event.items) > 1 and row["trend"] >= 9 and (
        not registry_cluster or clear_ecosystem_trend
    )

    if single_github:
        thresholds = (
            (f"总分 {row['score']:.1f} 未达到 75", row["score"] >= 75),
            (f"行业相关度 {row['relevance']:.0f}/25 不是高相关", row["tier"] == "高相关"),
            (f"时效性 {row['recency']:.0f}/25 未达到 22", row["recency"] >= 22),
            (f"可讨论性 {row['discussion']:.1f}/20 未达到 13", row["discussion"] >= 13),
            (f"内容价值 {row['content']:.1f}/10 未达到 6.5", row["content"] >= 6.5),
        )
        recommend = all(passed for _, passed in thresholds)
        if recommend:
            return (
                "建议跟进",
                f"总分 {row['score']:.1f}，且行业、时效、讨论性和内容价值全部越过单一 GitHub 仓库的严格门槛。",
            )
        failed = _failed_thresholds(row, thresholds)
        return (
            "观察",
            f"总分 {row['score']:.1f}，但该事件是单一 GitHub 仓库，{failed}；因此未通过单一仓库严格推荐门槛，"
            "stars 与 AI 关键词不能单独触发推荐。",
        )

    if registry_cluster and not clear_ecosystem_trend:
        return (
            "观察",
            f"总分 {row['score']:.1f}，但同一 npm/GitHub 来源只有 {len(event.items)} 条相关更新，"
            "既无跨来源/跨类型印证，也未达到 5 条的集中规模；因此未达到明显生态趋势门槛，保留观察。",
        )

    if grouped_trend:
        thresholds = (
            (f"总分 {row['score']:.1f} 未达到 62", row["score"] >= 62),
            (f"行业相关度 {row['relevance']:.0f}/25 不是高相关", row["tier"] == "高相关"),
            (f"内容价值 {row['content']:.1f}/10 未达到 6", row["content"] >= 6),
            (
                f"可讨论性 {row['discussion']:.1f}/20 且趋势信号 {row['trend']:.0f}/20 均未达聚合门槛",
                row["discussion"] >= 6 or row["trend"] >= 12,
            ),
        )
        recommend = all(passed for _, passed in thresholds)
    else:
        priority_editorial_event = (
            event.event_type in {"产品 / 工具发布", "行业新闻 / 公司动态"}
            and not _is_package_or_repo_event(event)
        )
        minimum_discussion = 7 if priority_editorial_event else 8
        thresholds = (
            (f"总分 {row['score']:.1f} 未达到 50", row["score"] >= 50),
            (f"行业相关度 {row['relevance']:.0f}/25 不是高相关", row["tier"] == "高相关"),
            (f"内容价值 {row['content']:.1f}/10 未达到 6", row["content"] >= 6),
            (
                f"可讨论性 {row['discussion']:.1f}/20 未达到 {minimum_discussion}",
                row["discussion"] >= minimum_discussion,
            ),
        )
        recommend = all(passed for _, passed in thresholds)
    if recommend:
        if grouped_trend:
            return (
                "建议跟进",
                f"总分 {row['score']:.1f}，行业相关度 {row['relevance']:.0f}/25、内容价值 "
                f"{row['content']:.1f}/10，且 {len(event.items)} 条记录形成趋势信号，满足聚合事件门槛。",
            )
        return (
            "建议跟进",
            f"总分 {row['score']:.1f}；虽然不一定高于所有观察事件，但行业相关度 {row['relevance']:.0f}/25、"
            f"内容价值 {row['content']:.1f}/10、可讨论性 {row['discussion']:.1f}/20 同时满足"
            f"{event.event_type}门槛。",
        )

    if row["score"] >= 44 and row["relevance"] >= 11:
        failed = _failed_thresholds(row, thresholds)
        return "观察", f"总分 {row['score']:.1f}，但{failed}，因此未通过{event.event_type}推荐门槛，保留观察。"
    failed = _failed_thresholds(row, thresholds)
    return (
        "不建议跟进",
        f"总分 {row['score']:.1f}，且{failed}；当前不足以占用科技/AI 账号的发布位。",
    )


def _package_family(event: EventDraft) -> str:
    for item in event.items:
        if item.title.startswith("@") and "/" in item.title:
            return item.title.split("/", 1)[0]
    return event.title.split(" ", 1)[0]


def _specific_recommendation_reason(row: dict) -> str:
    event: EventDraft = row["draft"]
    if event.event_type == "生态集中更新 / 软件包家族更新":
        family = _package_family(event)
        if len(event.items) >= 5:
            return (
                f"{len(event.items)} 个 {family} 相关组件集中更新，形成明显的生态级更新信号"
                f"（趋势 {row['trend']:.0f}/20、行业 {row['relevance']:.0f}/25）。"
            )
        return (
            f"{family} 的 {len(event.items)} 个相关组件同期更新，出现生态协同变化信号"
            f"（趋势 {row['trend']:.0f}/20、行业 {row['relevance']:.0f}/25）。"
        )
    if event.event_type == "技术观点 / 争议文章":
        return (
            f"虽然只有单一来源，但议题与 AI 开发实践高度相关（{row['relevance']:.0f}/25），"
            f"并具备明显讨论空间（{row['discussion']:.1f}/20）。"
        )
    if event.event_type == "开发者经验 / 案例分享":
        return (
            f"单一来源趋势信号较弱，但案例包含可复用的开发流程，内容价值 {row['content']:.1f}/10，"
            f"因此越过开发者案例类推荐门槛。"
        )
    if event.event_type == "产品 / 工具发布":
        return (
            f"该发布与 AI 开发工作流高度相关（{row['relevance']:.0f}/25），且具备明确测试对象和"
            f"方案对比价值（内容 {row['content']:.1f}/10）。"
        )
    if event.event_type == "开源项目 / GitHub 工具":
        return (
            f"该开源工具同时具备高行业相关度、强时效与足够讨论价值，已通过单一仓库的严格门槛"
            f"（总分 {row['score']:.1f}）。"
        )
    if event.event_type == "研究 / 新技术进展":
        return (
            f"研究结果与 AI 能力演进直接相关，并提供了可讨论的证据与落地距离判断"
            f"（行业 {row['relevance']:.0f}/25、讨论 {row['discussion']:.1f}/20）。"
        )
    return (
        f"该行业动作与 AI/科技账号定位高度相关，且时效、讨论与内容价值同时通过门槛"
        f"（总分 {row['score']:.1f}）。"
    )


def rank_events(
    drafts: list[EventDraft],
    preferences: dict[str, TopicPreference],
    now: datetime | None = None,
) -> list[HotspotEvent]:
    now = now or datetime.now(timezone.utc)
    preliminary: list[dict] = []
    for draft in drafts:
        recency_score, recency_detail = _recency(draft, now)
        trend_score, trend_detail = _trend_signal(draft)
        relevance_score, relevance_detail, relevance_tier = _relevance(draft)
        discussion_score, discussion_detail = _discussion(draft)
        content_score, content_detail = _content_value(draft, discussion_score)
        feedback_score, feedback_detail = _feedback(draft, preferences)
        base_score = recency_score + trend_score + relevance_score + discussion_score + content_score
        total = round(max(0.0, min(100.0, base_score + feedback_score)), 1)
        factors = (
            ScoreFactor("时效性", recency_score, 25, recency_detail),
            ScoreFactor("趋势形成信号", trend_score, 20, trend_detail),
            ScoreFactor("行业相关度", relevance_score, 25, relevance_detail),
            ScoreFactor("可讨论性", discussion_score, 20, discussion_detail),
            ScoreFactor("内容价值", content_score, 10, content_detail),
            ScoreFactor("历史偏好调整", feedback_score, 10, feedback_detail),
        )
        preliminary.append(
            {
                "draft": draft,
                "score": total,
                "base_score": round(base_score, 1),
                "feedback": feedback_score,
                "factors": factors,
                "recency": recency_score,
                "trend": trend_score,
                "relevance": relevance_score,
                "tier": relevance_tier,
                "discussion": discussion_score,
                "content": content_score,
            }
        )

    preliminary.sort(key=lambda row: (row["score"], row["draft"].published_at), reverse=True)

    events: list[HotspotEvent] = []
    for rank, row in enumerate(preliminary, start=1):
        draft: EventDraft = row["draft"]
        follow_up, follow_reason = _recommendation_decision(row)
        if follow_up == "建议跟进":
            angle = content_angle(draft)
            post = candidate_post(draft)
            recommendation = _specific_recommendation_reason(row)
        else:
            angle = None
            post = None
            recommendation = None

        events.append(
            HotspotEvent(
                event_id=draft.event_id,
                rank=rank,
                title=draft.title,
                summary=draft.summary,
                published_at=draft.published_at,
                items=draft.items,
                topics=draft.topics,
                event_type=draft.event_type,
                relevance_tier=row["tier"],
                merge_explanation=draft.merge_explanation,
                score=row["score"],
                base_score=row["base_score"],
                feedback_adjustment=row["feedback"],
                factors=row["factors"],
                follow_up=follow_up,
                follow_reason=follow_reason,
                content_angle=angle,
                candidate_post=post,
                recommendation_reason=recommendation,
            )
        )
    return events
