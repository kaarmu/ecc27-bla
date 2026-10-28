"""Explicit sampled spatial reservations, without a mutable session manager."""
from dataclasses import dataclass
from math import ceil
import numpy as np

from .levelsets import readonly


def dilate_xy(mask, x, y, radius):
    """Dilate grid-point occupancy by a disk in workspace units.

    This does not add a discretization/continuous-time safety margin. Callers
    must supply any additional cell, tracking or swept-motion allowance.
    """
    if not np.isfinite(radius) or radius < 0:
        raise ValueError("radius must be finite and nonnegative")
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 3 or mask.shape[1:] != (len(x), len(y)):
        raise ValueError("expected (time, x, y) occupancy")
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    if dx <= 0 or dy <= 0:
        raise ValueError("spatial coordinates must increase")
    result = np.zeros_like(mask)
    nx, ny = mask.shape[1:]
    for ix in range(-min(ceil(radius/dx), nx-1), min(ceil(radius/dx), nx-1)+1):
        for iy in range(-min(ceil(radius/dy), ny-1), min(ceil(radius/dy), ny-1)+1):
            if np.hypot(ix*dx, iy*dy) > radius + 1e-10:
                continue
            sx, tx = slice(max(0, -ix), min(nx, nx-ix)), slice(max(0, ix), min(nx, nx+ix))
            sy, ty = slice(max(0, -iy), min(ny, ny-iy)), slice(max(0, iy), min(ny, ny+iy))
            result[:, tx, ty] |= mask[:, sx, sy]
    return result


@dataclass(frozen=True, eq=False)
class SpatialReservation:
    """Possible reference-point positions at absolute time samples.

    The full vehicle-state corridor remains in AnalysisResult. This is its
    workspace projection, with a separately declared body radius.
    """
    times: object
    x: object
    y: object
    positions: object
    body_radius: float = 0.0

    def __post_init__(self):
        for name in ("times", "x", "y"):
            values = np.asarray(getattr(self, name), dtype=float)
            if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all() or np.any(np.diff(values) <= 0):
                raise ValueError(f"{name} must contain increasing finite coordinates")
            if name != "times" and not np.allclose(np.diff(values), np.diff(values)[0]):
                raise ValueError("spatial axes must be uniform")
            object.__setattr__(self, name, readonly(values))
        positions = np.asarray(self.positions, dtype=bool)
        if positions.shape != (len(self.times), len(self.x), len(self.y)):
            raise ValueError("reservation shape disagrees with its axes")
        if not np.isfinite(self.body_radius) or self.body_radius < 0:
            raise ValueError("body radius must be finite and nonnegative")
        object.__setattr__(self, "positions", readonly(positions))

    def on_grid(self, times, x, y, *, ego_radius=0.0, clearance=0.0):
        """Conservatively union bracketing samples of overlapping time cells.

        Different spatial grids are rejected rather than silently resampled.
        Unions cover the stored *samples*, not unknown motion between samples.
        """
        times = np.asarray(times, dtype=float)
        for wanted, stored in ((x, self.x), (y, self.y)):
            if np.shape(wanted) != stored.shape or not np.allclose(wanted, stored, atol=1e-7, rtol=0):
                raise ValueError("reservation and query spatial grids differ")
        if (times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all()
                or np.any(np.diff(times) <= 0)):
            raise ValueError("query times must increase")
        if any(not np.isfinite(v) or v < 0 for v in (ego_radius, clearance)):
            raise ValueError("radii and clearance must be finite and nonnegative")
        result = np.zeros((len(times), len(x), len(y)), bool)
        for i, start in enumerate(times):
            end = times[min(i+1, len(times)-1)]
            if end < self.times[0] or start > self.times[-1]:
                continue
            left = max(0, np.searchsorted(self.times, start, side="right")-1)
            right = min(len(self.times)-1, np.searchsorted(self.times, end, side="left"))
            result[i] = self.positions[left:right+1].any(axis=0)
        return dilate_xy(result, self.x, self.y, self.body_radius + ego_radius + clearance)
