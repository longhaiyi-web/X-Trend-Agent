"""Deterministic stage-two agent for event discovery and recommendation."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent.models import AgentReport
    from src.models import FetchReport


def run_agent(fetch_report: "FetchReport", history: list[dict[str, Any]]) -> "AgentReport":
    """Import lazily so the review store can reuse agent data models safely."""
    from src.agent.pipeline import run_agent as _run_agent

    return _run_agent(fetch_report, history)


__all__ = ["run_agent"]
