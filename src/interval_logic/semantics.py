from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import portion as P

from .ast import (
    And,
    Bool,
    Equal,
    Eventually,
    ExistentialCondition,
    Expression,
    NaturalLiteral,
    Not,
    Or,
    Proposition,
    Release,
    RestrictiveSelection,
    Selection,
    Signal,
    Term,
    Until,
    UniversalCondition,
    VacuousSelection,
    _coerce_expression,
)
from .temporal import RelativeInterval, parameter_interval, resolve_window
from .transform import lower_derived

PropositionValuation = Mapping[str, P.Interval]


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


def satisfying_anchors(
    expression: Expression | str,
    valuation: PropositionValuation,
    universe: P.Interval,
    *,
    signals: SignalValuation | None = None,
) -> P.Interval:
    """Return represented anchors that are locally true on the diagonal sweep."""

    expression, valuation, signals, universe = _validated_inputs(
        expression, valuation, signals, universe
    )
    return _EvaluationContext(valuation, signals, universe).truth(expression)


def anchored_denotation(
    expression: Expression | str,
    valuation: PropositionValuation,
    anchor: Any,
    universe: P.Interval,
    *,
    signals: SignalValuation | None = None,
) -> P.Interval:
    """Return ``expression``'s full denotation at one represented anchor."""

    expression, valuation, signals, universe = _validated_inputs(
        expression, valuation, signals, universe
    )
    if anchor not in universe:
        raise ValueError("anchor must be represented by the evaluation universe")
    return _EvaluationContext(valuation, signals, universe).denote(expression, anchor)


def satisfies(
    expression: Expression | str,
    valuation: PropositionValuation,
    at: Any,
    universe: P.Interval,
    *,
    signals: SignalValuation | None = None,
) -> bool:
    """Return whether an expression is locally true at one represented anchor."""

    return at in satisfying_anchors(expression, valuation, universe, signals=signals)


