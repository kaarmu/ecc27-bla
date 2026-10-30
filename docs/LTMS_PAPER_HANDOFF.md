# Paper extension handoff: entry, allocation and exit

This is a proposed extension for a writer familiar with
[protocol.ipynb](../notebooks/protocol.ipynb). That notebook remains authoritative
on the protocol and contract algebra; [LOGIC.md](LOGIC.md) remains authoritative
on trajectory semantics. [ltms_blas.ipynb](../notebooks/ltms_blas.ipynb) is an
implementation working document, not an implementation of the proposal below.

The proposed division of responsibility is:

> The vehicle chooses when to enter within an agreed entry window and executes
> an agreed driving rule. AIM/LTMS allocates space over time so that this client
> behavior results in exit during an agreed exit window.

The proposed contracts are

$$
C_{\rm client}=\langle A\mid E\land F\rangle,
\qquad R_{\rm task}=\langle\top\mid E\land F\land X\rangle,
$$

where $A$ means usable allocation, $E$ agreed entry, $F$ compliant driving and
$X$ agreed exit. The definitions and proof obligations follow below.

The owner determines exit possibilities through allocation; the vehicle still
controls its actuators. The extension concerns guarantees over windows, rather
than unilateral control of exact entry or exit instants.

**1. What changes from the paper companion.** In the booking example, the owner
sets one access signal, and the client sets a separate use signal:

$$
C_{\rm client}=\langle S_a\mid B\land S_u\rangle,
\qquad R_{\rm task}=\langle\top\mid B\land S_u\rangle.
$$

The client already promises the entire task when sufficient access is supplied.
The quotient consequently reduces to an access-only owner guarantee.

Here the client promises entry and compliant driving. The joint task additionally
requires timely exit. The owner must supply usable access and make the client's
promised behavior imply that additional outcome. The algebra is unchanged;
the access-only simplification is specific to the original example.

| Role | Booking example | Proposed intersection example |
| --- | --- | --- |
| Owner output | Single-valued access signal | Spatial allocation for each client over time |
| Client output | Use signal | Entry choice and steering/acceleration |
| Resource | Exclusive access to one resource | Subsets of physical space at each time |
| Client promise | Legal use for the required duration | Agreed entry and driving behavior |
| Joint requirement | The same legal-use task | Client behavior plus agreed exit |

Space is divisible: simultaneous leases and simultaneous crossings are allowed.
Boolean specifications about an allocation do not make the resource binary.

**2. Physical model and service terms.** For a first presentation, use nominal
deterministic vehicle dynamics

$$
\dot z_j=f_j(z_j,u_j),\qquad u_j(t)\in U_j,
\qquad p_j:Z_j\to\mathbb R^2.
$$

The vehicle controls $u_j$. The owner chooses

$$
r_j:[a,T]\to\mathcal P(W),
$$

where $W$ is the managed workspace and $a$ is the frozen negotiation anchor.
For the initial extension, the full allocation schedule is committed before
entry and remains fixed for the service. Online allocation feedback would require
owner strategies and a further causal analysis.

Let $\mathcal B_j(z_j(t))$ be the vehicle footprint. Define the interpreted atom

$$
\mathit{alloc}_j(t)
\quad\Longleftrightarrow\quad
\mathcal B_j(z_j(t))\subseteq r_j(t).
$$

A point vehicle is the special case $\mathcal B_j(z)=\{p_j(z)\}$.
Full vehicle-state tubes may help compute an allocation, but collision checking
uses the physical footprints and spatial allocations, including the declared
time and boundary conventions.

For one selected service, fix

$$
\theta=(j,J,K,\mathrm{in},\mathrm{out},z_{\rm in},\pi,T).
$$

Here $T>a$ and $J,K\subseteq[a,T]$ are nonempty bounded entry and exit windows, $z_{\rm in}(s)$
is the agreed entry state at time $s$, and $\pi$ is the agreed driving-rule
family. Initially use one exact entry state per entry time. A set of entry states
requires a further explicit quantifier over that set.

The client chooses the actual entry $s\in J$. The owner may propose $K$ and the
allocation, but the client must accept those service terms. Changing $J$, $K$,
the route or the driving rule requires a permitted service variant and rebuilding
its contracts before freezing that negotiation attempt. Offers of the same
selected service must support the same client entry freedom; an offer that only
works for one $s\in J$ does not support arbitrary choice within $J$.

Approach readiness is a stated precondition: the client can realize its agreed
entry state and time before entering the managed plant. This does not assume
that a moving vehicle can wait at a fixed entry state. If approach control is
part of the claimed result, extend the physical model to prove readiness.

