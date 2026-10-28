"""Independent numerical checks; no LTMS generation/set-operation helpers."""
import numpy as np


def boxes_disjoint(first, second):
    """Reject overlapping or touching closed raster cells at shared time slabs."""
    if first.shape != second.shape:
        raise ValueError('reservation grids differ')
    nx, ny = first.shape[1:]
    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            a = first[:, max(0, ix):min(nx, nx+ix), max(0, iy):min(ny, ny+iy)]
            b = second[:, max(0, -ix):min(nx, nx-ix), max(0, -iy):min(ny, ny-iy)]
            if np.any(a & b):
                return False
    return True


def rollout_checks(times, states, controls, *, tube, axes, body_radius,
                   goal_x=1.4, managed_halfwidth=1.2, tolerance=2e-5):
    # Reference controller: zero steering rate and acceleration. Check the
    # analytic solution against the Bicycle5D equations, with h=d=0.
    step = np.diff(times)
    rhs = np.column_stack((states[:-1, 4]*np.cos(states[:-1, 2]),
                           states[:-1, 4]*np.sin(states[:-1, 2]),
                           states[:-1, 4]*np.tan(states[:-1, 3])/.32,
                           controls[:-1, 0], controls[:-1, 1]))
    residual = np.max(abs(np.diff(states, axis=0)-step[:, None]*rhs))
    indices = [np.abs(np.asarray(a)[:, None]-q[None, :]).argmin(axis=0)
               for a, q in zip(axes, [times, *states.T])]
    values = tube[tuple(indices)]
    # The copied eastbound lane is y in [-.8,0], except the central square.
    road_ok = bool(np.all((states[:, 1]-body_radius >= -.8-tolerance) &
                          (states[:, 1]+body_radius <= tolerance)))
    clear_ok = bool(states[-1, 0] >= goal_x-tolerance and
                    states[-1, 0]-body_radius > managed_halfwidth and residual < 1e-8)
    return dict(rollout_inside=bool(values.max() <= tolerance),
                rollout_max_value=float(values.max()), road_ok=road_ok,
                clear_ok=clear_ok, input_ok=bool(np.max(abs(controls)) <= .1),
                dynamics_residual=float(residual))


def minimum_body_gap(first_times, first_states, second_times, second_states, radius):
    start, stop = max(first_times[0], second_times[0]), min(first_times[-1], second_times[-1])
    if start > stop:
        return float('inf')
    # Each supplied path is straight with constant speed: squared relative
    # separation is quadratic, so its clipped minimizer checks all time.
    a0 = np.array([np.interp(start, first_times, first_states[:, i]) for i in (0, 1)])
    b0 = np.array([np.interp(start, second_times, second_states[:, i]) for i in (0, 1)])
    av = (first_states[-1, :2]-first_states[0, :2])/(first_times[-1]-first_times[0])
    bv = (second_states[-1, :2]-second_states[0, :2])/(second_times[-1]-second_times[0])
    delta, velocity = a0-b0, av-bv
    tau = 0 if velocity@velocity == 0 else np.clip(-(delta@velocity)/(velocity@velocity), 0, stop-start)
    return float(np.linalg.norm(delta+tau*velocity)-2*radius)
