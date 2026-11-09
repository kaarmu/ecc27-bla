"""Reusable LTMS numerics, with pyspect as the reachability solver.

Configuration imports are dependency-light. Numerical exports load lazily so
the protocol package can share configuration without importing JAX.
"""
from importlib import import_module

from .config import Axis, GridSpec, TimeWindow, WindowPolicy

_NUMERICAL = {
    "LTMSPlanner": ".planner",
    "AnalysisResult": ".planner",
    "NoCorridorError": ".planner",
    "SpatialReservation": ".reservations",
    "ControlLimits": ".control",
    "NoAdmissibleControlError": ".control",
    "create_4way": ".environment",
    "create_chaos": ".environment",
    "route_constraints": ".environment",
}

__all__ = ["Axis", "GridSpec", "TimeWindow", "WindowPolicy", *_NUMERICAL]


def __getattr__(name):
    if name not in _NUMERICAL:
        raise AttributeError(name)
    try:
        value = getattr(import_module(_NUMERICAL[name], __name__), name)
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "LTMS numerical operations require pyspect[hj_reachability]==1.2 "
            "and pillow. See README.md for the reachability experiment command."
        ) from error
    globals()[name] = value
    return value