**3. Trajectory semantics and event discipline.** Use one common joint trajectory
$\xi$ containing vehicle states, controls, allocation and phase observations.
Its admissible behavior universe $\mathscr B_\theta(r)$ includes the physical
dynamics and approach preconditions. It does not assume that the client obeys
its contract. All queries share the represented universe $\mathbb I=[a,T]$;
physical trajectories remain defined beyond that interval as in `LOGIC.md`.

Use entry and exit event propositions, $e_{\rm in}$ and $e_{\rm out}$, with the
following physical interpretation: one service starts outside, enters once
through the agreed entry state, and can finish only through the requested exit.
The entry and exit events occur at their transition times, with exit strictly
after entry. A phase observation $m_j$ is true while the vehicle is managed,
including its entry and exit boundary events. It remains true through $T$ if
the vehicle has entered but has not exited. These rules prevent an arbitrary
appearance in an exit region from witnessing completion of this service.

At the common anchor $a$, define

$$
E_\theta:=\lozenge_J e_{\rm in},
\qquad X_\theta:=\lozenge_K e_{\rm out}.
$$

Define allocation and road compliance by

$$
B_r:=\square_{[a,T]}
\bigl(m_j\Rightarrow(\mathit{road}_\theta\land\mathit{alloc}_j)\bigr).
$$

These are conditions under the satisfaction relation in `LOGIC.md`. In
particular, an absolute window limits inspected future times; it does not
change the evaluation anchor. Use $\square$ for persistence, not a selection
mask. A departure-specific until formula must be evaluated at its departure;
a plain disjunction of such formulas does not automatically supply distinct
anchors. All witnesses and compliance requirements here concern the same
trajectory and the same service instance.

**4. Give “follow the corridor” an operational meaning.** The recommended first
model fixes a causal rule family $\pi_r$, parameterized by the allocation known
before entry. Let $\mathit{rule}_\pi$ be an interpreted observation that the
current control obeys this rule, including controller memory in the joint state
if needed. Put

$$
D_\pi:=\square_{[a,T]}(m_j\Rightarrow\mathit{rule}_\pi),
\qquad
F_\theta:=B_r\land D_\pi,
\qquad G_\theta:=E_\theta\land F_\theta.
$$

The rule may select controls from a certified set rather than select one unique
control. In that case the guarantee must cover every behavior it permits.
$D_\pi$ is a behavioral predicate; representing it in the signal language needs
an interpreted observation of controller compliance, not an unsupported numeric
formula for derivatives or controls.

This definition does not explicitly require exit. Geometric containment alone
would be a different, weaker $F_\theta=B_r$. It is permissible, but then the
owner's exit argument must cover every geometrically compliant trajectory,
including any that stop or circle. A picture of a tube or an existential
reachability result does not establish that argument.

**5. Define usable access without assuming successful exit.** Let
$\operatorname{Exec}_\theta(r,s)$ be the family of physically admissible managed
executions starting at $z_{\rm in}(s)$ at $s$ and following $\pi_r$, continued
through exit or through $T$ if no exit occurs. The agreed phase discipline supplies
the corresponding service trace. Define the owner-only predicate

$$
\begin{aligned}
A_\theta(r)\quad\Longleftrightarrow\quad
&\pi_r\text{ is a well-defined causal rule for this service},\\
&\forall s\in J:\quad
\operatorname{Exec}_\theta(r,s)\ne\varnothing
\quad\land\quad
\forall\xi\in\operatorname{Exec}_\theta(r,s):
(\xi,a)\models B_r.
\end{aligned}
$$

The notation $(\xi,a)$ uses the full service trace with managed execution
starting at $s$. Existence is required for each allowed entry time, not only for
one favorable time. The same rule family must support all those choices.
The client implementation chooses $s\in J$ and executes that rule. Under
approach readiness and $A_\theta$, it can therefore provide $G_\theta$.

$A_\theta$ does not contain $X_\theta$: it establishes nonempty, compliant
execution, not timely exit. It may hold for a vehicle that remains managed
through $T$. Requiring executions through $T$ prevents an impossible allocation
from being called usable merely because execution stops when it leaves the
allowed set.

This is stronger than the paper's satisfiability-based notion of realizability.
It is an additional implementation premise, to be proved for the selected
nominal model and driving rule. It is not furnished by contract algebra.

The dependence on future allocation is legitimate here because the committed
schedule is known in advance. This does not let the control at time $t$ depend
on future unobserved vehicle behavior.

**6. The proposed client contract and joint task.** Write $S_a:=A_\theta$ if
retaining the paper's access notation. The proposed pair is

$$
\boxed{
C_{\rm client}(\theta)
=\langle A_\theta\mid G_\theta\rangle,
\qquad
R_{\rm task}(\theta)
=\langle\top\mid G_\theta\land X_\theta\rangle.
}
$$

