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
The artifact format number is part of the cache key; it is raised whenever stored
evidence changes meaning, so old evidence is never read with a new interpretation.
The optional `--cwd notebooks` runner flag tests the other supported working
directory. For an independent cold run, use a new output directory:

```sh
uv run --group notebooks python scripts/run_ltms_notebook.py --output /tmp/ltms-fresh
```

## Workflow

The notebook is an executable derivation in the style of `protocol.ipynb`. Each
claim is labelled by its evidence strength: **[algebra]** (contract identities by
Boolean normalization), **[semantic]** (implications from reference/body containment
and the fixed client policy), **[numerical]** (TLT and corridor membership on the
declared grid) or **[independent]** (nominal execution checks and analytic bounds).

1. **Behaviour model and predicates.** `ltms_bla.model` fixes the actors, body,
   presence and lease intervals, road, goal and time conventions, and a predicate
   table (arguments, controlling actor, horizon, evidence) for $H_\kappa$, $a_s$,
   $S_a$, $B_j$ and $S_u$. Exact arithmetic shows that a covered eligible reference
   yields access compliance, road compliance and timely full-body clearance, and
   that slower or late references fail. The fixed client departs at the earliest
   eligible departure whose $a_s$ its accepted guarantee implies.
2. **Task → TLT → HJ.** The worker returns the task formula
   `road_e U_[7,8] exit_e`, the realized pyspect tree, the target time samples,
   the backend call and its constraint-at-witness convention. The local window
   $[7,8]$ is a sufficient strengthening of "clear by $d$" when $s+8\le d$;
   otherwise the template is `UNRESOLVED`. A table states which full-body facts the
   reference-point masks imply. The four LTMS passes are reported separately (pass 2
   reuses pass 1), with the lane intersection, the full five-state entry query, the
   reference check and the time-preserving projection and inflation.
3. **Contracts, admission and offers.** Cells tagged `definitions` define
   `service_contracts`, `qualify`, `admit`, `generate`, `commit` and `attempt`.
   Admission retains $C_{\rm client}$, $R_{\rm task}$, $Q$, $C_{\rm cmt}$ and
   $C_{\rm cmt}^{+}$ for each tried service and asserts their identities. Each
   template is qualified by *service evidence* (swept reference body inside the
   reservation, then the algebraic implication $K_\kappa\Rightarrow S_a$) and,
   separately, *compatibility evidence* (disjoint full space–time reservations, an
   allocation witness for $L\land H_\kappa$).
4. **Staged execution.** A is committed through `attempt`. B is walked through
   every stage against A's frozen snapshot: contracts, candidate statuses, both
   offers with their evidence, refinement and composition checks, bargaining
   (frozen utilities, rounds, accepted pair) and exact commitment, including a
   rejected stale re-commit. C–E use `attempt`; E shows its original and permitted
   replacement services with rebuilt contracts.
5. **Evidence.** An accepted-behaviour table evaluates the owner promise, reference
   access, client assumption, client guarantee and task for each accepted BLA, from
   evidence rather than normalization. A failure table separates geometric conflict,
   missing reference coverage, unresolved numerical evidence, proved impossibility
   and price failure. `run_scenario` then compiles the same definition cells and must
   reproduce the walkthrough's outcomes, offer identities, departures, prices and
   retained promises.

## Scenario

Five serial requests, all negotiated at frozen virtual decision time zero before
execution:

| Client | Intended case | Outcome |
| --- | --- | --- |
| A | First accepted eastbound crossing. | `COMMITTED` |
| B | Two westbound alternatives for one fixed service, accepted while A's lease remains active. | `COMMITTED` |
| C | Same-lane templates incompatible with A's retained reservation. | `NO-COMPATIBLE-OFFER` |
| D | Compatible later templates, rejected through price bargaining. | `PRICE-NO-BLA` |
| E | Original deadline excluded by an independent speed bound; a permitted later service is admitted and accepted. | `COMMITTED` |

