"""End-to-end tests for the compiled multi-agent graph (mock LLM)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("DB_PATH", "data/test_sales.db")

from app.database.connection import get_engine, init_database  # noqa: E402
from app.database.seed import seed_database  # noqa: E402
from app.graph.workflow import _summarize, build_workflow  # noqa: E402


@pytest.fixture(scope="module")
def workflow():
    # Rebuild a clean test DB (regenerate seeds it too).
    seed_database(regenerate=True)
    graph = build_workflow()
    return graph


def test_workflow_runs_end_to_end(workflow):
    result = workflow.invoke(
        {"user_query": "2025年每个月销售额趋势如何？"},
        config={"configurable": {"thread_id": "e2e-1"}},
    )
    summary = _summarize(result)
    assert summary["sql"]
    assert summary["data"]
    assert summary["analysis"]["summary"]
    assert summary["review"]["passed"] is True
    assert summary["answer"]


def test_workflow_with_chart(workflow):
    result = workflow.invoke(
        {"user_query": "分析不同地区销售额并画图。"},
        config={"configurable": {"thread_id": "e2e-2"}},
    )
    summary = _summarize(result)
    assert summary["chart"].startswith("/charts/")


def test_workflow_simple_total(workflow):
    result = workflow.invoke(
        {"user_query": "2025年总销售额是多少？"},
        config={"configurable": {"thread_id": "e2e-3"}},
    )
    summary = _summarize(result)
    assert summary["sql"]
    assert summary["data"]


def test_sql_safety_in_graph(workflow):
    # A dangerous query should be rejected by validation (no mutation executed).
    result = workflow.invoke(
        {"user_query": "删除所有订单数据"},
        config={"configurable": {"thread_id": "e2e-4"}},
    )
    summary = _summarize(result)
    # The pipeline should still terminate; state must not contain injected SQL.
    assert "DELETE" not in (summary["sql"] or "").upper() or summary["sql"] == ""