The client says: “Given usable access, I will enter within $J$ and execute the
agreed allocation-respecting driving rule.” The joint requirement says: “The
vehicle does that and exits through the requested exit within $K$.”

Exit is an explicit additional requirement in $R_{\rm task}$. It is not inserted
into the client guarantee or the access definition. The owner must use allocation
to connect client behavior to that outcome.

**7. Make the owner's exit responsibility precise.** Define an owner-only
property of an allocation by quantifying over its possible client behaviors:

$$
P_\theta(r)
:\Longleftrightarrow
\forall\xi\in\mathscr B_\theta(r):
\bigl((\xi,a)\models G_\theta\bigr)
\Rightarrow
\bigl((\xi,a)\models X_\theta\bigr).
$$

Although $G_\theta$ and $X_\theta$ inspect the vehicle, $P_\theta$ depends only on
the proposed allocation once the plant and client-rule family are fixed.
This separates responsibility for an outcome from exclusive ownership of the
signals mentioned in its statement.

Certify $A_\theta(r)\land P_\theta(r)$ together. $P_\theta$ alone can hold
vacuously when there is no compliant entry or continuation. Conversely,
$A_\theta$ alone can permit compliant execution without timely exit.

The quantifiers defining $A_\theta$ and $P_\theta$ are specification-level
definitions, not new operators in the interval-logic grammar. For algebra they
can be treated as interpreted predicates on the frozen allocation plan.
If represented as atoms in a state-based implementation, the committed plan
must be included as an immutable state parameter with the stated interpretation.
The current Boolean normalizer cannot establish these dynamical properties.

**8. Consequence for the developed protocol.** This derivation uses exactly the
notebook's saturation and quotient. Abbreviate $A=A_\theta$, $G=G_\theta$,
$X=X_\theta$, and $\widehat G=\neg A\lor G$. Then

$$
\begin{aligned}
Q&=R_{\rm task}/C_{\rm client}\\
 &=\left\langle\widehat G\ \middle|
 (A\land G\land X)\lor\neg\widehat G\right\rangle\\
 &=\boxed{\left\langle\neg A\lor G\ \middle|
 A\land(\neg G\lor X)\right\rangle}.
\end{aligned}
$$

For $C_{\rm cmt}=\langle\top\mid L\rangle$, the admission target is therefore

$$
C_{\rm cmt}^{+}
=\left\langle\top\ \middle|
L\land A\land(G\Rightarrow X)\right\rangle.
$$

The quotient has a relational guarantee, rather than the original access-only
guarantee. Proving $P_\theta(r)$ is a sufficient way to discharge its implication
for every admissible client behavior. Do not replace the derived guarantee by
$A$ or by an existential crossing-capability predicate.

A concrete unconditional offer can fix a candidate schedule:

$$
H_\kappa:=\bigl(r_j|_{[a,T]}=r_\kappa|_{[a,T]}\bigr),
\qquad K_\kappa:=\langle\top\mid H_\kappa\rangle.
$$

Its evidence must establish

$$
H_\kappa\Rightarrow A_\theta\land P_\theta,
\qquad\text{and compatibility with standing commitments.}
$$

Then $K_\kappa\preceq Q$ in the interpreted behavior model. The existing
refinement and quotient arguments give

$$
C_{\rm cmt}\wedge K_\kappa\preceq C_{\rm cmt}^{+},
\qquad
C_{\rm client}\otimes(C_{\rm cmt}\wedge K_\kappa)
\preceq C_{\rm cmt}\wedge R_{\rm task}.
$$

Semantically, an owner honoring the offer establishes $A$; a client honoring
its contract establishes $G$; and $P_\theta$ establishes $X$. Neither party
may satisfy its role merely by making the other's assumption impossible.

Exact allocation is a deliberately simple initial promise. The old template
$r_j\supseteq r_\kappa$ requires a fresh argument: enlarging a corridor may add
compliant behaviors that miss the exit window or change $\pi_r$. Exit assurance
is not automatically monotone under allocation enlargement. Inclusion offers
are valid only with a certificate covering every allocation they permit.

**9. Concurrency, compatibility and preservation.** For footprint allocations,
the following is a sufficient spatial compatibility condition while services
are active, with entry and exit boundaries included:

$$
r_i(t)\cap r_j(t)=\varnothing\qquad(i\ne j).
$$

Together with allocation compliance, it implies disjoint vehicle footprints.
It allows simultaneous use of different parts of the intersection. It is a
sufficient reservation policy, not a necessary characterization of every
collision-free coordinated motion.

Admission must preserve each accepted allocation promise and its certified
client-rule interpretation. It cannot silently shrink, move or recompute an
accepted corridor to accommodate a new client. The fixed-schedule model makes
this preservation explicit. More flexible promises require proving preservation
of the previously certified $A_i$ and $P_i$ under the permitted changes.

