"""Final Agent: composes the human-readable answer from all state outputs."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.mock_responses import TAG_FINAL
from app.graph.state import AnalysisState
from app.llm import get_chat_model

_FINAL_SYSTEM_PROMPT = """You are the Final Agent.
Compose a concise, well-structured final answer in Chinese that directly
answers the user's question, using only the verified data, findings and chart
in the state. Do not invent numbers. Use the [FINAL] marker."""


def final_node(state: AnalysisState) -> AnalysisState:
    model = get_chat_model()
    state_snapshot = _serialize(state)
    prompt = f"{TAG_FINAL}\nSTATE:\n{state_snapshot}"
    response = model.invoke(
        [SystemMessage(content=_FINAL_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    state["final_answer"] = str(response.content).strip()
    return state


def _serialize(state: AnalysisState) -> str:
    findings = "\n".join(f"- {f}" for f in state.get("key_findings", []))
    anomalies = "\n".join(f"- {a}" for a in state.get("anomalies", []))
    return (
        f"user_query: {state.get('user_query', '')}\n"
        f"analysis_summary: {state.get('analysis_summary', '')}\n"
        f"key_findings:\n{findings or '(none)'}\n"
        f"anomalies:\n{anomalies or '(none)'}\n"
        f"chart_path: {state.get('chart_path', '')}\n"
        f"sql_query: {state.get('sql_query', '')}\n"
        f"review_feedback: {state.get('review_feedback', '')}\n"
        f"SQL_ROWS_START\n{json.dumps((state.get('sql_result') or [])[:50], ensure_ascii=False)}\nSQL_ROWS_END"
    )
