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

Every run performs real Bicycle4D HJ integration (the four passes and the TLT);
nothing is cached between runs. The optional `--cwd notebooks` runner flag tests the
other supported working directory.

## Workflow

The notebook follows `protocol.ipynb` stage by stage (admit → generate → bargain →
commit), with corridor-valued offers in place of bookings and one dependency chain:

```
contracts → owner obligation F_s → generated query → TLT → HJ realization
```

Contract algebra manipulates specifications; reachability answers one stated
question about them under the dynamics. Claims are labelled **[algebra]** (contract
identities by Boolean normalization), **[semantic]** (entailments under the dynamics
and the fixed client rule) or **[numerical]** (HJ membership on the declared grid).

1. **Model.** The vehicle (pyspect's Bicycle4D: steering-angle and acceleration
   bounds, route-local chart), the road as boxes over named axes, the entry state,
   the lease and the certified-window relation $s+8\le d$. The client's task is a
   structured formula,
   $\Phi_s=(\mathit{road}\land\mathit{alloc}_j)\ \mathcal U_{[s,d]}\ \mathit{exit}$,
   read at departure $s$ from the entry state, and $T_\theta=\bigvee_s\Phi_s$. The
   capability predicate $F_s(r_j)$ ("some input satisfies $\Phi_s$ under the
   allocation $r_j$") is owner-only, and sufficient access is $S_a=\bigvee_s F_s$.
2. **Environment, generator and query.** The grid; the map regions as pyspect set
   builders. The four LTMS passes, the lane strip and the projection/inflation
   *generate* the candidate reservation $R_\kappa$; they are the owner's heuristic,
   not evidence. `ltms_bla.tlt.compile_query` generates the TLT from $\Phi_0$ with
   $\mathit{alloc}:=R_\kappa$ (as a signed-distance level set). Because
   $\mathit{alloc}$ occurs only positively, $F_s$ is monotone in the allocation, so
   $H_\kappa\vDash F_s$ exactly when $F_s(R_\kappa)$, which the realized value at the
   entry state decides. One query serves every template: the dynamics are
   time-invariant and the map is symmetric under rotation by pi.
3. **Contracts, admission and offers.** Cells tagged `definitions` hold the method:
   the model cells, `service_contracts`, `admit`, `generate`, `commit`, `attempt` and
   the scenario inputs. $C_{\rm client}=\langle S_a\mid T_\theta\rangle$,
   $R_{\rm task}=\langle\top\mid T_\theta\rangle$, and the quotient's guarantee is
   $S_a$. Admission asserts these identities and computes the feasible departures:
   the certified window fits, the generated query holds, and the template's
   reservation is disjoint from every standing one. It tries the original service,
   then permitted alternatives in order; exhaustion is `NO-BLA`. Each offer
   $K_\kappa=\langle\top\mid H_\kappa\land F_s\rangle$ records that evidence in a
   certificate; $K_\kappa\Rightarrow S_a$ is algebraic.
4. **Staged execution.** A is committed through `attempt`. B is walked through
   every stage against A: contracts and feasible departures, both offers with their
   certificates, bargaining and commitment. C–E use `attempt`.

The client $\pi_r$ (realize $V_r$ for $\Phi_s$ with $\mathit{alloc}:=r$ and execute
the HJ feedback) is part of the model, not of the evidence: with exact dynamics
and an exact value function, $F_s(r)$ and that rule give $\Phi_s$ **[semantic]**.

## Scenario

Five serial requests, all negotiated at frozen virtual decision time zero:

| Client | Intended case | Outcome |
| --- | --- | --- |
| A | First eastbound crossing. | `COMMITTED` |
| B | Two westbound alternatives for one fixed service, during A's lease. | `COMMITTED` |
| C | Same-lane templates incompatible with A's reservation: no feasible departure. | `NO-BLA` |
| D | Feasible later templates, rejected through price bargaining. | `NO-BLA` |
| E | Original deadline too short for the certified window; a permitted later service is accepted. | `COMMITTED` |

`ltms_reachability` supplies the four LTMS passes and the pyspect
constrained-until TLT. `protocol.Contract` and `normalize` derive the quotient and
the fixed-service implication. The actual `bargain` function body is loaded from
the `protocol.ipynb` definition cells; only its eligibility validator is replaced
for corridor offers (certified, compatible, implying $S_a$, one service). Commit
uses `protocol.validate_commit` unchanged.

`ltms_bla` contains only reusable machinery: immutable records, the TLT generator
for interpreted formulas, raster disjointness, the notebook-method loader and table
presentation. Prices are outside the guarantees.

## Mathematical scope

The plant is a kinematic bicycle with state `(x,y,h,v)` on an eastbound
route-local heading chart; westbound uses its rotation by pi. Vehicles are points.
The grid is `(37,31,61,9,7)` over `(t,x,y,h,speed)`.

The query is generated only from the supported fragment: Boolean combinations of
interpreted state atoms and one bounded until with a closed absolute window read
at its anchor; anything else is refused. pyspect marks the realized TLT as an
under-approximation. Reservations cover the full sampled corridor projection with
closed-cell and time-slab padding.

These results support the declared finite, nominal example. They do not prove
general feedback enforcement, uncertain tracking, complete offer coverage or
rigorous continuous-time HJ approximation bounds.

## Checks

```sh
PYTHONPATH=src uv run --no-project --python 3.13 \
  --with 'pyspect[hj_reachability]==1.2' --with pillow --with portion --with plotly \
  python -m unittest tests/test_ltms_bla_protocol.py tests/test_ltms_bla_geometry.py \
  tests/test_ltms_numerics.py -v
```

Lifecycle checks run the notebook's own definition cells, through `load_method`,
against a small synthetic reservation: scenario outcomes, prices and departures,
quotient/conjunction identities, service adaptation, refinement and composition,
rejection of uncertified offers, exact commit and parity with the charging
bargaining implementation. Numerical checks cover the LTMS passes, the generated
query against the windowed until, touching closed cells and neighbouring time
slabs. The fresh-kernel notebook is the real-backend integration check.
