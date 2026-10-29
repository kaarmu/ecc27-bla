# Reachability-based BLA notebook

Open `notebooks/ltms_blas.ipynb` or execute it from this repository root:

```sh
uv run --group notebooks python scripts/run_ltms_notebook.py --save
```

The notebook runs in a **Python 3.13 kernel** with `pyspect[hj_reachability]==1.2`,
because JAX has no Python 3.14 wheel on Intel macOS. The project itself keeps its
`requires-python >=3.14`; the protocol and logic packages also run unchanged on 3.13.
The runner starts that kernel with `uv run --no-project --python 3.13` and the
packages listed in `scripts/run_ltms_notebook.py`; uv provisions them. A
preconfigured interpreter can instead be selected with `LTMS_PYTHON`. To work
interactively, create a persistent environment and select it as the kernel:

```sh
uv venv --python 3.13 .venv-ltms
uv pip install --python .venv-ltms 'pyspect[hj_reachability]==1.2' pillow \
  'matplotlib>=3.10' 'portion>=2.6.1' plotly ipykernel
```

Do not source the legacy catkin workspace.

Every run performs real Bicycle4D HJ integration (the TLT, the four passes and a
half-step refinement); it takes about a minute. Nothing is cached between runs. The
optional `--cwd notebooks` runner flag tests the other supported working directory,
and `--output` writes the artifacts elsewhere:

```sh
uv run --group notebooks python scripts/run_ltms_notebook.py --output /tmp/ltms
```

## Workflow

The notebook is an executable derivation in the style of `protocol.ipynb`, with
one dependency chain:

```
contracts → owner obligation F_s → generated query → TLT → HJ realization
```

Contract algebra manipulates specifications; reachability answers one stated
question about them under the dynamics. Each claim is labelled by its evidence
strength: **[algebra]** (contract identities by Boolean normalization),
**[semantic]** (entailments under the dynamics and the declared client),
**[numerical]** (HJ membership on the declared grid) or **[independent]** (nominal
execution checks and analytic bounds).

