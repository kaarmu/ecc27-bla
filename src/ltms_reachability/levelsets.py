"""LTMS set helpers adapted from safe_intersections (see NOTICE).

Negative sublevel sets are inside. These are numerical set operations, not a
general exact set algebra or finite-body collision certificate.
"""
import numpy as np


def readonly(values):
    result = np.array(values, copy=True)
    result.setflags(write=False)
    return result


def complement(values):
    return -np.asarray(values)


def union(first, *others):
    result = np.asarray(first)
    for other in others:
        result = np.minimum(result, other)
    return result


def intersection(first, *others):
    result = np.asarray(first)
    for other in others:
        result = np.maximum(result, other)
    return result


def project_onto(values, *axes, keepdims=False):
    values = np.asarray(values)
    if not axes or len(set(axes)) != len(axes) or any(a < 0 or a >= values.ndim for a in axes):
        raise ValueError("projection needs unique valid axes")
    reduced = tuple(i for i in range(values.ndim) if i not in axes)
    result = values.min(axis=reduced, keepdims=keepdims)
    if not keepdims and tuple(axes) != tuple(sorted(axes)):
        result = result.transpose([sorted(axes).index(a) for a in axes])
    return result


def _coordinate(grid, axis):
    shape = [1] * grid.ndim
    shape[axis] = grid.shape[axis]
    return np.asarray(grid.coordinate_vectors[axis]).reshape(shape)


def hyperplane(grid, normal, offset, axes=None):
    """Legacy LTMS convention: normal dot (state - offset) <= 0."""
    axes = tuple(range(len(normal))) if axes is None else tuple(axes)
    if len(normal) != len(offset) or len(axes) != len(normal):
        raise ValueError("normal, offset and axes must have equal lengths")
    value = 0.0
    for axis, n, origin in zip(axes, normal, offset):
        value = value + n * (_coordinate(grid, axis) - origin)
    return np.broadcast_to(value, tuple(grid.shape))


def rectangle(grid, target_min, target_max, axes=None):
    if np.isscalar(axes):
        axes, target_min, target_max = (axes,), (target_min,), (target_max,)
    axes = tuple(range(len(target_min))) if axes is None else tuple(axes)
    if len(target_min) != len(target_max) or len(axes) != len(target_min):
        raise ValueError("bounds and axes must have equal lengths")
    result = -np.inf
    for axis, lower, upper in zip(axes, target_min, target_max):
        coordinate = _coordinate(grid, axis)
        low, high = lower - coordinate, coordinate - upper
        # Wrapped heading intervals cross the periodic seam.
        if lower > upper:
            periodic = bool(grid._is_periodic_dim[axis])
            if not periodic:
                raise ValueError("reversed bounds require a periodic axis")
            value = np.minimum(low, high)
        else:
            value = np.maximum(low, high)
        result = np.maximum(result, value)
    return np.broadcast_to(result, tuple(grid.shape))