class _EvaluationContext:
    def __init__(
        self,
        valuation: PropositionValuation,
        signals: SignalValuation,
        universe: P.Interval,
    ) -> None:
        self.valuation = valuation
        self.signals = signals
        self.universe = universe
        self._truth_cache: dict[Expression, P.Interval] = {}

    def truth(self, expression: Expression) -> P.Interval:
        cached = self._truth_cache.get(expression)
        if cached is not None:
            return cached
        result = self._truth_uncached(expression) & self.universe
        self._truth_cache[expression] = result
        return result

    def _truth_uncached(self, expression: Expression) -> P.Interval:
        universe = self.universe
        match expression:
            case Bool(value=True):
                return universe
            case Bool(value=False):
                return P.empty()
            case Proposition(name=name):
                return self._proposition(name)
            case Equal(left=left, right=right):
                return _equal_denotation(left, right, self.signals, universe)
            case Not(operand=operand):
                return universe - self.truth(operand)
            case And(operands=operands):
                result = universe
                for operand in operands:
                    result &= self.truth(operand)
                return result
            case Or(operands=operands):
                result = P.empty()
                for operand in operands:
                    result |= self.truth(operand)
                return result
            case RestrictiveSelection(interval=parameter, body=body):
                return self._selection_truth(parameter, body, Bool(False))
            case VacuousSelection(interval=parameter, body=body):
                return self._selection_truth(parameter, body, Bool(True))
            case Selection(parameter=parameter, inside=inside, outside=outside):
                return self._selection_truth(parameter, inside, outside)
            case UniversalCondition(interval=parameter, body=body):
                return self._condition_truth(parameter, body, universal=True)
            case ExistentialCondition(interval=parameter, body=body):
                return self._condition_truth(parameter, body, universal=False)
            case Eventually(parameter=parameter, body=body):
                return self._condition_truth(parameter, body, universal=False)
            case Until(parameter=parameter, left=left, right=right):
                return self._until_truth(parameter, left, right)
            case Release(parameter=parameter, left=left, right=right):
                dual = Until(parameter, Not(left), Not(right))
                return universe - self.truth(dual)
            case _:
                raise TypeError(
                    f"unsupported expression type: {type(expression).__name__}"
                )

    def denote(self, expression: Expression, anchor: Any) -> P.Interval:
        universe = self.universe
        match expression:
            case Bool(value=True):
                return universe
            case Bool(value=False):
                return P.empty()
            case Proposition(name=name):
                return self._proposition(name)
            case Equal(left=left, right=right):
                return _equal_denotation(left, right, self.signals, universe)
            case Not(operand=operand):
                return universe - self.denote(operand, anchor)
            case And(operands=operands):
                result = universe
                for operand in operands:
                    result &= self.denote(operand, anchor)
                return result
            case Or(operands=operands):
                result = P.empty()
                for operand in operands:
                    result |= self.denote(operand, anchor)
                return result
            case RestrictiveSelection(interval=parameter, body=body):
                window = resolve_window(parameter, anchor) & universe
                if window.empty:
                    return P.empty()
                return window & self.denote(body, anchor)
            case VacuousSelection(interval=parameter, body=body):
                window = resolve_window(parameter, anchor) & universe
                if window.empty:
                    return universe
                return (universe - window) | (window & self.denote(body, anchor))
            case Selection(parameter=parameter, inside=inside, outside=outside):
                window = resolve_window(parameter, anchor) & universe
                if window.empty:
                    return self.denote(outside, anchor)
                if (universe - window).empty:
                    return self.denote(inside, anchor)
                return (window & self.denote(inside, anchor)) | (
                    (universe - window) & self.denote(outside, anchor)
                )
            case UniversalCondition(interval=parameter, body=body):
                inspected = resolve_window(parameter, anchor) & universe
                if inspected.empty:
                    return universe
                holds = (inspected - self.truth(body)).empty
                return universe if holds else P.empty()
            case ExistentialCondition(interval=parameter, body=body):
                inspected = resolve_window(parameter, anchor) & universe
                if inspected.empty:
                    return P.empty()
                holds = not (inspected & self.truth(body)).empty
                return universe if holds else P.empty()
            case Eventually(parameter=parameter, body=body):
                inspected = resolve_window(parameter, anchor) & universe
                if inspected.empty:
                    return P.empty()
                holds = not (inspected & self.truth(body)).empty
                return universe if holds else P.empty()
            case Until(parameter=parameter, left=left, right=right):
                holds = _until_holds(
                    parameter,
                    anchor,
                    self.truth(left),
                    self.truth(right),
                    universe,
                )
                return universe if holds else P.empty()
            case Release(parameter=parameter, left=left, right=right):
                dual = Until(parameter, Not(left), Not(right))
                return universe - self.denote(dual, anchor)
            case _:
                raise TypeError(
                    f"unsupported expression type: {type(expression).__name__}"
                )

    def _proposition(self, name: str) -> P.Interval:
        try:
            value = self.valuation[name]
        except KeyError:
            raise KeyError(f"missing valuation for proposition {name!r}") from None
        if not isinstance(value, P.Interval):
            raise TypeError(
                f"valuation for proposition {name!r} must be a portion.Interval"
            )
        return value & self.universe

    def _selection_truth(
        self,
        parameter,
        inside: Expression,
        outside: Expression,
    ) -> P.Interval:
        if isinstance(parameter, RelativeInterval):
            selected = 0 in parameter.offsets
            return self.truth(inside if selected else outside)
        window = parameter & self.universe
        if window.empty:
            return self.truth(outside)
        if (self.universe - window).empty:
            return self.truth(inside)
        return (window & self.truth(inside)) | (
            (self.universe - window) & self.truth(outside)
        )

    def _condition_truth(
        self,
        parameter,
        body: Expression,
        *,
        universal: bool,
    ) -> P.Interval:
        if not isinstance(parameter, RelativeInterval):
            inspected = parameter & self.universe
            if inspected.empty:
                return self.universe if universal else P.empty()
            body_truth = self.truth(body)
            if universal:
                holds = (inspected - body_truth).empty
            else:
                holds = not (inspected & body_truth).empty
            return self.universe if holds else P.empty()
        if parameter.offsets.empty:
            return self.universe if universal else P.empty()
        body_truth = self.truth(body)
        if universal:
            failures = _relative_preimage(
                self.universe - body_truth,
                parameter.offsets,
            )
            return self.universe - failures
        return _relative_preimage(body_truth, parameter.offsets) & self.universe

    def _until_truth(
        self,
        parameter,
        left: Expression,
        right: Expression,
    ) -> P.Interval:
        if parameter_interval(parameter).empty:
            return P.empty()
        left_truth = self.truth(left)
        right_truth = self.truth(right)
        if not isinstance(parameter, RelativeInterval):
            holds = _until_holds(
                parameter,
                _representative(self.universe),
                left_truth,
                right_truth,
                self.universe,
            )
            return self.universe if holds else P.empty()
        return _relative_until_sweep(
            parameter,
            left_truth,
            right_truth,
            self.universe,
        )


