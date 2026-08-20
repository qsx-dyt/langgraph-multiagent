"""API routes: synchronous analysis and human-in-the-loop approval.

Frontend-facing streaming (SSE) is intentionally omitted: all demos run in
the terminal/editor via ``python -m scripts.demo``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.api.schemas import AnalysisInfo, AnalyzeRequest, AnalyzeResponse, ApproveRequest, ReviewInfo
from app.graph.workflow import build_workflow, _summarize

router = APIRouter(prefix="/api")

_graph: CompiledStateGraph | None = None


def get_graph() -> CompiledStateGraph:
    global _graph
    if _graph is None:
        _graph = build_workflow()
    return _graph


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """Run the full multi-agent analysis for a natural-language query."""
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": req.thread_id or "default"}}
        result = graph.invoke({"user_query": req.query}, config=config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc
    return _to_response(_summarize(result))


@router.post("/approve")
def approve(req: ApproveRequest):
    """Resume a workflow paused at a human-in-the-loop interrupt."""
    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": req.thread_id}}
        state = graph.get_state(config)
        if not state or not state.values:
            raise HTTPException(status_code=404, detail="No workflow state for this thread.")
        result = graph.invoke(
            Command(resume={"approved": req.approved}),
            config=config,
        )
        return _to_response(_summarize(result))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Resume failed: {exc}") from exc


def _to_response(summary: dict) -> AnalyzeResponse:
    return AnalyzeResponse(
        answer=summary.get("answer", ""),
        sql=summary.get("sql", ""),
        data=summary.get("data", []),
        chart=summary.get("chart", ""),
        review=ReviewInfo(
            passed=bool(summary.get("review", {}).get("passed")),
            feedback=summary.get("review", {}).get("feedback", ""),
        ),
        analysis=AnalysisInfo(
            summary=summary.get("analysis", {}).get("summary", ""),
            key_findings=summary.get("analysis", {}).get("key_findings", []),
            anomalies=summary.get("analysis", {}).get("anomalies", []),
        ),
    )
