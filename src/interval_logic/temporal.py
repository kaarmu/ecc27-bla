"""Temporal parameters and their represented trajectory windows."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, isnan
from numbers import Real
import re
from typing import TypeAlias

import portion as P


TimeValue: TypeAlias = Real
TimeSet: TypeAlias = P.Interval


@dataclass(frozen=True, slots=True)
class RelativeParameter:
    """A non-negative duration with an open or closed right endpoint."""

    duration: float
    include_endpoint: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.duration, bool) or not isinstance(self.duration, Real):
            raise TypeError("duration must be a real number")
        duration = float(self.duration)
        if not isfinite(duration) or duration < 0:
            raise ValueError("duration must be finite and non-negative")
        if type(self.include_endpoint) is not bool:
            raise TypeError("include_endpoint must be a bool")
        object.__setattr__(self, "duration", duration)


@dataclass(frozen=True, slots=True)
class AbsoluteParameter:
    """A connected interval on the absolute physical-time axis."""

    interval: TimeSet

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interval",
            validate_nonnegative_interval(
                self.interval, name="absolute temporal parameter", connected=True
            ),
        )


TemporalParameter: TypeAlias = RelativeParameter | AbsoluteParameter | None
TemporalParameterInput: TypeAlias = TemporalParameter | Real | TimeSet | str

_NUMBER = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_DURATION_WITH_END = re.compile(rf"^({_NUMBER})([\]\)])$")
_BARE_DURATION = re.compile(rf"^({_NUMBER})$")


def coerce_temporal_parameter(
    value: TemporalParameterInput | None,
) -> TemporalParameter:
    """Return the canonical runtime representation of ``value``."""

    if value is None:
        return None
    if isinstance(value, (RelativeParameter, AbsoluteParameter)):
        return value
    if isinstance(value, bool):
        raise TypeError("a temporal parameter cannot be a bool")
    if isinstance(value, Real):
        return RelativeParameter(value)
    if isinstance(value, P.Interval):
        return AbsoluteParameter(value)
    if not isinstance(value, str):
        raise TypeError(
            "a temporal parameter must be a duration, interval, string, or None"
        )

    source = value.strip()
    if not source:
        raise ValueError("a temporal parameter string cannot be empty")
    if source.endswith("+"):
        raise ValueError("trailing '+' temporal parameters are not supported")
    if re.search(r"(?i)(?:^|[^a-z])nan(?:$|[^a-z])", source):
        raise ValueError("absolute temporal parameter endpoints cannot be NaN")

    match = _DURATION_WITH_END.fullmatch(source)
    if match:
        return RelativeParameter(
            float(match.group(1)), include_endpoint=match.group(2) == "]"
        )
    match = _BARE_DURATION.fullmatch(source)
    if match:
        return RelativeParameter(float(match.group(1)))

    try:
        interval = P.from_string(source, conv=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid temporal parameter: {value!r}") from error
    return AbsoluteParameter(interval)


def format_temporal_parameter(parameter: TemporalParameter) -> str:
    """Format a canonical temporal parameter without its leading underscore."""

    canonical = coerce_temporal_parameter(parameter)
    if canonical is None:
        return ""
    if isinstance(canonical, RelativeParameter):
        suffix = "]" if canonical.include_endpoint else ""
        return f"{canonical.duration:g}{suffix}"
    return str(canonical.interval)


def temporal_window(
    parameter: TemporalParameter,
    anchor: TimeValue,
    universe: TimeSet,
) -> TimeSet:
    """Resolve the represented future window ``W_rho(anchor)``."""

    anchor_number = validate_time(anchor, name="anchor")
    validate_nonnegative_interval(universe, name="universe")
    canonical = coerce_temporal_parameter(parameter)
    if canonical is None:
        window = P.closed(anchor_number, P.inf)
    elif isinstance(canonical, RelativeParameter):
        upper = anchor_number + canonical.duration
        window = (
            P.closed(anchor_number, upper)
            if canonical.include_endpoint
            else P.closedopen(anchor_number, upper)
        )
    else:
        window = canonical.interval & P.closed(anchor_number, P.inf)
    return window & universe


def temporal_parameter_key(parameter: TemporalParameter) -> tuple[object, ...]:
    """Return a deterministic ordering key for a parameter."""

    canonical = coerce_temporal_parameter(parameter)
    if canonical is None:
        return (0,)
    if isinstance(canonical, RelativeParameter):
        return (1, canonical.duration, canonical.include_endpoint)
    return (2, str(canonical.interval))


def validate_time(value: object, *, name: str = "time") -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return numeric


def validate_nonnegative_interval(
    interval: TimeSet, *, name: str = "interval", connected: bool = False
) -> TimeSet:
    """Validate an interval contained in non-negative real time."""

    if not isinstance(interval, P.Interval):
        raise TypeError(f"{name} must be a portion.Interval")
    if connected and not interval.atomic:
        raise ValueError(f"{name} must be connected")
    for atom in interval:
        _validate_endpoint(atom.lower, name, lower=True)
        _validate_endpoint(atom.upper, name, lower=False)
    return interval


def _validate_endpoint(value: object, name: str, *, lower: bool) -> None:
    if value == P.inf:
        if lower:
            raise ValueError(f"{name} must be contained in non-negative real time")
        return
    if value == -P.inf:
        raise ValueError(f"{name} must be contained in non-negative real time")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise TypeError(f"{name} endpoints must be real numbers") from error
    if isnan(numeric):
        raise ValueError(f"{name} endpoints cannot be NaN")
    if lower and (numeric < 0 or numeric == float("inf")):
        raise ValueError(f"{name} must be contained in non-negative real time")
    if not lower and numeric == float("-inf"):
        raise ValueError(f"{name} must be contained in non-negative real time")
