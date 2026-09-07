"""Exact temporal parameters and represented, future-directed windows."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from numbers import Real
import re
from typing import TypeAlias

import portion as P

TimeValue: TypeAlias = Real
TimeSet: TypeAlias = P.Interval

# Fractions extend numeric spelling only in temporal positions.
NUMBER_PATTERN = r"(?:\d+/\d+|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
_DURATION = re.compile(rf"^({NUMBER_PATTERN})([\]\)])?$")


def validate_time(value: object, *, name: str = "time") -> Fraction:
    """Canonicalize real scalars by decimal spelling, preserving fractions."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    try:
        result = value if isinstance(value, Fraction) else Fraction(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError(f"{name} must be finite") from error
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def validate_nonnegative_interval(
    interval: TimeSet, *, name: str = "interval", connected: bool = False
) -> TimeSet:
    """Validate and canonicalize finite endpoints without binary rounding."""
    if not isinstance(interval, P.Interval):
        raise TypeError(f"{name} must be a portion.Interval")
    if connected and not interval.empty and not interval.atomic:
        raise ValueError(f"{name} must be connected")
    result = P.empty()
    for atom in interval:
        lower = validate_time(atom.lower, name=f"{name} lower bound")
        if atom.upper == P.inf:
            if atom.right != P.OPEN:
                raise ValueError(f"{name} cannot contain infinity")
            upper = P.inf
        else:
            upper = validate_time(atom.upper, name=f"{name} upper bound")
        result |= P.Interval.from_atomic(atom.left, lower, upper, atom.right)
    return result


@dataclass(frozen=True, slots=True)
class RelativeParameter:
    duration: TimeValue
    include_endpoint: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration", validate_time(self.duration, name="duration"))
        if type(self.include_endpoint) is not bool:
            raise TypeError("include_endpoint must be a bool")


@dataclass(frozen=True, slots=True)
class AbsoluteParameter:
    interval: TimeSet

    def __post_init__(self) -> None:
        object.__setattr__(self, "interval", validate_nonnegative_interval(
            self.interval, name="absolute temporal parameter", connected=True
        ))


TemporalParameter: TypeAlias = RelativeParameter | AbsoluteParameter | None
TemporalParameterInput: TypeAlias = TemporalParameter | Real | TimeSet | str


def coerce_temporal_parameter(value: TemporalParameterInput) -> TemporalParameter:
    if value is None or isinstance(value, (RelativeParameter, AbsoluteParameter)):
        return value
    if isinstance(value, bool):
        raise TypeError("a temporal parameter cannot be a bool")
    if isinstance(value, Real):
        return RelativeParameter(value)
    if isinstance(value, P.Interval):
        return AbsoluteParameter(value)
    if not isinstance(value, str):
        raise TypeError("expected a duration, interval, temporal parameter, string, or None")
    source = value.strip()
    match = _DURATION.fullmatch(source)
    try:
        if match:
            return RelativeParameter(Fraction(match[1]), match[2] == "]")
        # portion's parser handles empty, singleton, and unbounded intervals.
        return AbsoluteParameter(P.from_string(source, conv=Fraction))
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError(f"invalid temporal parameter: {value!r}") from error


def _format_time(value: Fraction) -> str:
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return f"{value.numerator}/{value.denominator}"
    places = max(twos, fives)
    if not places:
        return str(value.numerator)
    digits = str(value.numerator * 2 ** (places - twos) * 5 ** (places - fives))
    digits = digits.zfill(places + 1)
    return (digits[:-places] + "." + digits[-places:]).rstrip("0").rstrip(".")


def format_temporal_parameter(parameter: TemporalParameter) -> str:
    canonical = coerce_temporal_parameter(parameter)
    if canonical is None:
        return ""
    if isinstance(canonical, RelativeParameter):
        return _format_time(canonical.duration) + ("]" if canonical.include_endpoint else "")
    if canonical.interval.empty:
        return "()"
    atom = canonical.interval
    left = "[" if atom.left == P.CLOSED else "("
    right = "]" if atom.right == P.CLOSED else ")"
    upper = "+inf" if atom.upper == P.inf else _format_time(atom.upper)
    # Always spell both bounds, including singletons, for unambiguous parsing.
    return f"{left}{_format_time(atom.lower)},{upper}{right}"


def temporal_window(
    parameter: TemporalParameter, anchor: TimeValue, universe: TimeSet
) -> TimeSet:
    anchor = validate_time(anchor, name="anchor")
    universe = validate_nonnegative_interval(universe, name="universe")
    if anchor not in universe:
        raise ValueError("anchor must belong to the represented universe")
    canonical = coerce_temporal_parameter(parameter)
    if canonical is None:
        window = P.closedopen(anchor, P.inf)
    elif isinstance(canonical, RelativeParameter):
        constructor = P.closed if canonical.include_endpoint else P.closedopen
        window = constructor(anchor, anchor + canonical.duration)
    else:
        window = canonical.interval & P.closedopen(anchor, P.inf)
    return window & universe


def temporal_parameter_key(parameter: TemporalParameter) -> tuple[object, ...]:
    canonical = coerce_temporal_parameter(parameter)
    if canonical is None:
        return (0,)
    if isinstance(canonical, RelativeParameter):
        return (1, canonical.duration, canonical.include_endpoint)
    return (2, format_temporal_parameter(canonical))
