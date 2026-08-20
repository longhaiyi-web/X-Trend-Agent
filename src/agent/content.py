from __future__ import annotations

import re
from urllib.parse import quote

from src.agent.models import EventDraft


ANGLE_BY_EVENT_TYPE = {
    "产品 / 工具发布": (
        "产品判断：先说明它解决的具体问题，再比较相对现有方案的变化；指出最值得关注的用户，"
        "最后给出是否值得实际测试的判断。"
    ),
    "开源项目 / GitHub 工具": (
        "开源采用判断：拆解核心能力、使用门槛和真实工作流位置；重点判断它能否从高 Star 信号"
        "转化为可复用的生产价值。"
    ),
    "生态集中更新 / 软件包家族更新": (
        "生态信号判断：解释为什么多个相关组件同时更新、这是否代表协调式生态动作，以及对"
        "开发者升级路径和产品兼容性意味着什么。"
    ),
    "行业新闻 / 公司动态": (
        "行业影响判断：不复述新闻标题，聚焦公司动作背后的竞争位置、受影响的产品方，以及接下来"
        "最值得验证的市场信号。"
    ),
    "技术观点 / 争议文章": (
        "观点讨论：提炼核心主张，同时给出支持与反对两种视角；用一个开放问题邀请 X 用户讨论，"
        "避免把作者观点包装成事实。"
    ),
    "开发者经验 / 案例分享": (
        "经验提炼：从真实经历中找出可复制的一步、适用边界和常见代价，让开发者能把案例转化为"
        "自己的下一次实验。"
    ),
    "研究 / 新技术进展": (
        "研究解读：区分论文或基准结果与实际产品能力，说明新方法改变了什么、证据强度如何，以及"
        "距离开发者可用还有多远。"
    ),
}


HOOKS_BY_EVENT_TYPE = {
    "产品 / 工具发布": (
        "Worth watching:",
        "A release worth testing:",
    ),
    "开源项目 / GitHub 工具": (
        "If you’re building AI agents, this is worth a look:",
        "A repo worth testing, not just starring:",
    ),
    "生态集中更新 / 软件包家族更新": (
        "This is more interesting than the release itself:",
        "One signal worth paying attention to:",
    ),
    "行业新闻 / 公司动态": (
        "The real takeaway here isn’t the headline — it’s the shift behind it:",
        "One industry move worth tracking:",
    ),
    "技术观点 / 争议文章": (
        "A useful debate for AI builders:",
        "The question worth asking isn’t whether this is right — but where it breaks:",
    ),
    "开发者经验 / 案例分享": (
        "A small lesson worth stealing:",
        "What’s useful here isn’t the story — it’s the repeatable step:",
    ),
    "研究 / 新技术进展": (
        "A research signal worth tracking:",
        "Promising result, but the evidence matters:",
    ),
}


INSIGHT_BY_EVENT_TYPE = {
    "产品 / 工具发布": (
        "The useful test: who saves time, what changes versus current options, and whether the upgrade earns a trial."
    ),
    "开源项目 / GitHub 工具": (
        "The real test is whether it solves a repeatable workflow well enough to earn a place in production."
    ),
    "生态集中更新 / 软件包家族更新": (
        "Related components moved together—usually a stronger ecosystem signal than an isolated patch."
    ),
    "行业新闻 / 公司动态": (
        "Watch the competitive position it changes and the next market signal that can confirm the impact."
    ),
    "技术观点 / 争议文章": (
        "The value is the tension it surfaces. Which assumption holds in production—and which one breaks first?"
    ),
    "开发者经验 / 案例分享": (
        "The transferable value is one repeatable step, plus the boundary where that lesson stops working."
    ),
    "研究 / 新技术进展": (
        "Separate the measured result from product readiness: what improved, how strong is the evidence, and what remains?"
    ),
}

CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

ENGLISH_FALLBACK_BY_EVENT_TYPE = {
    "产品 / 工具发布": "A new AI product or tool update",
    "开源项目 / GitHub 工具": "A new open-source tool for AI builders",
    "生态集中更新 / 软件包家族更新": "A coordinated AI ecosystem update",
    "行业新闻 / 公司动态": "A new AI industry development",
    "技术观点 / 争议文章": "A debate worth having about AI development",
    "开发者经验 / 案例分享": "A practical AI developer case study",
    "研究 / 新技术进展": "A new AI research development",
}


def content_angle(event: EventDraft) -> str:
    return ANGLE_BY_EVENT_TYPE[event.event_type]


def _clip(value: str, limit: int) -> str:
    value = " ".join(value.split()).strip()
    if len(value) <= limit:
        return value
    clipped = value[: max(1, limit - 1)].rsplit(" ", 1)[0].rstrip(" ,.;:，。；：")
    return f"{clipped or value[: limit - 1]}…"


def _english_event_title(event: EventDraft) -> str:
    if event.event_type == "生态集中更新 / 软件包家族更新":
        family = next(
            (
                item.title.split("/", 1)[0]
                for item in event.items
                if item.title.startswith("@") and "/" in item.title
            ),
            "AI ecosystem",
        )
        return f"A coordinated {family} update across {len(event.items)} related packages"

    title = CJK_PATTERN.sub(" ", event.title)
    title = re.sub(r"[（）【】《》；，。：、]", " ", title)
    title = " ".join(title.split()).strip(" -—:.;")
    if not re.search(r"[A-Za-z]", title):
        return ENGLISH_FALLBACK_BY_EVENT_TYPE[event.event_type]
    return title


def candidate_post(event: EventDraft) -> str:
    """Create a deterministic, type-specific X draft without copying source descriptions."""
    hooks = HOOKS_BY_EVENT_TYPE[event.event_type]
    hook = hooks[int(event.event_id[-2:], 16) % len(hooks)]
    insight = INSIGHT_BY_EVENT_TYPE[event.event_type]
    title = _clip(_english_event_title(event), 86)
    link = quote(event.items[0].url, safe=":/?&=%#@+.-_~")

    if event.event_type == "生态集中更新 / 软件包家族更新":
        insight = f"{len(event.items)} related updates moved together—a stronger ecosystem signal than an isolated patch."
    elif len({item.source_type for item in event.items}) > 1:
        insight = f"Signals across {len({item.source_type for item in event.items})} source types make the impact worth checking."

    post = f"{hook} {title}. {insight} {link}"
    if len(post) <= 280:
        return post

    available = max(34, 280 - len(hook) - len(insight) - len(link) - 4)
    post = f"{hook} {_clip(title, available)}. {insight} {link}"
    if len(post) <= 280:
        return post

    compact_insight = _clip(insight, max(45, len(insight) - (len(post) - 280) - 2))
    post = f"{hook} {_clip(title, 60)}. {compact_insight} {link}"
    if len(post) <= 280:
        return post

    title_only_limit = max(16, 280 - len(hook) - len(link) - 3)
    return f"{hook} {_clip(title, title_only_limit)} {link}"[:280]
