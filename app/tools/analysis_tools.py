"""Deterministic analysis helpers used by the Analysis Agent.

These are plain, testable functions - the LLM decides *what* to compute,
the code performs the actual computation (LLM Decision + Deterministic Tool).
"""
from __future__ import annotations

import math
from collections import OrderedDict
from typing import Any


def to_records(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce rows (possibly from stringified tool output) into dicts."""
    if not data:
        return []
    if isinstance(data[0], dict):
        return data
    return [{"value": row} for row in data]


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def calculate_growth(data: list[dict[str, Any]], value_key: str = "value",
                     period_key: str | None = None, group_key: str | None = None) -> list[dict[str, Any]]:
    """Compute period-over-period growth for each group.

    - no group_key: single series over periods
    - group_key given: per-group series, growth computed within each group
    Returns records with keys ``<period_key>``, ``<group_key>`` (optional),
    ``value``, ``prev_value``, ``growth`` (fraction, None when no previous).
    """
    records = to_records(data)
    out: list[dict[str, Any]] = []
    groups: dict[Any, list[dict[str, Any]]] = OrderedDict()
    for r in records:
        g = r.get(group_key, None) if group_key else "__all__"
        groups.setdefault(g, []).append(r)

    for g, series in groups.items():
        series = sorted(series, key=lambda r: str(r.get(period_key, "")) if period_key else "")
        prev: float | None = None
        for r in series:
            cur = _num(r.get(value_key))
            rec = dict(r)
            rec["prev_value"] = prev
            rec["growth"] = None
            if cur is not None and prev is not None and prev != 0:
                rec["growth"] = (cur - prev) / prev
            out.append(rec)
            if cur is not None:
                prev = cur
    return out


def calculate_ratio(data: list[dict[str, Any]], value_key: str = "value",
                    group_key: str | None = None) -> list[dict[str, Any]]:
    """Share (%) of each record within its group (or overall)."""
    records = to_records(data)
    groups: dict[Any, list[dict[str, Any]]] = OrderedDict()
    for r in records:
        g = r.get(group_key, None) if group_key else "__all__"
        groups.setdefault(g, []).append(r)
    out = []
    for g, series in groups.items():
        total = sum(_num(r.get(value_key)) or 0 for r in series)
        for r in series:
            rec = dict(r)
            cur = _num(r.get(value_key))
            rec["ratio"] = (cur / total) if (total and cur is not None) else 0.0
            out.append(rec)
    return out


def detect_anomaly(data: list[dict[str, Any]], value_key: str = "value",
                   threshold: float = 0.15) -> list[dict[str, Any]]:
    """Flag records whose value deviates from the series mean by > threshold.

    Returns records annotated with ``mean``, ``deviation`` and ``anomaly``.
    """
    records = to_records(data)
    if not records:
        return []
    values = [_num(r.get(value_key)) for r in records]
    values = [v for v in values if v is not None]
    if not values:
        return []
    mean = sum(values) / len(values)
    out = []
    for r in records:
        cur = _num(r.get(value_key))
        dev = (cur - mean) / mean if (mean and cur is not None) else 0.0
        out.append({**r, "mean": round(mean, 4), "deviation": round(dev, 4), "anomaly": abs(dev) > threshold})
    return out


def top_k(data: list[dict[str, Any]], value_key: str = "value", k: int = 10,
          ascending: bool = False) -> list[dict[str, Any]]:
    """Return the top-k records by value (default: largest)."""
    records = to_records(data)
    return sorted(records, key=lambda r: _num(r.get(value_key)) or 0.0, reverse=not ascending)[:k]


def format_number(value: Any) -> str:
    """Human-friendly number formatting: 28310000 -> '2,831万'."""
    num = _num(value)
    if num is None:
        return "N/A"
    if abs(num) >= 1e8:
        return f"{num / 1e8:,.2f}亿"
    if abs(num) >= 1e4:
        return f"{num / 1e4:,.1f}万"
    if num == int(num):
        return f"{int(num):,}"
    return f"{num:,.2f}"


def summarize_series(data: list[dict[str, Any]], value_key: str = "value") -> dict[str, Any]:
    """Basic stats: min/max period, total, mean, growth of first vs last."""
    records = to_records(data)
    values = [_num(r.get(value_key)) for r in records]
    values = [v for v in values if v is not None]
    if not values:
        return {"count": 0}
    first, last = values[0], values[-1]
    return {
        "count": len(values),
        "total": sum(values),
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
        "first": first,
        "last": last,
        "overall_growth": (last - first) / first if first else None,
    }


def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct(x: float | None, digits: int = 1) -> str:
    return "N/A" if x is None else f"{x * 100:.{digits}f}%"
