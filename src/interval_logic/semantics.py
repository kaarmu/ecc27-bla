"""Local satisfaction and anchored denotation for represented trajectories."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeAlias

import portion as P

from .ast import (
    Always,
    And,
    Boolean,
    Equal,
    Equivalent,
    Eventually,
    Formula,
    Implies,
    NaturalLiteral,
    NaturalValue,
    Not,
    NumericTerm,
    Or,
    Proposition,
    Release,
    RestrictiveSelection,
    Selection,
    Signal,
    Until,
    VacuousSelection,
    WeakUntil,
    as_formula,
)
from .errors import TraceValidationError
from .temporal import (
    AbsoluteParameter,
    RelativeParameter,
    TimeSet,
    TimeValue,
    temporal_window,
    validate_nonnegative_interval,
    validate_time,
)


PropositionValuation: TypeAlias = Mapping[str, TimeSet]
SignalValuation: TypeAlias = Mapping[str, "NaturalSignal"]


@dataclass(frozen=True, slots=True, init=False)
class NaturalSignal:
    """A finitely represented natural-valued signal."""

    regions: Mapping[NaturalValue, TimeSet]
    default: NaturalValue | None

    def __init__(
        self,
        regions: Mapping[NaturalValue, TimeSet],
        default: NaturalValue | None = None,
    ) -> None:
        if not isinstance(regions, Mapping):
            raise TypeError("NaturalSignal regions must be a mapping")
        if default is not None:
            _require_natural(default, "NaturalSignal default")

        normalized: dict[int, TimeSet] = {}
        covered = P.empty()
        for value, interval in regions.items():
            _require_natural(value, "NaturalSignal region value")
            validate_nonnegative_interval(interval, name="NaturalSignal region")
            if not (covered & interval).empty:
                raise TraceValidationError(
                    "NaturalSignal regions must be pairwise disjoint"
                )
            normalized[value] = interval
            covered |= interval

        object.__setattr__(self, "regions", MappingProxyType(normalized))
        object.__setattr__(self, "default", default)

    def parts(self, universe: TimeSet) -> Mapping[NaturalValue, TimeSet]:
        """Return value regions clipped to ``universe`` and completed by default."""

        validate_nonnegative_interval(universe, name="universe")
        result: dict[int, TimeSet] = {}
        covered = P.empty()
        for value, interval in self.regions.items():
            effective = interval & universe
            if not effective.empty:
                result[value] = result.get(value, P.empty()) | effective
                covered |= effective

        uncovered = universe - covered
        if not uncovered.empty:
            if self.default is None:
                raise TraceValidationError(
                    f"NaturalSignal does not cover the trace universe: {uncovered}"
                )
            result[self.default] = result.get(self.default, P.empty()) | uncovered
        return MappingProxyType(result)


@dataclass(frozen=True, slots=True, init=False)
class Trace:
    """A complete known trace over a represented time universe."""

    universe: TimeSet
    propositions: PropositionValuation
    signals: SignalValuation

    def __init__(
        self,
        universe: TimeSet,
        propositions: PropositionValuation | None = None,
        signals: SignalValuation | None = None,
    ) -> None:
        validate_nonnegative_interval(universe, name="Trace universe")
        propositions = {} if propositions is None else propositions
        signals = {} if signals is None else signals
        if not isinstance(propositions, Mapping):
            raise TypeError("Trace propositions must be a mapping")
        if not isinstance(signals, Mapping):
            raise TypeError("Trace signals must be a mapping")

        proposition_copy: dict[str, TimeSet] = {}
        for name, interval in propositions.items():
            _require_mapping_name(name, "proposition")
            validate_nonnegative_interval(
                interval, name=f"valuation for proposition {name!r}"
            )
            proposition_copy[name] = interval

        signal_copy: dict[str, NaturalSignal] = {}
        for name, signal in signals.items():
            _require_mapping_name(name, "signal")
            if not isinstance(signal, NaturalSignal):
                raise TypeError(
                    f"valuation for signal {name!r} must be a NaturalSignal"
                )
            signal.parts(universe)
            signal_copy[name] = signal

        object.__setattr__(self, "universe", universe)
        object.__setattr__(self, "propositions", MappingProxyType(proposition_copy))
        object.__setattr__(self, "signals", MappingProxyType(signal_copy))


def denote(
    formula: Formula | str, trace: Trace, anchor: TimeValue
) -> TimeSet:
    """Return the complete anchored denotation ``[[formula]]_anchor``."""

    formula, trace, anchor_number = _validated_request(formula, trace, anchor)
    return _EvaluationContext(trace).denotation(formula, anchor_number)


def satisfies(
    formula: Formula | str, trace: Trace, at: TimeValue
) -> bool:
    """Evaluate the fundamental local satisfaction relation at one time."""

    formula, trace, at_number = _validated_request(formula, trace, at)
    return _EvaluationContext(trace).local_truth(formula, at_number)


def satisfying_times(formula: Formula | str, trace: Trace) -> TimeSet:
    """Return all represented anchors that locally satisfy ``formula``."""

    if not isinstance(trace, Trace):
        raise TypeError("trace must be a Trace")
    return _EvaluationContext(trace).satisfying(as_formula(formula))


class _EvaluationContext:
    def __init__(self, trace: Trace) -> None:
        self.trace = trace
        self.universe = trace.universe
        self._truth_cache: dict[tuple[Formula, float], bool] = {}
        self._satisfying_cache: dict[Formula, TimeSet] = {}
        self._denotation_cache: dict[tuple[Formula, float], TimeSet] = {}

    def local_truth(self, formula: Formula, at: float) -> bool:
        """Evaluate ``(w, at) satisfies formula`` directly."""

        key = (formula, at)
        cached = self._truth_cache.get(key)
        if cached is not None:
            return cached

        match formula:
            case Boolean(value=value):
                result = value
            case Proposition(name=name):
                result = at in self.trace.propositions.get(name, P.empty())
            case Equal(left=left, right=right):
                result = self._term_value(left, at) == self._term_value(right, at)
            case Not(operand=operand):
                result = not self.local_truth(operand, at)
            case And(operands=operands):
                result = all(self.local_truth(operand, at) for operand in operands)
            case Or(operands=operands):
                result = any(self.local_truth(operand, at) for operand in operands)
            case Implies(left=left, right=right):
                result = not self.local_truth(left, at) or self.local_truth(right, at)
            case Equivalent(left=left, right=right):
                result = self.local_truth(left, at) == self.local_truth(right, at)
            case Selection(inside=inside, outside=outside, parameter=parameter):
                branch = (
                    inside
                    if at in temporal_window(parameter, at, self.universe)
                    else outside
                )
                result = self.local_truth(branch, at)
            case VacuousSelection(body=body, parameter=parameter):
                result = (
                    at not in temporal_window(parameter, at, self.universe)
                    or self.local_truth(body, at)
                )
            case RestrictiveSelection(body=body, parameter=parameter):
                result = (
                    at in temporal_window(parameter, at, self.universe)
                    and self.local_truth(body, at)
                )
            case Eventually(body=body, parameter=parameter):
                result = not (
                    temporal_window(parameter, at, self.universe)
                    & self.satisfying(body)
                ).empty
            case Always(body=body, parameter=parameter):
                window = temporal_window(parameter, at, self.universe)
                result = (window - self.satisfying(body)).empty
            case Until(left=left, right=right, parameter=parameter):
                result = self._until_truth(left, right, parameter, at)
            case Release(left=left, right=right, parameter=parameter):
                result = not self._until_truth(
                    Not(left), Not(right), parameter, at
                )
            case WeakUntil(left=left, right=right, parameter=parameter):
                result = self._weak_until_truth(left, right, parameter, at)
            case _:
                raise TypeError(f"unsupported formula type: {type(formula).__name__}")

        self._truth_cache[key] = result
        return result

    def denotation(self, formula: Formula, anchor: float) -> TimeSet:
        key = (formula, anchor)
        cached = self._denotation_cache.get(key)
        if cached is not None:
            return cached

        universe = self.universe
        match formula:
            case Boolean(value=True):
                result = universe
            case Boolean(value=False):
                result = P.empty()
            case Proposition() | Equal():
                result = self.satisfying(formula)
            case Not(operand=operand):
                result = universe - self.denotation(operand, anchor)
            case And(operands=operands):
                result = universe
                for operand in operands:
                    result &= self.denotation(operand, anchor)
            case Or(operands=operands):
                result = P.empty()
                for operand in operands:
                    result |= self.denotation(operand, anchor)
            case Implies(left=left, right=right):
                result = (
                    universe - self.denotation(left, anchor)
                ) | self.denotation(right, anchor)
            case Equivalent(left=left, right=right):
                left_set = self.denotation(left, anchor)
                right_set = self.denotation(right, anchor)
                result = (left_set & right_set) | (
                    (universe - left_set) & (universe - right_set)
                )
            case Selection(inside=inside, outside=outside, parameter=parameter):
                window = temporal_window(parameter, anchor, universe)
                result = (window & self.satisfying(inside)) | (
                    (universe - window) & self.satisfying(outside)
                )
            case VacuousSelection(body=body, parameter=parameter):
                window = temporal_window(parameter, anchor, universe)
                result = (universe - window) | (window & self.satisfying(body))
            case RestrictiveSelection(body=body, parameter=parameter):
                window = temporal_window(parameter, anchor, universe)
                result = window & self.satisfying(body)
            case Eventually() | Always() | Until() | Release() | WeakUntil():
                result = universe if self.local_truth(formula, anchor) else P.empty()
            case _:
                raise TypeError(f"unsupported formula type: {type(formula).__name__}")

        result &= universe
        self._denotation_cache[key] = result
        return result

    def satisfying(self, formula: Formula) -> TimeSet:
        cached = self._satisfying_cache.get(formula)
        if cached is not None:
            return cached

        if isinstance(formula, Boolean):
            result = self.universe if formula.value else P.empty()
            self._satisfying_cache[formula] = result
            return result
        if isinstance(formula, Proposition):
            result = (
                self.trace.propositions.get(formula.name, P.empty())
                & self.universe
            )
            self._satisfying_cache[formula] = result
            return result
        if isinstance(formula, Equal):
            result = self._equal_satisfying_times(formula.left, formula.right)
            self._satisfying_cache[formula] = result
            return result

        # Child truth sets establish every finite boundary at which this
        # formula can change. Relative upper bounds add backward-shifted
        # copies of those boundaries.
        child_sets = tuple(self.satisfying(child) for child in formula.children)
        boundaries = _finite_endpoints(self.universe)
        for child_set in child_sets:
            boundaries.update(_finite_endpoints(child_set))
        parameter = getattr(formula, "parameter", None)
        if isinstance(parameter, AbsoluteParameter):
            boundaries.update(_finite_endpoints(parameter.interval))
        elif isinstance(parameter, RelativeParameter):
            duration = parameter.duration
            shifted_sources = set(_finite_endpoints(self.universe))
            for child_set in child_sets:
                shifted_sources.update(_finite_endpoints(child_set))
            boundaries.update(
                endpoint - duration
                for endpoint in shifted_sources
                if endpoint - duration >= 0
            )

        result = P.empty()
        for atom in self.universe:
            atom_boundaries = sorted(
                boundary
                for boundary in boundaries
                if atom.lower <= boundary <= atom.upper
            )
            if atom.lower != -P.inf:
                atom_boundaries.append(float(atom.lower))
            if atom.upper != P.inf:
                atom_boundaries.append(float(atom.upper))
            points = sorted(set(atom_boundaries))

            for point in points:
                if point in atom and self.local_truth(formula, point):
                    result |= P.closed(point, point)
            for lower, upper in zip(points, points[1:]):
                region = P.open(lower, upper) & atom
                if not region.empty:
                    sample = (lower + upper) / 2
                    if self.local_truth(formula, sample):
                        result |= region
            if atom.upper == P.inf:
                lower = points[-1]
                region = P.open(lower, P.inf) & atom
                if not region.empty and self.local_truth(formula, lower + 1):
                    result |= region

        result &= self.universe
        self._satisfying_cache[formula] = result
        return result

    def _until_truth(
        self, left: Formula, right: Formula, parameter, anchor: float
    ) -> bool:
        window = temporal_window(parameter, anchor, self.universe)
        candidates = window & self.satisfying(right)
        if candidates.empty:
            return False

        bad = (
            self.universe - self.satisfying(left)
        ) & P.closed(anchor, P.inf)
        if bad.empty:
            return True
        first_bad = next(iter(bad)).lower
        allowed = P.openclosed(-P.inf, first_bad)
        return not (candidates & allowed).empty

    def _weak_until_truth(
        self, left: Formula, right: Formula, parameter, anchor: float
    ) -> bool:
        if self._until_truth(left, right, parameter, anchor):
            return True
        window = temporal_window(parameter, anchor, self.universe)
        if window.empty:
            return True
        last = tuple(window)[-1]
        if last.upper == P.inf:
            prefix = P.closed(anchor, P.inf)
        elif last.right == P.CLOSED:
            prefix = P.closed(anchor, last.upper)
        else:
            prefix = P.closedopen(anchor, last.upper)
        horizon = prefix & self.universe
        return (horizon - self.satisfying(left)).empty

    def _equal_satisfying_times(
        self, left: NumericTerm, right: NumericTerm
    ) -> TimeSet:
        if left == right:
            return self.universe
        if isinstance(left, NaturalLiteral) and isinstance(right, NaturalLiteral):
            return P.empty()

        left_parts = self._term_parts(left)
        right_parts = self._term_parts(right)
        result = P.empty()
        for value in left_parts.keys() & right_parts.keys():
            result |= left_parts[value] & right_parts[value]
        return result

    def _term_value(self, term: NumericTerm, at: float) -> NaturalValue:
        if isinstance(term, NaturalLiteral):
            return term.value
        for value, region in self._term_parts(term).items():
            if at in region:
                return value
        raise TraceValidationError("signal has no value at the requested time")

    def _term_parts(self, term: NumericTerm) -> Mapping[int, TimeSet]:
        if isinstance(term, NaturalLiteral):
            return {term.value: self.universe}
        if isinstance(term, Signal):
            try:
                signal = self.trace.signals[term.name]
            except KeyError as error:
                raise TraceValidationError(
                    f"missing valuation for signal {term.name!r}"
                ) from error
            return signal.parts(self.universe)
        raise TypeError(f"unsupported term type: {type(term).__name__}")


def _validated_request(
    formula: Formula | str, trace: Trace, anchor: TimeValue
) -> tuple[Formula, Trace, float]:
    if not isinstance(trace, Trace):
        raise TypeError("trace must be a Trace")
    anchor_number = validate_time(anchor, name="anchor")
    if anchor_number not in trace.universe:
        raise TraceValidationError(
            "anchor must be represented by the trace universe"
        )
    return as_formula(formula), trace, anchor_number


def _finite_endpoints(interval: TimeSet) -> set[float]:
    result: set[float] = set()
    for atom in interval:
        if atom.lower not in {-P.inf, P.inf}:
            result.add(float(atom.lower))
        if atom.upper not in {-P.inf, P.inf}:
            result.add(float(atom.upper))
    return result


def _require_natural(value: object, label: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")


def _require_mapping_name(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} valuation names must be strings")
    if not value:
        raise ValueError(f"{label} valuation names must not be empty")
