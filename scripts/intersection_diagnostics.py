"""Experiment B diagnostics on request A (follow-up prompt, Part 1): why checks 5-6 fail.

Run from the root: uv run --locked --extra reachability --group experiment python scripts/intersection_diagnostics.py
Writes artifacts/intersection_experiment/diagnostics/diagnostics.json (README.md is written by hand).
`--dt 0.125` runs the baseline on a finer time grid (in a subprocess of the full run).

Request A's corridor is candidate κ2 (K = [6, 7.25] s), the offer accepted in the first run.
Nothing in intersection_experiment.py or the notebook is changed; variants are local to this file.
Grid-based HJ: all sets and controls here are numerical approximations.
"""
import argparse
import json
import os
import resource
import subprocess
import sys
from math import pi
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.ndimage import distance_transform_cdt, distance_transform_edt
from scipy.interpolate import RegularGridInterpolator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'intersection_experiment' / 'diagnostics'
TOTAL, ORIGINAL = 100, 25


def load_experiment(dt):
    """Import intersection_experiment with the notebook's DT replaced (only for the finer-grid variant)."""
    import ltms_bla.scenario as scenario
    if dt != .25:
        cells = scenario.definition_cells

        def patched(root):
            out = []
            for name, source in cells(root):
                if 'HORIZON, DT = 10, .25' in source:
                    source = source.replace('HORIZON, DT = 10, .25', f'HORIZON, DT = 10, {dt}')
                out.append((name, source))
            return out
        scenario.definition_cells = patched
    import intersection_experiment as E
    return E


# ---------------------------------------------------------------- request A's corridor
def corridor_A(E):
    spec = E.SCENARIO[0]
    started = perf_counter()
    admission = E.M.admit(spec.request, ())
    seconds = perf_counter() - started
    offer = next(o for o in admission.candidates if o.index == 2)
    return offer, seconds, [c for c in E.COMPUTE if c['kind'] == 'corridor']


# ---------------------------------------------------------------- entry states
class Recorder:
    """Replays the first run's rng to recover its 25 entry states (entry choice, then four uniforms)."""
    def __init__(self, rng):
        self.rng, self.entries, self.pending = rng, [], None

    def choice(self, a):
        r = self.rng.choice(a)
        if isinstance(a, list):
            self.pending = [int(r)]
        return r

    def uniform(self, lo, hi):
        r = self.rng.uniform(lo, hi)
        self.pending.append(float(r))
        if len(self.pending) == 5:
            self.entries.append(tuple(self.pending))
        return r


def entries(E, offer):
    E.SAMPLES = ORIGINAL
    recorder = Recorder(np.random.default_rng(E.SEED))
    outcomes, _ = E.simulate(offer, E.Tube(offer.corridor), recorder)
    replay = dict(left=sum(o['left_corridor'] is not None for o in outcomes),
                  blocked=sum(o['blocked'] is not None for o in outcomes),
                  no_exit=sum(o['exited'] is None for o in outcomes))
    rng = np.random.default_rng(1)
    J = [k for k in range(len(E.T)) if E.T[k] <= .5 + 1e-6]
    extra = [(int(rng.choice(J)), rng.uniform(-.1, .1), rng.uniform(-.1, .1), rng.uniform(-pi/8, pi/8),
              rng.uniform(-.08, .08)) for _ in range(TOTAL - ORIGINAL)]
    px, py, ph, pv = E.M.ENTRY[offer.service.inbound]
    out = [(float(E.T[k]), np.array([[px + a, py + b, ph + c, pv + d]])) for k, a, b, c, d in recorder.entries + extra]
    return out, replay


# ---------------------------------------------------------------- level functions on the corridor grid
def padded_inside(E, inside):
    """Pad h periodically and x, y, v with outside cells (the grid edge bounds the map and the speed limit)."""
    wrap = np.concatenate([inside[..., -1:, :], inside, inside[..., :1, :]], axis=-2)
    return np.pad(wrap, [(0, 0), (1, 1), (1, 1), (0, 0), (1, 1)], constant_values=False)


def unpad(a):
    return a[:, 1:-1, 1:-1, 1:-1, 1:-1]


def cell_distance(E, inside, metric):
    """Per time slice: distance in grid cells from each inside cell to the nearest outside cell."""
    p = padded_inside(E, inside)
    out = np.zeros(p.shape, float)
    for k in range(len(p)):
        if p[k].any():
            out[k] = (distance_transform_cdt(p[k], metric='chessboard') if metric == 'chessboard'
                      else distance_transform_edt(p[k]))
    return unpad(out)


def eroded_level(E, corridor, cells):
    """W <= 0 on cells farther than `cells` grid cells (Euclidean) from the outside; smooth across nodes."""
    inside = corridor <= E.TOL
    d_in = cell_distance(E, inside, 'euclid')
    d_out = cell_distance(E, ~inside, 'euclid')
    return np.where(inside, cells + .5 - d_in, cells + .5 + d_out)


