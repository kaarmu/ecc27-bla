"""Exact interval operations used by relative-time temporal operators."""

from __future__ import annotations

import portion as P


def dilate_backward(interval: P.Interval, delta: float) -> P.Interval:
    """Return starts whose closed forward window intersects interval."""

    if delta == 0:
        return interval
    result = P.empty()
    for atom in interval:
        lower = atom.lower if atom.lower == -P.inf else atom.lower - delta
        result |= P.from_data([(atom.left, lower, atom.upper, atom.right)])
    return result


def minkowski_forward(interval: P.Interval, delta: float) -> P.Interval:
    """Return the Minkowski sum of interval and the closed interval ``[0, delta]``."""

    if delta == 0:
        return interval
    result = P.empty()
    for atom in interval:
        upper = atom.upper if atom.upper == P.inf else atom.upper + delta
        result |= P.from_data([(atom.left, atom.lower, upper, atom.right)])
    return result
