"""Numerical driving limits adapted from LTMS Solver.lrcs (see NOTICE)."""
from dataclasses import dataclass
import numpy as np
from .levelsets import readonly


class NoAdmissibleControlError(ValueError):
    pass


@dataclass(frozen=True, eq=False)
class ControlLimits:
    """Box-bounded controls satisfying the numerical inequality a + b @ u <= 0."""
    a: float
    b: object
    lower: object
    upper: object

    def __post_init__(self):
        b, lower, upper = (np.asarray(x, dtype=float) for x in (self.b, self.lower, self.upper))
        if (b.ndim != 1 or b.shape != lower.shape or b.shape != upper.shape
                or not all(np.isfinite(x).all() for x in (b, lower, upper))
                or not np.isfinite(self.a) or np.any(lower > upper)):
            raise ValueError("invalid control half-space or bounds")
        for name, value in (("b", b), ("lower", lower), ("upper", upper)):
            object.__setattr__(self, name, readonly(value))

    def contains(self, control, *, tolerance=1e-9):
        control = np.asarray(control, dtype=float)
        return bool(control.shape == self.b.shape and np.isfinite(control).all()
                    and np.all(control >= self.lower-tolerance)
                    and np.all(control <= self.upper+tolerance)
                    and self.a + self.b @ control <= tolerance)

    def project(self, nominal):
        """Euclidean projection into the control box and half-space."""
        nominal = np.asarray(nominal, dtype=float)
        if nominal.shape != self.b.shape or not np.isfinite(nominal).all():
            raise ValueError("nominal control has wrong shape or nonfinite values")
        minimum = self.a + self.b @ np.where(self.b >= 0, self.lower, self.upper)
        if minimum > 1e-10:
            raise NoAdmissibleControlError("numerical control set is empty")
        clipped = np.clip(nominal, self.lower, self.upper)
        if self.contains(clipped):
            return readonly(clipped)
        low, high = 0.0, 1.0
        for _ in range(100):
            if self.a + self.b @ np.clip(nominal-high*self.b, self.lower, self.upper) <= 1e-12:
                break
            high *= 2
        else:
            raise NoAdmissibleControlError("control projection failed to bracket a solution")
        for _ in range(80):
            middle = (low+high)/2
            if self.a + self.b @ np.clip(nominal-middle*self.b, self.lower, self.upper) <= 0:
                high = middle
            else:
                low = middle
        return readonly(np.clip(nominal-high*self.b, self.lower, self.upper))

    def sample(self, points=51):
        if type(points) is not int or points < 2:
            raise ValueError("at least two control samples required")
        axes = tuple(np.linspace(lo, hi, points) for lo, hi in zip(self.lower, self.upper))
        grids = np.meshgrid(*axes, indexing="ij")
        mask = self.a + sum(b*g for b, g in zip(self.b, grids)) <= 0
        return tuple(readonly(a) for a in axes), readonly(mask)
