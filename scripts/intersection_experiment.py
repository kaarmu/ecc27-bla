"""Section V, Experiment B: four-way intersection, five sequential crossing requests.

Run from the root: uv run --locked --extra reachability --group experiment python scripts/intersection_experiment.py
Writes artifacts/intersection_experiment/{log.json,table.csv,figure.pdf,environment.json}.

The model, map, grid, TLT query of φ_j and the corridor passes are notebooks/ltms_blas.ipynb's
definition cells, compiled verbatim (ltms_bla.scenario.load_method). The protocol stages are
bla_stages.py, shared with Experiment A (charging): only admit, generate and the utilities differ.
New here: the scenario and utilities, offer records, the candidate-worker test, the checks, the
driving limits for Bicycle4D, the sampled simulation and the outputs.

Grid-based HJ: every set below is a sampled, numerical approximation, not an exact set.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from hashlib import sha256
from importlib.metadata import version, PackageNotFoundError
from math import pi
from pathlib import Path
from time import perf_counter
import csv
import json
import platform
import resource
import sys

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from ltms_bla.scenario import load_method
from bla_stages import Backend, Checks, Protocol, attempt, same_protocol_code, validators_pass

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'intersection_experiment'
M = load_method(ROOT)                    # the notebook's definitions; M.admit.__globals__ is their namespace
GRID = tuple(F(q) for q in range(0, 21))  # €0, €1, ..., €20, as in Experiment A
ROUND_BUDGET = 4
PROTOCOL = Protocol(GRID, ROUND_BUDGET)
OWNER = dict(target=F(6), minimum=F(1))   # u_m = q - kappa |Phi|
KAPPA = F(1)                              # € per m²·s of reserved space-time
SEED, SAMPLES = 0, 25                     # sampled entries per committed vehicle
CONTROL_POINTS, SUBSTEPS = 9, 10          # control grid per axis; RK4 substeps per time step
TOL, BODY = M.TOLERANCE, M.BODY           # corridor membership V <= TOL; vehicle radius [m]

T, X, Y, H, V = (np.asarray(a, dtype=float) for a in (M.impl.timeline, M.x, M.y, M.h, M.v))
DT = float(M.DT)
SPACING = [F(4, len(X) - 1), F(4, len(Y) - 1)]
assert np.allclose(np.diff(X), float(SPACING[0])) and np.allclose(np.diff(Y), float(SPACING[1]))
CELL = SPACING[0] * SPACING[1] * F(DT)    # m²·s per reserved (t, x, y) cell


# ---------------------------------------------------------------- instrumentation of the notebook's numerics
COMPUTE = []  # one row per TLT (sat∃) or corridor computation


def _timed(kind, function):
    def wrapper(service, *args):
        started, ok = perf_counter(), False
        try:
            result = function(service, *args)
            ok = True
            return result
        finally:
            COMPUTE.append(dict(kind=kind, client=service.client, J=[float(e) for e in service.entry],
                                exit=list(args[-1]) if kind == 'corridor' else None, ok=ok,
                                seconds=perf_counter() - started))
    return wrapper


NAMESPACE = M.admit.__globals__
NAMESPACE['crossing_set'] = _timed('sat', NAMESPACE['crossing_set'])
NAMESPACE['corridor'] = _timed('corridor', NAMESPACE['corridor'])


# ---------------------------------------------------------------- scenario
def window(a):
    return (F(a), F(a) + F(1, 2))  # J = [a, a + 0.5] s


@dataclass(frozen=True)
class Spec:
    branch: str
    received: F
    request: object
    v: F                  # u_v = v - q - gamma * (exit time after the requested J start)
    gamma: F
    client_target: F
    client_minimum: F = F(1)

    @property
    def targets(self):
        return {'owner': OWNER['target'], 'client': self.client_target}

    @property
    def minima(self):
        return {'owner': OWNER['minimum'], 'client': self.client_minimum}


def crossing(k, inbound, outbound, a, *alternatives):
    service = M.Crossing(k, inbound, outbound, window(a))
    return M.Request(k, service, tuple(M.Crossing(k, inbound, outbound, window(b)) for b in alternatives))


SCENARIO = (
    Spec('as requested, accepted', F(-5), crossing('A', 'east', 'east', 0), F(20), F(1, 2), F(5)),
    Spec('simultaneous, non-conflicting', F(-4), crossing('B', 'west', 'west', 0), F(20), F(1, 2), F(5)),
    Spec('NO-BLA, budget exhausted', F(-3), crossing('C', 'south', 'south', 4), F(8), F(1, 2), F(4)),
    Spec('rejected on price, then accepted', F(-2), crossing('D', 'east', 'south', 3), F(20), F(1, 2), F(11)),
    Spec('entry condition fails; adapted', F(-1), crossing('E', 'north', 'west', 1, 5), F(24), F(1, 4), F(8)),
)


# ---------------------------------------------------------------- domain backend (intersection)
@dataclass(frozen=True, eq=False)
class Committed:
    """What the notebook's admit reads from a standing BLA: its corridor (offer) and contract."""
    offer: object

    @property
    def contract(self):
        return self.offer.contract


