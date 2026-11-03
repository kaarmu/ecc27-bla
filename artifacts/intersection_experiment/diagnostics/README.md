# Experiment B diagnostics: request A (Parts 1–2 of the follow-up prompt)

**Result: no configuration reaches zero violations.** The smallest residual is one-step driving limits that target an
inner corridor {V ≤ −0.03}. It gives 0/100 runs leaving the corridor, but 8/100 blocked before exit and 32/5,864
empty cells. All numbers are grid-based HJ approximations, not exact sets.

Reproduce from the `interval_logic` root:

```sh
uv run --locked --extra reachability --group experiment python scripts/intersection_diagnostics.py
```

This writes `diagnostics.json`. The run takes about 3 min on an NVIDIA GPU; the machine and versions are in
`../environment.json`.

## Setup

| | |
|:--|:--|
| Corridor | request A (east→east, J = [0, 0.5] s), candidate κ2, K = [6, 7.25] s; the offer accepted in the first run |
| Grid | (t, x, y, h, v) = 41 × 41 × 41 × 16 × 5; Δt = 0.25 s, 0.1 m, π/8 ≈ 0.39 rad, 0.075 m/s |
| Samples | M = 100 per configuration, the same for all. Samples 1–25 are the first run's entry states, recovered by replaying its seed; 26–100 use seed 1. Controls use seed 2. |
| Stay check | outer corridor V ≤ 2·10⁻⁵ at every substep (Δt/10), by multilinear interpolation over (t, x, y, h, v); outside the grid counts as outside |
| Non-blocking | evaluated at every grid node of the set the vehicle drives in, before exit; nodes in E_out during K are exempt |

## 1. Where the 311 empty cells are

