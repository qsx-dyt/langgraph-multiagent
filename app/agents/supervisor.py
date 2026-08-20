"""Supervisor Agent: understands the request and schedules the specialist agents.

It does NOT do data analysis. It reads the user question, classifies the task
(which specialist agents are needed) via the LLM, and initialises the ordered
step worklist in the shared state. The main graph routes accordingly.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.mock_responses import TAG_SUPERVISOR
from app.graph.state import AnalysisState
from app.llm import get_chat_model

_SUPERVISOR_PROMPT = """You are the Supervisor Agent of a data-analysis system.

You only decide WHAT work is needed - never perform the analysis yourself.
Classify the user's question and respond with a JSON object:

{"steps": ["sql", "analysis", "chart"]}

Rules:
- "sql" is always required when the user asks about the data.
- "analysis" when statistical insight, trends, comparisons, anomalies or reasons are needed.
- "chart" when the user asks for a chart / visualization / trend plot.
Use the [ROUTER] marker."""


def supervisor_node(state: AnalysisState) -> AnalysisState:
    """Classify the request and initialise the step worklist (once)."""
    if state.get("pending_steps"):
        # Worklist already scheduled; nothing to do on subsequent visits.
        return state

    model = get_chat_model()
    question = state.get("user_query", "")
    response = model.invoke(
        [SystemMessage(content=_SUPERVISOR_PROMPT), HumanMessage(content=f"{TAG_SUPERVISOR}\nQUESTION: {question}")]
    )
    raw = str(response.content).strip()
    state["task_type"] = raw
    try:
        decision = json.loads(raw)
        steps = [s for s in decision.get("steps", []) if s in ("sql", "analysis", "chart")]
    except json.JSONDecodeError:
        steps = []
    state["pending_steps"] = list(dict.fromkeys(steps)) or ["sql"]
    state["completed_steps"] = []
    state["stage"] = "running"
    return state