Template statuses keep their meanings: `QUALIFIED`, `GEOMETRIC_CONFLICT` (template
rejected), `UNRESOLVED` (numerical evidence does not apply) and `PROVED_IMPOSSIBLE`
(independent bound). An empty family is not physical impossibility.

`ltms_reachability` supplies the copied four-way geometry, Bicycle5D adapter,
four LTMS passes and actual pyspect constrained-until TLT. `protocol.Contract`
and `normalize` derive the quotient and fixed-service implication. The actual
`bargain` function body is loaded from the trusted `protocol.ipynb` definition
cells. Its eligibility validator is replaced for corridor records, requiring both
certificates, one service and one snapshot; price data, affine policies,
response/concession checks and round rules are reused verbatim. The charging
booking SAT procedure is not used as a spatial solver.

The finite family reuses one verified tube under time translation and map
rotation. Each attempt filters whole corridor reservations against its frozen
accepted snapshot. Conflicting templates are rejected; this example does not
recompute more permissive HJ corridors around an existing reservation.

`ltms_bla` contains the declared model, immutable records, worker transport and
artifact checks, the notebook-method loader and serial runner, the persistent JSON
worker, independent geometry checks and presentation helpers. Prices are outside
the guarantees. The exact accepted offer object and price are stored without
regeneration. A commit rejects stale snapshots, substituted objects and changed
artifacts. Unsuccessful attempts preserve earlier BLAs and full reservations,
which remain promised until lease end. There is no live transport, cancellation
or concurrent allocation.

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
whole-reference body-coverage predicates, fixed before filtering the family
against standing commitments. The offer promises its complete corridor
reservation plus the geometrically implied reference access. Because Boolean
normalization cannot infer containment between different atoms, the containment
evidence is checked before the algebraic implication, and compatibility is
checked separately.

The four-pass output is intersected with a narrow straight lane strip; the strip
plus the body radius lies inside the lane. A single concrete reference is checked
inside this conjunction, not assembled from independent temporal witnesses. The
road/goal TLT is an independent task-feasibility check: it does not check offer
allocations, and its witness is not the reference controller. The cropped corridor
is not advertised as a controlled-invariant set for arbitrary inputs. Reservations
cover the full sampled corridor projection with conservative closed-cell, body and
time-slab padding; the reference's complete swept-body boxes are independently
checked. Nominal pairwise body separation is minimized analytically over each
common straight-motion interval. A native TLT entry check is also repeated at half
the temporal grid step.

These results support the declared finite, nominal example. They do not prove
general feedback enforcement, uncertain tracking, complete offer coverage or
rigorous continuous-time HJ approximation bounds. The original global LTMS
reproduction and final manuscript model/claims remain separate review work.

## Artifacts and checks

All generated files live under the ignored `artifacts/ltms_blas/` directory:
hashed full-state arrays, offer JSON, `report.json`, `results.md`, standalone
SVG/PNG, and an offline interactive HTML figure. The saved notebook keeps compact
results and native Plotly data. The HTML export includes Plotly itself.

```sh
uv run python -m unittest tests/test_ltms_bla_protocol.py tests/test_ltms_bla_model.py -v
PYTHONPATH=src uv run --no-project --python 3.13 \
  --with 'pyspect[hj_reachability]==1.2' --with pillow \
  python -m unittest tests/test_ltms_bla_geometry.py tests/test_ltms_numerics.py -v
```

Lifecycle checks run the notebook's own definition cells, through `load_method`,
against synthetic worker replies: scenario outcomes, prices and departures,
quotient/conjunction identities, service adaptation, refinement and composition,
rejection of false evidence, distinct failure meanings, exact identity, stale
snapshots and parity with the charging bargaining implementation. Model checks
cover the exact client argument, deadline relations and mask-to-body implications.
Numerical checks cover timed-target endpoints, the constraint-at-witness convention,
touching closed cells, between-sample collisions and swept-body coverage. The
fresh-kernel notebook is the real-backend integration check; synthetic unit-test
evidence is never used in the executed scenario.
