# LTMS reachability numerics

`src/ltms_reachability` extracts the reusable numerical parts of
`safe_intersections` into this workspace, alongside `protocol`. All HJ PDE
integration goes through **`pyspect[hj_reachability]==1.2`** and its `TVHJImpl`.
There is no dependency on ROS, NATS, catkin or the thesis workspace.

## Environment

The core project keeps its Python **>=3.14** requirement. Numerical dependencies
are optional:

```sh
uv sync --extra reachability --group notebooks
uv run --extra reachability python examples/smoke_ltms.py
uv run --extra reachability python -m unittest discover -s tests -p 'test_ltms_*.py' -v
```

JAX wheels must support the interpreter and platform. On the development Intel
Mac, the requested stack has no Python 3.14 `jaxlib` wheel. Its numerical tests
were therefore run in an isolated Python 3.13 process, using the package source:

```sh
PYTHONPATH=src uv run --no-project --python 3.13 \
  --with 'pyspect[hj_reachability]==1.2' --with pillow \
  python examples/smoke_ltms.py

PYTHONPATH=src uv run --no-project --python 3.13 \
  --with 'pyspect[hj_reachability]==1.2' --with pillow \
  python -m unittest discover -s tests -p 'test_ltms_*.py' -v
```

These commands run from the repository root and do not install the >=3.14 root
distribution into Python 3.13. `GridSpec`, `Axis`, `TimeWindow` and `WindowPolicy`
can be imported by `protocol` without NumPy/JAX/pyspect. Running the numerical
planner **inside** the 3.14 protocol process on that Mac still needs a compatible
backend environment; a cross-process protocol adapter is not included here.
Use a clean shell without the old catkin Python path, which can shadow the
current `hj_reachability` dependency. Pillow is included because pyspect's
imports use it.

## Notebook starting point

```python
from ltms_reachability import (
    GridSpec, LTMSPlanner, TimeWindow, WindowPolicy,
    create_4way, route_constraints,
)

planner = LTMSPlanner.bicycle5d(GridSpec.bicycle5d())
regions = create_4way(planner.grid)
entry, goal = regions['entry_w'], regions['exit_e']
rules = route_constraints(regions, 'entry_w', 'exit_e')

# Cache this only for the identical grid, dynamics, goal and constraints.
offline = planner.reach(goal, rules)
result = planner.analyze(
    entry=entry, goal=goal, constraints=rules, offline=offline,
    entry_window=TimeWindow(0, 3),
    policy=WindowPolicy(min_entry=1, max_entry=2, min_exit=1, max_exit=2),
    reservations=(), time_origin=0,
)

tube = result.corridor               # (t, x, y, heading, steering, speed)
window = result.entry_window         # local time, explicit closed endpoints
spatial = result.reservation(body_radius=0.0)  # explicit reference-point projection
```

The default grid is the source notebook's `(41,41,25,5,7)` state grid and
76 time samples over 15 s. One float32 tube occupies about **426 MiB**; four
passes, work buffers and JAX compilation need substantially more memory.
`examples/smoke_ltms.py` uses a tiny grid and short horizon to verify
installation, rather than attempting a complete intersection crossing.

`analyze` computes four passes: road/goal backward reachability; backward
recomputation avoiding explicit reservations; forward restriction to the chosen
entry window; backward restriction to the chosen exit window. It returns
read-only arrays and metadata, never commits a reservation or writes a cache.
An `offline` array must have been computed with the same model and rules;
shape compatibility alone cannot verify its provenance. `GridSpec.fingerprint`
is a configuration identifier, not a complete certificate or cache key.

To connect a temporal query to the actual pyspect TLT:

```python
tree, root = planner.until(rules, goal, target_window=TimeWindow(8, 12))
# TLT(UNTIL(admissible, goal-in-window)) -> TVHJImpl -> hj_reachability
```

This helper builds pyspect's `ContLTL` constrained-until tree. The backend also
requires the constraint at the target witness. It does not translate the full
`interval_logic` language, and numerical output is not an exact satisfaction set.
For lower-level experiments, use `planner.impl` directly.

## Reservation and control interfaces

`result.reservation(body_radius=...)` projects each full state slice onto the
xy-plane. It preserves time: it is **not** the union of the corridor over time.
The radius is a separately declared physical body bound; wheelbase does not
determine it. Pass accepted `SpatialReservation` objects to `analyze`, with
`time_origin` aligning local solver time to their absolute timestamps.
Avoidance expands the stored grid-point occupancy by the sum of both body
radii and `clearance`, measured in workspace units. Different spatial grids
are rejected. Time alignment unions the stored samples bracketing each query
time cell; it does not bound unknown motion between those samples. Cell size,
tracking uncertainty and swept-body allowances need a separate justification.

`planner.control_limits(tube, state, time_index)` adapts the legacy driving-limit
calculation. For control-affine dynamics it returns the box and half-space

`a + b @ u <= 0`, with `a = V[k+1,i] + dt * grad(V[k])[i] @ f(x)` and
`b = dt * grad(V[k])[i] @ g(x)`.

`limits.project(nominal)` projects a nominal input into this numerical set;
`limits.sample()` exposes a control grid. This is a finite-difference heuristic,
not a certified safety controller. Terminal indices and out-of-domain states
are rejected.

## Provenance and validation boundary

Adapted from `safe_intersections` commit
`c6a324aab36ac536dcc82b6873394dd1fd23bbbc`, branch `pyspect-1.2`:

- `src/ltms/src/ltms_util/solver.py`: four-pass workflow and driving limits;
- `src/ltms/src/ltms_util/env.py`: four-way and chaos geometry;
- `src/ltms/src/hj_reachability/shapes.py`: level-set geometry and projection.

The original MIT notice is in the package's `NOTICE`. The legacy PDE solver,
server/session code, transport, plots, machine-specific artifacts and notebooks
are not copied. Bicycle5D and PDE integration come from pyspect.

Intentional changes: independent work buffers; explicit time/axis metadata;
window durations measured between samples with inclusive selected endpoints;
explicit pass indices; five-state support in the four-way map; full-horizon
pass-2 recomputation; disk margins in physical workspace units; and explicit
exceptions instead of assertions or debugger entry. Exit selection uses the
first qualifying sampled goal-overlap window; it does not retain the source's
second heuristic for exit-window selection. Consequently this is a tested
adaptation, not bit-for-bit reproduction of the old planner.

Tests exercise real HJ integration, agreement with a native TLT, known 1D motion,
four-pass candidate-order independence, cached-input preservation, sampled
reservation avoidance, geometry, time endpoints and control projection.
`NoCorridorError` reports that this sampled procedure found no suitable window;
it does not prove physical impossibility. The full source-resolution LTMS
baseline, continuous-time collision bounds, client/BLA model, admission,
bargaining and paper experiments remain subsequent work.
