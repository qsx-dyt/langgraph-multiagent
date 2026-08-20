"""Analysis Agent: consumes the SQL result and produces structured findings.

It does NOT touch the database. It decides which statistics to compute, then
relies on deterministic tools for the actual computation (LLM Decision +
Deterministic Tool). Output uses structured JSON:
  {"summary": str, "key_findings": [str], "anomalies": [str]}
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.mock_responses import TAG_ANALYSIS
from app.graph.state import AnalysisState
from app.llm import get_chat_model

_ANALYSIS_SYSTEM_PROMPT = """You are an Analysis Agent.

Input is the user's question and the SQL query result. Decide what statistics
matter (trends, MoM/YoY growth, Top-K, share, anomalies) and return a JSON:
{"summary": "...", "key_findings": [...], "anomalies": [...]}
All numbers must come from the provided data - never invent figures.
Use the [ANALYSIS] marker."""


def _rows_to_json(rows: list[dict[str, Any]] | None) -> str:
    if not rows:
        return "[]"
    return json.dumps(rows[:200], ensure_ascii=False)


def analysis_node(state: AnalysisState) -> AnalysisState:
    model = get_chat_model()
    question = state.get("user_query", "")
    rows = state.get("sql_result") or []
    prompt = (
        f"{TAG_ANALYSIS}\nQUESTION: {question}\n"
        f"STATE:\nanalysis_summary: {state.get('analysis_summary', '')}\n"
        f"SQL_ROWS_START\n{_rows_to_json(rows)}\nSQL_ROWS_END"
    )
    response = model.invoke(
        [SystemMessage(content=_ANALYSIS_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    raw = str(response.content).strip()
    parsed = _parse_json(raw)
    state["analysis_summary"] = parsed.get("summary", raw)
    state["key_findings"] = parsed.get("key_findings", [])
    state["anomalies"] = parsed.get("anomalies", [])
    state["analysis_raw"] = raw
    return state


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # try to find the first {...} block
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}
