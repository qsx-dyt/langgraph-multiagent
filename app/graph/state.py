"""LangGraph shared state for the multi-agent workflow."""
from __future__ import annotations

from typing import Any, Literal, TypedDict

# Names of the agent nodes in the main graph.
AgentName = Literal["sql", "analysis", "chart", "final"]


class AnalysisState(TypedDict, total=False):
    """Explicit business state shared by all agents.

    Agents never call each other directly; they read/write this state,
    which is what makes the workflow inspectable and resumable.
    """

    # -- user input -------------------------------------------------------
    user_query: str
    task_type: str  # short label such as "trend", "comparison", "topk"

    # -- scheduling (worklist + stage machine) ----------------------------
    pending_steps: list[str]  # ordered agent steps from the Supervisor
    completed_steps: list[str]  # steps that have run
    stage: str  # "running" | "review" | "retry" | "done"

    # -- SQL Agent --------------------------------------------------------
    sql_query: str
    sql_result: list[dict[str, Any]] | None
    sql_error: str
    sql_attempts: int
    sql_auto_fixed: bool
    sensitive_detected: bool

    # -- Analysis Agent ---------------------------------------------------
    analysis_summary: str
    key_findings: list[str]
    anomalies: list[str]
    analysis_raw: str

    # -- Chart Agent ------------------------------------------------------
    chart_type: str
    chart_path: str
    chart_error: str

    # -- Reviewer ---------------------------------------------------------
    review_passed: bool
    review_feedback: str
    retry_agent: AgentName | None
    review_count: int
    needs_review: bool

    # -- Final ------------------------------------------------------------
    final_answer: str

    # -- Human-in-the-loop ------------------------------------------------
    pending_human_confirmation: bool
    confirmed: bool

    # -- Runtime tracing --------------------------------------------------
    node_logs: list[dict[str, Any]]  # {node, message} for streaming events