LAST = {}  # the notebook's per-service fates and the compute count at the end of admission


def intersection_admit(request, commitment, resources, now):
    ledger = tuple(Committed(o) for o in resources)
    assert M.standing(ledger) == commitment, 'commitment and committed corridors disagree'
    tried = []
    admission = M.admit(request, ledger, tried)
    LAST.update(tried=tuple(tried), computed=len(COMPUTE))
    return admission


def intersection_generate(admission):
    return M.generate(() if admission is None else admission.candidates)


def volume(offer):
    """|Phi|: reserved (t, x, y) cells of the corridor's workspace projection, in m²·s."""
    return int(offer.reserved.positions.sum()) * CELL


def intersection_utility(spec, offers):
    """u_m = q - kappa |Phi|; u_v = v - q - gamma * (latest exit - requested J start)."""
    a = spec.request.service.entry[0]

    def utility(party, offer, price):
        if party == 'owner':
            return price - KAPPA * volume(offer)
        return spec.v - price - spec.gamma * (F(offer.exit[1]) - a)
    return utility


BACKEND = Backend(admit=intersection_admit, generate=intersection_generate, utility=intersection_utility,
                  validate_offers=M.validate_offers)


# ---------------------------------------------------------------- offer records
def tube_hash(values):
    values = np.ascontiguousarray(values)
    return sha256(f'{values.dtype}{values.shape}'.encode() + values.tobytes()).hexdigest()


GRID_META = dict(axes=[{k: v for k, v in a.items()} for a in M.AXES], accuracy='medium',
                 dynamics=dict(cls='Bicycle4D', wheelbase=M.WHEELBASE, **M.CONTROLS), solver='pyspect TVHJImpl')
GRID_ID = sha256(json.dumps(GRID_META, sort_keys=True, default=float).encode()).hexdigest()[:16]
RECORDS = {}  # id(offer) -> record; tubes stay in this process, referenced by hash


def commitment_version(resources):
    ids = [RECORDS[id(o)]['id'] for o in resources]
    return dict(n=len(ids), digest=sha256(json.dumps(ids).encode()).hexdigest()[:16])


def offer_record(offer, resources):
    if id(offer) in RECORDS:
        return RECORDS[id(offer)]
    s, digest = offer.service, tube_hash(offer.corridor)
    theta = dict(client=s.client, inbound=s.inbound, outbound=s.outbound, J=[float(e) for e in s.entry])
    oid = sha256(json.dumps(dict(theta=theta, exit=list(offer.exit), tube=digest)).encode()).hexdigest()[:16]
    tol_only = int(((offer.corridor > 0) & (offer.corridor <= TOL)).sum())
    RECORDS[id(offer)] = record = dict(
        id=oid, theta=theta, time_origin=float(s.entry[0]), entry_window=[float(e) for e in s.entry],
        exit_window=[float(e) for e in offer.exit], candidate=offer.index,
        tube=dict(sha256=digest, shape=list(offer.corridor.shape), dtype=str(offer.corridor.dtype),
                  nbytes=int(offer.corridor.nbytes), writeable=bool(offer.corridor.flags.writeable)),
        reserved_cells=int(offer.reserved.positions.sum()), volume_m2s=str(volume(offer)),
        grid=GRID_ID, commitment_version=commitment_version(resources),
        evidence=dict(certified=bool(offer.certified), cells_0_lt_V_le_tol=tol_only))
    return record


# ---------------------------------------------------------------- independent grid checks
def periodic_distance(a, b):
    return np.abs((a - b + pi) % (2 * pi) - pi)


def entry_points(service):
    """Grid points of E_in, from the box bounds (tolerance 1e-6), not from pyspect's set builder."""
    px, py, ph, pv = M.ENTRY[service.inbound]
    e = 1e-6
    mx, my = np.abs(X - px) <= .1 + e, np.abs(Y - py) <= .1 + e
    mh, mv = periodic_distance(H, ph) <= pi / 8 + e, np.abs(V - pv) <= .08 + e
    return np.ix_(mx, my, mh, mv)


def coverage(corridor, service):
    """(covered, points): corridor <= TOL at every grid point of E_in x J (local J samples)."""
    a, b = service.entry
    during = T <= float(b - a) + 1e-6
    block = corridor[during][(slice(None), *entry_points(service))]
    return bool((block <= TOL).all()), int(block.size)


def rules_cells(offer):
    """Corridor cells outside C_j (the inbound and outbound roads)."""
    s = offer.service
    road = np.minimum(np.asarray(M.ROAD[s.inbound](M.impl)), np.asarray(M.ROAD[s.outbound](M.impl)))
    return int(((offer.corridor <= TOL) & (np.broadcast_to(road, offer.corridor.shape) > TOL)).sum())


