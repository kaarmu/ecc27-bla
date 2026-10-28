"""LTMS corridor workflow adapted to pyspect TVHJImpl (see NOTICE).

This module delegates every PDE integration to pyspect. It does not implement
BLA admission, bargaining, controller certification, or automatic commitment.
"""
from dataclasses import dataclass
from math import isfinite, pi
from time import perf_counter
from types import MappingProxyType

import numpy as np
import jax.numpy as jnp
from pyspect import ContLTL, Set, TLT, UNTIL
from pyspect.impls.hj_reachability import TVHJImpl
from pyspect.systems.hj_reachability import Bicycle5D

from .config import GridSpec, WindowPolicy
from .control import ControlLimits
from .levelsets import intersection, project_onto, readonly
from .reservations import SpatialReservation
from .windows import select_window, window_mask


class NoCorridorError(ValueError):
    """The numerical procedure found no qualifying sampled window.

    This is not a proof of physical infeasibility.
    """
    def __init__(self, stage, message):
        self.stage = stage
        super().__init__(f"{stage}: {message}")


@dataclass(frozen=True, eq=False)
class AnalysisResult:
    passes: object
    times: object
    entry_window: object
    exit_window: object
    time_origin: float
    axes: tuple[str, ...]
    coordinates: tuple
    timings: object

    @property
    def corridor(self):
        return self.passes["pass4"]

    def reservation(self, *, body_radius=0.0):
        """Return an explicit projection; the caller decides whether to commit it."""
        if "x" not in self.axes or "y" not in self.axes:
            raise ValueError("workspace reservations require x and y axes")
        ix, iy = self.axes.index("x"), self.axes.index("y")
        positions = project_onto(self.corridor, 0, ix+1, iy+1) <= 0
        return SpatialReservation(self.times+self.time_origin,
                                  self.coordinates[ix], self.coordinates[iy],
                                  positions, body_radius)


