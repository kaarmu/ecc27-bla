# Section V, Experiment B: four-way intersection

Five crossing requests, handled one at a time through the same protocol stages as Experiment A (charging).
Every set is a grid-based HJ approximation (pyspect `TVHJImpl`, 41×41×16×5 grid over (x, y, h, v), Δt = 0.25 s,
corridor membership V ≤ 2·10⁻⁵), not an exact set.

## Reproduce

From the repository root:

```
uv run --locked --extra reachability --group experiment python scripts/intersection_experiment.py
```

The run takes about 18 s on the machine in `environment.json`. It writes `log.json`, `table.csv`,
`environment.json` and `figure.pdf` here, and exits non-zero if any check fails. The figure is written
only for a complete run with zero violations.

- Code: commit `886d969` (`scripts/intersection_experiment.py`, `scripts/bla_stages.py`,
  `notebooks/ltms_blas.ipynb`).
- Protocol: `notebooks/protocol.ipynb` and `src/protocol/`, unchanged since Experiment A (`18b28f5`).
- Seed 0. The scenario has no random draws.

## Scenario

| Request | Route | J [s] | Case |
|:--|:--|:--|:--|
| A | east→east | [0, 0.5] | as requested, accepted |
| B | west→west | [0, 0.5] | simultaneous with A, non-conflicting, its own corridor |
| C | south→south | [4, 4.5] | NO-BLA: the owner's minimum is below the client's highest acceptable price, but the 4-round budget runs out |
| D | east→south | [3, 3.5] | rejected on price in round 1, accepted in round 2 |
| E | north→west | [1, 1.5], then J′ = [5, 5.5] | E_in × J ⊄ sat∃(φ_E): published AIM's `reserve` refuses it. Adapted to J′; 3 certified, compatible offers with different exit windows; bargained and committed |

## Checks (owner side, after every attempt)

| Check | Evaluated | Violations |
|:--|--:|--:|
| 1 Committed corridors pairwise disjoint, clearance 2 × 0.075 m | 11 | 0 |
| 2 Certified flag = independent coverage of E_in × J | 15 | 0 |
| 2 Offer covers E_in × J | 11 | 0 |
| 2 Offer within 𝒞_j | 11 | 0 |
| 2 Offer leads E_in → E_out | 11 | 0 |
| 3 Offer compatible: avoids 𝒟_j | 11 | 0 |
| 4 Candidates order-independent; caches, inputs and committed tubes unchanged | 5 | 0 |
| 5 No computation after admission | 5 | 0 |
| 5 Commit = priced offer (ID and tube hash) | 4 | 0 |
| 5 NO-BLA/rejection leaves commitments unchanged | 1 | 0 |
| 5 Committed tubes unchanged | 5 | 0 |
| 6 Bargaining and commit validators | 5 | 0 |
| 7 Protocol code shared with charging | 5 | 0 |

- Check 1 compares (x, y) cells projected over (h, v), at t_i and t_{i+1}. It is evaluated over all committed
  pairs after each attempt (0 + 1 + 1 + 3 + 6 = 11).
- Checks 2–3 recompute E_in from the box bounds and compute 𝒞_j, E_out and 𝒟_j independently of the notebook's
  `covers` and `danger`.

## Figure

`figure.pdf`: 8.5 cm wide, 7 pt text. It shows x–y slices of every committed corridor at t = 5, 6 and 7 s,
projected over (h, v): earlier corridors in gray, E's in blue rgb(30, 100, 180). The times are chosen
automatically: 6 s is when E's corridor comes closest to an earlier one (0.4 m, to D), plus one second
either side.

## Deviations from the prompt

- **Notebook `covers` changed (`886d969`).**
  - Problem: it read E_in as pyspect's level set ≤ 0. Grid points on the box bounds have float32 values up to
    about 10⁻⁷, so 63 of the box's 81 grid points per time sample dropped out, including every point with
    h ≠ 0. Check 2 found this on request D's κ1, which missed one corner of the closed box (V = 1.6·10⁻³).
  - Fix: `covers` now uses the same tolerance as corridor membership, so it certifies against the closed box.
  - Effect: D's κ1 is no longer certified. In the notebook's own sequence, F now gets 2 offers instead of 3.
- **No closed-loop trajectories (D136).** The driving-limit check and the sampled rollouts are removed, and
  the optional trajectory in the figure is left out.
- **Caches (check 4).** The planner keeps no caches by design (`src/ltms_reachability/planner.py:65`).
  Check 4 confirms this by digesting the planner's and the solver's attributes before and after the
  candidate runs.
- **Path.** Outputs are in `artifacts/intersection_experiment/` at the repository root.
- **Table columns.** `table.csv` names its columns with units: `J_s`, `J_admitted_s`, `K_star_s` (exit window),
  `q_star_eur` (price), `time_s`.
- **Earlier work.** `diagnostics/` is the earlier request-A diagnostic of the dropped checks, kept for the record.
