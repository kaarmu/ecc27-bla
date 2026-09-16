# PROTOCOL.md gaps

Open work on [PROTOCOL.md](PROTOCOL.md), split into two sections. Section A
(A.1-A.12) is specification gaps, derived by treating
[`notebooks/protocol.ipynb`](../notebooks/protocol.ipynb) as the reference
implementation and asking what the specification fails to say; each names the
location in PROTOCOL.md and what the notebook does instead. Section B
(B.1-B.7) is a design direction rather than a gap: giving the contracts'
assumption slot something to do.

Fix order: A.1 and A.2 are the places a careful reader cannot proceed without
inventing something. A.12 is the most consequential: it is the difference
between every other item in Section A being a gap in a contract-driven
derivation and being a note on a separate interval algorithm that contracts
merely narrate. It cannot be stated before A.1, A.8 (region difference needs
$\mathbb I$ pinned) and A.10 (the region a formula denotes is anchor-relative).

## Section A — Specification gaps

**Status: closed.** All twelve items are implemented in
[PROTOCOL.md](PROTOCOL.md). The three structural additions are
§Inputs/*Contracts* (saturation, refinement, the $\bullet$ and $\div$ formulas,
and the consistency/compatibility/realizability triple),
§Inputs/*The reservation fragment and its realization* (the one lemma that
Steps 2, 3, 4 and 6 now each apply), and the pinning of
$\mathbb I:=[0,\infty)$ and of the admissible shape of $I$. The remaining
items are local: §2 states consistency as a query and derives the intersection
test from it, §3 carries the $\bar C^{\mathrm{post}}$ derivation and the
soundness argument for promotion, §4 gives erosion endpoints and the
representative rule, §5 fixes the burst and the tie-break, and §6 gives the
revalidation predicate and compare-and-restart atomicity.

### Definitional holes

The specification cannot be implemented as written until these are closed.

- [x] **A.1. Define merging, separation, and consistency for conditional
  contracts, and state saturation.**
  [§Inputs L129-130](PROTOCOL.md#L129-L130) defines
  merging only for unconditional contracts, but
  [§3 L281-283](PROTOCOL.md#L281-L283) merges
  $\bar C^{sp}\bullet\bar C^{\mathrm{cmt}}$, where $\bar C^{sp}$ has a
  nontrivial assumption. Separation is only characterized as the least
  separating contract in the refinement preorder
  ([L286-293](PROTOCOL.md#L286-L293)), never given.
  Consistency is given only semantically and only for unconditional contracts
  ([L130-131](PROTOCOL.md#L130-L131), "some admissible trajectory satisfies
  $(\xi,0)\models G$"): there is no operational definition to compute with,
  and nothing says what it means once the assumption is nontrivial, where
  compatibility of $A$ is also at stake (B.5 and B.6 reach this from the other
  side). Saturation is not mentioned at all, although the operations below are
  only correct on saturated contracts. The notebook stores
  $\langle A\mid G\rangle$ as $\langle A\mid G\lor\neg A\rangle$, decides
  consistency by evaluating the guarantee with `simplify`, and takes

  $$
  C_1\bullet C_2=\langle A_1\land A_2\mid (G_1\land G_2)\lor\neg(A_1\land A_2)\rangle,
  \qquad
  C_1\div C_2=\langle (A_1\land G_2)\lor\neg(G_1\land A_2)\mid G_1\land A_2\rangle.
  $$

- [x] **A.2. Make §4 well-defined for a continuous start set, or restrict
  $I$.** The boxed $\mathcal J$ at
  [§4 L344-348](PROTOCOL.md#L344-L348) is a set comprehension over $s\in I$,
  which is uncountable when $I$ is continuous.
  $I$ is itself only introduced by example
  ([§Inputs L96-103](PROTOCOL.md#L96-L103), "The start-grid policy is, for
  example"), so the admissible shape of a request's start set is never stated.
  The notebook takes $I$ to be any bounded finite union of intervals and
  singletons, computes the whole feasible region
  $F=I\cap\{s:[s,s+d)\subseteq J\}$, and then selects finitely many
  representatives: every singleton, plus each continuous component's left
  endpoint when included and otherwise its exact midpoint. No representative
  rule appears in the specification. Either add one or restrict $I$ to be
  finite.

### Claims presented as immediate

- [x] **A.3. Show, or flag the cost of, the $\bar C^{\mathrm{post}}$
  equality.** [§3 L302-309](PROTOCOL.md#L302-L309) asserts
  $\langle\top\mid\bar A^{ms}\land\bar G^{ms}\rangle=\langle\top\mid\bar K\land\lozenge_{I\oplus[0,d)}p\rangle$
  as "the specialization of the separation/merging algebra to these
  unconditional inputs". Using the specification's own worked example
  ($I\oplus[0,d)=[1,5)$, $R=[1.5,3)$), what the algebra returns before
  reduction is

  $$
  (\lozenge_{[1,5)}p\land\lozenge_{[1.5,3)}p\lor\lozenge_{[1,5)}p\land\square_{[1.5,3)}\neg p)
  \land(\square_{[1,5)}\neg p\lor\square_{[1.5,3)}\neg p),
  $$

  and reaching the boxed form takes Boolean resolution across clauses, not
  region simplification. Either give the derivation or say the reduction is
  nontrivial.

- [x] **A.4. Justify promoting the repaired assumption.**
  [§3 L299-301](PROTOCOL.md#L299-L301) says to "make its assumption an
  explicit requirement" without an argument for soundness or an account of
  what it means contractually. It is a modelling choice presented as a step.

- [x] **A.5. Invert the consistency criterion.**
  The boxed biconditional at [§2 L235-237](PROTOCOL.md#L235-L237) — consistent
  iff $(I\oplus[0,d))\cap R=\varnothing$ — is what a reader will implement,
  and it makes the construction circular: deciding the question by
  intersecting intervals needs no contracts. Define consistency as a
  formula-level query over admissible trajectories and derive the intersection
  criterion as that query's realization on the reservation fragment — not as a
  separate result later shown to agree with it. The aside at
  [L249-251](PROTOCOL.md#L249-L251) already names the formula-level query, but
  as a fallback for richer models rather than as the definition the criterion
  realizes. This is one of
  three sites where
  [A.12](#making-the-contract-driven-design-internally-consistent) asks for
  one shared realization instead of a local shortcut.

### Under-determined choices

- [x] **A.6. Pin down the offer burst.**
  [§5 L382-386](PROTOCOL.md#L382-L386) gives $\mathcal O_r\subseteq\{\dots\}$
  with $u^{\mathrm{prop}}\approx u^{\mathrm{prop}}_{\mathrm{exp},r}$; neither
  the subset nor the approximation is specified. The notebook sends every
  alternative, priced to meet the target exactly, filtered by the proposer's
  floor.

- [x] **A.7. Specify the evaluator's tie-break.**
  [§5 L396-399](PROTOCOL.md#L396-L399) selects from an $\arg\max$, leaving
  runs non-reproducible. The notebook breaks ties by earliest start.

- [x] **A.8. Fix the represented universe $\mathbb I$.**
  [§Inputs L92-94](PROTOCOL.md#L92-L94) bounds $\mathbb I$ only from below
  ("containing $0$, the full request envelope, and all reservation
  intervals"), yet the results depend on it: a finite or disconnected
  universe changes which rewrites are valid. The notebook uses $[0,\infty)$.

### Unstated conventions and edge cases

- [x] **A.9. State the erosion endpoints.**
  $J_s\subseteq J$ ([§4 L345](PROTOCOL.md#L345)) means an available component
  $[a,b)$ admits starts $[a,b-d]$, **closed** at $b-d$, because $[s,s+d)$ fits
  when $s+d$ equals an excluded right endpoint. A component shorter than $d$
  admits none. The only endpoint remark is the aside at
  [L446-447](PROTOCOL.md#L446-L447).

- [x] **A.10. Note that the strengthening equivalence is anchor-dependent.**
  [§2 L210-212](PROTOCOL.md#L210-L212) states
  $\square_I\square_dp\equiv\square_{I\oplus[0,d)}p$ as a plain identity. The
  envelope is really built from the window $I\cap[a,\infty)\cap\mathbb I$: at
  anchor $3$ the same formula gives $\square_{[3,6)}p$, not
  $\square_{[1,6)}p$. It holds here only because anchor $0$ is fixed.

- [x] **A.11. Move the revalidation predicate into normative §6, and specify
  atomicity.** [§6 L422](PROTOCOL.md#L422) says only "revalidate feasibility
  under current inputs"; the actual checks appear as prose in the example at
  [L597-599](PROTOCOL.md#L597-599). The notebook requires the same job, a
  duration exactly equal to $d$ (not merely at least $d$), a start in $I$, and
  consistency with the current commitments. Atomicity is likewise implied
  only by [L435](PROTOCOL.md#L435) and the flowchart's
  `Valid -- No --> Input` edge; the snapshot and compare-and-restart
  semantics is never specified.

### Making the contract-driven design internally consistent

- [x] **A.12. Give the contract operations one realization over the formula
  fragment this protocol produces, instead of a local interval shortcut at
  each site.** [The introduction (L18-23)](PROTOCOL.md#L18-L23) commits the
  protocol to being contract-driven, so interval arithmetic may appear only
  *inside the realization of a contract operation*, never as a second,
  independently-computed answer that a contract-level statement is then
  reconciled with. (Policy inputs are outside this:
  [A.2](#definitional-holes)'s representative rule and the start grid choose
  which contracts to build; they do not compute a contract's result.) The
  protocol reaches into the fragment at four places. Three take the second
  form — an interval result asserted directly, with a note that it agrees
  with the contract reading — and the fourth is left as prose:

  - [§2 L235-237, L249-251](PROTOCOL.md#L235-L237): the consistency query on
    $\bar C^{\mathrm{cand}}$, asserted as $(I\oplus[0,d))\cap R=\varnothing$
    and labelled "exact for the reservation model". A.5 asks for this fix on
    this instance alone.
  - [§3 L327-330](PROTOCOL.md#L327-L330): reading $J$ out of
    $\bar K\land\lozenge_Jp$, with equivalence disclaimed. (Dropping $\bar K$
    is a guarantee-weakening and should be named as refinement; the read-off
    is the separate problem.)
  - [§4 L351](PROTOCOL.md#L351): $J_s\subseteq J$, re-asserted in its own
    "reservation model" aside as if unrelated to §2's.
  - [§6 L422](PROTOCOL.md#L422): revalidation re-runs the §2 consistency query
    against the current commitments ([A.11](#unstated-conventions-and-edge-cases)),
    so it is a fourth caller of the same lemma, not a new check.

  Every formula the protocol builds is a Boolean combination of atoms
  $\square_S(\textit{job}=k)$ — or their projections $\square_Sp$,
  $\square_S\neg p$ — over finite-union regions $S$: call this the
  reservation fragment. The region a formula denotes is anchor-relative
  ([A.10](#unstated-conventions-and-edge-cases)), so the lemma is stated at a
  fixed anchor. State once how the primitives named in
  [§Inputs](PROTOCOL.md#L127-L131) — merge, separation, consistency — are
  realized on this fragment: normalize to region atoms, resolve the Boolean
  structure ([A.3](#claims-presented-as-immediate) is the warning that this
  step is real work and not bookkeeping), then read the answer off the
  surviving regions as union, difference, or containment — all derived from
  [A.1](#definitional-holes)'s operational definitions. Each site above then
  becomes an application of that one lemma. The notebook should follow:
  `consistent`, `availability`, and `erode`'s containment check become the
  same procedure applied to different contracts rather than three pieces of
  code that happen to agree.

## Section B — Making the assumption slot load-bearing

Every contract in the protocol is $\langle\top\mid G\rangle$. The one
non-trivial assumption that ever appears,
$\square_{[1,6)}\neg p\lor\square_{[2,3)}\neg p$, is an artifact of separation
rather than a statement about anyone's environment, and `require_assumption`
conjoins it away immediately. The assume-guarantee machinery therefore carries
no load. From the charger's side the environment is the vehicle, so a useful
assumption has to be about vehicle behaviour, has to vary over time, and has to
be revisable mid-session so that a violation is a well-defined event.

Fix order: B.1 fixes the model, and B.3 and B.5 have to land with it — the
first conditional contract makes §4's and §6's consistency checks unsound, not
merely imprecise. B.2, B.4, B.6 and B.7 are independent of that bundle.

**Status: closed** (B.4 excepted — see the note below). The bundle landed
together: `plugged` and the one-connector reading are in
[PROTOCOL.md](PROTOCOL.md) §Inputs, offers and stored agreements are
conditional (§4, §6), the realization lemma is generalized to per-signal
contradiction with three queries over one `satisfiable` procedure, the
strengthening derivation is §2/*Where strengthening comes from*, and intake
compatibility with its attribution table is §Inputs and §5. The reference
implementation in [`notebooks/protocol.ipynb`](../notebooks/protocol.ipynb)
runs end to end and asserts the B.5 failure it is meant to prevent.

**B.4 has no body in this file.** The fix-order note above still lists it, but
the item itself is absent — it appears to have been dropped in an edit. The
order-atom decision it asked for was written up in
[LOGIC.md](LOGIC.md)/*Deferred: order atoms* (defer $\le$ and $<$; if added,
both are needed for NNF closure, and the real cost is the simplifier's
signal-assignment check becoming an integer-bounds domain). That section stands
on its own, but it is unchecked work — restore B.4 here or delete the reference
to it.

- [x] **B.1. Add a `plugged` presence signal and make offers conditional on
  it.** Presence is a second signal, controlled by the vehicle and
  structurally identical to `job`:

  $$
  \textit{plugged}:X\to\mathbb N_0,
  \qquad
  \textit{plugged}(t)=0 \text{ means nothing connected},
  \qquad
  \textit{plugged}(t)=k \text{ means vehicle } k \text{ is connected.}
  $$

  Keeping it separate from `job` is the point: `job` is the charger's decision,
  `plugged` is the vehicle's. Energy flows only where the two meet, so
  $\textit{charging}_k:=(\textit{job}=k)\land(\textit{plugged}=k)$, and the
  offer contract of [§4](PROTOCOL.md#L334-L338) becomes

  $$
  C^{J_s}=\left\langle\ \square_{J_s}(\textit{plugged}=k)\ \middle|\ \square_{J_s}(\textit{job}=k)\right\rangle,
  $$

  whose saturated guarantee reads *either the vehicle was absent, or the point
  was allocated*. This also gives [A.11](#unstated-conventions-and-edge-cases)
  a principled account of renegotiation: "inputs changed, restart scheduling"
  becomes "the assumption was violated at $t$, so the guarantee is void from
  $t$", which is checkable rather than procedural.

  **Open sub-decision: signal or proposition.** A bare proposition `plugged`
  cannot say *which* vehicle is connected, so the charger would be obligated
  when the wrong car is present. A signal keeps the identity and inherits the
  mutual exclusion the simplifier already enforces on signal assignments. One
  proposition per job (`plugged_k`) is a third option that works for a fixed
  finite job set but scales badly. Recommend the signal.

- [x] **B.2. Derive conjunctive strengthening from an existential presence
  assumption.** Presence admits several strengths, weakest commitment last:

  1. **Committed window (Preferred)** — $\square_{J_s}(\textit{plugged}=k)$, matching the
     offer window. The natural default.
  2. **Committed duration, flexible start** —
     $\lozenge_I\square_d(\textit{plugged}=k)$, mirroring the request itself.
     The vehicle promises to be present for *some* full $d$-window in $I$
     without saying which, so the charger cannot pin the slot and must either
     hold the whole envelope $I\oplus[0,d)$ or price the flexibility.
  3. **Arrival and departure bounds** —
     $\square_{[t_0,t_1)}(\textit{plugged}\ne k)$ and
     $\square_{[t_2,\infty)}(\textit{plugged}\ne k)$.

  Strength 2 is worth writing up: it makes conjunctive strengthening, currently
  an unmotivated technical device in [§2](PROTOCOL.md#L203-L216), the charger's
  honest response to an existential presence assumption. It would stop being a
  proof device and become part of the model. It also opens negotiation over
  assumption strength rather than price alone, which is what the
  assume-guarantee framing is for.


- [x] **B.3. Update the plumbing that assumes $\top$ assumptions.** No change
  to [LOGIC.md](LOGIC.md) is required — the grammar already allows several
  signals ($\tau::=n\mid\textit{job}$ with $\textit{job}:X\to\mathbb N_0$, and
  the charging-station example already uses
  $\textit{job}_1,\ldots,\textit{job}_n$), and the package supports it today:

  ```text
  saturated   : ◇_[3,4) plugged ≠ 2 ∨ □_[3,4) job = 2
  cross-signal: □_[3,4) job = 2 ∧ □_[3,4) plugged = 3
  same-signal : ⊥
  A: False | G: True | saturated: True     (trace where the vehicle unplugs at 3.5)
  ```

  What does need changing:

  - `project` in the notebook maps *every* `Equal` node to $p$ or $\neg p$
    regardless of signal, and runs on assumptions as well as guarantees, so it
    would silently turn `plugged = 2` into $p$. It must become signal-aware and
    leave environment signals alone.
  - Conditional merging and separation ([A.1](#definitional-holes)) stop
    being a documentation gap and become load-bearing on the first run.
  - `consistent` is not the thing to extend: it is the definition of its own
    question ([PROTOCOL.md L204-232](PROTOCOL.md#L204-L232)), and what is
    missing is its two siblings. Add one `satisfiable` procedure — clause 1 of
    the realization lemma — and give it three entry points:

    ```python
    def satisfiable(formula): return normalize(formula).simplify(anchor=0) != il.Boolean(False)
    def consistent(c):        return satisfiable(c.guarantee)
    def compatible(c):        return satisfiable(c.assumption)
    def realizable(c):        return satisfiable(c.assumption & c.guarantee)
    ```

    Note that `realizable(c) == consistent(c.require_assumption())`, which is
    what [L229-232](PROTOCOL.md#L229-L232) already says about
    $\bar C^{\mathrm{post}}$: promotion is the query device, and [A.4](#claims-presented-as-immediate)
    carries its soundness argument. Promotion stays a device — an offer that
    *demands* presence is a different commercial object from one that assumes
    it. Which site asks which query is B.5; what an unsatisfiable assumption
    means for a request is B.6.

  - Generalize the realization lemma's fragment from one signal to several
    ([PROTOCOL.md L262-276](PROTOCOL.md#L262-L276)). Region atoms become
    $\square_S(\sigma=k)$ for a signal $\sigma$, and clause 1's contradiction
    table becomes per signal,

    $$
    \square_S(\sigma=k)\land\square_{S'}(\sigma=k')\equiv\bot
    \iff k\ne k'\ \text{and}\ S\cap S'\ne\varnothing,
    $$

    with no contradiction across distinct signals. The interval arithmetic
    underneath is unchanged; `project` carries two independent projections,
    $p$ for $\textit{job}=k$ and $q$ for $\textit{plugged}=k$, instead of
    collapsing both onto $p$.

  **Verified while implementing.** All four lines of the block above reproduce
  exactly against the package, and `_combine`'s signal-assignment check is as
  described. The `satisfiable`/`consistent`/`compatible`/`realizable` shape was
  adopted verbatim, and the two-projection fix ($p$ for `job`, $q$ for
  `plugged`) is exercised by a notebook assertion.



- [x] **B.5. Ask realizability, not consistency, at the merge sites.** Once
  B.1 gives $C_i^{\mathrm{acc}}$ a presence assumption, $C^{\mathrm{cmt}}$ is a merge of
  conditional contracts and its assumption is the conjunction of all presence
  windows. `plugged` is one signal, so two commitments with overlapping windows
  and different vehicles give

  $$
  A_1\land A_2
  =\square_{J_1}(\textit{plugged}=k_1)\land\square_{J_2}(\textit{plugged}=k_2)
  \equiv\bot,
  $$

  and merging ([§Inputs L181-196](PROTOCOL.md#L181-L196)) returns the guarantee
  $(G_1\land G_2)\lor\neg(A_1\land A_2)=\top$. So §6's check (iv) —
  "$C^{\mathrm{cmt}}\bullet C_i^{\mathrm{acc}}$ is consistent",
  [L849](PROTOCOL.md#L849) — **passes, and stores the double booking**,
  precisely because the two reservations conflict. §4's per-start check
  ([L682](PROTOCOL.md#L682)) fails the same way. This is not a sharpening of an
  already-correct test: consistency at these two sites becomes unsound on the
  first conditional contract, which is why B.5 has to land with B.1.

  The fix is to ask `realizable` at both sites; it returns false here because
  $A\land G$ is $\bot$. PROTOCOL.md already names the disease
  ([L224-228](PROTOCOL.md#L224-L228), "a contract with an unsatisfiable
  assumption is consistent and useless"); what is missing is that §4 and §6 are
  where it bites. The realization lemma's caller table
  ([L344-349](PROTOCOL.md#L344-L349)) then lists three queries over one
  procedure rather than one query four times, and §2 keeps `consistent`, since
  $\bar C^{\mathrm{cand}}$ stays unconditional.

  Worth stating as the payoff, since it is the first place the assumption slot
  does work: the non-overlap check now appears twice, once on `job` (may the
  charger allocate?) and once on `plugged` (can the vehicles all be there?),
  and both are the same lemma clause over different signals.

  **Confirmed against the package.** Two overlapping agreements for different
  vehicles give `compatible=False`, `consistent=True`, `realizable=False` — so
  consistency does store the double booking, exactly as described. The notebook
  now asserts all three.

- [x] **B.6. Give the intake an incompatible-request outcome, and say who moves
  on each failure.** Compatibility depends only on the request, never on the
  commitments, so it cannot change while scheduling proceeds: it is input
  validation, not a scheduling result. Check it once, before Step 1, and give it
  its own terminal outcome, distinct from "no feasible offer" — the
  assumption-side twin of the $I=\varnothing$ rule already at
  [§Inputs L246](PROTOCOL.md#L246):

  > A request whose assumption is unsatisfiable is **malformed**: it promises a
  > presence pattern no admissible trajectory realizes — for instance B.2's
  > strength-3 bounds with $[t_0,t_1)\cup[t_2,\infty)$ leaving no $d$-window in
  > $I$. No allocation repairs it, so negotiation terminates without agreement
  > and the defect is reported to the vehicle.

  This also gives [§5](PROTOCOL.md#L382-L399) and the "Other outcomes" note at
  [L1070-1075](PROTOCOL.md#L1070-L1075) a three-way outcome with an attribution
  rule, which is what the assume-guarantee framing is for outside §2:

  | Failing query | What it means | Who moves |
  | --- | --- | --- |
  | request not `compatible` | the request contradicts itself | vehicle: fix the request |
  | merge not `compatible` | the connector is already promised to another vehicle | scheduler: no offer at this $J_s$ |
  | merge `compatible`, not `realizable` | no free window | charger: counteroffer, or vehicle weakens to B.2 strength 2 |

  The rows are distinguished by exactly the calls B.3 adds: `compatible` on the
  request at intake, then `compatible` and `realizable` on the merge. The middle
  row is the one that needs a name in §5 — it is a refusal the vehicle cannot
  price its way out of, unlike the third.

- [x] **B.7. Fix the connector multiplicity that B.1 presumes.** B.5's
  assumption-side conflict check works because `plugged` is a single signal
  whose values are mutually exclusive — that is, because the station has one
  connector. A multi-connector station indexes presence per connector
  ($\textit{plugged}_c$), mutual exclusion holds per signal, and the check
  becomes per-connector while `job` either stays station-wide or splits with it.
  Nothing in PROTOCOL.md states which station is being modelled. Say so in
  §Inputs before B.1's signal is introduced; one connector is the reading the
  rest of the document already assumes, since a single commitment set $K$ with
  mutually exclusive job values admits no overlapping reservations at all.
