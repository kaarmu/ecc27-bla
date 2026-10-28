"""Sample-window selection adapted from the LTMS window helpers."""
from dataclasses import dataclass
import numpy as np

from .config import TimeWindow


@dataclass(frozen=True)
class SampleWindow:
    first: int
    last: int  # Inclusive.

    @property
    def slice(self):
        return slice(self.first, self.last + 1)

    def times(self, timeline):
        return TimeWindow(float(timeline[self.first]), float(timeline[self.last]))


def window_mask(timeline, window):
    timeline = np.asarray(timeline, dtype=float)
    if window is None:
        return np.ones(timeline.shape, dtype=bool)
    # Resolve floating representation of an endpoint, not an extra physical margin.
    tolerance = max(1.0, np.max(np.abs(timeline))) * 2e-7
    left = np.isclose(timeline, window.start, atol=tolerance, rtol=0)
    right = np.isclose(timeline, window.end, atol=tolerance, rtol=0)
    return ((timeline > window.start) | left if window.left_closed else
            (timeline > window.start) & ~left) & (
        (timeline < window.end) | right if window.right_closed else
        (timeline < window.end) & ~right)


def select_window(timeline, mask, minimum, maximum):
    """Earliest consecutive run, trimmed to maximum elapsed duration.

    Minimum/maximum refer to elapsed time, not number of grid points. Returns
    None when the samples contain no qualifying window. This is not a proof
    that the continuous-time problem is infeasible.
    """
    times = np.asarray(timeline, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if (times.ndim != 1 or mask.shape != times.shape or len(times) < 2
            or not np.isfinite(times).all() or np.any(np.diff(times) <= 0)):
        raise ValueError("need increasing time samples and an equally sized mask")
    if not np.isfinite((minimum, maximum)).all() or not 0 <= minimum <= maximum:
        raise ValueError("invalid duration limits")
    tolerance = max(1.0, abs(times[-1])) * 2e-7
    edges = np.diff(np.r_[False, mask, False].astype(int))
    for start, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
        retained = np.flatnonzero(times[start:stop] - times[start] <= maximum + tolerance)
        last = start + retained[-1]
        if times[last] - times[start] >= minimum - tolerance:
            return SampleWindow(int(start), int(last))
    return None
