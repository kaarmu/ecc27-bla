"""Persistent JSON-lines Bicycle5D worker. Stdout is reserved for replies.

Large arrays and solver internals stay here. Replies carry compact, inspectable
descriptions tied to hashed artifacts: the task formula and tree, time masks,
mask conventions, pass metadata, the full-state entry query and offer evidence.
"""
from contextlib import redirect_stdout
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
import json
import resource
import sys
import traceback

import numpy as np
import jax
import ltms_reachability
from scipy.ndimage import maximum_filter

from ltms_reachability import Axis, GridSpec, LTMSPlanner, TimeWindow, WindowPolicy, create_4way
from ltms_reachability.levelsets import rectangle
from ltms_reachability.windows import window_mask
from . import model as M
from .checks import boxes_disjoint, rollout_checks, minimum_body_gap, reference_coverage

FORMAT = 3  # artifact/cache schema; bump whenever stored evidence changes meaning
DT = .25
TOLERANCE = 2e-5
SERVICE_CHECKS = ('entry_inside', 'rollout_inside', 'road_ok', 'clear_ok', 'input_ok', 'reference_covered')


def file_digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def load_offer(record):
    path = Path(record['artifact'])
    if file_digest(path) != record['artifact_digest']:
        raise ValueError('offer artifact changed')
    info = json.loads(path.read_text())
    if file_digest(info['base']) != info['base_digest']:
        raise ValueError('numerical artifact changed')
    return info


def physical_mask(base, route):
    return base['reserved'] if route == 'east' else base['reserved'][:, ::-1, ::-1]


def physical_states(states, route):
    result = states.copy()
    if route == 'west':
        result[:, :2] *= -1
        result[:, 2] += np.pi
    return result


def aligned_disjoint(a, depart_a, b, depart_b):
    offset = int(round((depart_b-depart_a)/DT))
    first, last = max(0, offset), min(len(a), offset+len(b))
    if first >= last:
        return True
    # Treat slab endpoints as closed: check neighboring time slabs too.
    for shift in (-1, 0, 1):
        lo, hi = max(first, offset+shift), min(last, offset+shift+len(b))
        if lo < hi and not boxes_disjoint(a[lo:hi], b[lo-offset-shift:hi-offset-shift]):
            return False
    return True


def extent(mask, coordinates, axis):
    """Grid extent of the inside points along one state axis."""
    inside = np.asarray(mask) <= 0
    present = inside.any(axis=tuple(i for i in range(inside.ndim) if i != axis))
    values = np.asarray(coordinates[axis])[present]
    return [float(values.min()), float(values.max())] if len(values) else None


def describe_pass(values, entry_index, times):
    inside = values <= 0
    occupied = np.flatnonzero(inside.any(axis=tuple(range(1, values.ndim))))
    return dict(inside_fraction=float(inside.mean()), entry_value=float(values[(0, *entry_index)]),
                nonempty_times=None if not len(occupied) else [float(times[occupied[0]]),
                                                                float(times[occupied[-1]])])


