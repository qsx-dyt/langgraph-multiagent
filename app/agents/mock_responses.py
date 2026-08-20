"""Deterministic mock LLM responder.

When ``LLM_PROVIDER=mock`` (the default), the whole multi-agent workflow runs
offline with no API key. Each node asks the model a targeted question and the
responder inspects the last message + the current workflow state to return a
plausible, rule-based answer.

Design rule: the *real* SQL generation / analysis still run through the actual
tools. The mock only replaces the free-form LLM reasoning step so the pipeline
is deterministic and testable without network access.
"""
from __future__ import annotations

import json
from typing import Any

from app.tools.analysis_tools import calculate_growth

# Markers we embed in prompts so the responder can route precisely.
TAG_SUPERVISOR = "[ROUTER]"
TAG_SQL = "[SQLGEN]"
TAG_ANALYSIS = "[ANALYSIS]"
TAG_CHART = "[CHART]"
TAG_REVIEW = "[REVIEW]"
TAG_FINAL = "[FINAL]"


def _last_text(messages) -> str:
    for m in reversed(messages):
        content = getattr(m, "content", None)
        if content:
            return str(content)
    return ""


class MockResponder:
    """Stateless responder; all routing state is kept in the LangGraph state."""

    def __call__(self, messages, **kwargs) -> str:
        text = _last_text(messages)
        if TAG_SQL in text:
            return self._sql(text)
        if TAG_SUPERVISOR in text:
            return self._supervisor(text)
        if TAG_ANALYSIS in text:
            return self._analysis(text)
        if TAG_CHART in text:
            return self._chart(text)
        if TAG_REVIEW in text:
            return self._review(text)
        if TAG_FINAL in text:
            return self._final(text)
        return "ok"

    # -- supervisor -------------------------------------------------------
    def _supervisor(self, text: str) -> str:
        q = text.split("QUESTION:", 1)[-1].strip().lower()
        has_chart = any(k in q for k in ["图表", "图", "chart", "画", "可视化", "plot", "trend", "趋势"])
        has_trend = any(k in q for k in ["趋势", "月份", "每月", "时间", "环比", "同比", "下降", "增长", "trend", "month"])
        has_reason = any(k in q for k in ["原因", "为什么", "why"])
        has_compare = any(k in q for k in ["占比", "比例", "比较", "排名", "top", "最高", "最多", "分布"])
        steps: list[str] = ["sql"]
        if has_trend or has_compare or has_reason or "销售额" in q:
            steps.append("analysis")
        if has_chart or has_trend:
            steps.append("chart")
        return json.dumps({"steps": list(dict.fromkeys(steps))}, ensure_ascii=False)

    # -- sql --------------------------------------------------------------
    def _sql(self, text: str) -> str:
        question = text.split("QUESTION:", 1)[-1].split("\nSTATE:", 1)[0].strip()
        error_hint = (
            text.split("ERROR_HINT:", 1)[-1].split("\nSTATE:", 1)[0].strip()
            if "ERROR_HINT:" in text else ""
        )
        if error_hint:
            return self._fix_sql(question, error_hint)
        return self._generate_sql(question)

    def _generate_sql(self, q: str) -> str:
        ql = q.lower()
        year = "2025" if "2025" in q else ("2024" if "2024" in q else "")
        if "占比" in q or "比例" in q:
            return self._sql_share(q, year)
        if "产品" in q and ("最高" in q or "top" in ql or "排行" in q):
            return self._sql_top_products(q, year)
        if "客户" in q and ("最高" in q or "top" in ql):
            return self._sql_top_customers(year)
        if "月份" in q or "每月" in q or "趋势" in q or "时间" in q or "trend" in ql:
            return self._sql_monthly(q, year)
        if "地区" in q or "区域" in q or "region" in ql:
            return self._sql_region(q, year)
        return self._sql_total(q, year)

    def _fix_sql(self, q: str, error_hint: str) -> str:
        year = "2025" if "2025" in q else ("2024" if "2024" in q else "")
        base = f"WHERE substr(o.order_date,1,4) = '{year}' AND o.status = 'completed'" if year else "WHERE o.status = 'completed'"
        return (
            f"SELECT substr(o.order_date, 1, 7) AS month, ROUND(SUM(o.amount), 2) AS total_sales\n"
            f"FROM orders o\n{base}\nGROUP BY month\nORDER BY month;"
        )

    def _sql_total(self, q: str, year: str) -> str:
        where = f"WHERE substr(o.order_date,1,4) = '{year}' AND o.status = 'completed'" if year else "WHERE o.status = 'completed'"
        return (
            f"SELECT ROUND(SUM(o.amount), 2) AS total_sales, COUNT(*) AS order_count\n"
            f"FROM orders o\n{where};"
        )

    def _sql_region(self, q: str, year: str) -> str:
        where = f"WHERE substr(o.order_date,1,4) = '{year}' AND o.status = 'completed'" if year else "WHERE o.status = 'completed'"
        return (
            f"SELECT c.region, ROUND(SUM(o.amount), 2) AS total_sales\n"
            f"FROM orders o JOIN customers c ON o.customer_id = c.id\n{where}\n"
            f"GROUP BY c.region\nORDER BY total_sales DESC;"
        )

    def _sql_monthly(self, q: str, year: str) -> str:
        where = f"WHERE substr(o.order_date,1,4) = '{year}' AND o.status = 'completed'" if year else "WHERE o.status = 'completed'"
        return (
            f"SELECT substr(o.order_date, 1, 7) AS month, ROUND(SUM(o.amount), 2) AS total_sales\n"
            f"FROM orders o\n{where}\nGROUP BY month\nORDER BY month;"
        )

    def _sql_top_products(self, q: str, year: str) -> str:
        return (
            f"SELECT p.name AS product, ROUND(SUM(oi.quantity * oi.price), 2) AS sales\n"
            f"FROM order_items oi\nJOIN orders o ON oi.order_id = o.id\nJOIN products p ON oi.product_id = p.id\n"
            f"WHERE substr(o.order_date,1,4) = '2025' AND o.status = 'completed'\n"
            f"GROUP BY p.name\nORDER BY sales DESC\nLIMIT 10;"
        )

    def _sql_top_customers(self, year: str) -> str:
        return (
            f"SELECT c.name AS customer, ROUND(SUM(o.amount), 2) AS total_spent\n"
            f"FROM orders o JOIN customers c ON o.customer_id = c.id\n"
            f"WHERE substr(o.order_date,1,4) = '2025' AND o.status = 'completed'\n"
            f"GROUP BY c.name\nORDER BY total_spent DESC\nLIMIT 10;"
        )

    def _sql_share(self, q: str, year: str) -> str:
        if "产品" in q or "类别" in q or "category" in q.lower():
            return (
                f"SELECT p.category AS category, ROUND(SUM(oi.quantity * oi.price), 2) AS sales\n"
                f"FROM order_items oi\nJOIN orders o ON oi.order_id = o.id\nJOIN products p ON oi.product_id = p.id\n"
                f"WHERE substr(o.order_date,1,4) = '2025' AND o.status = 'completed'\n"
                f"GROUP BY p.category\nORDER BY sales DESC;"
            )
        return self._sql_region(q, year)

    # -- analysis ---------------------------------------------------------
    def _analysis(self, text: str) -> str:
        state = text.split("STATE:", 1)[-1] if "\nSTATE:" in text else ""
        rows = self._rows_from_state(state)
        if not rows:
            return json.dumps({
                "summary": "暂无可分析的数据。",
                "key_findings": [],
                "anomalies": [],
            }, ensure_ascii=False)
        if "month" in rows[0]:
            return self._analysis_ts(rows)
        if "region" in rows[0]:
            return self._analysis_group(rows, "region")
        if "category" in rows[0]:
            return self._analysis_group(rows, "category")
        return json.dumps({
            "summary": "数据已完成统计汇总。",
            "key_findings": [],
            "anomalies": [],
        }, ensure_ascii=False)

    def _analysis_ts(self, rows: list[dict]) -> str:
        growth = calculate_growth(rows, value_key="total_sales", period_key="month")
        valid = [r for r in growth if r.get("growth") is not None]
        findings = []
        if valid:
            worst = min(valid, key=lambda r: r["growth"])
            findings.append(
                f"{worst['month']} 销售额环比下降 {abs(worst['growth']) * 100:.1f}%，为观察期内下降最明显的月份。"
            )
        anomalies = [r for r in growth if r.get("growth") is not None and r["growth"] < -0.10]
        anomalies_text = [f"{r['month']}（环比{r['growth'] * 100:.1f}%）" for r in anomalies]
        return json.dumps({
            "summary": "按月趋势统计完成。",
            "key_findings": findings,
            "anomalies": anomalies_text,
        }, ensure_ascii=False)

    def _analysis_group(self, rows: list[dict], key: str) -> str:
        def _val(r):
            return float(r.get("total_sales") or r.get("sales") or 0)

        biggest = max(rows, key=_val)
        return json.dumps({
            "summary": f"按{key}维度汇总完成，{biggest[key]}销售额最高。",
            "key_findings": [f"{biggest[key]}销售额最高（{_val(biggest) / 1e4:.1f}万）。"],
            "anomalies": [],
        }, ensure_ascii=False)

    # -- chart ------------------------------------------------------------
    def _chart(self, text: str) -> str:
        state = text.split("STATE:", 1)[-1] if "\nSTATE:" in text else ""
        rows = self._rows_from_state(state)
        if not rows:
            return json.dumps({"chart_type": "bar", "x_key": "label", "y_key": "value"}, ensure_ascii=False)
        keys = list(rows[0].keys())
        if "month" in keys:
            return json.dumps({"chart_type": "line", "x_key": "month", "y_key": "total_sales"}, ensure_ascii=False)
        return json.dumps(
            {"chart_type": "bar", "x_key": keys[0], "y_key": "total_sales" if "total_sales" in keys else keys[-1]},
            ensure_ascii=False,
        )

    # -- reviewer ---------------------------------------------------------
    def _review(self, text: str) -> str:
        # Passes when the planned work actually produced output:
        # - a query-only task needs non-empty SQL results
        # - a task that plans analysis additionally needs a real conclusion
        state = text.split("STATE:", 1)[-1] if "\nSTATE:" in text else ""
        rows = self._rows_from_state(state)
        has_analysis_planned = "PLANNED_HAS_ANALYSIS: True" in text
        analysis_val = ""
        for line in state.splitlines():
            if line.startswith("analysis_summary:"):
                analysis_val = line.split(":", 1)[1].strip()
        if not rows:
            return json.dumps({"passed": False, "reason": "查询结果为空，需要重新生成 SQL。", "retry_agent": "sql"}, ensure_ascii=False)
        if has_analysis_planned and analysis_val in ("", "None"):
            return json.dumps({"passed": False, "reason": "缺少分析结论，需要重新分析。", "retry_agent": "analysis"}, ensure_ascii=False)
        return json.dumps({"passed": True, "reason": "校验通过：SQL、分析结论与数据一致。", "retry_agent": None}, ensure_ascii=False)

    # -- final ------------------------------------------------------------
    def _final(self, text: str) -> str:
        state = text.split("STATE:", 1)[-1] if "\nSTATE:" in text else ""
        summary = ""
        for line in state.splitlines():
            if line.startswith("analysis_summary:"):
                summary = line.split(":", 1)[1].strip()
        rows = self._rows_from_state(state)
        parts = []
        if summary:
            parts.append(summary)
        elif rows:
            first = rows[0]
            parts.append("查询结果：" + "，".join(f"{k}={v}" for k, v in first.items()))
        if not parts:
            parts.append("分析完成。")
        return "；".join(parts)

    # -- helpers ----------------------------------------------------------
    def _rows_from_state(self, state: str) -> list[dict]:
        marker = "SQL_ROWS_START"
        if marker not in state:
            return []
        body = state.split(marker, 1)[1].split("SQL_ROWS_END", 1)[0]
        try:
            data = json.loads(body)
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
        except Exception:
            return []
        return []