1. **Model.** Notebook cells define the vehicle, a point-mass kinematic bicycle
   (`bicycle4d`, steering-angle and acceleration bounds, chart; equal to the
   solver's Bicycle4D), the road as boxes over named axes (`LANE`, the zones,
   `inside`; the same boxes become pyspect set builders in §2) and the client: entry
   state, lease, the certified-window and speed-bound relations, the HJ-feedback
   rule `hj_feedback` and its execution `execute`. The client's task is a structured
   formula, not an opaque atom:
   $\Phi_s=(\mathit{road}\land\mathit{alloc}_j)\ \mathcal U_{[s,d]}\ \mathit{exit}$,
   read at departure $s$ from the entry state, and $T_\theta=\bigvee_s\Phi_s$. The
   capability predicate $F_s(r_j)$ ("some input satisfies $\Phi_s$ under the
   allocation $r_j$") is owner-only, and sufficient access is $S_a=\bigvee_s F_s$.
2. **Environment, generator, query and client.** The grid; the map regions as
   pyspect set builders (`BoxSet`, `PolytopeSet`, `Inter`, `Union`; realized inside
   sets asserted equal to the legacy map). The four LTMS passes, the lane strip and
   the projection/inflation *generate* the candidate reservation $R_\kappa$; they are
   the owner's heuristic, not evidence. `ltms_bla.tlt.compile_query` then generates
   the TLT from $\Phi_0$ with $\mathit{alloc}:=R_\kappa$ (as a signed-distance level
   set): Boolean combinations of state atoms become one realized set and the bounded
   until becomes a TLT until with a box on $t$. Because $\mathit{alloc}$ occurs only
   positively, $F_s$ is monotone in the allocation, so $H_\kappa\vDash F_s$ exactly
   when $F_s(R_\kappa)$, which the realized value at the entry state decides. The
   declared client $\pi_R$ (bang-bang minimizer of $\nabla V_R\cdot f$) is executed
   from the entry state and checked at every sample: in the lane, in the closed
   reserved cells of its slab, in the exit zone before the lease ends, with bounded
   inputs. One query serves every template: the dynamics are time-invariant and the
   map is symmetric under rotation by pi. The certified window is the lease
   $[s,s+8]\subseteq[s,d]$; otherwise the template is `UNRESOLVED`.
3. **Contracts, admission and offers.** Cells tagged `definitions` hold the method:
   the model cells, `service_contracts`, `qualify`, `admit`, `generate`, `commit` and
   `attempt`, and the scenario inputs. $C_{\rm client}=\langle S_a\mid T_\theta\rangle$,
   $R_{\rm task}=\langle\top\mid T_\theta\rangle$ and the quotient's guarantee is $S_a$:
   the physical task leaves the owner's obligation but stays in the definition of
   $F_s$. Admission retains $C_{\rm client}$, $R_{\rm task}$, $Q$, $C_{\rm cmt}$ and
   $C_{\rm cmt}^{+}$ for each tried service and asserts their identities. Each
   template is qualified by *service evidence* (the generated query and the client's
   execution, then the algebraic implication
   $K_\kappa=\langle\top\mid H_\kappa\land F_s\rangle\Rightarrow S_a$) and, separately,
   *compatibility evidence* (disjoint full space–time reservations, an allocation
   witness for $L\land H_\kappa$).
4. **Staged execution.** A is committed through `attempt`. B is walked through
   every stage against A's frozen snapshot: contracts, candidate statuses, both
   offers with their evidence, refinement and composition checks, bargaining
   (frozen utilities, rounds, accepted pair) and exact commitment, including a
   rejected stale re-commit. C–E use `attempt`; E shows its original and permitted
   replacement services with rebuilt contracts.
5. **Evidence.** An accepted-behaviour table evaluates the owner promise, capability,
   client assumption, client guarantee and task for each accepted BLA from evidence:
   until subformulas take the value of the client's checked execution. A failure
   table separates geometric conflict, missing capability (the generated query
   answers no when the allocation starts 1 s late), unresolved numerical evidence,
   proved impossibility and price failure. `run_scenario` then compiles the same
   definition cells and must reproduce the walkthrough's outcomes, offer
   identities, departures, prices and retained promises.

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

`ltms_reachability` supplies the copied four-way geometry,
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

`ltms_bla` contains only reusable machinery: immutable records, the TLT generator
for interpreted formulas, generic raster geometry, artifact storage and verification, the
notebook-method loader and serial runner, and presentation helpers. The model,
environment and numerical construction live in the notebook. Prices are outside
the guarantees. The exact accepted offer object and price are stored without
regeneration. A commit rejects stale snapshots, substituted objects and changed
artifacts. Unsuccessful attempts preserve earlier BLAs and full reservations,
which remain promised until lease end. There is no live transport, cancellation
or concurrent allocation.

## Mathematical scope

The plant is pyspect's Bicycle4D, a kinematic bicycle with state `(x,y,h,v)` and
steering angle and acceleration as inputs, on an eastbound route-local heading chart;
westbound uses its rotation by pi. Vehicles are points: no body size enters the
lane, exit, reservations or separation checks. The grid is `(37,31,61,9,7)` over
`(t,x,y,h,speed)`. This is not the legacy global-grid baseline.

The client is one fixed rule parameterized by the offered allocation: realize
$V_R$ for $\Phi_s$ with $\mathit{alloc}:=R$ and execute the HJ feedback. With exact
dynamics and an exact value function, $F_s(R)$ and that rule give $\Phi_s$; this is
what makes $C_{\rm client}$ valid, and the sampled execution is its independent
check. Sufficient access is a finite disjunction of capability predicates, fixed
before filtering the family against standing commitments. The offer promises its
complete corridor reservation plus the implied capability. Because Boolean
normalization cannot infer entailments between atoms under the dynamics, the
capability evidence is checked before the algebraic implication, and compatibility
is checked separately.

The query is generated only from the supported fragment: Boolean combinations of
interpreted state atoms and one bounded until with a closed absolute window read
at its anchor; anything else is refused. pyspect marks the realized TLT as an
under-approximation. Reservations cover the full sampled corridor projection with
closed-cell and time-slab padding. Pairwise separation of the executions is
sampled every 0.025 s. The generated query is repeated at half the temporal grid
step.

These results support the declared finite, nominal example. They do not prove
general feedback enforcement, uncertain tracking, complete offer coverage or
rigorous continuous-time HJ approximation bounds. The original global LTMS
reproduction and final manuscript model/claims remain separate review work.

## Artifacts and checks

All generated files live under the ignored `artifacts/ltms_blas/` directory:
the full corridor and reservation (`base.npz`, referenced by digest from each offer), offer JSON, `report.json`, `results.md`, standalone
SVG/PNG, and an offline interactive HTML figure. The saved notebook keeps compact
results and native Plotly data. The HTML export includes Plotly itself.

```sh
PYTHONPATH=src uv run --no-project --python 3.13 \
  --with 'pyspect[hj_reachability]==1.2' --with pillow --with portion --with plotly \
  python -m unittest tests/test_ltms_bla_protocol.py tests/test_ltms_bla_geometry.py \
  tests/test_ltms_numerics.py -v
```

Lifecycle checks run the notebook's own definition cells, through `load_method`,
against a small synthetic reservation: scenario outcomes, prices and departures,
quotient/conjunction identities, service adaptation, refinement and composition,
rejection of false evidence, distinct failure meanings, exact identity, stale
snapshots and parity with the charging bargaining implementation. Model checks
exercise the notebook's model cells: the structured task formula and its quotient,
`bicycle4d` against the solver's Bicycle4D, the execution and the HJ-feedback rule,
and the deadline relations. Numerical checks cover timed-target endpoints, the
constraint-at-witness convention, the generated query against the windowed until
(and its refusals), touching closed cells, neighbouring time slabs, between-sample
collisions, sampled separation and box coverage. The
fresh-kernel notebook is the real-backend integration check; synthetic unit-test
evidence is never used in the executed scenario.
