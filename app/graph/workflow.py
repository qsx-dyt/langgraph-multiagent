"""Main LangGraph workflow: compiles all agents into a single graph.

Flow:
    START -> supervisor -> (worklist router) -> sql / analysis / chart
    sql_agent, analysis_agent -> supervisor        (multi-step scheduling)
    chart_agent -> reviewer
    reviewer -> (conditional) -> retry agent OR final

The Supervisor maintains a step worklist + stage machine:
- "running": dispatch first incomplete step
- "review":  all steps done -> Reviewer
- "retry":   Reviewer rejected -> flagged agent, which returns to review

Extra capabilities:
- Human-in-the-loop: sensitive SQL pauses via interrupt() before executing.
- Checkpointing: InMemorySaver keyed by thread_id.
- Streaming: graph.stream(stream_mode="updates") yields node events.
"""
from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import GraphInterrupt, interrupt

from app.agents.analysis_agent import analysis_node
from app.agents.chart_agent import chart_node
from app.agents.final_agent import final_node
from app.agents.reviewer import reviewer_node
from app.agents.supervisor import supervisor_node
from app.graph.router import reviewer_router, supervisor_router
from app.graph.sql_subgraph import build_sql_subgraph
from app.graph.state import AnalysisState

# The SQL SubGraph is nested inside this graph; compile it once.
_SQL_GRAPH = build_sql_subgraph().compile()


def _mark_step(state: AnalysisState, step: str, done: bool) -> AnalysisState:
    """Update the worklist after an agent runs."""
    completed = list(state.get("completed_steps") or [])
    if done and step not in completed:
        completed.append(step)
    state["completed_steps"] = completed
    planned = state.get("pending_steps") or [step]
    if done and all(s in completed for s in planned):
        state["stage"] = "review"
    else:
        state["stage"] = "running"
    return state


def _sql_agent_node(state: AnalysisState) -> AnalysisState:
    """Run the SQL SubGraph, then optionally pause for sensitive-SQL approval."""
    state = _SQL_GRAPH.invoke(state)

    if state.get("sensitive_detected") and not state.get("confirmed"):
        state["pending_human_confirmation"] = True
        decision: dict = interrupt({"message": "Sensitive query", "sql": state.get("sql_query", "")})
        approved = bool(decision.get("approved", True))
        if not approved:
            state["sql_result"] = []
            state["sql_error"] = "Sensitive query rejected by user."
            state["sql_query"] = ""
        state["confirmed"] = True
        state["pending_human_confirmation"] = False

    # A retry was just handled; drop the retry marker so we re-review.
    if state.get("stage") == "retry":
        state["stage"] = "review"
    return _mark_step(state, "sql", done=True)


def _analysis_agent_node(state: AnalysisState) -> AnalysisState:
    state = analysis_node(state)
    if state.get("stage") == "retry":
        state["stage"] = "review"
    return _mark_step(state, "analysis", done=True)


def _chart_agent_node(state: AnalysisState) -> AnalysisState:
    state = chart_node(state)
    if state.get("stage") == "retry":
        state["stage"] = "review"
    return _mark_step(state, "chart", done=True)


def _reviewer_node(state: AnalysisState) -> AnalysisState:
    state = reviewer_node(state)
    state["needs_review"] = not state.get("review_passed", False)
    return state


def build_workflow(checkpointer: Any | None = None) -> CompiledStateGraph:
    """Compile the full multi-agent workflow."""
    builder = StateGraph(AnalysisState)

    builder.add_node("supervisor", supervisor_node)
    builder.add_node("sql_agent", _sql_agent_node)
    builder.add_node("analysis_agent", _analysis_agent_node)
    builder.add_node("chart_agent", _chart_agent_node)
    builder.add_node("reviewer", _reviewer_node)
    builder.add_node("final", final_node)

    builder.add_edge(START, "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        supervisor_router,
        {
            "sql": "sql_agent",
            "analysis": "analysis_agent",
            "chart": "chart_agent",
            "reviewer": "reviewer",
            "final": "final",
        },
    )

    builder.add_edge("sql_agent", "supervisor")
    builder.add_edge("analysis_agent", "supervisor")
    builder.add_edge("chart_agent", "reviewer")

    builder.add_conditional_edges(
        "reviewer",
        reviewer_router,
        {
            "sql": "sql_agent",
            "analysis": "analysis_agent",
            "chart": "chart_agent",
            "final": "final",
        },
    )

    builder.add_edge("final", END)

    checkpointer = checkpointer or InMemorySaver()
    return builder.compile(checkpointer=checkpointer)


def invoke_analysis(query: str, thread_id: str = "default") -> dict:
    """Run the workflow for a single user query (no interruptions expected)."""
    graph = build_workflow()
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"user_query": query}, config=config)
    return _summarize(result)


def _summarize(state: dict) -> dict:
    return {
        "answer": state.get("final_answer", ""),
        "sql": state.get("sql_query", ""),
        "data": state.get("sql_result") or [],
        "chart": state.get("chart_path", ""),
        "review": {"passed": state.get("review_passed"), "feedback": state.get("review_feedback", "")},
        "analysis": {
            "summary": state.get("analysis_summary", ""),
            "key_findings": state.get("key_findings", []),
            "anomalies": state.get("anomalies", []),
        },
        "interrupted": state.get("pending_human_confirmation", False),
        "pending_sql": state.get("sql_query", ""),
    }