| Property | Result |
|:--|:--|
| Distance to the boundary (Chebyshev, grid cells; grid edge counts as outside) | **all 311 at distance 1**; no interior cell is empty |
| Value V | min −2.4·10⁻³, median 0, max 1.3·10⁻⁷: 118 negative, 59 exactly 0, 134 with 0 < V ≤ tol |
| Outside neighbour along the axis | h: **311**, y: 308, v: 297, x: 287 |
| Speed of the empty cells | v = 0.300: 70, 0.375: 85, 0.450: 56, 0.525: 52, 0.600: 48 (the corridor's v = 0.3 layer holds 13% of its cells but 23% of the empty ones) |
| Time | spread over 0–6.75 s, 2–19 cells per sample, no concentration at entry or exit |

The whole corridor's values are similarly degenerate. Of its 16,377 cells, 5,397 have V exactly 0 and 1,609 have
0 < V ≤ tol. Values range only from −0.1 to 0.

## 2. What the current driving limits implement

- **Definition.** Control u, from a 9 × 9 grid over δ ∈ [−π/4, π/4] and a ∈ [−0.15, 0.15], is admissible at (t_k, z)
  iff holding u for Δt gives V(t_{k+1}, z⁺) ≤ 2·10⁻⁵. Here z⁺ comes from 10 RK4 substeps, and V is read at z⁺ by
  multilinear interpolation. So it is one-step membership of the next sample state in the corridor.
- **Non-blocking (check 5).** This condition, evaluated at the corridor's grid nodes z.
- **Sampled runs (check 6).**
  - Nothing is snapped to a node: the same interpolated test is applied at the continuous state at each time sample.
  - A random admissible u is held for Δt.
  - Corridor membership is checked at the 10 substeps, also interpolated, including in time.
- **Sensitivity.** The result does not depend on the control grid: 9×9, 21×21 and 41×41 all give 311 empty cells.
  Nearest-node membership gives 319.

## 3–6. Configurations (100 runs each)

| Configuration | Empty driving-limit cells | Left corridor | Blocked (= no exit) | Any violation (of first 25) | E_in×J ⊆ driving set |
|:--|--:|--:|--:|--:|:--|
| Current: one-step, outer corridor | 311 / 13,921 | 66 | 13 | 68 (15) | yes |
| **3** value gradient ∂ₜV + ∇V·f ≤ 0, everywhere | 1,625 / 13,921 | 0 | 100 | 100 (25) | yes |
| 3′ value gradient, any u where V ≤ 0 | 221 / 13,921 | 71 | 89 | 95 (24) | yes |
| **4** one-step, inner = eroded by 0 cells | 628 / 13,921 | 23 | 49 | 64 (12) | yes |
| 4 one-step, inner = eroded by 1 cell | 1 / 437 | 0 | 41 | 41 (10) | **no** |
| 4 one-step, inner = eroded by 2 or 3 cells | 0 / 0 (empty set) | 0 | 100 | 100 (25) | **no** |
| 4 one-step, inner = {V ≤ −0.005} | 29 / 7,086 | 22 | 17 | 38 (8) | yes |
| 4 one-step, inner = {V ≤ −0.01} | 39 / 6,866 | 0 | 16 | 16 (2) | yes |
| 4 one-step, inner = {V ≤ −0.02} | 43 / 6,391 | 0 | 10 | 10 (1) | yes |
| **4 one-step, inner = {V ≤ −0.03}** | **32 / 5,864** | **0** | **8** | **8 (4)** | yes |
| 4 one-step, inner = {V ≤ −0.05} | 43 / 4,578 | 0 | 24 | 24 (5) | **no** |
| **6** value gradient, any u where V ≤ −ε, ε = 0.005 / 0.01 / 0.02 | 711 / 747 / 838 | 21 / 6 / 1 | 86 / 82 / 86 | 89 / 85 / 86 | yes |
| **5** current construction, Δt = 0.125 s | 746 / 28,443 | 47 | 38 | 62 (16) | yes |
| **6** one-step, inner {V ≤ −0.03}, Δt = 0.125 s | 213 / 12,690 | 0 | 35 | 35 (8) | yes |

Notes on the table:
- The manager still reserves the full corridor in every row; only the vehicle's control rule changes.
- **Erosion by grid cells** uses Euclidean distance in cells over (x, y, h, v), with the grid edge counted as outside
  (the v grid is exactly the speed limit). It removes the set almost entirely: the corridor is at most about two cells
  thick in h and v.
- **{V ≤ −ε}** is the "equivalent in V". One grid step of V is about 0.005–0.02 near the boundary (median one-cell
  increments along y, h and v).
- **Value-gradient controls** use ∂ₜV as a forward difference and ∇V by central differences, with h periodic. They are
  re-chosen at every substep, since the condition is a continuous-time one.
- **Δt = 0.125 s:**
  - the tube is 81 × 41 × 41 × 16 × 5, 42 MiB at float32 (2× the 21 MiB at Δt = 0.25 s);
  - the three corridors take 3.0 s instead of 2.6 s on the GPU;
  - peak process memory is the same (5.3 GiB, dominated by JAX);
  - K rounds to [6, 7.375] s.

## Best explanation (a hypothesis, not established)

- **The bottleneck is state resolution, especially heading.**
  - Every empty cell has an outside neighbour along h.
  - The corridor is only one to two heading cells (0.39 rad each) wide.
  - It cannot be eroded by even 2 cells without vanishing.
  - Halving Δt does not help; it doubles the empty cells, at a similar rate (2.6% vs 2.2%).
- **The minimum speed contributes.** At v = 0.3 m/s, braking leaves the grid, which is also the speed limit, so
  v = 0.3 cells are over-represented among the empty ones.
- **The value function is too flat for gradient controls.** V is clipped (a third of the corridor is exactly 0) and the
  set moves about 1.1 cells per time step. So ∂ₜV > 0 is not offset by ∇V·f, and the gradient filter's set is empty
  along every sampled path.
- **The margin trades leaving for blocking.** With {V ≤ −ε}, the vehicle never leaves the reserved corridor. The
  remaining blocks happen when the inner set's slice thins out (blocks at 2.5–6.75 s).

**Untested next step:** a finer heading and speed grid, e.g. 32 × 9 instead of 16 × 5. It costs about 3.6× the memory
per tube (about 76 MiB) and a comparable factor in compute. This was not run.

## Deviations from the prompt

- The paper repository and its `docs/shared/intersection_experiment/` are not on this machine. The diagnostics are in
  `interval_logic/artifacts/intersection_experiment/diagnostics/` instead.
- The paper-repository commit hash is unknown.
- The `interval_logic` code commit is recorded in this file's git history.
- The driving limits are this harness's definitions, because the port's `control_limits` does not support the
  non-control-affine `Bicycle4D`.
