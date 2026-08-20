"""Chart Agent: decides the chart type via LLM, then calls the deterministic
matplotlib tool to actually render it (LLM Decision + Deterministic Tool).

Supported types: line, bar, pie, scatter.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.mock_responses import TAG_CHART
from app.graph.state import AnalysisState
from app.llm import get_chat_model
from app.tools import chart_tools

_CHART_SYSTEM_PROMPT = """You are a Visualization Agent.
Decide the best chart type for the data and return JSON:
{"chart_type": "line|bar|pie|scatter", "x_key": "...", "y_key": "..."}
- time series -> line
- category comparison -> bar
- share / proportion -> pie
- two-dimensional relationship -> scatter
Use the [CHART] marker."""

_CHART_TITLES = {
    "line": "Sales Trend",
    "bar": "Category Comparison",
    "pie": "Sales Share",
    "scatter": "Scatter",
}


def _rows_to_json(state: AnalysisState) -> str:
    rows = state.get("sql_result") or []
    return json.dumps(rows[:200], ensure_ascii=False)


def chart_node(state: AnalysisState) -> AnalysisState:
    model = get_chat_model()
    question = state.get("user_query", "")
    prompt = f"{TAG_CHART}\nQUESTION: {question}\nSTATE:\nSQL_ROWS_START\n{_rows_to_json(state)}\nSQL_ROWS_END"
    response = model.invoke(
        [SystemMessage(content=_CHART_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    spec = _parse_spec(str(response.content))
    chart_type = spec.get("chart_type", "bar")
    x_key = spec.get("x_key", "label")
    y_key = spec.get("y_key", "value")
    rows = state.get("sql_result") or []
    try:
        state["chart_path"] = _render(chart_type, rows, x_key, y_key, question)
        state["chart_type"] = chart_type
        state["chart_error"] = ""
    except Exception as exc:  # noqa: BLE001
        state["chart_path"] = ""
        state["chart_type"] = chart_type
        state["chart_error"] = f"{type(exc).__name__}: {exc}"
    return state


def _render(chart_type: str, rows, x_key: str, y_key: str, question: str) -> str:
    if chart_type == "line":
        return chart_tools.plot_line(rows, x_key, y_key, _CHART_TITLES["line"])
    if chart_type == "pie":
        return chart_tools.plot_pie(rows, x_key, y_key, _CHART_TITLES["pie"])
    if chart_type == "scatter":
        return chart_tools.plot_scatter(rows, x_key, y_key, _CHART_TITLES["scatter"])
    return chart_tools.plot_bar(rows, x_key, y_key, _CHART_TITLES["bar"])


def _parse_spec(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}