def _relative_preimage(truth: P.Interval, offsets: P.Interval) -> P.Interval:
    """Return anchors whose translated offset interval intersects ``truth``."""

    if truth.empty or offsets.empty:
        return P.empty()
    result = P.empty()
    for truth_atom in truth:
        for offset_atom in offsets:
            lower = (
                -P.inf
                if truth_atom.lower == -P.inf or offset_atom.upper == P.inf
                else truth_atom.lower - offset_atom.upper
            )
            upper = (
                P.inf
                if truth_atom.upper == P.inf
                else truth_atom.upper - offset_atom.lower
            )
            left = (
                P.CLOSED
                if truth_atom.left.name == "CLOSED"
                and offset_atom.right.name == "CLOSED"
                and lower != -P.inf
                else P.OPEN
            )
            right = (
                P.CLOSED
                if truth_atom.right.name == "CLOSED"
                and offset_atom.left.name == "CLOSED"
                and upper != P.inf
                else P.OPEN
            )
            result |= P.from_data([(left, lower, upper, right)])
    return result


def _until_holds(
    parameter,
    anchor: Any,
    left_truth: P.Interval,
    right_truth: P.Interval,
    universe: P.Interval,
) -> bool:
    witnesses = resolve_window(parameter, anchor) & universe & right_truth
    if witnesses.empty:
        return False

    if isinstance(parameter, RelativeInterval):
        bad = (universe - left_truth) & P.closed(anchor, P.inf)
    else:
        bad = (parameter & universe) - left_truth
    if bad.empty:
        return True

    first_bad = next(iter(bad)).lower
    allowed = P.openclosed(-P.inf, first_bad)
    return not (witnesses & allowed).empty


def _relative_until_sweep(
    parameter: RelativeInterval,
    left_truth: P.Interval,
    right_truth: P.Interval,
    universe: P.Interval,
) -> P.Interval:
    if universe.empty or parameter.offsets.empty:
        return P.empty()

    bad = universe - left_truth
    points = _critical_points(
        (universe, left_truth, right_truth, bad), parameter.offsets
    )
    result = P.empty()

    bounds = [-P.inf, *points, P.inf]
    for lower, upper in zip(bounds, bounds[1:]):
        cell = P.open(lower, upper) & universe
        for atom in cell:
            sample = _representative(atom)
            if _until_holds(parameter, sample, left_truth, right_truth, universe):
                result |= atom

    for point in points:
        if point in universe and _until_holds(
            parameter, point, left_truth, right_truth, universe
        ):
            result |= P.singleton(point)
    return result & universe


def _critical_points(
    intervals: tuple[P.Interval, ...], offsets: P.Interval
) -> list[Any]:
    base: set[Any] = set()
    for interval in intervals:
        for atom in interval:
            for value in (atom.lower, atom.upper):
                if value not in (-P.inf, P.inf):
                    base.add(value)

    offset_bounds: set[Any] = set()
    for atom in offsets:
        for value in (atom.lower, atom.upper):
            if value not in (-P.inf, P.inf):
                offset_bounds.add(value)

    result = set(base)
    for point in base:
        for offset in offset_bounds:
            result.add(point - offset)
    try:
        return sorted(result)
    except TypeError as error:
        raise TypeError("temporal interval endpoints must be mutually comparable") from error


def _representative(interval: P.Interval) -> Any:
    if interval.empty:
        return 0.0
    atom = next(iter(interval))
    lower, upper = atom.lower, atom.upper
    if lower == -P.inf and upper == P.inf:
        return 0.0
    if lower == -P.inf:
        return upper - 1
    if upper == P.inf:
        return lower + 1
    return (lower + upper) / 2


def _validated_inputs(expression, valuation, signals, universe):
    expression = lower_derived(_coerce_expression(expression, "expression"))
    if not isinstance(universe, P.Interval):
        raise TypeError("universe must be a portion.Interval")
    if not isinstance(valuation, Mapping):
        raise TypeError("valuation must be a mapping")
    if signals is None:
        signals = {}
    if not isinstance(signals, Mapping):
        raise TypeError("signals must be a mapping")
    return expression, valuation, signals, universe


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
        case NaturalLiteral(value=value):
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