def gradients(E, V):
    """(∂t, ∂x, ∂y, ∂h, ∂v) of V on the grid: forward in time, central in state, periodic in h."""
    dt = np.zeros_like(V)
    dt[:-1] = (V[1:] - V[:-1]) / E.DT
    out = [dt]
    for axis, coords in zip(range(1, 5), (E.X, E.Y, E.H, E.V)):
        step = coords[1] - coords[0]
        if axis == 3:
            out.append((np.roll(V, -1, axis) - np.roll(V, 1, axis)) / (2 * step))
        else:
            out.append(np.gradient(V, step, axis=axis))
    return np.stack(out, -1)


class Field:
    """Multilinear interpolation of a (T, X, Y, H, V, ...) field; periodic h; `fill` outside the grid."""
    def __init__(self, E, values, fill):
        self.E = E
        values = np.concatenate([values, values[:, :, :, :1]], axis=3).astype(float)
        self.f = RegularGridInterpolator((E.T, E.X, E.Y, E.H_EXT, E.V), values, bounds_error=False, fill_value=fill)

    def __call__(self, t, z):
        z = np.atleast_2d(z)
        h = (z[:, 2] - self.E.H[0]) % (2 * pi) + self.E.H[0]
        return self.f(np.column_stack([np.broadcast_to(t, len(z)), z[:, 0], z[:, 1], h, z[:, 3]]))


# ---------------------------------------------------------------- driving-limit constructions
class OneStep:
    """u admissible at sample k iff the held step's end state has target(t_{k+1}) <= level. Held for Δt."""
    hold = 'sample'

    def __init__(self, E, target, level, name):
        self.E, self.target, self.level, self.name = E, target, level, name
        self.field = Field(E, target, 1.0)

    def at_nodes(self, k, states):
        E = self.E
        n = len(states)
        z, u = np.repeat(states, len(E.U_GRID), 0), np.tile(E.U_GRID, (n, 1))
        end, _ = E.step(z, u)
        return (self.field(E.T[k + 1], end) <= self.level).reshape(n, -1)

    def __call__(self, t, k, z):
        return self.at_nodes(k, z)[0]

    def drive_set(self):
        return self.target <= self.level


class Gradient:
    """u admissible iff ∂V/∂t + ∇V·f(z, u) <= 0; with margin eps, any u where V <= -eps (least-restrictive).
    Re-chosen at every substep (the condition is a continuous-time one)."""
    hold = 'substep'

    def __init__(self, E, V, eps, name):
        self.E, self.V, self.eps, self.name = E, V, eps, name
        self.grad = gradients(E, V)
        self.gfield = Field(E, self.grad, 0.0)
        self.vfield = Field(E, V, 1.0)

    def _ok(self, g, z, v):
        E = self.E
        f = np.stack([z[:, 3, None] * np.cos(z[:, 2, None]) * np.ones(len(E.U_GRID)),
                      z[:, 3, None] * np.sin(z[:, 2, None]) * np.ones(len(E.U_GRID)),
                      z[:, 3, None] * np.tan(E.U_GRID[None, :, 0]) / E.M.WHEELBASE,
                      np.broadcast_to(E.U_GRID[None, :, 1], (len(z), len(E.U_GRID)))], -1)
        rate = g[:, None, 0] + np.einsum('ni,nui->nu', g[:, 1:], f)
        ok = rate <= 1e-12
        if self.eps is not None:
            ok |= (v <= -self.eps)[:, None]
        return ok

    def at_nodes(self, k, states, index):
        return self._ok(self.grad[(k, *index)], states, self.V[(k, *index)])

    def __call__(self, t, k, z):
        return self._ok(self.gfield(t, z), z, self.vfield(t, z))[0]

    def drive_set(self):
        return self.V <= self.E.TOL


# ---------------------------------------------------------------- checks 5 and 6 for one construction
def non_blocking(E, offer, method):
    exits, last = E.exit_indices(offer), max(E.exit_indices(offer))
    zone = np.broadcast_to(np.asarray(E.M.EXIT_ZONE[offer.service.outbound](E.M.impl)), offer.corridor.shape)
    drive = method.drive_set()
    evaluated, empty, mask = 0, 0, np.zeros(offer.corridor.shape, bool)
    for k in range(last):
        inside = drive[k] & ~(zone[k] <= 0) if k in exits else drive[k]
        index = np.nonzero(inside)
        if not len(index[0]):
            continue
        states = E.grid_states(index)
        if isinstance(method, Gradient):
            ok = method.at_nodes(k, states, index).any(1)
        else:
            ok = np.concatenate([method.at_nodes(k, states[i:i + 4000]).any(1) for i in range(0, len(states), 4000)])
        evaluated += len(states)
        empty += int((~ok).sum())
        bad = tuple(i[~ok] for i in index)
        mask[(np.full(len(bad[0]), k), *bad)] = True
    return evaluated, empty, mask


