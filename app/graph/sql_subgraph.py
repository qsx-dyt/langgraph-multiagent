"""SQL Agent as a nested SubGraph.

Pipeline (each step is a node):
    generate (list tables + schema + SQL) -> validate -> execute
    execute failure -> rewrite_sql (error feedback) -> re-validate -> re-execute
    execute success -> end (writes sql_query / sql_result into shared state)

The sub-graph reuses the parent ``AnalysisState`` so its output flows straight
back into the main graph - this is the SubGraph + Loop pattern.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app import config
from app.agents.mock_responses import TAG_SQL
from app.graph.state import AnalysisState
from app.llm import get_chat_model
from app.tools.sql_tools import detect_sensitive_columns, execute_readonly_query, validate_sql

_SQL_SYSTEM_PROMPT = """You are a SQL analysis agent.
Your responsibility is to convert natural language questions into safe and accurate SQL queries.

Rules:
1. Only generate SELECT statements.
2. Never modify database data.
3. Always inspect relevant table schemas before writing SQL.
4. Never use SELECT * unless explicitly required.
5. Check SQL syntax before execution.
6. If execution fails, analyze the error and rewrite the SQL.
7. Return both the SQL and the query results.

The query must read from the read-only sales database. Use the [SQLGEN] marker."""


def _ask_model(question: str, state: dict) -> str:
    model = get_chat_model()
    return str(
        model.invoke(
            [SystemMessage(content=_SQL_SYSTEM_PROMPT), HumanMessage(content=f"{TAG_SQL}\nQUESTION: {question}\nSTATE: {_serialize(state)}")]
        ).content
    )


def _serialize(state: dict) -> str:
    body = [f"sql_attempts:{state.get('sql_attempts', 0)}"]
    rows = state.get("sql_result")
    if rows:
        body.append(f"SQL_ROWS_START\n{json.dumps(rows[:50], ensure_ascii=False)}\nSQL_ROWS_END")
    return "\n".join(body)


def _generate_sql(state: AnalysisState) -> AnalysisState:
    """List tables, inspect schema and generate SQL for the user question."""
    from app.tools.sql_tools import get_schema, list_tables

    question = state.get("user_query", "")
    state["sql_error"] = ""
    state["sql_attempts"] = state.get("sql_attempts", 0) + 1
    schema_hint = list_tables.invoke({})
    schema_hint += "\n" + get_schema.invoke({"table_name": "orders"})
    sql_text = _ask_model(f"{question}\nSCHEMA:\n{schema_hint}", state)
    state["sql_query"] = _clean_sql(sql_text)
    return state


def _clean_sql(text: str) -> str:
    """Extract the first SQL statement from model output."""
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith(("SELECT", "WITH")):
            return line.rstrip(";")
    return text.strip()


def _validate_sql(state: AnalysisState) -> AnalysisState:
    try:
        validate_sql(state.get("sql_query", ""))
        state["sql_error"] = ""
    except ValueError as exc:
        state["sql_error"] = str(exc)
    # Sensitive column detection triggers human-in-the-loop at the graph level.
    state["sensitive_detected"] = bool(detect_sensitive_columns(state.get("sql_query", "")))
    return state


def _execute_sql(state: AnalysisState) -> AnalysisState:
    if state.get("sql_error"):
        return state
    query = state.get("sql_query", "")
    try:
        state["sql_result"] = execute_readonly_query(query)
        state["sql_error"] = ""
    except Exception as exc:  # noqa: BLE001 - surfaced to the rewrite loop
        state["sql_result"] = None
        state["sql_error"] = f"{type(exc).__name__}: {exc}"
    return state


def _rewrite_sql(state: AnalysisState) -> AnalysisState:
    """Rewrites SQL based on the database error feedback (auto-fix loop)."""
    question = state.get("user_query", "")
    state["sql_attempts"] = state.get("sql_attempts", 0) + 1
    hint = state.get("sql_error", "")
    sql_text = _ask_model(f"{question}\nERROR_HINT: {hint}", state)
    state["sql_query"] = _clean_sql(sql_text)
    state["sql_error"] = ""
    state["sql_auto_fixed"] = True
    return state


def _route_after_validate(state: AnalysisState) -> str:
    return "execute" if not state.get("sql_error") else "rewrite"


def _route_after_execute(state: AnalysisState) -> str:
    if state.get("sql_error") and state.get("sql_attempts", 0) < config.MAX_SQL_RETRIES:
        return "rewrite"
    return END


def build_sql_subgraph() -> StateGraph:
    builder = StateGraph(AnalysisState)

    builder.add_node("list_tables", _generate_sql)  # combined introspect + generate
    builder.add_node("validate", _validate_sql)
    builder.add_node("execute", _execute_sql)
    builder.add_node("rewrite", _rewrite_sql)

    builder.add_edge(START, "list_tables")
    builder.add_edge("list_tables", "validate")
    builder.add_conditional_edges("validate", _route_after_validate, {"execute": "execute", "rewrite": "rewrite"})
    builder.add_conditional_edges("execute", _route_after_execute, {"rewrite": "rewrite", END: END})
    builder.add_edge("rewrite", "validate")
    return builder