The protocol still admits a selected service, generates certified compatible
offers, negotiates one exact offer and price, and commits that pair. Original
service first, permitted alternatives in order, frozen commitments and offer
family during bargaining, price as metadata, and preservation on `NO-BLA` all
remain applicable. The interval-overlap pruning procedure is replaced by a
model-specific admission procedure; no completeness claim transfers from the
booking example. Finite candidate failure means this method found no offer.

**10. Where LTMS passes enter the argument.** The current
[planner](../src/ltms_reachability/planner.py) performs:

| Pass | Computation | Possible contribution to the extension |
| --- | --- | --- |
| 1 | Road-constrained backward reachability to the exit | Offline physical crossing possibilities |
| 2 | Backward recomputation avoiding standing reservations | Remaining crossing possibilities |
| 3 | Forward restriction from a selected entry window inside Pass 2 | Candidate motion associated with the client's entry freedom |
| 4 | Backward restriction to a selected exit window inside Pass 3 | Candidate tube shaped around the owner's exit objective |

This supports the intuition behind the entry/exit split. A pass is a time–state
set, not a contract assumption or guarantee. A nonempty slice of Pass 3 does
not by itself prove $A_\theta$, and membership in Pass 4 does not by itself prove
$P_\theta$. Projection from full state to physical space also admits combinations
of headings and speeds absent from the original tube, unless the driving rule
or another constraint excludes them.

An existential query establishes that a successful control exists. For this
extension, one must additionally establish that the agreed client rule provides
compliant execution for each allowed entry and that every behavior it permits
exits in $K$. For a deterministic rule with unique solutions, these obligations
reduce to properties of those solutions for every allowed entry, but a finite
sample still does not prove a continuous-window claim.

The current backend provides existential reachability, not a general universal
verification procedure. The first implementation should therefore use a finite
entry library with explicit entry states and a specified nominal rule, or
provide additional verification sufficient for a continuous entry window.
Label these restrictions as implementation scope. The formal service definition
can still admit an interval $J$.

Do not claim that nominal HJ grid membership proves continuous-time footprint
separation, tracking robustness or a strategy theorem. Those require their own
error bounds and model assumptions. In particular, “there is a trajectory in
the tube” and “following this rule always realizes the promised exit” are
different statements.

**11. The statement the paper can aim to prove.**

> Fix the physical model, approach readiness, selected service and driving-rule
> family. Suppose the accepted owner offer supplies an allocation satisfying
> $A_\theta\land P_\theta$, and the client implements its promised entry choice
> and driving rule. Then the resulting execution satisfies
> $G_\theta\land X_\theta$. If standing and new allocations are spatially
> compatible and all active clients comply, their managed footprints are
> pairwise disjoint, including the declared entry and exit boundaries.

The task part follows from $A\Rightarrow G$ for the implemented client and
$P_\theta:\ G\Rightarrow X$. The spatial part follows from footprint
containment and disjoint allocations. Contract identities establish how offers
compose; they do not establish the implementation premise $A\Rightarrow G$,
the allocation certificate $P_\theta$, or spatial compatibility.

For the extension, give the writer these proof obligations separately:

1. **Client implementation:** approach readiness and usable allocation let the
   fixed rule honor $E_\theta\land F_\theta$ for every allowed entry choice.
2. **Owner exit certificate:** every admissible behavior satisfying that promise
   exits through the requested exit during $K$.
3. **Joint compatibility:** the candidate allocation coexists with retained
   promises and preserves their interpretations.
4. **Protocol preservation:** certification, frozen bargaining and exact commit
   preserve the preceding properties under sequential requests.

**12. Suggested presentation and evidence.** Begin the extension with concurrent
crossings to motivate spatial allocation. Introduce the entry/exit division,
then define $A$, $G$ and $X$, and give the proposed client contract and task.
Derive the changed quotient before describing numerical candidate generation.
Present the implementation as one way of obtaining and assessing offers for
these specifications.

A worked example should show two simultaneous compatible crossings, a
reservation conflict, an unusable allocation, and a usable allocation that
fails exit assurance. Include at least two client-selected entry times under
one allocation; report finite choices explicitly if that is the tested scope.
A no-entry client should leave the owner promise intact while failing the joint
task, as in the original paper companion. A client that enters and complies
but exits outside $K$ is a counterexample to the owner's exit certificate.

Separate **algebraic identities**, **semantic implementation/certificate
arguments**, and **numerical evidence**. The new contribution is a spatial
resource model and a division of behavioral and outcome responsibilities
within the existing protocol. A general synthesis method or a universal
reachability backend would be an additional contribution requiring additional
results.
