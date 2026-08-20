"""CLI demo: run the full multi-agent workflow entirely in the terminal.

No frontend / browser needed. Every demo question prints:
  1. live agent execution trace (Supervisor -> SQL -> Analysis -> Chart -> Reviewer -> Final)
  2. generated SQL
  3. result data as a simple text table
  4. local chart file path (if a chart was generated)
  5. analysis summary + key findings + anomalies
  6. reviewer verdict and final answer

Human-in-the-loop: if a query triggers a sensitive column, the workflow pauses
and asks for approval right in the terminal (``--interactive``).

Usage:
    python -m scripts.demo                 # all questions
    python -m scripts.demo 3               # only question #3
    python -m scripts.demo 10 --interactive
"""
from __future__ import annotations

import argparse
from pathlib import Path

from langgraph.types import Command, GraphInterrupt

from app.database.connection import ensure_database
from app.graph.workflow import _summarize, build_workflow

DEMO_QUESTIONS = [
    "2025年总销售额是多少？",
    "2025年各地区销售额分别是多少？",
    "2025年每个月销售额趋势如何？",
    "销售额最高的10个产品是什么？",
    "哪些客户购买金额最高？",
    "2025年哪个月销售额下降最多？",
    "各产品类别销售额占比是多少？",
    "找出2025年销售额异常下降的月份。",
    "分析不同地区销售额并画图。",
    "分析2025年销售额下降的原因，并给出图表。",
]

_NODE_LABELS = {
    "supervisor": "Supervisor Agent",
    "sql_agent": "SQL Agent",
    "analysis_agent": "Analysis Agent",
    "chart_agent": "Chart Agent",
    "reviewer": "Reviewer Agent",
    "final": "Final Agent",
}


def _print_header(text: str, char: str = "=", width: int = 72) -> None:
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("  (无数据)")
        return
    headers = list(rows[0].keys())
    col_w = {h: max(len(h), max((len(str(r.get(h, ""))) for r in rows), default=0)) for h in headers}
    line = " | ".join(h.ljust(col_w[h]) for h in headers)
    print(f"  {line}")
    print(f"  {'-' * len(line)}")
    for r in rows[:20]:
        print("  " + " | ".join(str(r.get(h, "")).ljust(col_w[h]) for h in headers))
    if len(rows) > 20:
        print(f"  ... 共 {len(rows)} 行，仅显示前 20 行")


def _print_report(summary: dict) -> None:
    print("\n[SQL]")
    print(f"  {summary.get('sql', '')}")

    print("\n[数据]")
    _print_table(summary.get("data", []))

    if summary.get("chart"):
        print(f"\n[图表] {summary['chart']}")

    print("\n[分析结论]")
    print(f"  摘要: {summary['analysis']['summary']}")
    for f in summary["analysis"]["key_findings"]:
        print(f"  - {f}")
    for a in summary["analysis"]["anomalies"]:
        print(f"  ! 异常: {a}")

    print("\n[最终报告]")
    print(f"  {summary['answer']}")

    verdict = summary["review"]
    print(f"\n[校验] {'通过' if verdict['passed'] else '未通过'}: {verdict['feedback']}")


def run_question(graph, question: str, thread_id: str, interactive: bool) -> dict:
    """Run one question, printing agent events live and handling interrupts."""
    config = {"configurable": {"thread_id": thread_id}}
    final_state = {}

    def stream_once(inputs):
        for event in graph.stream(inputs, config=config, stream_mode="updates"):
            for node_name, payload in event.items():
                label = _NODE_LABELS.get(node_name, node_name)
                if node_name == "supervisor":
                    print(f"  [{label}] 任务拆解 -> {payload.get('task_type', '')}")
                elif node_name == "sql_agent":
                    print(f"  [{label}] 生成 SQL: {payload.get('sql_query', '')[:100]}")
                    if payload.get("sql_error"):
                        print(f"  [{label}] 执行异常: {payload['sql_error'][:120]}")
                elif node_name == "analysis_agent":
                    print(f"  [{label}] 结论: {payload.get('analysis_summary', '')[:100]}")
                elif node_name == "chart_agent":
                    print(f"  [{label}] 图表: {payload.get('chart_path', '')}")
                elif node_name == "reviewer":
                    passed = payload.get("review_passed")
                    print(f"  [{label}] {'通过' if passed else '未通过: ' + payload.get('review_feedback', '')}")
                elif node_name == "final":
                    print(f"  [{label}] 报告生成完成")

    try:
        stream_once({"user_query": question})
    except GraphInterrupt:  # interrupt() pauses streaming for human approval
        state = graph.get_state(config)
        if state and state.values.get("pending_human_confirmation"):
            print("\n  [Human-in-the-loop] 检测到敏感 SQL，需要人工确认：")
            print(f"    SQL: {state.values.get('sql_query', '')}")
            if interactive:
                answer = input("    是否批准执行？[y/N]: ").strip().lower()
                approved = answer in ("y", "yes")
            else:
                approved = False
                print("    (非交互模式，默认拒绝)")
            graph.invoke(Command(resume={"approved": approved}), config=config)
            final_state = graph.get_state(config).values or {}
        else:
            raise
    else:
        final_state = graph.get_state(config).values or {}

    return _summarize(final_state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Agent SQL Analyst - CLI demo")
    parser.add_argument("index", nargs="?", type=int, help="run only question #N (1-based)")
    parser.add_argument("--interactive", action="store_true", help="allow human-in-the-loop approval input")
    args = parser.parse_args()

    ensure_database()
    graph = build_workflow()

    indices = [args.index] if args.index else range(1, len(DEMO_QUESTIONS) + 1)
    for i in indices:
        q = DEMO_QUESTIONS[i - 1]
        _print_header(f"[{i}] 问题: {q}")
        try:
            summary = run_question(graph, q, thread_id=f"demo-{i}", interactive=args.interactive)
            _print_report(summary)
        except Exception as exc:  # noqa: BLE001
            print(f"执行失败: {exc}")

    print("\n演示结束。图表文件保存在 charts/ 目录，数据库在 data/ 目录。")


if __name__ == "__main__":
    main()