def simulate(E, offer, method, starts, rng):
    """Random admissible controls from `method`; membership of the outer corridor at every substep."""
    outer = E.Tube(offer.corridor)
    origin = float(offer.service.entry[0])
    exits, last = E.exit_indices(offer), max(E.exit_indices(offer))
    sub_dt = E.DT / E.SUBSTEPS
    rows = []
    for t0, z in starts:
        k = int(round(t0 / E.DT))
        row = dict(entry_t=float(E.T[k]) + origin, entry_controls=bool(method(E.T[k], k, z).any()),
                   left=None, blocked=None, exited=None)
        while True:
            if k in exits and E.in_exit(offer, z)[0]:
                row['exited'] = float(E.T[k]) + origin
                break
            if k >= last:
                break
            if method.hold == 'sample':
                ok = method(E.T[k], k, z)
                if not ok.any():
                    row['blocked'] = float(E.T[k]) + origin
                    break
                _, path = E.step(z, E.U_GRID[rng.choice(np.flatnonzero(ok))][None])
            else:
                path, zs = [], z
                for s in range(E.SUBSTEPS):
                    ok = method(E.T[k] + s * sub_dt, k, zs)
                    if not ok.any():
                        row['blocked'] = float(E.T[k] + s * sub_dt) + origin
                        break
                    zs = E.rk4(zs, E.U_GRID[rng.choice(np.flatnonzero(ok))][None], sub_dt)
                    path.append(zs)
                if row['blocked'] is not None:
                    break
            for s, zs in enumerate(path, 1):
                if row['left'] is None and outer(E.T[k] + s * sub_dt, zs)[0] > E.TOL:
                    row['left'] = float(E.T[k] + s * sub_dt) + origin
            z, k = path[-1], k + 1
        rows.append(row)
    return rows


def summarize(rows):
    def count(rs):
        return dict(n=len(rs), left=sum(r['left'] is not None for r in rs), blocked=sum(r['blocked'] is not None for r in rs),
                    no_exit=sum(r['exited'] is None for r in rs), any=sum(r['left'] is not None or r['exited'] is None for r in rs))
    return dict(all=count(rows), original_25=count(rows[:ORIGINAL]))


def evaluate(E, offer, method, starts, coverage_set):
    t = perf_counter()
    evaluated, empty, _ = non_blocking(E, offer, method)
    nb_seconds = perf_counter() - t
    t = perf_counter()
    rows = simulate(E, offer, method, starts, np.random.default_rng(2))
    return dict(name=method.name, non_blocking=dict(cells=evaluated, empty=empty, seconds=nb_seconds),
                sampling=summarize(rows), sampling_seconds=perf_counter() - t,
                entry_covered=None if coverage_set is None else covered(E, offer, coverage_set))


def covered(E, offer, inside):
    """E_in × J (all grid points from the box bounds) inside the given set."""
    during = E.T <= .5 + 1e-6
    return bool(inside[during][(slice(None), *E.entry_points(offer.service))].all())


# ---------------------------------------------------------------- item 1: where the empty cells are
def where_empty(E, offer, mask):
    C = offer.corridor
    inside = C <= E.TOL
    cheb = cell_distance(E, inside, 'chessboard')
    idx = np.nonzero(mask)
    d, v = cheb[idx], C[idx]
    times = E.T[idx[0]] + float(offer.service.entry[0])
    # Which neighbour along each axis is outside (the grid edge counts as outside).
    p = padded_inside(E, inside)
    axis_out = {}
    for name, axis in zip('xyhv', range(1, 5)):
        lo = np.roll(p, 1, axis)[:, 1:-1, 1:-1, 1:-1, 1:-1][idx]
        hi = np.roll(p, -1, axis)[:, 1:-1, 1:-1, 1:-1, 1:-1][idx]
        axis_out[name] = int((~lo | ~hi).sum())
    vidx = idx[4]
    return dict(
        cells=int(mask.sum()),
        distance_to_boundary_cells={str(int(k)): int((d == k).sum()) for k in np.unique(d)},
        V=dict(min=float(v.min()), median=float(np.median(v)), max=float(v.max()),
               exactly_zero=int((v == 0).sum()), positive_le_tol=int(((v > 0) & (v <= E.TOL)).sum()),
               negative=int((v < 0).sum())),
        corridor_V=dict(cells=int(inside.sum()), exactly_zero=int((C[inside] == 0).sum()),
                        positive_le_tol=int(((C > 0) & (C <= E.TOL)).sum())),
        time_s={f'{float(t):g}': int((times == t).sum()) for t in np.unique(times)},
        outside_neighbour_along=axis_out,
        speed_index={f'{float(E.V[i]):.3f}': int((vidx == i).sum()) for i in range(len(E.V))},
        corridor_speed_index={f'{float(E.V[i]):.3f}': int(inside[..., i].sum()) for i in range(len(E.V))})


