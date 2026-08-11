from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from math import isfinite
from typing import Any

import portion as P

from .ast import Expression, _coerce_expression
from .semantics import NaturalSignal, SignalValuation, Valuation, denote


@dataclass(frozen=True, slots=True)
class TimelineRow:
    """One exact truth-set row in a formula timeline."""

    label: str
    interval: P.Interval
    kind: str = "valuation"


@dataclass(frozen=True, slots=True)
class Timeline:
    """Terminal and notebook representation of a formula and its valuation."""

    expression: Expression | str
    universe: P.Interval
    rows: tuple[TimelineRow, ...]
    width: int = 900

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "expression", _coerce_expression(self.expression, "expression")
        )

    def __str__(self) -> str:
        label_width = max(len(row.label) for row in self.rows)
        heading = f"{'row':<{label_width}}  holds on"
        separator = f"{'-' * label_width}  {'-' * 8}"
        values = [
            f"{row.label:<{label_width}}  {row.interval}"
            for row in self.rows
        ]
        return "\n".join((heading, separator, *values))

    def _repr_pretty_(self, printer: Any, cycle: bool) -> None:
        printer.text("..." if cycle else str(self))

    def _repr_html_(self) -> str:
        table = _html_table(self.rows)
        chart = _svg_chart(self.rows, self.universe, self.width)
        note = "" if chart else (
            '<p style="color:#666;margin:.4rem 0 0">'
            "Graphical rendering requires a finite numeric universe; "
            "the exact interval table remains valid.</p>"
        )
        return (
            '<div class="interval-logic-timeline" '
            'style="font-family:system-ui,sans-serif;max-width:100%;overflow-x:auto">'
            f"{chart}{table}{note}</div>"
        )


def timeline(
    expression: Expression | str,
    valuation: Valuation,
    universe: P.Interval,
    *,
    signals: SignalValuation | None = None,
    formula_label: str | None = None,
    width: int = 900,
) -> Timeline:
    """Build an exact timeline for atom, signal, and formula denotations."""

    expression = _coerce_expression(expression, "expression")
    if not isinstance(universe, P.Interval):
        raise TypeError("universe must be a portion.Interval")
    if type(width) is not int or width < 320:
        raise ValueError("width must be an integer of at least 320 pixels")

    if signals is None:
        signals = {}
    if not isinstance(signals, Mapping):
        raise TypeError("signals must be a mapping")

    truth = denote(expression, valuation, universe, signals=signals)
    rows = [TimelineRow("Universe", universe, "universe")]
    for name in sorted(valuation):
        value = valuation[name]
        if not isinstance(value, P.Interval):
            raise TypeError(f"valuation for atom {name!r} must be a portion.Interval")
        rows.append(TimelineRow(name, value & universe))
    for name in sorted(signals):
        signal = signals[name]
        if not isinstance(signal, NaturalSignal):
            raise TypeError(
                f"valuation for signal {name!r} must be a NaturalSignal"
            )
        for value, interval in signal.parts(universe):
            rows.append(TimelineRow(f"{name} = {value}", interval, "signal"))
    label = formula_label if formula_label is not None else f"φ = {expression}"
    if not isinstance(label, str) or not label:
        raise ValueError("formula_label must be a non-empty string")
    rows.append(TimelineRow(label, truth, "formula"))
    return Timeline(expression, universe, tuple(rows), width)


def _html_table(rows: tuple[TimelineRow, ...]) -> str:
    body = []
    for row in rows:
        color = _row_color(row.kind)
        body.append(
            "<tr>"
            f'<td style="padding:.25rem .5rem;white-space:nowrap">'
            f'<span style="display:inline-block;width:.7rem;height:.7rem;'
            f'background:{color};border-radius:2px;margin-right:.45rem"></span>'
            f"{escape(row.label)}</td>"
            f'<td style="padding:.25rem .5rem;font-family:ui-monospace,monospace">'
            f"{escape(str(row.interval))}</td>"
            "</tr>"
        )
    return (
        '<table style="border-collapse:collapse;margin:.5rem 0">'
        '<thead><tr style="border-bottom:1px solid #aaa">'
        '<th style="text-align:left;padding:.25rem .5rem">Row</th>'
        '<th style="text-align:left;padding:.25rem .5rem">Holds on</th>'
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _svg_chart(
    rows: tuple[TimelineRow, ...], universe: P.Interval, width: int
) -> str:
    domain = _numeric_domain(universe)
    if domain is None:
        return ""
    lower, upper = domain
    label_width = min(260, max(110, max(len(row.label) for row in rows) * 7 + 16))
    right_margin = 20
    plot_width = width - label_width - right_margin
    row_height = 32
    top = 24
    axis_height = 28
    height = top + len(rows) * row_height + axis_height

    def x(value: Any) -> float:
        return label_width + (float(value) - lower) / (upper - lower) * plot_width

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        'style="max-width:100%;height:auto;background:transparent">'
    ]

    for index, row in enumerate(rows):
        y = top + index * row_height + row_height / 2
        parts.append(
            f'<text x="{label_width - 10}" y="{y + 4}" text-anchor="end" '
            f'font-size="12" fill="currentColor">{escape(row.label)}</text>'
        )
        parts.append(
            f'<line x1="{label_width}" x2="{label_width + plot_width}" '
            f'y1="{y}" y2="{y}" stroke="#c8c8c8" stroke-width="1"/>'
        )
        color = _row_color(row.kind)
        for atom in row.interval & universe:
            start, end = x(atom.lower), x(atom.upper)
            if end > start:
                parts.append(
                    f'<line x1="{start:.2f}" x2="{end:.2f}" y1="{y}" y2="{y}" '
                    f'stroke="{color}" stroke-width="12" stroke-linecap="butt"/>'
                )
            _endpoint(parts, start, y, atom.left.name == "CLOSED", color)
            _endpoint(parts, end, y, atom.right.name == "CLOSED", color)

    axis_y = top + len(rows) * row_height
    parts.append(
        f'<line x1="{label_width}" x2="{label_width + plot_width}" '
        f'y1="{axis_y}" y2="{axis_y}" stroke="currentColor" stroke-width="1"/>'
    )
    for index in range(5):
        ratio = index / 4
        value = lower + (upper - lower) * ratio
        tick_x = label_width + plot_width * ratio
        parts.append(
            f'<line x1="{tick_x:.2f}" x2="{tick_x:.2f}" y1="{axis_y}" '
            f'y2="{axis_y + 5}" stroke="currentColor"/>'
            f'<text x="{tick_x:.2f}" y="{axis_y + 19}" text-anchor="middle" '
            f'font-size="11" fill="currentColor">{escape(_number(value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _endpoint(
    parts: list[str], x: float, y: float, closed: bool, color: str
) -> None:
    fill = color if closed else "white"
    parts.append(
        f'<circle cx="{x:.2f}" cy="{y}" r="4" fill="{fill}" '
        f'stroke="{color}" stroke-width="2"/>'
    )


def _numeric_domain(universe: P.Interval) -> tuple[float, float] | None:
    if universe.empty:
        return None
    atoms = list(universe)
    try:
        lower = float(atoms[0].lower)
        upper = float(atoms[-1].upper)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(lower) or not isfinite(upper) or lower >= upper:
        return None
    return lower, upper


def _row_color(kind: str) -> str:
    return {
        "universe": "#8a8f98",
        "formula": "#2e9d57",
        "signal": "#d9822b",
    }.get(kind, "#3478c8")


def _number(value: float) -> str:
    return f"{value:g}"
