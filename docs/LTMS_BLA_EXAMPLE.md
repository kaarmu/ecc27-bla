# Reachability-based BLA notebook

Open `notebooks/ltms_blas.ipynb` or execute it from this repository root:

```sh
uv run --group notebooks python scripts/run_ltms_notebook.py --save
```

The coordinator uses the project's Python >=3.14 environment. By default a
persistent worker is launched with `uv run --no-project --python 3.13`,
`pyspect[hj_reachability]==1.2`, Pillow and Matplotlib. uv provisions missing dependencies.
This avoids the missing Python 3.14 JAX wheel on Intel macOS. A preconfigured
numerical interpreter can instead be selected with `LTMS_WORKER_PYTHON`.
Do not source the legacy catkin workspace. The coordinator does not import JAX.

The first run performs real Bicycle5D HJ integration; it can take several minutes
and substantial memory. Progress goes to `artifacts/ltms_blas/worker.log`.
The notebook reports cold numerical time, memory and model settings. Later runs
check source/configuration/version and artifact hashes before reusing data.
The optional `--cwd notebooks` runner flag tests the other supported working
directory. For an independent cold run, use a new output directory:

```sh
uv run --group notebooks python scripts/run_ltms_notebook.py --output /tmp/ltms-fresh
```

## Scenario and reuse

The notebook illustrates five serial requests, all negotiated at frozen virtual
decision time zero before execution:

| Client | Intended case |
| --- | --- |
| A | First accepted eastbound crossing. |
| B | Two alternative westbound corridors for one fixed client/service; accepted while A's lease remains active. |
| C | Same-lane templates incompatible with A's retained spatial reservation. |
| D | Compatible later corridors, rejected through price bargaining. |
| E | Original deadline excluded by an independent speed bound; a permitted later service is admitted and accepted. |

`ltms_reachability` supplies the copied four-way geometry, Bicycle5D adapter,
four LTMS passes and actual pyspect constrained-until TLT. `protocol.Contract`
and `normalize` derive the quotient and fixed-service implication. The actual
`bargain` function body is loaded from the trusted `protocol.ipynb` definition
cells. Its eligibility validator is replaced for corridor records; price data,
affine policies, response/concession checks and round rules are reused verbatim.
The charging booking SAT procedure is not used as a spatial solver.

The finite family reuses one verified tube under time translation and map
rotation. Each attempt filters whole corridor reservations against its frozen
accepted snapshot. Conflicting templates are rejected; this example does not
recompute more permissive HJ corridors around an existing reservation.

`ltms_bla` contains the immutable records, coordinator, persistent JSON worker,
independent geometry checks and presentation helpers. Prices are outside the
guarantees. The exact accepted offer object and price are stored without
regeneration. A commit rejects stale snapshots, substituted objects and changed
artifacts. Unsuccessful attempts preserve earlier BLAs and full reservations.
There is no live transport, cancellation or concurrent allocation.

## Mathematical scope

The plant is Bicycle5D with an eastbound route-local heading chart; westbound
uses its rotation by pi. The grid is `(37,31,61,9,5,7)` over
`(t,x,y,h,steering,speed)`. Nonperiodic local heading, steering and speed bounds
and smaller control bounds are declared in the notebook and report. This is
not the legacy global-grid baseline. One stored float32 tube occupies 84 MiB.

The fixed client library consists of straight nominal references with zero
steering rate and acceleration from the specified full entry state. Under
perfect initial state/dynamics, each reference solves the Bicycle5D equations
and clears by its declared time. Sufficient access is a finite disjunction of
whole-reference body-coverage predicates. It is fixed before filtering the
family against standing commitments. The offer promises its complete corridor
reservation plus the geometrically implied reference access. The code checks
the Boolean implication and workspace compatibility separately.

The four-pass output is intersected with a narrow straight lane strip. A single
concrete reference is checked inside this conjunction, not assembled from
independent temporal witnesses. The cropped corridor is not advertised as a
controlled-invariant set for arbitrary inputs. Reservations cover the full
sampled corridor projection with conservative closed-cell, body and time-slab
padding; the reference's complete swept-body boxes are independently checked.
Nominal pairwise body separation is minimized analytically over each common
straight-motion interval. The full body is clear at exit. A native TLT entry
check is also repeated at half the temporal grid step.

These results support the declared finite, nominal example. They do not prove
general feedback enforcement, uncertain tracking, complete offer coverage or
rigorous continuous-time HJ approximation bounds. `UNRESOLVED`, geometric
conflict, price failure and independently proved deadline impossibility are
distinct outcomes. The original global LTMS reproduction and final manuscript
model/claims remain separate review work.

## Artifacts and checks

All generated files live under the ignored `artifacts/ltms_blas/` directory:
hashed full-state arrays, offer JSON, `report.json`, `results.md`, standalone
SVG/PNG, and an offline interactive HTML figure. The saved notebook keeps compact
results and native Plotly data. The HTML export includes Plotly itself.

```sh
uv run python -m unittest discover -s tests -p 'test_ltms_bla_protocol.py' -v
PYTHONPATH=src uv run --no-project --python 3.13 \
  --with 'pyspect[hj_reachability]==1.2' --with pillow \
  python -m unittest discover -s tests -p 'test_ltms_bla_geometry.py' -v
```

Lifecycle checks compare the adapter's bargaining rounds with the original
charging implementation on equivalent utilities and test fixed-service,
exact-identity, stale-snapshot and unsuccessful-attempt invariants. Geometry
checks reject touching closed cells and detect a collision between samples.
The fresh-kernel notebook is the real-backend integration check; synthetic
unit-test evidence is never used in the executed scenario.