def endpoint_cells(offer):
    """Corridor cells at J's first sample outside the entry zone, and at K's last sample outside E_out."""
    s = offer.service
    first = int(np.flatnonzero((offer.corridor <= TOL).any(axis=(1, 2, 3, 4)))[0])
    last = int(np.flatnonzero((offer.corridor <= TOL).any(axis=(1, 2, 3, 4)))[-1])
    zone_in = np.broadcast_to(np.asarray(M.ENTRY_ZONE[s.inbound](M.impl)), offer.corridor.shape)
    zone_out = np.broadcast_to(np.asarray(M.EXIT_ZONE[s.outbound](M.impl)), offer.corridor.shape)
    return (int(((offer.corridor[first] <= TOL) & (zone_in[first] > TOL)).sum()),
            int(((offer.corridor[last] <= TOL) & (zone_out[last] > TOL)).sum()),
            float(T[first] + float(s.entry[0])), float(T[last] + float(s.entry[0])))


def dilate(mask, radius):
    out = np.zeros_like(mask)
    dx, dy = X[1] - X[0], Y[1] - Y[0]
    nx, ny = mask.shape[-2:]
    for i in range(-int(np.ceil(radius / dx)), int(np.ceil(radius / dx)) + 1):
        for j in range(-int(np.ceil(radius / dy)), int(np.ceil(radius / dy)) + 1):
            if np.hypot(i * dx, j * dy) > radius + 1e-10:
                continue
            sx, tx = slice(max(0, -i), min(nx, nx - i)), slice(max(0, i), min(nx, nx + i))
            sy, ty = slice(max(0, -j), min(ny, ny - j)), slice(max(0, j), min(ny, ny + j))
            out[..., tx, ty] |= mask[..., sx, sy]
    return out


def occupancy(offer):
    """{absolute time step index: (x, y) cells}, corridor <= TOL projected over (h, v)."""
    cells = (offer.corridor <= TOL).any(axis=(3, 4))
    origin = round(float(offer.service.entry[0]) / DT)
    return {origin + k: cells[k] for k in range(len(T)) if cells[k].any()}


def conflict_cells(later, earlier):
    """Cells of `later` at t_i within 2*BODY of `earlier` at t_i or t_{i+1} (the D_j sweep)."""
    a, b = occupancy(later), occupancy(earlier)
    count = 0
    for i, cells in a.items():
        near = np.zeros_like(cells)
        for k in (i, i + 1):
            if k in b:
                near |= b[k]
        if near.any():
            count += int((cells & dilate(near, 2 * BODY)).sum())
    return count


# ---------------------------------------------------------------- driving limits and simulation (Bicycle4D)
H_EXT = np.r_[H, H[0] + 2 * pi]
U_GRID = np.stack(np.meshgrid(np.linspace(M.CONTROLS['min_steer'], M.CONTROLS['max_steer'], CONTROL_POINTS),
                              np.linspace(M.CONTROLS['min_accel'], M.CONTROLS['max_accel'], CONTROL_POINTS),
                              indexing='ij'), -1).reshape(-1, 2)


class Tube:
    """Multilinear interpolation of a corridor over (t, x, y, h, v); periodic h; outside the grid = outside."""
    def __init__(self, corridor):
        values = np.concatenate([corridor, corridor[:, :, :, :1]], axis=3).astype(float)
        self.f = RegularGridInterpolator((T, X, Y, H_EXT, V), values, bounds_error=False, fill_value=1.0)

    def __call__(self, t, z):
        z = np.atleast_2d(z)
        h = (z[:, 2] - H[0]) % (2 * pi) + H[0]
        return self.f(np.column_stack([np.broadcast_to(t, len(z)), z[:, 0], z[:, 1], h, z[:, 3]]))


def dynamics(z, u):
    return np.column_stack([z[:, 3] * np.cos(z[:, 2]), z[:, 3] * np.sin(z[:, 2]),
                            z[:, 3] * np.tan(u[:, 0]) / M.WHEELBASE, u[:, 1]])


def rk4(z, u, dt):
    k1 = dynamics(z, u); k2 = dynamics(z + dt / 2 * k1, u)
    k3 = dynamics(z + dt / 2 * k2, u); k4 = dynamics(z + dt * k3, u)
    return z + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


def step(z, u):
    """Zero-order hold over one time step; returns the end state and the substep states."""
    path = []
    for _ in range(SUBSTEPS):
        z = rk4(z, u, DT / SUBSTEPS)
        path.append(z)
    return z, path


def admissible(tube, k, states):
    """Driving limits on the control grid: u with V_{k+1}(z after one held step) <= TOL. (n, |U|) bool."""
    n = len(states)
    z = np.repeat(states, len(U_GRID), axis=0)
    u = np.tile(U_GRID, (n, 1))
    end, _ = step(z, u)
    return (tube(T[k + 1], end) <= TOL).reshape(n, len(U_GRID))


