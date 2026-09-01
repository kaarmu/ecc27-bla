"""Temporal-parameter values and exact window resolution."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
import re
from typing import Any, TypeAlias

import portion as P


@dataclass(frozen=True, slots=True)
class RelativeInterval:
    """A nonempty connected interval of non-negative relative offsets."""

    offsets: P.Interval | str

    def __post_init__(self) -> None:
        value = self.offsets
        if isinstance(value, str):
            try:
                value = P.from_string(value.strip(), float)
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid relative interval {self.offsets!r}") from error
        if not isinstance(value, P.Interval):
            raise TypeError("RelativeInterval offsets must be a portion.Interval or string")
        atoms = list(value)
        if len(atoms) != 1:
            raise ValueError("relative temporal parameter must be nonempty and connected")
        atom = atoms[0]
        if atom.lower == -P.inf or atom.lower < 0:
            raise ValueError("relative temporal offsets must be non-negative")
        object.__setattr__(self, "offsets", value)


TemporalParameter: TypeAlias = P.Interval | RelativeInterval
TemporalParameterInput: TypeAlias = TemporalParameter | str | Real | None

DEFAULT_TEMPORAL_PARAMETER = RelativeInterval(P.closed(0.0, P.inf))

_DURATION_PARAMETER = re.compile(
    r"(?P<value>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?P<end>[\]\)])\Z"
)


def coerce_temporal_parameter(value: TemporalParameterInput) -> TemporalParameter:
    """Normalize a public temporal-parameter input.

    ``portion.Interval`` and ordinary interval strings are absolute. ``None``
    is the unbounded default relative interval, real numbers are closed
    one-sided durations, and a trailing ``+`` marks an interval as relative.
    """

    if value is None:
        return DEFAULT_TEMPORAL_PARAMETER
    if isinstance(value, RelativeInterval):
        return value
    if isinstance(value, bool):
        raise TypeError("temporal parameter must not be a bool")
    if isinstance(value, Real):
        duration = float(value)
        if not isfinite(duration) or duration < 0:
            raise ValueError("temporal duration must be finite and non-negative")
        return RelativeInterval(P.closed(0.0, 0.0 if duration == 0 else duration))
    if isinstance(value, P.Interval):
        return _validate_absolute(value)
    if not isinstance(value, str):
        raise TypeError(
            "temporal parameter must be an interval, relative interval, string, "
            "non-negative real duration, or None"
        )

    text = value.strip()
    if not text:
        raise ValueError("temporal parameter string must not be empty")
    if text.endswith("+"):
        interval_text = text[:-1].strip()
        if not interval_text:
            raise ValueError("expected an interval before '+'")
        try:
            return RelativeInterval(P.from_string(interval_text, float))
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid relative temporal parameter {text!r}") from error

    duration_match = _DURATION_PARAMETER.fullmatch(text)
    if duration_match is not None and not text.startswith(("[", "(")):
        duration = float(duration_match.group("value"))
        if not isfinite(duration) or duration < 0:
            raise ValueError("temporal duration must be finite and non-negative")
        interval = (
            P.closed(0.0, duration)
            if duration_match.group("end") == "]"
            else P.closedopen(0.0, duration)
        )
        # portion represents [0,0) as empty, which is intentionally permitted
        # for this special one-sided syntax even though general D+ is nonempty.
        if interval.empty:
            return _EmptyRelativeInterval()
        return RelativeInterval(interval)

    try:
        return _validate_absolute(P.from_string(text, float))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid absolute temporal parameter {text!r}") from error


@dataclass(frozen=True, slots=True)
class _EmptyRelativeInterval(RelativeInterval):
    """Internal representation of the specified empty ``0)`` window."""

    offsets: P.Interval | str = P.empty()

    def __post_init__(self) -> None:
        value = self.offsets
        if not isinstance(value, P.Interval) or not value.empty:
            raise ValueError("empty relative parameter must contain no offsets")


def resolve_window(parameter: TemporalParameterInput, anchor: Any) -> P.Interval:
    """Resolve a temporal parameter at ``anchor`` without universe clipping."""

    normalized = coerce_temporal_parameter(parameter)
    if isinstance(normalized, P.Interval):
        return normalized
    result = P.empty()
    for atom in normalized.offsets:
        lower = atom.lower if atom.lower == -P.inf else anchor + atom.lower
        upper = atom.upper if atom.upper == P.inf else anchor + atom.upper
        result |= P.from_data([(atom.left, lower, upper, atom.right)])
    return result


def span_parameter(parameter: TemporalParameterInput) -> TemporalParameter:
    """Return the weak-until no-witness span specified by ``LOGIC.md``."""

    normalized = coerce_temporal_parameter(parameter)
    if isinstance(normalized, P.Interval):
        return normalized
    if normalized.offsets.empty:
        return normalized
    atom = next(iter(normalized.offsets))
    if atom.upper == P.inf:
        return DEFAULT_TEMPORAL_PARAMETER
    offsets = (
        P.closed(0.0, atom.upper)
        if atom.right.name == "CLOSED"
        else P.closedopen(0.0, atom.upper)
    )
    if offsets.empty:
        return _EmptyRelativeInterval()
    return RelativeInterval(offsets)


def format_temporal_parameter(parameter: TemporalParameterInput) -> str:
    normalized = coerce_temporal_parameter(parameter)
    if isinstance(normalized, P.Interval):
        return _format_interval(normalized)
    if normalized.offsets.empty:
        return "0)"
    atom = next(iter(normalized.offsets))
    if atom.lower == 0 and atom.left.name == "CLOSED" and atom.upper != P.inf:
        suffix = "]" if atom.right.name == "CLOSED" else ")"
        return f"{_format_number(atom.upper)}{suffix}"
    return f"{_format_interval(normalized.offsets)}+"


def temporal_parameter_key(parameter: TemporalParameterInput) -> tuple[Any, ...]:
    normalized = coerce_temporal_parameter(parameter)
    kind = 1 if isinstance(normalized, RelativeInterval) else 0
    interval = normalized.offsets if isinstance(normalized, RelativeInterval) else normalized
    return (
        kind,
        tuple(
            (repr(atom.lower), repr(atom.upper), atom.left.name, atom.right.name)
            for atom in interval
        ),
    )


def is_relative(parameter: TemporalParameterInput) -> bool:
    return isinstance(coerce_temporal_parameter(parameter), RelativeInterval)


def parameter_interval(parameter: TemporalParameterInput) -> P.Interval:
    normalized = coerce_temporal_parameter(parameter)
    return normalized.offsets if isinstance(normalized, RelativeInterval) else normalized


def _validate_absolute(interval: P.Interval) -> P.Interval:
    if len(list(interval)) > 1:
        raise ValueError("absolute temporal parameter must be connected")
    return interval


def _format_number(value: Any) -> str:
    if value == P.inf:
        return "+inf"
    if value == -P.inf:
        return "-inf"
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)
    if isfinite(numeric) and numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:g}"


def _format_interval(interval: P.Interval) -> str:
    if interval.empty:
        return "()"
    atoms = list(interval)
    if len(atoms) != 1:
        return str(interval)
    atom = atoms[0]
    left = "[" if atom.left.name == "CLOSED" else "("
    right = "]" if atom.right.name == "CLOSED" else ")"
    return (
        f"{left}{_format_number(atom.lower)},{_format_number(atom.upper)}{right}"
    )
