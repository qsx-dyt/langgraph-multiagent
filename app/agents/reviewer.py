"""Reviewer Agent: independent quality gate (generation vs verification).

Checks SQL correctness, result non-emptiness, consistency between the
analysis conclusions / chart and the underlying data, and whether the user
question was answered. Returns:
  {"passed": bool, "reason": str, "retry_agent": "sql"|"analysis"|"chart"|null}
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.mock_responses import TAG_REVIEW
from app.graph.state import AnalysisState
from app.llm import get_chat_model

_REVIEWER_SYSTEM_PROMPT = """You are a data analysis reviewer.
Check:
1. Is the SQL logically correct?
2. Does the SQL answer the user's question?
3. Are the analysis conclusions supported by the data?
4. Is there any hallucination?
5. Does the chart represent the returned data?
6. Should another agent retry?
Return JSON: {"passed": bool, "reason": "...", "retry_agent": "sql"|"analysis"|"chart"|null}
Use the [REVIEW] marker."""


def reviewer_node(state: AnalysisState) -> AnalysisState:
    model = get_chat_model()
    prompt = _build_review_prompt(state)
    response = model.invoke(
        [SystemMessage(content=_REVIEWER_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    verdict = _parse_verdict(str(response.content))
    state["review_passed"] = bool(verdict.get("passed"))
    state["review_feedback"] = verdict.get("reason", "")
    state["retry_agent"] = verdict.get("retry_agent")
    state["review_count"] = state.get("review_count", 0) + 1
    return state


def _build_review_prompt(state: AnalysisState) -> str:
    return (
        f"{TAG_REVIEW}\n"
        f"QUESTION: {state.get('user_query', '')}\n"
        f"PLANNED_HAS_ANALYSIS: {'analysis' in (state.get('pending_steps') or [])}\n"
        f"PLANNED_HAS_CHART: {'chart' in (state.get('pending_steps') or [])}\n"
        f"SQL: {state.get('sql_query', '')}\n"
        f"SQL_RESULT_ROWS: {len(state.get('sql_result') or [])}\n"
        f"ANALYSIS_SUMMARY: {state.get('analysis_summary', '')}\n"
        f"FINDINGS: {json.dumps(state.get('key_findings', []), ensure_ascii=False)}\n"
        f"CHART: {state.get('chart_path', '')}\n"
        f"STATE:\nanalysis_summary: {state.get('analysis_summary', '')}\n"
        f"SQL_ROWS_START\n{json.dumps((state.get('sql_result') or [])[:100], ensure_ascii=False)}\nSQL_ROWS_END"
    )


def _parse_verdict(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"passed": False, "reason": "Reviewer returned no parseable verdict.", "retry_agent": "sql"}
