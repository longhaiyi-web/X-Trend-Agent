from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st

from src.agent import run_agent
from src.agent.models import HotspotEvent, ScoreFactor
from src.models import FetchReport, HotspotItem
from src.pipeline import fetch_all_sources
from src.review_store import add_to_pool, decide_candidate, load_state


CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


st.set_page_config(
    page_title="每日热点到候选内容池 Agent",
    page_icon="📡",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 1180px; padding-top: 1.7rem; padding-bottom: 4rem;}
      .hero-kicker {font-size: .78rem; letter-spacing: .14em; text-transform: uppercase;
                    color: #0f766e; font-weight: 750; margin-bottom: .35rem;}
      .hero-copy {color: #475569; max-width: 850px; line-height: 1.65; margin-bottom: .4rem;}
      .event-meta {color: #64748b; font-size: .86rem; margin-bottom: .45rem;}
      .topic-chip {display: inline-block; border: 1px solid #cbd5e1; background: #f8fafc;
                   color: #334155; border-radius: 999px; padding: .16rem .56rem;
                   font-size: .75rem; font-weight: 650; margin: 0 .28rem .2rem 0;}
      .decision-yes {color: #047857; font-weight: 750;}
      .decision-watch {color: #b45309; font-weight: 750;}
      .decision-no {color: #64748b; font-weight: 750;}
      div[data-testid="stMetric"] {background: #fff; border: 1px solid #e2e8f0;
                                   padding: .9rem 1rem; border-radius: .8rem;}
      div[data-testid="stVerticalBlockBorderWrapper"] {background: rgba(255,255,255,.78);}
      div[data-testid="stVerticalBlockBorderWrapper"] h3 {margin-bottom: .25rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=600, show_spinner=False)
def load_report() -> FetchReport:
    return fetch_all_sources(limit_per_source=15)


def format_time(value: datetime, pattern: str = "%Y-%m-%d %H:%M") -> str:
    return value.astimezone(CHINA_TZ).strftime(pattern)


def markdown_label(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def factor_value(factor: ScoreFactor) -> str:
    if factor.name == "历史偏好调整":
        return f"{factor.score:+g} / ±{factor.max_score:g}"
    return f"{factor.score:g} / {factor.max_score:g}"


def render_sources(event: HotspotEvent) -> None:
    st.markdown("**信息来源与原文依据**")
    for index, item in enumerate(event.items, start=1):
        st.markdown(
            f"{index}. [{markdown_label(item.title)}]({item.url})  "
            f"— {item.source_name} · {format_time(item.published_at)}"
        )


def render_score_explanation(event: HotspotEvent) -> None:
    st.caption(f"事件聚合：{event.merge_explanation}。以下分项全部来自可见规则与公开字段。")
    for factor in event.factors:
        st.markdown(f"- **{factor.name} {factor_value(factor)}** — {factor.explanation}")
    st.markdown(
        f"**基础分 {event.base_score:.1f} + 历史偏好 {event.feedback_adjustment:+.1f} "
        f"= 最终热点评分 {event.score:.1f} / 100**"
    )


def render_recommended_event(
    event: HotspotEvent,
    pending_ids: set[str],
    reviewed_ids: set[str],
) -> None:
    with st.container(border=True):
        header_left, header_right = st.columns([5, 1])
        with header_left:
            st.caption(f"TOP {event.rank:02d} · <span class='decision-yes'>建议跟进</span>", unsafe_allow_html=True)
            st.subheader(event.title)
        with header_right:
            st.metric("热点评分", f"{event.score:.1f}")

        chips = f'<span class="topic-chip">{escape(event.event_type)}</span>' + "".join(
            f'<span class="topic-chip">{escape(topic)}</span>' for topic in event.topics
        )
        st.markdown(chips, unsafe_allow_html=True)
        source_count = len({item.source_name for item in event.items})
        source_type_count = len({item.source_type for item in event.items})
        st.markdown(
            f'<div class="event-meta">{source_count} 个来源 / {source_type_count} 种来源类型 / '
            f'{len(event.items)} 条原始信息 · '
            f'最新信号 {format_time(event.published_at)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**一句话推荐理由**　{event.recommendation_reason}")
        st.markdown("**推荐内容角度**")
        st.write(event.content_angle)
        st.markdown("**英文 X 候选文案**")
        st.code(event.candidate_post or "", language=None, wrap_lines=True)

        if event.event_id in pending_ids:
            st.button("已在待审核内容池", key=f"pending-{event.event_id}", disabled=True)
        elif event.event_id in reviewed_ids:
            st.button("该事件已完成审核", key=f"reviewed-{event.event_id}", disabled=True)
        elif st.button("加入待审核内容池", key=f"add-{event.event_id}", type="primary"):
            _, message = add_to_pool(event)
            st.session_state["flash_message"] = message
            st.rerun()

        with st.expander("展开：评分拆解、事件摘要与全部来源"):
            st.markdown(f"**X 跟进判断依据**　{event.follow_reason}")
            st.markdown("**原始事件摘要**")
            st.write(event.summary)
            st.markdown("**为什么这个热点排在这里**")
            render_score_explanation(event)
            render_sources(event)


def render_pool_record(record: dict) -> None:
    with st.container(border=True):
        st.subheader(record.get("title", "未命名候选"))
        topics = " · ".join(record.get("topics", []))
        event_type = record.get("event_type", "历史候选")
        st.caption(f"评分 {record.get('score', 0):.1f} · {event_type} · {topics} · 加入于 {record.get('added_at', '')[:19]}")
        st.write(record.get("event_summary", ""))
        st.markdown("**候选文案**")
        st.code(record.get("candidate_post", ""), language=None, wrap_lines=True)
        st.markdown("**推荐角度**")
        st.write(record.get("content_angle", ""))
        with st.expander("原始来源"):
            for source in record.get("sources", []):
                st.markdown(
                    f"- [{markdown_label(source.get('title', '原文'))}]({source.get('url', '')}) "
                    f"— {source.get('source_name', '')}"
                )
        adopt_col, reject_col, _ = st.columns([1, 1, 3])
        with adopt_col:
            if st.button("采用这条", key=f"adopt-{record.get('id')}", type="primary", width="stretch"):
                _, message = decide_candidate(record.get("id", ""), "采用")
                st.session_state["flash_message"] = message
                st.rerun()
        with reject_col:
            if st.button("驳回这条", key=f"reject-{record.get('id')}", width="stretch"):
                _, message = decide_candidate(record.get("id", ""), "驳回")
                st.session_state["flash_message"] = message
                st.rerun()


st.markdown('<div class="hero-kicker">X TREND AGENT / EVENT INTELLIGENCE</div>', unsafe_allow_html=True)
st.title("每日热点到候选内容池 Agent")
st.markdown(
    '<div class="hero-copy">从真实公开来源开始，将原始信息聚合为事件，给出可解释的优先级和 X 跟进判断，'
    '再把少量高价值候选送入人工审核。当前使用本地规则型 Agent，不调用 LLM API。</div>',
    unsafe_allow_html=True,
)

toolbar_left, toolbar_right = st.columns([5, 1])
with toolbar_left:
    st.caption("公开来源缓存 10 分钟；审核与反馈保存在本地 data/review_state.json，刷新页面不会丢失。")
with toolbar_right:
    if st.button("重新抓取来源", type="primary", width="stretch"):
        st.cache_data.clear()
        st.rerun()

with st.spinner("正在抓取真实公开数据并运行事件级 Agent……"):
    fetch_report = load_report()

review_state = load_state()
agent_report = run_agent(fetch_report, review_state["history"])
pending_ids = {record.get("id", "") for record in review_state["pool"]}
reviewed_ids = {record.get("id", "") for record in review_state["history"]}
recommended_events = [event for event in agent_report.events if event.follow_up == "建议跟进"]
failed_sources = [source for source in fetch_report.sources if not source.success]

if "flash_message" in st.session_state:
    st.toast(st.session_state.pop("flash_message"))

metric_raw, metric_events, metric_recommended, metric_pool = st.columns(4)
metric_raw.metric("今天发现原始信息", f"{agent_report.raw_count} 条")
metric_events.metric("聚合后热点事件", f"{agent_report.event_count} 个", help=f"其中 {agent_report.grouped_event_count} 个事件合并了多条原始记录")
metric_recommended.metric("推荐跟进", f"{agent_report.recommended_count} 个")
metric_pool.metric("当前待审核", f"{len(review_state['pool'])} 条")
st.caption(
    f"本次抓取 {len(fetch_report.sources) - len(failed_sources)} / {len(fetch_report.sources)} 个来源成功 · "
    f"{agent_report.raw_count} 条原始信息 → {agent_report.event_count} 个事件 → "
    f"{agent_report.recommended_count} 个建议跟进 → {len(review_state['pool'])} 条待审核"
)

if failed_sources:
    names = "、".join(source.display_name for source in failed_sources)
    st.warning(f"{names} 本次抓取失败；Agent 已基于其余 {agent_report.raw_count} 条真实信息继续运行。详情见“数据来源 / 原始信息”。")

candidate_tab, pool_tab, feedback_tab, raw_tab = st.tabs(
    [
        "候选热点",
        f"待审核内容池 · {len(review_state['pool'])}",
        f"反馈与偏好 · {len(review_state['history'])}",
        "数据来源 / 原始信息",
    ]
)

with candidate_tab:
    st.header("Top 热点与候选内容")
    st.caption("仅展示越过动态阈值的“建议跟进”事件，不设置固定推荐名额；完整依据收在卡片折叠区。")
    if not recommended_events:
        st.info("本轮没有事件同时达到相关度、讨论价值和总分门槛。原始数据仍可在最后一个 Tab 查看。")
    for event in recommended_events:
        render_recommended_event(event, pending_ids, reviewed_ids)

    st.divider()
    st.subheader("全部聚合事件与 X 跟进判断")
    st.caption("这里保留每个事件的判断与简短理由，避免只显示被推荐的结果。")
    event_rows = [
        {
            "排名": event.rank,
            "热点事件": event.title,
            "评分": event.score,
            "判断": event.follow_up,
            "事件类型": event.event_type,
            "相关层级": event.relevance_tier,
            "主题": "、".join(event.topics),
            "原始记录": len(event.items),
            "判断理由": event.follow_reason,
        }
        for event in agent_report.events
    ]
    st.dataframe(event_rows, hide_index=True, width="stretch", height=430)

with pool_tab:
    st.header("待审核内容池")
    st.caption("只有你主动加入的候选会出现在这里。采用或驳回后会从待审核列表移入历史记录。")
    if not review_state["pool"]:
        st.info("当前没有待审核内容。请从“候选热点”中加入一条。")
    for record in review_state["pool"]:
        render_pool_record(record)

with feedback_tab:
    st.header("反馈历史与可解释偏好")
    st.info(
        "这是本地历史反馈驱动的规则型偏好调整，不是模型自动学习。每个主题的采用数减去驳回数，每次影响 1.5 分；"
        "同主题连续采用或连续驳回达到 2 次后，"
        "再追加同方向 streak 权重。单主题调整限制在 ±8 分，事件总反馈调整限制在 ±10 分。",
        icon="ℹ️",
    )
    if not agent_report.preferences:
        st.write("暂无采用/驳回历史。当前所有事件的历史偏好调整均为 0 分。")
    else:
        positive = [f"{item.topic} {item.adjustment:+.1f}" for item in agent_report.preferences if item.adjustment > 0]
        negative = [f"{item.topic} {item.adjustment:+.1f}" for item in agent_report.preferences if item.adjustment < 0]
        st.success("正向调整主题：" + ("、".join(positive) if positive else "暂无"))
        st.warning("降权主题：" + ("、".join(negative) if negative else "暂无"))
        preference_rows = [
            {
                "主题": item.topic,
                "采用": item.adopted,
                "驳回": item.rejected,
                "当前连续反馈": f"{item.streak_action or '-'} × {item.streak_count}",
                "评分调整": f"{item.adjustment:+.1f}",
                "使用的最近证据": "；".join(item.evidence_titles),
            }
            for item in agent_report.preferences
        ]
        st.dataframe(preference_rows, hide_index=True, width="stretch")

    st.subheader("采用 / 驳回历史")
    if not review_state["history"]:
        st.caption("暂无历史记录。")
    for record in reversed(review_state["history"]):
        action = record.get("action", "")
        icon = "✅" if action == "采用" else "⛔"
        with st.expander(f"{icon} {action} · {record.get('title', '未命名事件')}"):
            st.caption(f"决定时间：{record.get('decided_at', '')} · 主题：{'、'.join(record.get('topics', []))}")
            st.code(record.get("candidate_post", ""), language=None, wrap_lines=True)
            for source in record.get("sources", []):
                st.markdown(f"- [{markdown_label(source.get('title', '原文'))}]({source.get('url', '')})")

with raw_tab:
    st.header("数据来源 / 原始信息")
    st.caption("该区域保留第一阶段能力，用于审计和追溯；它不再是首页的主要工作流。")
    with st.expander("查看信息源运行状态", expanded=bool(failed_sources)):
        for source in fetch_report.sources:
            if source.success:
                st.success(f"{source.display_name} · {source.source_type}：成功返回 {source.item_count} 条（{source.elapsed_ms} ms）")
            else:
                st.error(f"{source.display_name} · {source.source_type}：抓取失败——{source.error}。其他来源继续运行。")

    source_types = sorted({item.source_type for item in fetch_report.items})
    selected_types = st.multiselect("按来源类型筛选", source_types, default=source_types)
    visible_items = [item for item in fetch_report.items if item.source_type in selected_types]
    visible_items.sort(key=lambda item: item.published_at, reverse=True)
    raw_rows = [
        {
            "标题": item.title,
            "来源名称": item.source_name,
            "来源类型": item.source_type,
            "发布时间": format_time(item.published_at),
            "简短原始描述": item.description,
            "原文链接": item.url,
        }
        for item in visible_items
    ]
    st.dataframe(
        raw_rows,
        hide_index=True,
        width="stretch",
        height=520,
        column_config={"原文链接": st.column_config.LinkColumn("原文链接", display_text="打开原文 ↗")},
    )
