"""Routing functions for the main graph (conditional edges).

The Supervisor maintains a worklist of steps and a stage machine:

- "running": dispatch the first not-yet-completed step (sql -> analysis -> chart).
- "review":   all planned steps have run -> route to the Reviewer.
- "retry":    the Reviewer rejected output -> route to the retry agent.
"""
from __future__ import annotations

import json

from app import config
from app.graph.state import AnalysisState

_PLANNED_ORDER = ["sql", "analysis", "chart"]


def _parse_steps(raw: str) -> list[str]:
    try:
        if isinstance(raw, str) and raw.strip().startswith("{"):
            data = json.loads(raw)
            steps = data.get("steps", [])
            return [s for s in steps if s in ("sql", "analysis", "chart")]
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


def supervisor_router(state: AnalysisState) -> str:
    """Dispatch the next step, or go to review when all steps are done."""
    stage = state.get("stage", "running")

    if stage == "review":
        return "reviewer"
    if stage == "retry":
        agent = state.get("retry_agent")
        if agent in ("sql", "analysis", "chart"):
            return agent

    steps = state.get("pending_steps") or []
    completed = state.get("completed_steps") or []
    for step in _PLANNED_ORDER:
        if step in steps and step not in completed:
            return step
    return "final"


def reviewer_router(state: AnalysisState) -> str:
    """After review: finish when passed, otherwise retry the flagged agent."""
    if state.get("review_passed"):
        return "final"
    if state.get("review_count", 0) >= config.MAX_REVIEW_RETRIES:
        return "final"  # give up after repeated failures, still produce a report
    agent = state.get("retry_agent")
    if agent in ("sql", "analysis", "chart"):
        return agent
    return "final"
