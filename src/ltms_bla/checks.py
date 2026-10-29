"""Generic raster and straight-motion geometry. Model constants live in the notebook."""
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


def aligned_disjoint(a, depart_a, b, depart_b, dt):
    """Two reservations on one time grid, shifted to their departures, never meet."""
    offset = int(round((depart_b-depart_a)/dt))
    first, last = max(0, offset), min(len(a), offset+len(b))
    if first >= last:
        return True
    # Treat slab endpoints as closed: check neighboring time slabs too.
    for shift in (-1, 0, 1):
        lo, hi = max(first, offset+shift), min(last, offset+shift+len(b))
        if lo < hi and not boxes_disjoint(a[lo:hi], b[lo-offset-shift:hi-offset-shift]):
            return False
    return True


def boxes_covered(reserved, rx, ry, boxes):
    """Every closed workspace box (slab, x0, x1, y0, y1) meets only reserved cells."""
    dx, dy = float(rx[1]-rx[0]), float(ry[1]-ry[0])
    for slab, x0, x1, y0, y1 in boxes:
        ix = (rx+dx/2 >= x0) & (rx-dx/2 <= x1)
        iy = (ry+dy/2 >= y0) & (ry-dy/2 <= y1)
        if not reserved[slab][np.ix_(ix, iy)].all():
            return False
    return True


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