def exit_indices(offer):
    origin = float(offer.service.entry[0])
    return {k for k in range(len(T)) if offer.exit[0] - 1e-9 <= T[k] + origin <= offer.exit[1] + 1e-9}


def in_exit(offer, z):
    m = M.MAP[offer.service.outbound]
    (x0, x1), (y0, y1) = m['exit']['x'], m['exit']['y']
    return ((x0 <= z[:, 0]) & (z[:, 0] <= x1) & (y0 <= z[:, 1]) & (z[:, 1] <= y1)
            & (periodic_distance(z[:, 2], m['heading']) <= M.HEADING_BAND)
            & (M.SPEED_LIMIT[0] <= z[:, 3]) & (z[:, 3] <= M.SPEED_LIMIT[1]))


def grid_states(index):
    return np.column_stack([X[index[0]], Y[index[1]], H[index[2]], V[index[3]]])


def non_blocking(offer, tube):
    """Corridor grid cells before exit whose driving-limit set (on the control grid) is empty."""
    exits, corridor = exit_indices(offer), offer.corridor
    zone_out = np.broadcast_to(np.asarray(M.EXIT_ZONE[offer.service.outbound](M.impl)), corridor.shape)
    last, evaluated, empty, where = max(exits), 0, 0, []
    for k in range(len(T) - 1):
        if k >= last:
            break
        inside = corridor[k] <= TOL
        if k in exits:
            inside &= zone_out[k] > 0   # cells already in E_out during K may stop
        index = np.nonzero(inside)
        if not len(index[0]):
            continue
        states = grid_states(index)
        ok = np.concatenate([admissible(tube, k, states[i:i + 4000]).any(axis=1)
                             for i in range(0, len(states), 4000)])
        evaluated += len(states)
        empty += int((~ok).sum())
        if (~ok).any():
            where.append(dict(t=float(T[k] + float(offer.service.entry[0])), cells=int((~ok).sum())))
    return evaluated, empty, where


def simulate(offer, tube, rng):
    """M sampled entries in E_in x J, random admissible controls until E_out. Returns outcomes and paths."""
    px, py, ph, pv = M.ENTRY[offer.service.inbound]
    origin = round(float(offer.service.entry[0]) / DT)
    J = [k for k in range(len(T)) if T[k] <= float(offer.service.entry[1] - offer.service.entry[0]) + 1e-6]
    exits, last = exit_indices(offer), max(exit_indices(offer))
    outcomes, paths = [], []
    for _ in range(SAMPLES):
        k = int(rng.choice(J))
        z = np.array([[px + rng.uniform(-.1, .1), py + rng.uniform(-.1, .1),
                       ph + rng.uniform(-pi / 8, pi / 8), pv + rng.uniform(-.08, .08)]])
        out = dict(entry_t=float(T[k]) + origin * DT, entry_in_corridor=bool(tube(T[k], z)[0] <= TOL),
                   left_corridor=None, blocked=None, exited=None)
        path = {(origin + k) * SUBSTEPS: z[0, :2].copy()}
        while True:
            if k in exits and in_exit(offer, z)[0]:
                out['exited'] = float(T[k]) + origin * DT
                break
            if k >= last:
                break
            ok = admissible(tube, k, z)[0]
            if not ok.any():
                out['blocked'] = float(T[k]) + origin * DT
                break
            u = U_GRID[rng.choice(np.flatnonzero(ok))][None]
            _, sub = step(z, u)
            for s, zs in enumerate(sub, 1):
                if out['left_corridor'] is None and tube(T[k] + s * DT / SUBSTEPS, zs)[0] > TOL:
                    out['left_corridor'] = float(T[k] + s * DT / SUBSTEPS) + origin * DT
                path[(origin + k) * SUBSTEPS + s] = zs[0, :2].copy()
            z, k = sub[-1], k + 1
        outcomes.append(out)
        paths.append(path)
    return outcomes, paths


def collisions(paths_a, paths_b):
    """Sample pairs that come within 2*BODY at a common substep while both are present."""
    pairs, hits, closest = 0, 0, np.inf
    for pa in paths_a:
        for pb in paths_b:
            common = sorted(pa.keys() & pb.keys())
            pairs += 1
            if common:
                d = np.hypot(*(np.array([pa[c] for c in common]) - np.array([pb[c] for c in common])).T)
                closest = min(closest, float(d.min()))
                hits += bool((d < 2 * BODY).any())
    return pairs, hits, closest


