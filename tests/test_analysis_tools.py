"""Tests for deterministic analysis and chart helpers."""
from __future__ import annotations

import pytest

from app.tools.analysis_tools import calculate_growth, calculate_ratio, detect_anomaly, format_number, top_k
from app.tools.chart_tools import plot_bar, plot_line


def test_calculate_growth():
    data = [
        {"month": "2025-01", "total_sales": 100},
        {"month": "2025-02", "total_sales": 90},
        {"month": "2025-03", "total_sales": 99},
    ]
    out = calculate_growth(data, value_key="total_sales", period_key="month")
    assert out[0]["growth"] is None
    assert out[1]["growth"] == pytest.approx(-0.1)
    assert out[2]["growth"] == pytest.approx(0.1)


def test_calculate_ratio():
    data = [{"region": "华东", "total_sales": 100}, {"region": "华南", "total_sales": 300}]
    out = calculate_ratio(data, value_key="total_sales", group_key="region")
    assert out[0]["ratio"] == pytest.approx(0.25)
    assert out[1]["ratio"] == pytest.approx(0.75)


def test_top_k():
    data = [{"k": i, "v": i * 2} for i in range(5)]
    out = top_k(data, value_key="v", k=2)
    assert [r["k"] for r in out] == [4, 3]


def test_detect_anomaly():
    data = [{"m": i, "v": 100.0} for i in range(10)]
    data[5]["v"] = 50.0
    out = detect_anomaly(data, value_key="v", threshold=0.2)
    flagged = [r["m"] for r in out if r["anomaly"]]
    assert flagged == [5]


def test_format_number():
    assert format_number(28310000) == "2,831.0万"
    assert format_number(123) == "123"
    assert format_number(None) == "N/A"


def test_chart_tools_render(tmp_path, monkeypatch):
    import app.tools.chart_tools as ct

    monkeypatch.setattr(ct, "CHARTS_DIR", tmp_path)
    url = plot_line([{"month": "2025-01", "v": 1}, {"month": "2025-02", "v": 2}], "month", "v")
    assert url.startswith("/charts/")
    assert (tmp_path / "line.png").exists()

    url2 = plot_bar([{"r": "华东", "v": 10}], "r", "v")
    assert (tmp_path / "bar.png").exists()
