"""Chart generation tools (deterministic plotting, LLM decides the type).

Uses matplotlib Agg backend and saves PNGs under the charts directory.
"""
from __future__ import annotations

import re
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.config import CHARTS_DIR, CHART_FONT

# Default CJK font handling: try common fonts, otherwise fall back to ASCII.
_KNOWN_CJK_FONTS = ["SimHei", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei"]
_cjk = None

try:
    from matplotlib import font_manager

    _available = {f.name for f in font_manager.fontManager.ttflist}
    _cjk = next((f for f in _KNOWN_CJK_FONTS if f in _available), None)
    if _cjk:
        plt.rcParams["font.sans-serif"] = [_cjk, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
except Exception:  # noqa: BLE001 - non-fatal
    _cjk = None

if CHART_FONT:
    plt.rcParams["font.sans-serif"] = [CHART_FONT, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_") or "chart"


def _safe_label(value: Any) -> str:
    s = str(value)
    # Non-ASCII labels may render as boxes if no CJK font is present.
    return s if (_cjk or CHART_FONT) else (s.encode("ascii", "replace").decode() or "?")


def _new_figure(name: str) -> tuple[Any, str]:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / f"{_sanitize_filename(name)}.png"
    fig, ax = plt.subplots(figsize=(9, 5))
    return fig, str(path)


def _save(fig, path: str, name: str) -> str:
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f"/charts/{_sanitize_filename(name)}.png"


def _set_labels(ax, title: str):
    ax.set_title(_safe_label(title) or "", pad=12)
    ax.grid(True, alpha=0.3)


def plot_line(data: list[dict[str, Any]], x_key: str, y_key: str, title: str = "") -> str:
    """Render a line chart and return the web URL of the saved PNG."""
    xs = [_safe_label(r.get(x_key)) for r in data]
    ys = [float(r.get(y_key) or 0) for r in data]
    fig, path = _new_figure("line")
    ax = fig.axes[0]
    ax.plot(range(len(xs)), ys, marker="o", linewidth=2, color="#2f6fed")
    ax.set_xticks(range(len(xs)), xs, rotation=45, ha="right")
    _set_labels(ax, title or "Trend")
    return _save(fig, path, "line")


def plot_bar(data: list[dict[str, Any]], x_key: str, y_key: str, title: str = "") -> str:
    """Render a bar chart and return the web URL of the saved PNG."""
    xs = [_safe_label(r.get(x_key)) for r in data]
    ys = [float(r.get(y_key) or 0) for r in data]
    fig, path = _new_figure("bar")
    ax = fig.axes[0]
    ax.bar(range(len(xs)), ys, color="#2f6fed")
    ax.set_xticks(range(len(xs)), xs, rotation=45, ha="right")
    _set_labels(ax, title or "Comparison")
    return _save(fig, path, "bar")


def plot_pie(data: list[dict[str, Any]], label_key: str, value_key: str, title: str = "") -> str:
    """Render a pie chart and return the web URL of the saved PNG."""
    labels = [_safe_label(r.get(label_key)) for r in data]
    values = [float(r.get(value_key) or 0) for r in data]
    fig, path = _new_figure("pie")
    ax = fig.axes[0]
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90, counterclock=False)
    ax.set_title(_safe_label(title) or "Share", pad=12)
    ax.axis("equal")
    return _save(fig, path, "pie")


def plot_scatter(data: list[dict[str, Any]], x_key: str, y_key: str, title: str = "") -> str:
    """Render a scatter chart and return the web URL of the saved PNG."""
    xs = [float(r.get(x_key) or 0) for r in data]
    ys = [float(r.get(y_key) or 0) for r in data]
    fig, path = _new_figure("scatter")
    ax = fig.axes[0]
    ax.scatter(xs, ys, color="#2f6fed", s=40, alpha=0.7)
    _set_labels(ax, title or "Scatter")
    return _save(fig, path, "scatter")