# ---------------------------------------------------------------- candidate worker (Stage 1)
def candidate_worker(service, resources):
    """Candidates computed in either order are identical; inputs and committed tubes are unchanged."""
    ledger = tuple(Committed(o) for o in resources)
    committed = [tube_hash(o.corridor) for o in resources]
    crossing = M.crossing_set(service, ledger)
    before = tube_hash(crossing)
    windows = M.exit_windows(service)

    def run(order):
        out = {}
        for k in order:
            try:
                out[k] = M.corridor(service, crossing, windows[k]).corridor
            except M.NoCorridorError:
                out[k] = None
        return out
    forward = run(range(len(windows)))
    first = {k: None if v is None else tube_hash(v) for k, v in forward.items()}
    backward = run(reversed(range(len(windows))))
    same = all((forward[k] is None) == (backward[k] is None) and
               (forward[k] is None or tube_hash(backward[k]) == first[k]) for k in forward)
    untouched = (all(first[k] is None or tube_hash(forward[k]) == first[k] for k in forward)
                 and tube_hash(crossing) == before
                 and [tube_hash(o.corridor) for o in resources] == committed)
    readonly = all(v is None or not v.flags.writeable for v in (*forward.values(), *backward.values()))
    return dict(order_independent=same, inputs_untouched=untouched, readonly=readonly, hashes=first)


# ---------------------------------------------------------------- attempt checks
def check_attempt(check, spec, record, commitment, resources, ledger, after, sims, rng):
    request, label = spec.request, f'request {spec.request.client}'
    admission, offers, negotiation, result = (record[k] for k in ('admission', 'offers', 'negotiation', 'result'))
    detail = {}

    # 1. Committed corridors pairwise disjoint with clearance 2*BODY (independent of D_j's bitmap).
    for i, later in enumerate(after):
        for earlier in after[:i]:
            n = conflict_cells(later, earlier)
            check('1 committed corridors disjoint (2·body)', n == 0,
                  f'{later.service.client}/{earlier.service.client}: {n} cells')

    if admission is not None:
        # 2. Every generated candidate's coverage, rules and compatibility; offered ones must pass.
        detail['candidates'] = []
        for o in admission.candidates:
            covered, points = coverage(o.corridor, o.service)
            outside_rules = rules_cells(o)
            entry_out, exit_out, t_first, t_last = endpoint_cells(o)
            conflicts = {e.service.client: conflict_cells(o, e) for e in resources}
            rec = offer_record(o, resources)
            rec['evidence'].update(coverage_independent=covered, entry_points=points,
                                   cells_outside_rules=outside_rules, first_sample_outside_entry_zone=entry_out,
                                   last_sample_outside_exit_zone=exit_out, corridor_span=[t_first, t_last],
                                   conflict_cells=conflicts, compatible=not any(conflicts.values()))
            detail['candidates'].append(rec['id'])
            check('2 certified: notebook covers = independent coverage', covered == o.certified, f'{label} κ{o.index}')
            if o in offers:
                check('2 offer certified: E_in×J covered', covered and o.certified, f'{label} κ{o.index}')
                check('2 offer certified: within C_j, E_in→E_out', outside_rules == 0 and entry_out == 0 and exit_out == 0,
                      f'{label} κ{o.index} rules={outside_rules} entry={entry_out} exit={exit_out}')
                check('2 offer compatible: avoids D_j', not any(conflicts.values()), f'{label} κ{o.index} {conflicts}')

        # Stage 1: candidate worker, against the same frozen commitments.
        worker = candidate_worker(admission.service, resources)
        detail['worker'] = worker
        generated = {o.index - 1: tube_hash(o.corridor) for o in admission.candidates}
        check('S1 candidates order-independent, inputs untouched',
              worker['order_independent'] and worker['inputs_untouched'] and worker['readonly']
              and all(worker['hashes'][k] == h for k, h in generated.items()), label)

    # 3. Commit installs exactly the priced offer; failures change nothing; committed tubes immutable.
    check('3 no computation after admission', len(COMPUTE) == LAST.get('computed', len(COMPUTE)) or admission is None, label)
    if result.agreement is not None:
        pair = negotiation.agreement
        rec = offer_record(pair.offer, resources)
        check('3 commit = priced offer (ID, tube hash)',
              after[-1] is pair.offer and tube_hash(after[-1].corridor) == rec['tube']['sha256']
              and result.agreement.contract == pair.offer.contract and result.agreement.price == pair.price
              and result.commitment == commitment.conjoin(pair.offer.contract), label)
    else:
        check('3 unchanged on NO-BLA/rejection', result.commitment is commitment and result.ledger == ledger
              and after is resources, label)
    check('3 committed tubes unchanged', all(tube_hash(o.corridor) == offer_record(o, ())['tube']['sha256']
                                             and not o.corridor.flags.writeable for o in after), label)

    # 4. Bargaining and commit validators; bargain is protocol.ipynb's code object.
    if negotiation is not None:
        check('4 validators', validators_pass(spec, record, BACKEND, PROTOCOL), label)
        check('4 bargain/commit = protocol.ipynb code', same_protocol_code(BACKEND), label)

    # 5./6. Non-blocking and sampling for the newly committed vehicle.
    if result.agreement is not None:
        offer = after[-1]
        tube = Tube(offer.corridor)
        t = perf_counter()
        evaluated, empty, where = non_blocking(offer, tube)
        detail['non_blocking'] = dict(cells=evaluated, empty=empty, where=where[:10], seconds=perf_counter() - t)
        check('5 non-blocking: driving limits nonempty', empty == 0, f'{label}: {empty}/{evaluated} cells')
        t = perf_counter()
        outcomes, paths = simulate(offer, tube, rng)
        sims[offer.service.client] = paths
        for o in outcomes:
            check('6 sampled: entry state in corridor', o['entry_in_corridor'], f'{label} {o}')
            check('6 sampled: stays in corridor', o['left_corridor'] is None, f'{label} {o}')
            check('6 sampled: not blocked', o['blocked'] is None, f'{label} {o}')
            check('6 sampled: exits through E_out in K', o['exited'] is not None, f'{label} {o}')
        pairs = {}
        for other in after[:-1]:
            n, hits, closest = collisions(paths, sims[other.service.client])
            pairs[other.service.client] = dict(pairs=n, collisions=hits, closest_m=closest)
            check('6 sampled: no collision', hits == 0, f'{label}/{other.service.client}: {hits}/{n}')
        detail['sampling'] = dict(samples=len(outcomes), outcomes=outcomes, pairs=pairs, seconds=perf_counter() - t)
    return detail


