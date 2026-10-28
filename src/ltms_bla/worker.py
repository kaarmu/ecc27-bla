"""Persistent JSON-lines Bicycle5D worker. Stdout is reserved for replies."""
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
from ltms_reachability.levelsets import intersection, rectangle
from .checks import boxes_disjoint, rollout_checks, minimum_body_gap

BODY = .18  # circumscribed disk, toy body 0.32 m x 0.16 m, rounded upward
TRACKING = .01
DT = .25
SPEED = .45
ARRIVAL = 7.


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


class Worker:
    def __init__(self):
        self.base = None
        self.base_path = None
        self.metadata = None

    def prepare(self, output):
        output = Path(output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        spec = GridSpec((Axis('t', 0, 9, 37), Axis('x', -2, 2, 31),
                         Axis('y', -2, 2, 61), Axis('h', -.5, .5, 9),
                         Axis('d', -.15, .15, 5), Axis('v', .3, .6, 7)), accuracy='medium')
        self.spec = spec
        settings = dict(min_steer=-.1, max_steer=.1, min_accel=-.15, max_accel=.15)
        sources = [Path(__file__), Path(__file__).with_name('checks.py'),
                   *sorted(Path(ltms_reachability.__file__).parent.glob('*.py'))]
        source_hash = sha256(b''.join(p.name.encode()+p.read_bytes() for p in sources)).hexdigest()
        config = dict(grid=spec.fingerprint(dynamics=settings), controls=settings,
                      axes=[a.pyspect_spec() for a in spec.axes], accuracy=spec.accuracy,
                      dtype='float64' if jax.config.x64_enabled else 'float32',
                      device=str(jax.devices()[0]), python=sys.version.split()[0],
                      source_digest=source_hash,
                      body_radius=BODY, tracking=TRACKING, dt=DT, format=2,
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
        p = LTMSPlanner.bicycle5d(spec, **settings)
        regions = create_4way(p.grid, 'entry_w', 'exit_e', 'road_e', 'center')
        rules = regions['road_e']
        goal = regions['exit_e']
        tree, root = p.until(rules, goal, target_window=TimeWindow(7, 8))
        result = p.analyze(entry=regions['entry_w'], goal=goal, constraints=rules,
                           entry_window=TimeWindow(0, .5), exit_window=TimeWindow(7, 8),
                           policy=WindowPolicy(0, .5, 0, 1))
        # Restrict the promised corridor to a straight lane strip. Qualification
        # checks ONE concrete execution inside the conjunction, rather than
        # intersecting independently existential temporal satisfaction sets.
        lane = rectangle(p.grid, [-.46], [-.34], axes=[1])
        tube = np.maximum(result.corridor, lane).astype(np.float32)
        coordinates = [np.asarray(a) for a in p.grid.coordinate_vectors]
        entry_state = np.array([-1.6, -.4, 0, 0, SPEED])
        entry_index = tuple(np.abs(a-s).argmin() for a, s in zip(coordinates, entry_state))
        fine_times = np.linspace(0, ARRIVAL, 281)
        states = np.tile(entry_state, (len(fine_times), 1))
        states[:, 0] += SPEED*fine_times
        controls = np.zeros((len(fine_times), 2))
        checked = rollout_checks(fine_times, states, controls, tube=tube,
                                 axes=[p.times, *coordinates], body_radius=BODY)
        checked['entry_inside'] = bool(tube[(0, *entry_index)] <= 2e-5 and root[(0, *entry_index)] <= 2e-5)
        checked['tlt_entry_value'] = float(root[(0, *entry_index)])
        checked['corridor_entry_value'] = float(tube[(0, *entry_index)])
        if not all(checked[k] for k in ('entry_inside', 'rollout_inside', 'road_ok', 'clear_ok', 'input_ok')):
            raise RuntimeError(f'crossing does not qualify on this grid: {checked}')
        projection = (tube <= 0).any(axis=(3, 4, 5))
        x, y = coordinates[:2]
        dx, dy = float(x[1]-x[0]), float(y[1]-y[0])
        # Closed spatial cells plus body/tracking bounds and one time slab's
        # componentwise travel. Padding preserves bodies near domain edges.
        mx = BODY+TRACKING+dx/2+.6*DT
        my = BODY+TRACKING+dy/2+.6*np.sin(.5)*DT
        kx, ky = int(np.ceil(mx/dx)), int(np.ceil(my/dy))
        pad_x, pad_y = kx+2, ky+2
        projected = np.pad(projection, ((0, 0), (pad_x, pad_x), (pad_y, pad_y)))
        slabs = projected.copy()
        slabs[:-1] |= projected[1:]
        reserved = maximum_filter(slabs.astype(np.uint8), size=(1, 2*kx+1, 2*ky+1), mode='constant') > 0
        rx = x[0] + np.arange(-pad_x, len(x)+pad_x)*dx
        ry = y[0] + np.arange(-pad_y, len(y)+pad_y)*dy
        # Independent check of every complete swept reference-body bounding
        # box on each slab, not just pointwise vehicle-center membership.
        covered = True
        for i, t in enumerate(p.times[:-1]):
            if t > ARRIVAL+1e-7:
                continue
            a, b = -1.6+SPEED*min(t, ARRIVAL), -1.6+SPEED*min(p.times[i+1], ARRIVAL)
            ix = (rx+dx/2 >= a-BODY) & (rx-dx/2 <= b+BODY)
            iy = (ry+dy/2 >= -.4-BODY) & (ry-dy/2 <= -.4+BODY)
            covered &= bool(reserved[i][np.ix_(ix, iy)].all())
        checked['reference_covered'] = covered
        if not covered:
            raise RuntimeError('reference swept-body coverage failed')
        ih, idelta, iv = entry_index[2:]
        np.savez_compressed(self.base_path, tube=tube, times=p.times,
                            x=x, y=y, h=coordinates[2], d=coordinates[3], v=coordinates[4],
                            reserved=reserved, rx=rx, ry=ry, fine_times=fine_times,
                            states=states, controls=controls,
                            tlt_slice=root[0, :, :, ih, idelta, iv])
        self.metadata = dict(config=config, checks=checked, shape=list(tube.shape),
                             base=str(self.base_path), base_digest=file_digest(self.base_path),
                             cold_seconds=perf_counter()-started, pass_seconds=dict(result.timings),
                             entry_window=[result.entry_window.start, result.entry_window.end],
                             exit_window=[result.exit_window.start, result.exit_window.end],
                             tube_mib=tube.nbytes/2**20, cache_hit=False,
                             reservation_margins=[mx, my], body_radius=BODY,
                             backend='pyspect TVHJImpl / Bicycle5D',
                             peak_worker_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                                 (2**20 if sys.platform == 'darwin' else 1024),
                             chart='route-local heading [-0.5,0.5], nonperiodic')
        meta_path.write_text(json.dumps(self.metadata, indent=2, allow_nan=False))
        self.base = np.load(self.base_path, allow_pickle=False)
        return self.metadata

    def evaluate(self, message):
        service, departure = message['service'], message['departure']
        if .6*(service['deadline']-departure) < 3.-1e-9:
            return dict(status='PROVED_IMPOSSIBLE', reason='distance 3 m exceeds vmax * available time',
                        distance_lower_bound=3., vmax=.6, available=service['deadline']-departure)
        if departure+8 > service['deadline']:
            return dict(status='UNRESOLVED', reason='no template within the selected deadline')
        base = self.base
        mask = physical_mask(base, service['route'])
        comparisons = []
        for record in message['accepted']:
            old = load_offer(record)
            with np.load(old['base'], allow_pickle=False) as previous:
                compatible = aligned_disjoint(mask, departure, physical_mask(previous, old['route']), old['departure'])
                comparisons.append(dict(offer=old['id'], disjoint=compatible))
        if any(not c['disjoint'] for c in comparisons):
            return dict(status='GEOMETRIC_CONFLICT', comparisons=comparisons)
        info = dict(id=message['id'], service=service, departure=departure,
                    route=service['route'], snapshot=message['snapshot'], end=departure+8,
                    base=str(self.base_path), base_digest=self.metadata['base_digest'],
                    checks={**self.metadata['checks'], 'compatible': True}, comparisons=comparisons,
                    evidence='WITNESSED', scope='Bicycle5D numerical corridor and exact nominal straight-motion execution')
        path = self.base_path.parent/f"offer-{message['id']}.json"
        path.write_text(json.dumps(info, sort_keys=True, indent=2, allow_nan=False))
        return dict(status='QUALIFIED', artifact=str(path), artifact_digest=file_digest(path), info=info)

    def refine(self):
        path = self.base_path.with_suffix('.refinement.json')
        if path.exists():
            data = json.loads(path.read_text())
            if data['base_digest'] == self.metadata['base_digest']:
                return {**data, 'cache_hit': True}
        started = perf_counter()
        spec = GridSpec((Axis('t', 0, 9, 73), *self.spec.axes[1:]), accuracy=self.spec.accuracy)
        p = LTMSPlanner.bicycle5d(spec, **self.metadata['config']['controls'])
        regions = create_4way(p.grid, 'road_e', 'exit_e')
        _, tube = p.until(regions['road_e'], regions['exit_e'], target_window=TimeWindow(7, 8))
        index = tuple(np.abs(np.asarray(a)-s).argmin() for a, s in
                      zip(p.grid.coordinate_vectors, [-1.6, -.4, 0, 0, SPEED]))
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
                                       np.array(b['times']), np.array(b['states']), BODY)
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
        if message['op'] == 'prepare':
            return self.prepare(message['output'])
        if message['op'] == 'evaluate':
            return self.evaluate(message)
        if message['op'] == 'refine':
            return self.refine()
        if message['op'] == 'final':
            return self.final(message['accepted'], message['attempts'])
        raise ValueError('unknown worker operation')


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
