"""Generic raster geometry. Model constants live in the notebook."""
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
