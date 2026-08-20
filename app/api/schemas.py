"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language analysis request")
    thread_id: Optional[str] = Field(default="default", description="Session id for checkpointing")


class ApproveRequest(BaseModel):
    thread_id: str = Field(..., description="Session id to resume")
    approved: bool = Field(default=True, description="Approve or reject the sensitive SQL")


class ReviewInfo(BaseModel):
    passed: bool
    feedback: str = ""


class AnalysisInfo(BaseModel):
    summary: str = ""
    key_findings: list[str] = []
    anomalies: list[str] = []


class AnalyzeResponse(BaseModel):
    answer: str = ""
    sql: str = ""
    data: list[dict[str, Any]] = []
    chart: str = ""
    review: ReviewInfo
    analysis: AnalysisInfo