# ---------------------------------------------------------------- outputs
def theta_json(service):
    return dict(route=f'{service.inbound}→{service.outbound}', manoeuvre=M.manoeuvre(service),
                J=[float(e) for e in service.entry])


def log_entry(spec, record, resources, detail, compute, seconds):
    request, admission, negotiation, offers = spec.request, record['admission'], record['negotiation'], record['offers']
    tried = LAST['tried']
    status = ('rejected' if admission is None else 'as requested' if admission.service == request.service
              else f'adapted ({request.alternatives.index(admission.service) + 1})')
    entry_condition = tried[0][1] != 'entry condition fails'
    agreement = None if negotiation is None else negotiation.agreement
    outcome = ('REJECTED' if admission is None else 'NO-BLA (no offer)' if not offers
               else 'NO-BLA' if agreement is None else 'ACCEPTED')
    candidates = [] if admission is None else [RECORDS[id(o)] for o in admission.candidates]
    sat = [c for c in compute if c['kind'] == 'sat']
    corr = [c for c in compute if c['kind'] == 'corridor']
    return dict(
        request=request.client, branch=spec.branch, received=float(spec.received),
        theta=theta_json(request.service), adaptations=[theta_json(s) for s in request.alternatives],
        policy=dict(v=str(spec.v), gamma=str(spec.gamma), kappa=str(KAPPA),
                    targets={p: str(x) for p, x in spec.targets.items()},
                    minima={p: str(x) for p, x in spec.minima.items()}),
        standing=[RECORDS[id(o)]['id'] for o in resources],
        commitment_version=commitment_version(resources),
        tried=[dict(J=[float(e) for e in J], fate=fate) for J, fate in tried],
        entry_condition_as_requested=entry_condition,
        baseline_aim='reserve' if entry_condition else 'reject (E_in×J ⊄ sat∃(φ))',
        admission=status, J_admitted=None if admission is None else [float(e) for e in admission.service.entry],
        offers=dict(exit_windows_tried=0 if admission is None else len(M.exit_windows(admission.service)),
                    generated=len(candidates), certified=sum(c['evidence']['certified'] for c in candidates),
                    compatible=sum(c['evidence']['compatible'] for c in candidates),
                    offered=[RECORDS[id(o)]['id'] for o in offers]),
        candidates=candidates,
        rounds=[] if negotiation is None else [
            dict(round=r.number, proposer=r.proposer, offer=RECORDS[id(r.proposal.offer)]['id'],
                 exit_window=list(r.proposal.offer.exit), price=str(r.proposal.price),
                 targets={p: str(x) for p, x in r.targets}, utilities={p: str(x) for p, x in r.utilities},
                 response='accept' if r.accepted else 'reject') for r in negotiation.history],
        outcome=outcome,
        accepted=None if agreement is None else RECORDS[id(agreement.offer)]['id'],
        K_star=None if agreement is None else list(agreement.offer.exit),
        q_star=None if agreement is None else str(agreement.price),
        compute=dict(sat_seconds=[c['seconds'] for c in sat], corridor_seconds=[c['seconds'] for c in corr],
                     per_offer_seconds=None if not corr else sum(c['seconds'] for c in corr) / len(corr)),
        seconds={**record['times'], 'total': sum(record['times'].values()), **seconds},
        memory=dict(tube_mib=None if not candidates else candidates[0]['tube']['nbytes'] / 2**20,
                    peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        checks_detail={k: v for k, v in detail.items() if k != 'candidates'})


def write_table(entries, path):
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['request', 'route', 'J_s', 'baseline_aim', 'admission', 'J_admitted_s', 'offers_gen',
                    'offers_cert', 'offers_compat', 'rounds', 'outcome', 'K_star_s', 'q_star_eur', 'time_s'])
        for e in entries:
            w.writerow([e['request'], e['theta']['route'], '[{:g}, {:g}]'.format(*e['theta']['J']),
                        e['baseline_aim'].split(' ')[0], e['admission'],
                        '' if e['J_admitted'] is None else '[{:g}, {:g}]'.format(*e['J_admitted']),
                        e['offers']['generated'], e['offers']['certified'], e['offers']['compatible'],
                        len(e['rounds']), e['outcome'],
                        '' if e['K_star'] is None else '[{:g}, {:g}]'.format(*e['K_star']),
                        e['q_star'] or '', f"{e['seconds']['total']:.2f}"])


