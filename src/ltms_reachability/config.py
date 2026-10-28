"""Grid and window configuration independent of NumPy/JAX."""
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite, pi
import json


def _finite(value, name):
    if isinstance(value, bool) or not isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return float(value)


@dataclass(frozen=True)
class Axis:
    name: str
    lower: float
    upper: float
    points: int
    periodic: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or self.name.startswith("*"):
            raise ValueError("axis name must be nonempty, without the periodic '*' prefix")
        object.__setattr__(self, "lower", _finite(self.lower, "lower bound"))
        object.__setattr__(self, "upper", _finite(self.upper, "upper bound"))
        if self.lower >= self.upper or type(self.points) is not int or self.points < 3:
            raise ValueError("an axis needs increasing bounds and at least three points")
        if type(self.periodic) is not bool:
            raise ValueError("periodic must be a boolean")

    def pyspect_spec(self):
        return dict(name=("*" if self.periodic else "") + self.name,
                    bounds=[self.lower, self.upper], points=self.points)


@dataclass(frozen=True)
class GridSpec:
    axes: tuple[Axis, ...]
    accuracy: str = "low"

    def __post_init__(self):
        axes = tuple(self.axes)
        if (len(axes) < 2 or not all(isinstance(a, Axis) for a in axes)
                or axes[0].name != "t" or axes[0].periodic
                or len({a.name for a in axes}) != len(axes)):
            raise ValueError("grid needs unique axes starting with nonperiodic time 't'")
        if self.accuracy not in ("low", "medium", "high", "very_high"):
            raise ValueError("unsupported pyspect accuracy")
        object.__setattr__(self, "axes", axes)

    @classmethod
    def bicycle5d(cls, *, horizon=15.0, time_step=0.2,
                  shape=(41, 41, 25, 5, 7), accuracy="low"):
        horizon, time_step = _finite(horizon, "horizon"), _finite(time_step, "time step")
        if horizon <= 0 or time_step <= 0 or len(shape) != 5:
            raise ValueError("positive horizon/step and five spatial dimensions required")
        intervals = round(horizon / time_step)
        if intervals < 2 or abs(intervals * time_step - horizon) > 1e-9 * max(1, horizon):
            raise ValueError("horizon must contain an integral number (at least two) of steps")
        bounds = ((-2, 2), (-2, 2), (-pi, pi), (-pi/4, pi/4), (0, 0.6))
        axes = (Axis("t", 0, horizon, intervals + 1),) + tuple(
            Axis(name, *bound, n, periodic=name == "h")
            for name, bound, n in zip(("x", "y", "h", "d", "v"), bounds, shape)
        )
        return cls(axes, accuracy)

    def fingerprint(self, *, dynamics=None):
        payload = {"axes": [a.pyspect_spec() for a in self.axes],
                   "accuracy": self.accuracy, "dynamics": dynamics}
        return sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class TimeWindow:
    """Window in the solver's local time coordinates, with explicit endpoints."""
    start: float
    end: float
    left_closed: bool = True
    right_closed: bool = True

    def __post_init__(self):
        object.__setattr__(self, "start", _finite(self.start, "window start"))
        object.__setattr__(self, "end", _finite(self.end, "window end"))
        if (self.start > self.end or type(self.left_closed) is not bool
                or type(self.right_closed) is not bool):
            raise ValueError("invalid window")
        if self.start == self.end and not (self.left_closed and self.right_closed):
            raise ValueError("a singleton window must include its point")


@dataclass(frozen=True)
class WindowPolicy:
    """Durations between the first and last retained time samples."""
    min_entry: float = 1.0
    max_entry: float = 2.0
    min_exit: float = 1.0
    max_exit: float = 2.0

    def __post_init__(self):
        for name in ("min_entry", "max_entry", "min_exit", "max_exit"):
            value = _finite(getattr(self, name), name)
            if value < 0:
                raise ValueError("window durations must be nonnegative")
            object.__setattr__(self, name, value)
        if self.min_entry > self.max_entry or self.min_exit > self.max_exit:
            raise ValueError("minimum duration exceeds maximum")