class LTMSPlanner:
    """Four-pass LTMS analysis on one configured pyspect backend.

    Inputs and returned results are never modified by later evaluations. No
    reservations, cache files or sessions are created implicitly.
    """
    def __init__(self, impl, *, progress_bar=False):
        if not isinstance(impl, TVHJImpl):
            raise TypeError("LTMSPlanner requires pyspect TVHJImpl")
        self.impl = impl
        self.grid = impl.grid
        self.times = readonly(np.asarray(impl.timeline, dtype=float))
        if len(self.times) < 3 or np.any(np.diff(self.times) <= 0):
            raise ValueError("backend requires at least three increasing time samples")
        self.shape = tuple(impl.shape)
        self.dtype = np.asarray(impl.timeline).dtype
        self.progress_bar = bool(progress_bar)

    @classmethod
    def bicycle5d(cls, spec=None, *, min_steer=-pi*5/4, max_steer=pi*5/4,
                  min_accel=-1.5, max_accel=1.5, wheelbase=0.32, progress_bar=False):
        spec = GridSpec.bicycle5d() if spec is None else spec
        if tuple(a.name for a in spec.axes) != ("t", "x", "y", "h", "d", "v"):
            raise ValueError("Bicycle5D axes must be (t, x, y, h, d, v)")
        parameters = (min_steer, max_steer, min_accel, max_accel, wheelbase)
        if (not all(isfinite(v) for v in parameters) or min_steer > max_steer
                or min_accel > max_accel or wheelbase <= 0):
            raise ValueError("invalid Bicycle5D control bounds or wheelbase")
        impl = TVHJImpl(dict(cls=Bicycle5D, min_steer=min_steer, max_steer=max_steer,
                             min_accel=min_accel, max_accel=max_accel, wheelbase=wheelbase),
                        [a.pyspect_spec() for a in spec.axes], accuracy=spec.accuracy)
        return cls(impl, progress_bar=progress_bar)

    def _tube(self, values):
        values = np.asarray(values, dtype=self.dtype)
        try:
            values = np.broadcast_to(values, self.shape)
        except ValueError as error:
            raise ValueError(f"set shape {values.shape} cannot broadcast to {self.shape}") from error
        if not np.isfinite(values).all():
            raise ValueError("level sets must be finite; use a finite positive empty-set value")
        return values

    def _solve(self, direction, target, constraints=None, *, first=0, last=None):
        last = len(self.times)-1 if last is None else last
        if not 0 <= first <= last < len(self.times):
            raise ValueError("invalid solve interval")
        target = self._tube(target)[first:last+1]
        constraints = None if constraints is None else self._tube(constraints)[first:last+1]
        times = self.times[first:last+1]
        if len(times) == 1:
            return readonly(target if constraints is None else np.maximum(target, constraints))
        if direction == "forward":
            dynamics = self.impl.avoid_dynamics
        elif direction in ("reach", "avoid"):
            dynamics = self.impl.reach_dynamics if direction == "reach" else self.impl.avoid_dynamics
            times = -times
            target = np.flip(target, axis=0)
            constraints = None if constraints is None else np.flip(constraints, axis=0)
        else:
            raise ValueError("direction must be reach, avoid or forward")
        output = self.impl.solve(dynamics, self.grid, jnp.asarray(times), jnp.asarray(target),
                                 None if constraints is None else jnp.asarray(constraints),
                                 progress_bar=self.progress_bar, stack=True)
        if direction != "forward":
            output = jnp.flip(output, axis=0)
        return readonly(np.asarray(output))

    def reach(self, target, constraints=None):
        return self._solve("reach", target, constraints)

    def avoid(self, target, constraints=None):
        return self._solve("avoid", target, constraints)

    def forward(self, target, constraints=None):
        return self._solve("forward", target, constraints)

    def until(self, constraint, target, *, target_window=None):
        """Build an actual pyspect TLT and return (tree, numerical root tube).

        Time masks constrain the target. Native TVHJImpl also intersects its
        target with the constraint at witness samples; this is not a compiler
        for the paper's entire interval language or an exact satisfaction set.
        """
        target = self._tube(target)
        if target_window is not None:
            mask = window_mask(self.times, target_window).reshape((-1,) + (1,)*self.grid.ndim)
            target = np.where(mask, target, 1.0)
        tree = TLT(UNTIL("admissible", "goal"), primitives=ContLTL,
                   where={"admissible": Set(self._tube(constraint)), "goal": Set(target)})
        return tree, readonly(np.asarray(tree.realize(self.impl)))

    def _spatial_danger(self, reservations, time_origin, body_radius, clearance):
        if not reservations:
            return None
        names = tuple(self.impl.axis_name(i) for i in range(self.impl.ndim))
        if names[1:3] != ("x", "y"):
            raise ValueError("reservation avoidance currently requires x and y as the first state axes")
        x, y = (np.asarray(self.grid.coordinate_vectors[i]) for i in (0, 1))
        danger = np.zeros((len(self.times), len(x), len(y)), bool)
        for reservation in reservations:
            if not isinstance(reservation, SpatialReservation):
                raise TypeError("reservations must be SpatialReservation objects")
            danger |= reservation.on_grid(self.times+time_origin, x, y,
                                          ego_radius=body_radius, clearance=clearance)
        # A bitmap is not a signed distance function. Values encode occupied
        # grid cells only; physical margins were applied in workspace units.
        return np.where(danger, -1.0, 1.0).reshape(danger.shape + (1,)*(self.grid.ndim-2))

    def analyze(self, *, entry, goal, constraints, entry_window=None, exit_window=None,
                policy=None, reservations=(), time_origin=0.0, body_radius=0.0,
                clearance=0.0, offline=None):
        """Compute independent pass1–pass4 tubes for one candidate.

        Windows use local solver time; time_origin aligns explicit reservations
        in absolute time. offline optionally supplies an existing pass1 tube.
        Returned windows describe sampled feasibility, not every entry state.
        """
        policy = WindowPolicy() if policy is None else policy
        if not isinstance(policy, WindowPolicy):
            raise TypeError("policy must be WindowPolicy")
        if not all(isfinite(v) for v in (time_origin, body_radius, clearance)) or min(body_radius, clearance) < 0:
            raise ValueError("invalid time origin, body radius or clearance")
        entry, goal, constraints = map(self._tube, (entry, goal, constraints))
        timings = {}
        started = perf_counter()
        pass1 = self.reach(goal, constraints) if offline is None else readonly(self._tube(offline))
        timings["pass1"] = perf_counter()-started

        started = perf_counter()
        danger = self._spatial_danger(tuple(reservations), time_origin, body_radius, clearance)
        pass2 = pass1 if danger is None else self.reach(goal, intersection(pass1, -danger))
        timings["pass2"] = perf_counter()-started

        started = perf_counter()
        entry_target = intersection(pass2, entry)
        available = (entry_target <= 0).any(axis=tuple(range(1, len(self.shape))))
        selected_entry = select_window(self.times, available & window_mask(self.times, entry_window),
                                       policy.min_entry, policy.max_entry)
        if selected_entry is None:
            raise NoCorridorError("pass3", "no qualifying sampled entry window")
        seed_mask = np.zeros(len(self.times), bool)
        seed_mask[selected_entry.slice] = True
        entry_target = np.where(seed_mask.reshape((-1,)+(1,)*self.grid.ndim), entry_target, 1.0)
        pass3 = np.ones(self.shape, dtype=self.dtype)
        pass3[selected_entry.first:] = self._solve("forward", entry_target, pass2,
                                                   first=selected_entry.first)
        pass3 = readonly(pass3)
        timings["pass3"] = perf_counter()-started

        started = perf_counter()
        exit_target = intersection(pass3, goal)
        available = (exit_target <= 0).any(axis=tuple(range(1, len(self.shape))))
        selected_exit = select_window(self.times, available & window_mask(self.times, exit_window),
                                      policy.min_exit, policy.max_exit)
        if selected_exit is None or selected_exit.last < selected_entry.first:
            raise NoCorridorError("pass4", "no qualifying sampled exit window")
        goal_mask = np.zeros(len(self.times), bool)
        goal_mask[selected_exit.slice] = True
        exit_target = np.where(goal_mask.reshape((-1,)+(1,)*self.grid.ndim), exit_target, 1.0)
        pass4 = np.ones(self.shape, dtype=self.dtype)
        pass4[selected_entry.first:selected_exit.last+1] = self._solve(
            "reach", exit_target, pass3, first=selected_entry.first, last=selected_exit.last)
        pass4 = readonly(pass4)
        valid_entry = (intersection(pass4, entry) <= 0).any(axis=tuple(range(1, len(self.shape))))
        final_entry = select_window(self.times, valid_entry & seed_mask,
                                    policy.min_entry, policy.max_entry)
        if final_entry is None:
            raise NoCorridorError("pass4", "exit pruning removed the sampled entry window")
        timings["pass4"] = perf_counter()-started
        timings["total"] = sum(timings.values())
        return AnalysisResult(MappingProxyType(dict(pass1=pass1, pass2=pass2, pass3=pass3, pass4=pass4)),
                              self.times, final_entry.times(self.times), selected_exit.times(self.times),
                              float(time_origin), tuple(self.impl.axis_name(i+1) for i in range(self.grid.ndim)),
                              tuple(readonly(np.asarray(a)) for a in self.grid.coordinate_vectors),
                              MappingProxyType(timings))

    def control_limits(self, tube, state, time_index):
        """Legacy LTMS finite-difference driving-limit approximation.

        This is numerical evidence, not a verified continuous-time safety
        filter. Out-of-domain states and the terminal time sample are rejected.
        """
        tube = self._tube(tube)
        if type(time_index) is not int or not 0 <= time_index < len(self.times)-1:
            raise ValueError("control limits require a nonterminal time index")
        state = np.asarray(state, dtype=float).copy()
        if state.shape != (self.grid.ndim,) or not np.isfinite(state).all():
            raise ValueError("invalid vehicle state")
        for i in range(self.grid.ndim):
            lo, hi = float(self.grid.domain.lo[i]), float(self.grid.domain.hi[i])
            if self.grid._is_periodic_dim[i]:
                state[i] = (state[i]-lo) % (hi-lo) + lo
            elif not lo <= state[i] <= hi:
                raise ValueError("vehicle state is outside the grid")
        index = tuple(int(i) for i in np.asarray(self.grid.nearest_index(jnp.asarray(state))))
        gradients = []
        values = tube[time_index]
        for axis, i in enumerate(index):
            before, after = list(index), list(index)
            n = self.grid.shape[axis]
            if self.grid._is_periodic_dim[axis]:
                before[axis], after[axis], width = (i-1) % n, (i+1) % n, 2
            else:
                before[axis], after[axis] = max(0, i-1), min(n-1, i+1)
                width = after[axis]-before[axis]
            gradients.append((values[tuple(after)]-values[tuple(before)]) /
                             (width*float(self.grid.spacings[axis])))
        gradient = np.asarray(gradients)
        dynamics = self.impl.reach_dynamics
        f = np.asarray(dynamics.open_loop_dynamics(jnp.asarray(state), self.times[time_index]))
        g = np.asarray(dynamics.control_jacobian(jnp.asarray(state), self.times[time_index]))
        dt = self.times[time_index+1]-self.times[time_index]
        return ControlLimits(float(tube[(time_index+1, *index)] + dt*(gradient @ f)),
                             dt*(gradient @ g), np.asarray(dynamics.control_space.lo),
                             np.asarray(dynamics.control_space.hi))