def plot(resources, last, times, path):
    """x-y slices of committed corridors at absolute times; earlier gray, the last vehicle's blue."""
    import matplotlib
    matplotlib.use('pdf')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle
    plt.rcParams.update({'font.size': 7, 'font.family': 'serif', 'font.serif': ['STIXGeneral'],
                         'mathtext.fontset': 'stix', 'pdf.fonttype': 42, 'axes.linewidth': .5,
                         'xtick.major.width': .5, 'ytick.major.width': .5})
    blue, gray, ink, road = (30 / 255, 100 / 255, 180 / 255), '#A8A8A8', '#222222', '#EFEFEF'
    fig, axes = plt.subplots(1, len(times), figsize=(8.5 / 2.54, 3.55 / 2.54), sharey=True)
    edges_x = np.r_[X - (X[1] - X[0]) / 2, X[-1] + (X[1] - X[0]) / 2]
    edges_y = np.r_[Y - (Y[1] - Y[0]) / 2, Y[-1] + (Y[1] - Y[0]) / 2]
    for ax, t in zip(axes, times):
        ax.add_patch(Rectangle((-2, -.8), 4, 1.6, fc=road, ec='none', zorder=0))
        ax.add_patch(Rectangle((-.8, -2), 1.6, 4, fc=road, ec='none', zorder=0))
        for o in resources:
            k = round((t - float(o.service.entry[0])) / DT)
            if not 0 <= k < len(T):
                continue
            cells = (o.corridor[k] <= TOL).any(axis=(2, 3))
            if not cells.any():
                continue
            color = blue if o is last else gray
            ax.pcolormesh(edges_x, edges_y, np.ma.masked_where(~cells.T, np.ones_like(cells.T, float)),
                          cmap=matplotlib.colors.ListedColormap([color]), vmin=0, vmax=1, linewidth=0,
                          rasterized=False, zorder=2 if o is last else 1)
            cx, cy = np.nonzero(cells)
            ax.text(X[cx].mean(), Y[cy].mean(), o.service.client, ha='center', va='center', fontsize=6,
                    color='white' if o is last else ink, zorder=3)
        ax.set_title(f'$t={t:g}$ s', pad=2)
        ax.set_xlim(-2, 2); ax.set_ylim(-2, 2); ax.set_aspect('equal')
        ax.set_xticks([-2, 0, 2]); ax.set_yticks([-2, 0, 2])
        ax.tick_params(length=2, pad=1.5)
    axes[0].set_ylabel('$y$ [m]')
    axes[len(times) // 2].set_xlabel('$x$ [m]', labelpad=1)
    handles = [Patch(color=gray, label='earlier corridors'),
               Patch(color=blue, label=f'{last.service.client}, adapted $J\'$'), Patch(color=road, label='roads')]
    fig.legend(handles=handles, loc='upper center', ncol=3, frameon=False, handlelength=1.2,
               columnspacing=1, handletextpad=.4, bbox_to_anchor=(.5, 1.02))
    fig.subplots_adjust(left=.1, right=.99, top=.76, bottom=.2, wspace=.12)
    fig.savefig(path)
    plt.close(fig)


def package(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def environment():
    import jax
    cpu = next((l.split(':', 1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines()
                if l.startswith('model name')), platform.processor()) if Path('/proc/cpuinfo').exists() \
        else platform.processor()
    return dict(python=sys.version, platform=platform.platform(), machine=platform.machine(), cpu=cpu,
                jax_devices=[str(d) for d in jax.devices()],
                packages={p: package(p) for p in ('interval-logic', 'pyspect', 'hj-reachability', 'jax', 'jaxlib',
                                                   'jax-cuda13-plugin', 'numpy', 'scipy', 'portion', 'matplotlib')},
                note='jax-cuda13-plugin is installed in .venv outside uv.lock; without it JAX runs on CPU',
                grid=GRID_META, grid_id=GRID_ID,
                timing='time.perf_counter, single run, one process; stage times exclude checks; '
                       'JIT compilation is included in the first computations')


# ---------------------------------------------------------------- run
def main():
    assert same_protocol_code(BACKEND)
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    check, sims = Checks(), {}
    commitment, resources, ledger = M.standing(()), (), ()
    entries = []
    for spec in SCENARIO:
        mark = len(COMPUTE)
        record = attempt(spec, commitment, resources, ledger, BACKEND, PROTOCOL)
        result = record['result']
        compute = COMPUTE[mark:]
        after = resources if result.agreement is None else (*resources, record['negotiation'].agreement.offer)
        for o in (() if record['admission'] is None else record['admission'].candidates):
            offer_record(o, resources)
        t = perf_counter()
        detail = check_attempt(check, spec, record, commitment, resources, ledger, after, sims, rng)
        entries.append(log_entry(spec, record, resources, detail, compute, dict(checks=perf_counter() - t)))
        print(f"{spec.request.client}: {entries[-1]['admission']:14s} {entries[-1]['outcome']:8s} "
              f"rounds={len(entries[-1]['rounds'])} q*={entries[-1]['q_star']} K*={entries[-1]['K_star']} "
              f"({entries[-1]['seconds']['total']:.1f} s + checks {entries[-1]['seconds']['checks']:.1f} s)", flush=True)
        if check.violations:
            break                                 # stop at the first violating attempt
        commitment, resources, ledger = result.commitment, after, result.ledger

    branches = {
        'as requested, accepted': any(e['admission'] == 'as requested' and e['outcome'] == 'ACCEPTED' for e in entries),
        'simultaneous non-conflicting pair': any(a['J_admitted'] == b['J_admitted'] and a['outcome'] == b['outcome'] == 'ACCEPTED'
                                                 for i, a in enumerate(entries) for b in entries[:i]),
        'NO-BLA, budget exhausted': any(e['outcome'] == 'NO-BLA' and len(e['rounds']) == ROUND_BUDGET for e in entries),
        'rejected on price, then accepted': any(e['outcome'] == 'ACCEPTED' and len(e['rounds']) > 1 for e in entries),
        'last: AIM rejects, adapted, ~3 offers, accepted': bool(entries) and entries[-1]['baseline_aim'] != 'reserve'
            and entries[-1]['admission'].startswith('adapted') and entries[-1]['offers']['certified'] >= 2
            and entries[-1]['outcome'] == 'ACCEPTED' and len(entries) == len(SCENARIO),
    }
    charging = json.loads((ROOT / 'artifacts' / 'charging_experiment' / 'log.json').read_text())['requests']
    per_offer = [s for e in entries for s in e['compute']['corridor_seconds']]
    comparison = dict(
        charging=dict(access='fixed booking window: □_[s,s+d) acc = k', satisfiability='exact interval arithmetic '
                      'and contract normalization (decide_booking)', offer_parameter='start s ∈ J ∩ residual',
                      median_request_ms=1000 * float(np.median([e['seconds']['total'] for e in charging]))),
        intersection=dict(access='time-state corridor Φ_j ⊆ (t, x, y, h, v) grid; R = □(X → Φ_j)',
                          satisfiability='pyspect TLT / HJ reachability on a grid (sat∃(φ_j), passes 3–4)',
                          offer_parameter='exit window K', median_request_s=float(np.median([e['seconds']['total'] for e in entries])),
                          median_corridor_s=float(np.median(per_offer)) if per_offer else None))
    summary = dict(seed=SEED, round_budget=ROUND_BUDGET, price_grid=f'€{GRID[0]}..€{GRID[-1]} step €1',
                   owner=dict(target=str(OWNER['target']), minimum=str(OWNER['minimum']), kappa=str(KAPPA)),
                   model='point vehicle (x, y, h, v) with a disk body of radius 0.075 m; clearance 2·0.075 m',
                   samples_per_vehicle=SAMPLES, control_grid=f'{CONTROL_POINTS}x{CONTROL_POINTS}', substeps=SUBSTEPS,
                   tolerance=TOL,
                   checks={k: dict(evaluated=n, violations=bad) for k, (n, bad) in check.counts.items()},
                   violations=check.violations[:50], branches=branches, comparison=comparison,
                   committed=[RECORDS[id(o)]['id'] for o in resources])
    (OUT / 'log.json').write_text(json.dumps(dict(summary=summary, requests=entries), indent=1, ensure_ascii=False))
    (OUT / 'environment.json').write_text(json.dumps(environment(), indent=1, default=float))
    write_table(entries, OUT / 'table.csv')
    if not check.violations and len(entries) == len(SCENARIO) and entries[-1]['outcome'] == 'ACCEPTED':
        plot(resources, resources[-1], FIGURE_TIMES, OUT / 'figure.pdf')   # only for a complete, clean run

    for name, c in summary['checks'].items():
        print(f'{name:48s} {c["evaluated"]:5d} evaluated, {c["violations"]} violations')
    print('branches:', branches)
    print(f'wrote {OUT}/{{log.json,table.csv,figure.pdf,environment.json}}')
    if check.violations or not all(branches.values()):
        sys.exit('FAILED: ' + '; '.join(check.violations[:5] or ['branch coverage']))


FIGURE_TIMES = (1.5, 5.5, 8.0)

if __name__ == '__main__':
    main()
