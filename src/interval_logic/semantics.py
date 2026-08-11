from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import portion as P

from .ast import (
    And,
    Atom,
    Bool,
    Equal,
    Exists,
    Expression,
    ForAll,
    Guard,
    Natural,
    Not,
    Or,
    Restrict,
    Signal,
    Term,
    _coerce_expression,
)
from .transform import lower_derived

Valuation = Mapping[str, P.Interval]


@dataclass(frozen=True, slots=True, init=False)
class NaturalSignal:
    """An exact piecewise-constant natural-number signal."""

    regions: tuple[tuple[int, P.Interval], ...]
    default: int | None

    def __init__(
        self,
        regions: Mapping[int, P.Interval],
        *,
        default: int | None = None,
    ) -> None:
        if not isinstance(regions, Mapping):
            raise TypeError("NaturalSignal regions must be a mapping")
        if default is not None:
            _require_natural(default, "NaturalSignal default")

        values: list[tuple[int, P.Interval]] = []
        covered = P.empty()
        for value, interval in regions.items():
            _require_natural(value, "NaturalSignal region value")
            if not isinstance(interval, P.Interval):
                raise TypeError("NaturalSignal regions must be portion.Interval values")
            if not (covered & interval).empty:
                raise ValueError("NaturalSignal regions must be pairwise disjoint")
            covered |= interval
            values.append((value, interval))

        object.__setattr__(self, "regions", tuple(sorted(values)))
        object.__setattr__(self, "default", default)

    def parts(self, universe: P.Interval) -> tuple[tuple[int, P.Interval], ...]:
        """Return the signal's value regions clipped to a universe."""

        if not isinstance(universe, P.Interval):
            raise TypeError("universe must be a portion.Interval")
        result: dict[int, P.Interval] = {}
        covered = P.empty()
        for value, interval in self.regions:
            effective = interval & universe
            if not effective.empty:
                result[value] = effective
                covered |= effective

        uncovered = universe - covered
        if not uncovered.empty:
            if self.default is None:
                raise ValueError(
                    f"NaturalSignal does not cover evaluation universe: {uncovered}"
                )
            result[self.default] = result.get(self.default, P.empty()) | uncovered
        return tuple(sorted(result.items()))


SignalValuation = Mapping[str, NaturalSignal]


def denote(
    expression: Expression | str,
    valuation: Valuation,
    universe: P.Interval,
    *,
    signals: SignalValuation | None = None,
) -> P.Interval:
    """Return the absolute times where an expression is true."""

    expression = _coerce_expression(expression, "expression")
    if not isinstance(universe, P.Interval):
        raise TypeError("universe must be a portion.Interval")
    if not isinstance(valuation, Mapping):
        raise TypeError("valuation must be a mapping")
    if signals is None:
        signals = {}
    if not isinstance(signals, Mapping):
        raise TypeError("signals must be a mapping")
    return _denote(lower_derived(expression), valuation, signals, universe)


def holds(
    expression: Expression | str,
    valuation: Valuation,
    at: Any,
    universe: P.Interval,
    *,
    signals: SignalValuation | None = None,
) -> bool:
    """Return whether an expression is true at one absolute time."""

    return at in denote(expression, valuation, universe, signals=signals)


def _denote(
    expression: Expression,
    valuation: Valuation,
    signals: SignalValuation,
    universe: P.Interval,
) -> P.Interval:
    match expression:
        case Bool(value=True):
            return universe
        case Bool(value=False):
            return P.empty()
        case Atom(name=name):
            try:
                value = valuation[name]
            except KeyError:
                raise KeyError(f"missing valuation for atom {name!r}") from None
            if not isinstance(value, P.Interval):
                raise TypeError(f"valuation for atom {name!r} must be a portion.Interval")
            return value & universe
        case Equal(left=left, right=right):
            return _equal_denotation(left, right, signals, universe)
        case Not(operand=operand):
            return universe - _denote(operand, valuation, signals, universe)
        case And(operands=operands):
            result = universe
            for operand in operands:
                result &= _denote(operand, valuation, signals, universe)
            return result
        case Or(operands=operands):
            result = P.empty()
            for operand in operands:
                result |= _denote(operand, valuation, signals, universe)
            return result
        case Restrict(interval=interval, body=body):
            effective = interval & universe
            if effective.empty:
                return P.empty()
            return effective & _denote(body, valuation, signals, universe)
        case Guard(interval=interval, body=body):
            effective = interval & universe
            if effective.empty:
                return universe
            truth = _denote(body, valuation, signals, universe)
            return (universe - effective) | (effective & truth)
        case ForAll(interval=interval, body=body):
            quantified = interval & universe
            if quantified.empty:
                return universe
            truth = _denote(body, valuation, signals, universe)
            return universe if (quantified - truth).empty else P.empty()
        case Exists(interval=interval, body=body):
            quantified = interval & universe
            if quantified.empty:
                return P.empty()
            truth = _denote(body, valuation, signals, universe)
            return universe if not (quantified & truth).empty else P.empty()
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _equal_denotation(
    left: Term,
    right: Term,
    signals: SignalValuation,
    universe: P.Interval,
) -> P.Interval:
    left_parts = dict(_term_parts(left, signals, universe))
    right_parts = dict(_term_parts(right, signals, universe))
    result = P.empty()
    for value in left_parts.keys() & right_parts.keys():
        result |= left_parts[value] & right_parts[value]
    return result


def _term_parts(
    term: Term,
    signals: SignalValuation,
    universe: P.Interval,
) -> tuple[tuple[int, P.Interval], ...]:
    match term:
        case Natural(value=value):
            return ((value, universe),)
        case Signal(name=name):
            try:
                signal = signals[name]
            except KeyError:
                raise KeyError(f"missing valuation for signal {name!r}") from None
            if not isinstance(signal, NaturalSignal):
                raise TypeError(
                    f"valuation for signal {name!r} must be a NaturalSignal"
                )
            return signal.parts(universe)
        case _:
            raise TypeError(f"unsupported term type: {type(term).__name__}")


def _require_natural(value: object, label: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