# ---------------------------------------------------------------- runs
def baseline_only(dt, starts):
    """For the finer time grid: the current construction only, with its cost."""
    E = load_experiment(dt)
    offer, seconds, computes = corridor_A(E)
    starts = [(t, np.array([z])) for t, z in starts]
    method = OneStep(E, offer.corridor, E.TOL, f'current, Δt = {dt}')
    result = evaluate(E, offer, method, starts, offer.corridor <= E.TOL)
    C = offer.corridor.astype(float)
    result['combination'] = evaluate(E, offer, OneStep(E, C, -.03, f'one-step, inner = {{V <= -0.03}}, Δt = {dt}'),
                                     starts, C <= -.03)
    result.update(dt=dt, exit_window=list(offer.exit), certified=bool(offer.certified),
                  corridor_seconds=[c['seconds'] for c in computes], admission_seconds=seconds,
                  tube_mib=offer.corridor.nbytes / 2**20, tube_shape=list(offer.corridor.shape),
                  peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                  note='the same 100 entry states and times as the Δt = 0.25 s runs')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dt', type=float, default=.25)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    if args.dt != .25:
        starts = json.loads(args.json.read_text())
        args.json.write_text(json.dumps(baseline_only(args.dt, starts), indent=1))
        return

    E = load_experiment(.25)
    offer, seconds, computes = corridor_A(E)
    starts, replay = entries(E, offer)
    C = offer.corridor.astype(float)
    report = dict(request='A east→east, J = [0, 0.5] s', offer=dict(candidate=offer.index, exit_window=list(offer.exit),
                  tube_sha256=E.tube_hash(offer.corridor)), samples=dict(total=TOTAL, original=ORIGINAL,
                  replay_of_first_run=replay), control_grid=f'{E.CONTROL_POINTS}x{E.CONTROL_POINTS}',
                  substeps=E.SUBSTEPS, tolerance=E.TOL, admission_seconds=seconds,
                  corridor_seconds=[c['seconds'] for c in computes])
    print('replay of the first run (25 samples):', replay, flush=True)

    base = OneStep(E, C, E.TOL, 'current: one-step, outer corridor')
    _, _, mask = non_blocking(E, offer, base)
    report['item1_where_empty'] = where_empty(E, offer, mask)
    print('item 1:', report['item1_where_empty']['distance_to_boundary_cells'], flush=True)

    configs = [(base, C <= E.TOL)]
    configs.append((Gradient(E, C, None, 'value gradient, everywhere'), C <= E.TOL))
    for cells in (0, 1, 2, 3):
        W = eroded_level(E, C, cells)
        configs.append((OneStep(E, W, 0.0, f'one-step, inner = eroded by {cells} cells'), W <= 0))
    for eps in (.005, .01, .02, .03, .05):
        configs.append((OneStep(E, C, -eps, f'one-step, inner = {{V <= -{eps}}}'), C <= -eps))
    for eps in (0.0, .005, .01, .02):
        configs.append((Gradient(E, C, eps, f'value gradient, any u where V <= -{eps}'), C <= -eps if eps else C <= 0))
    report['configurations'] = []
    for method, inner in configs:
        result = evaluate(E, offer, method, starts, inner)
        report['configurations'].append(result)
        s = result['sampling']['all']
        print(f"{method.name:48s} non-blocking {result['non_blocking']['empty']:5d}/{result['non_blocking']['cells']:5d}"
              f"  left {s['left']:3d} blocked {s['blocked']:3d} no-exit {s['no_exit']:3d} /{s['n']}"
              f"  E_in covered {result['entry_covered']}", flush=True)

    fine = OUT / 'dt_0125.json'
    fine.write_text(json.dumps([(t, z[0].tolist()) for t, z in starts]))
    subprocess.run([sys.executable, __file__, '--dt', '0.125', '--json', str(fine)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ})
    report['item5_finer_time_step'] = json.loads(fine.read_text())
    fine.unlink()
    r = report['item5_finer_time_step']
    print('Δt = 0.125:', r['non_blocking'], r['sampling']['all'], f"{r['tube_mib']:.0f} MiB", flush=True)
    print('Δt = 0.125, V <= -0.03:', r['combination']['non_blocking'], r['combination']['sampling']['all'],
          r['combination']['entry_covered'], flush=True)
    report['peak_rss_mib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    (OUT / 'diagnostics.json').write_text(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    main()