class Worker:
    def __init__(self):
        self.base = None
        self.base_path = None
        self.metadata = None

    def prepare(self, output):
        output = Path(output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        spec = GridSpec((Axis('t', 0, 9, 37), Axis('x', -2, 2, 31),
                         Axis('y', -2, 2, 61), Axis('h', *M.CHART['h'], 9),
                         Axis('d', *M.CHART['d'], 5), Axis('v', *M.CHART['v'], 7)), accuracy='medium')
        self.spec = spec
        settings = dict(M.CONTROLS)
        sources = [Path(__file__), *(Path(__file__).with_name(n) for n in ('checks.py', 'model.py')),
                   *sorted(Path(ltms_reachability.__file__).parent.glob('*.py'))]
        source_hash = sha256(b''.join(p.name.encode()+p.read_bytes() for p in sources)).hexdigest()
        config = dict(grid=spec.fingerprint(dynamics=settings), controls=settings,
                      axes=[a.pyspect_spec() for a in spec.axes], accuracy=spec.accuracy,
                      dtype='float64' if jax.config.x64_enabled else 'float32',
                      device=str(jax.devices()[0]), python=sys.version.split()[0],
                      source_digest=source_hash,
                      body_radius=M.BODY_RADIUS, tracking=M.TRACKING, dt=DT, format=FORMAT,
                      versions={n: version(n) for n in ('pyspect', 'hj-reachability', 'jax', 'numpy')})
        key = sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:20]
        self.base_path = output/f'base-{key}.npz'
        meta_path = self.base_path.with_suffix('.json')
        if self.base_path.exists() and meta_path.exists():
            self.metadata = json.loads(meta_path.read_text())
            if file_digest(self.base_path) != self.metadata['base_digest']:
                raise ValueError('cached base digest mismatch')
            self.base = np.load(self.base_path, allow_pickle=False)
            return {**self.metadata, 'cache_hit': True}
        started = perf_counter()
        p = LTMSPlanner.bicycle5d(spec, wheelbase=M.WHEELBASE, **settings)
        regions = create_4way(p.grid, 'entry_w', 'exit_e', 'road_e', 'center')
        rules, goal = regions['road_e'], regions['exit_e']
        clear = TimeWindow(*M.CLEAR_WINDOW)
        # Task feasibility: the actual constrained-until TLT, realized by TVHJImpl.
        tree, root = p.until(rules, goal, target_window=clear)
        # Offer construction: the four LTMS passes. No reservations are passed,
        # so pass 2 is pass 1 (the unreserved base calculation).
        result = p.analyze(entry=regions['entry_w'], goal=goal, constraints=rules,
                           entry_window=TimeWindow(*M.ENTRY_WINDOW), exit_window=clear,
                           policy=WindowPolicy(0, .5, 0, 1))
        # Restrict the promised corridor to a straight lane strip. Qualification
        # checks ONE concrete execution inside the conjunction, rather than
        # intersecting independently existential temporal satisfaction sets.
        lane = rectangle(p.grid, [M.LANE_STRIP[0]], [M.LANE_STRIP[1]], axes=[1])
        tube = np.maximum(result.corridor, lane).astype(np.float32)
        coordinates = [np.asarray(a) for a in p.grid.coordinate_vectors]
        entry_state = np.array(M.ENTRY)
        entry_index = tuple(int(np.abs(a-s).argmin()) for a, s in zip(coordinates, entry_state))
        fine_times = np.linspace(0, M.CROSSING, 281)
        states = np.tile(entry_state, (len(fine_times), 1))
        states[:, 0] += M.SPEED*fine_times
        controls = np.zeros((len(fine_times), 2))
        checked = rollout_checks(fine_times, states, controls, tube=tube,
                                 axes=[p.times, *coordinates], body_radius=M.BODY_RADIUS)
        checked['entry_inside'] = bool(tube[(0, *entry_index)] <= TOLERANCE and root[(0, *entry_index)] <= TOLERANCE)
        checked['tlt_entry_value'] = float(root[(0, *entry_index)])
        checked['corridor_entry_value'] = float(tube[(0, *entry_index)])
        if not all(checked[k] for k in ('entry_inside', 'rollout_inside', 'road_ok', 'clear_ok', 'input_ok')):
            raise RuntimeError(f'crossing does not qualify on this grid: {checked}')
        # Time-preserving workspace projection over (h, delta, v).
        projection = (tube <= 0).any(axis=(3, 4, 5))
        x, y = coordinates[:2]
        dx, dy = float(x[1]-x[0]), float(y[1]-y[0])
        # Closed spatial cells plus body/tracking bounds and one time slab's
        # componentwise travel. Padding preserves bodies near domain edges.
        mx = M.BODY_RADIUS+M.TRACKING+dx/2+M.VMAX*DT
        my = M.BODY_RADIUS+M.TRACKING+dy/2+M.VMAX*np.sin(M.CHART['h'][1])*DT
        kx, ky = int(np.ceil(mx/dx)), int(np.ceil(my/dy))
        pad_x, pad_y = kx+2, ky+2
        projected = np.pad(projection, ((0, 0), (pad_x, pad_x), (pad_y, pad_y)))
        slabs = projected.copy()
        slabs[:-1] |= projected[1:]
        reserved = maximum_filter(slabs.astype(np.uint8), size=(1, 2*kx+1, 2*ky+1), mode='constant') > 0
        rx = x[0] + np.arange(-pad_x, len(x)+pad_x)*dx
        ry = y[0] + np.arange(-pad_y, len(y)+pad_y)*dy
        checked['reference_covered'] = reference_coverage(reserved, rx, ry, p.times)
        if not checked['reference_covered']:
            raise RuntimeError('reference swept-body coverage failed')
        mask = window_mask(p.times, clear)
        task = dict(
            formula='road_e U_[7,8] exit_e  (local time; evaluated at tau = 0)',
            tree=repr(tree), source='TLT(UNTIL("admissible", "goal"), primitives=ContLTL)',
            atoms=dict(admissible='road_e: reference point in the eastbound road (y, heading, speed) or the center',
                       goal='exit_e ∩ road_e, target masked to the local window [7, 8]'),
            backend='pyspect TVHJImpl.solve (hj_reachability), Bicycle5D; tree.realize(impl)',
            convention=('time mask sets the target to +1 (empty) outside [7, 8]; native TVHJImpl '
                        'also intersects the target with the constraint at each witness sample'),
            target_samples=[float(t) for t in p.times[mask]],
            road_y_extent_at_entry_x=extent(np.take(rules, entry_index[0], axis=0), coordinates[1:], 0),
            exit_extent=dict(x=extent(goal, coordinates, 0), y=extent(goal, coordinates, 1)),
            entry_value=checked['tlt_entry_value'],
            # Exact semantics give TLT ⊆ pass 1 (a timed target lies in the untimed one); the
            # two separately computed tubes need not agree cell by cell on the grid.
            outside_pass1_fraction=float(np.mean((root <= 0) & (result.passes['pass1'] > 0))),
            outside_pass1_max=float(np.max(np.where(root <= 0, result.passes['pass1'], -np.inf))))
        passes = {name: describe_pass(result.passes[name], entry_index, p.times)
                  for name in ('pass1', 'pass2', 'pass3', 'pass4')}
        passes['pass2_reuses_pass1'] = result.passes['pass2'] is result.passes['pass1']
        corridor = dict(lane_strip=list(M.LANE_STRIP), pass4_inside_fraction=passes['pass4']['inside_fraction'],
                        corridor_inside_fraction=float((tube <= 0).mean()),
                        y_extent=extent(tube[0], coordinates, 1),
                        reference_max_value=checked['rollout_max_value'])
        entry_query = dict(declared=list(M.ENTRY), index=list(entry_index),
                           grid_state=[float(a[i]) for a, i in zip(coordinates, entry_index)],
                           tlt_root=checked['tlt_entry_value'], corridor=checked['corridor_entry_value'],
                           tolerance=TOLERANCE)
        reservation = dict(margins=[mx, my], kernel_cells=[kx, ky], cell=[dx, dy],
                           slab_rule='R(t_i) covers the projections at t_i and t_(i+1), inflated',
                           reserved_cells=int(reserved.sum()), body_radius=M.BODY_RADIUS,
                           tracking=M.TRACKING)
        ih, idelta, iv = entry_index[2:]
        np.savez_compressed(self.base_path, tube=tube, times=p.times,
                            x=x, y=y, h=coordinates[2], d=coordinates[3], v=coordinates[4],
                            reserved=reserved, rx=rx, ry=ry, fine_times=fine_times,
                            states=states, controls=controls,
                            tlt_slice=root[0, :, :, ih, idelta, iv])
        self.metadata = dict(config=config, checks=checked, task=task, passes=passes,
                             corridor=corridor, entry_query=entry_query, reservation=reservation,
                             shape=list(tube.shape),
                             base=str(self.base_path), base_digest=file_digest(self.base_path),
                             cold_seconds=perf_counter()-started, pass_seconds=dict(result.timings),
                             entry_window=[result.entry_window.start, result.entry_window.end],
                             exit_window=[result.exit_window.start, result.exit_window.end],
                             tube_mib=tube.nbytes/2**20, cache_hit=False,
                             reservation_margins=[mx, my], body_radius=M.BODY_RADIUS,
                             backend='pyspect TVHJImpl / Bicycle5D',
                             peak_worker_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                                 (2**20 if sys.platform == 'darwin' else 1024),
                             chart='route-local heading [-0.5,0.5], nonperiodic')
        meta_path.write_text(json.dumps(self.metadata, indent=2, allow_nan=False))
        self.base = np.load(self.base_path, allow_pickle=False)
        return self.metadata

    def evaluate(self, message):
        service, departure = message['service'], message['departure']
        deadline = service['deadline']
        if M.speed_bound_excludes(departure, deadline):
            distance = float(M.exact(M.EXIT[0][0])-M.exact(M.ENTRY[0]))
            return dict(status='PROVED_IMPOSSIBLE', evidence='independent analytic bound',
                        reason=f'distance {distance:g} m to exit_e exceeds vmax · available time',
                        distance_lower_bound=distance, vmax=M.VMAX, available=deadline-departure)
        service_checks = {k: self.metadata['checks'][k] for k in SERVICE_CHECKS}
        if not M.tlt_evidence_applies(departure, deadline):
            return dict(status='UNRESOLVED', evidence='numerical evidence does not apply',
                        reason='local clearance window [s+7, s+8] is not within the deadline',
                        reference_eligible=departure+M.CROSSING <= deadline)
        mask = physical_mask(self.base, service['route'])
        comparisons = []
        for record in message['accepted']:
            old = load_offer(record)
            with np.load(old['base'], allow_pickle=False) as previous:
                compatible = aligned_disjoint(mask, departure, physical_mask(previous, old['route']), old['departure'])
                comparisons.append(dict(offer=old['id'], disjoint=compatible))
        if any(not c['disjoint'] for c in comparisons):
            return dict(status='GEOMETRIC_CONFLICT', evidence='template rejected',
                        reason='reservation meets a standing reservation', service=service_checks,
                        comparisons=comparisons)
        checks = dict(service={**service_checks, 'tlt_window_within_deadline': True},
                      compatibility=dict(compatible=True, disjoint_from=comparisons))
        info = dict(id=message['id'], service=service, departure=departure,
                    route=service['route'], snapshot=message['snapshot'], end=departure+M.LEASE,
                    base=str(self.base_path), base_digest=self.metadata['base_digest'],
                    checks=checks, format=FORMAT, evidence='WITNESSED',
                    scope='Bicycle5D numerical corridor and exact nominal straight-motion execution')
        path = self.base_path.parent/f"offer-{message['id']}.json"
        path.write_text(json.dumps(info, sort_keys=True, indent=2, allow_nan=False))
        return dict(status='QUALIFIED', artifact=str(path), artifact_digest=file_digest(path), info=info)

    def coverage(self, message):
        """Reference coverage by the base reservation for a delayed reference."""
        base = self.base
        return dict(delay=message['delay'], covered=reference_coverage(
            base['reserved'], base['rx'], base['ry'], base['times'], delay=message['delay']))

    def refine(self):
        path = self.base_path.with_suffix('.refinement.json')
        if path.exists():
            data = json.loads(path.read_text())
            if data['base_digest'] == self.metadata['base_digest']:
                return {**data, 'cache_hit': True}
        started = perf_counter()
        spec = GridSpec((Axis('t', 0, 9, 73), *self.spec.axes[1:]), accuracy=self.spec.accuracy)
        p = LTMSPlanner.bicycle5d(spec, wheelbase=M.WHEELBASE, **self.metadata['config']['controls'])
        regions = create_4way(p.grid, 'road_e', 'exit_e')
        _, tube = p.until(regions['road_e'], regions['exit_e'], target_window=TimeWindow(*M.CLEAR_WINDOW))
        index = tuple(np.abs(np.asarray(a)-s).argmin() for a, s in
                      zip(p.grid.coordinate_vectors, M.ENTRY))
        value = float(tube[(0, *index)])
        if value > 0:
            raise RuntimeError('temporal refinement changed entry membership')
        data = dict(base_digest=self.metadata['base_digest'], coarse_dt=DT, fine_dt=DT/2,
                    coarse_value=self.metadata['checks']['tlt_entry_value'], fine_value=value,
                    entry_membership_stable=True, seconds=perf_counter()-started, cache_hit=False,
                    scope='temporal refinement only; not a numerical error bound')
        path.write_text(json.dumps(data, indent=2))
        return data

    def final(self, records, attempts):
        paths, pairs = [], []
        for record in records:
            info = load_offer(record)
            states = physical_states(self.base['states'], info['route'])
            times = self.base['fine_times']+info['departure']
            mask = physical_mask(self.base, info['route'])
            paths.append(dict(id=info['id'], times=times.tolist(), states=states.tolist(), route=info['route'],
                              reserved_union=mask.any(axis=0).T.astype(int).tolist()))
        for i, a in enumerate(paths):
            for b in paths[i+1:]:
                gap = minimum_body_gap(np.array(a['times']), np.array(a['states']),
                                       np.array(b['times']), np.array(b['states']), M.BODY_RADIUS)
                pairs.append(dict(first=a['id'], second=b['id'],
                                  minimum_body_gap=None if not np.isfinite(gap) else gap))
                if gap <= 0:
                    raise RuntimeError('independent continuous-time body check failed')
        result = dict(paths=paths, pair_checks=pairs, x=self.base['x'].tolist(), y=self.base['y'].tolist(),
                      rx=self.base['rx'].tolist(), ry=self.base['ry'].tolist(),
                      slice=self.base['tlt_slice'].T.tolist(), metadata=self.metadata)
        from .static_figure import export_figure
        export_figure(result, attempts, self.base_path.parent)
        return result

    def handle(self, message):
        operations = dict(prepare=lambda: self.prepare(message['output']),
                          evaluate=lambda: self.evaluate(message),
                          coverage=lambda: self.coverage(message),
                          refine=self.refine,
                          final=lambda: self.final(message['accepted'], message['attempts']))
        if message['op'] not in operations:
            raise ValueError('unknown worker operation')
        return operations[message['op']]()


def main():
    worker = Worker()
    for line in sys.stdin:
        try:
            with redirect_stdout(sys.stderr):
                result = worker.handle(json.loads(line))
            print(json.dumps(dict(ok=True, result=result), allow_nan=False), flush=True)
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps(dict(ok=False, error=str(error))), flush=True)


if __name__ == '__main__':
    main()
