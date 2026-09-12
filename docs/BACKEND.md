# Backend

## High-level description

`SymbolicSystem` implements reachability by **symbolic backward propagation over a transition relation**. It represents sets of states exactly, computes their one-transition predecessors, and combines those predecessors according to the timing model.

The description below applies to **state-predicate operands**. It does not assume that arbitrary temporal subformulas can first be replaced by independently computed state sets.

**State space and symbolic representation**

For \(n\) signal coordinates, the charging-station invariant defines

\[
X=
\left\{
x\in\mathbb N_0^n:
\forall i<j,\quad x_i=x_j\Longrightarrow x_i=0
\right\}.
\]

This is `AllDifferentExceptZero()`. The alternative `AllDifferent()` instead requires \(x_i\ne x_j\) for every \(i<j\).

A symbolic region is a tuple of one-dimensional domains,

\[
D=(D_1,\ldots,D_n),
\qquad D_i\subseteq\mathbb N_0,
\]

whose meaning is

\[
\gamma(D):=X\cap\prod_{i=1}^{n}D_i.
\]

Each \(D_i\) is represented by a finite union of integer intervals, possibly unbounded. A `StateSet` stores finitely many such regions:

\[
S=\bigcup_{r=1}^{m}\gamma(D^{(r)}).
\]

Thus the interval objects describe **signal values**, not physical time. Dependence between coordinates comes from the invariant and the union of regions; the implementation does not merge a union into a single Cartesian product.

Domains are canonicalized as integer sets. For example,

\[
(1,5]\cap\mathbb N_0=\{2,3,4,5\}.
\]

Normalization removes infeasible regions and regions contained coordinatewise in another stored region. This normalization is not necessarily a minimal representation of the set.

**Feasibility and set algebra**

For strict `AllDifferent`, a region is feasible exactly when there is an injective assignment

\[
f:\{1,\ldots,n\}\to\mathbb N_0,
\qquad f(i)\in D_i.
\]

The implementation checks this with bipartite matching. It needs only the first \(n\) values of each domain: a coordinate having at least \(n\) candidates always has a candidate outside the values assigned to the other \(n-1\) coordinates.

For `AllDifferentExceptZero`, every coordinate whose domain contains zero can independently choose zero. Feasibility therefore reduces to strict matching on

\[
J=\{i:0\notin D_i\}.
\]

The set operations then follow ordinary set semantics relative to \(X\). In particular,

\[
\gamma(D)\cap\gamma(E)
=
X\cap\prod_i(D_i\cap E_i),
\]

and

\[
X\setminus\gamma(D)
=
\bigcup_{i=1}^{n}
\left(
X\cap
\left(
\prod_{j<i}\mathbb N_0
\times(\mathbb N_0\setminus D_i)
\times\prod_{j>i}\mathbb N_0
\right)
\right).
\]

Complements of unions are computed using De Morgan’s law. Subset checking uses

\[
S\subseteq T
\quad\Longleftrightarrow\quad
S\setminus T=\varnothing.
\]

**One-transition predecessors**

Write \(x\to y\) for the transition relation. The two supported relations are

\[
x\to_{\mathrm{one}}y
\quad\Longleftrightarrow\quad
\left|\{i:x_i\ne y_i\}\right|\leq1,
\]

and

\[
x\to_{\mathrm{all}}y
\quad\Longleftrightarrow\quad
x,y\in X.
\]

Both include self-loops.

For a target \(B\subseteq X\), define

\[
\operatorname{Pre}(B)
=
\{x\in X:\exists y\in B,\ x\to y\}.
\]

With a source constraint \(A\subseteq X\),

\[
\operatorname{Pre}_A(B)
:=
A\cap\operatorname{Pre}(B).
\]

These are `pre(B)` and `pre(B, A)`.

For `UnrestrictedTransition`,

\[
\operatorname{Pre}(B)=
\begin{cases}
\varnothing,&B=\varnothing,\\
X,&B\ne\varnothing.
\end{cases}
\]

For `OneVariableTransition`, consider a target region \(\gamma(D)\). Choose a coordinate \(i\) that may change and its successor value \(v\in D_i\). Define the values that would collide with \(v\) by

\[
C(v)=
\begin{cases}
\varnothing,&v=0\text{ under AllDifferentExceptZero},\\
\{v\},&\text{otherwise}.
\end{cases}
\]

Then

\[
\operatorname{Pre}(\gamma(D))
=
\bigcup_{i=1}^{n}\ \bigcup_{v\in D_i}
\left\{
x\in X:
\forall j\ne i,\ x_j\in D_j\setminus C(v)
\right\}.
\]

The old value of coordinate \(i\) is unrestricted, subject to \(x\in X\).

This union is computed finitely. If \(D_i\) has fewer than \(n\) values, the implementation enumerates them. Otherwise, some successor value avoids all possible collisions with the other \(n-1\) coordinates, so that branch simply frees coordinate \(i\) and retains the other domains.

Predecessors distribute over the stored union of target regions.

**Untimed reachability**

Define the iterated constrained predecessor

\[
P_A^0(B)=B,
\qquad
P_A^{k+1}(B)=\operatorname{Pre}_A(P_A^k(B)).
\]

This is `pre_k(B, k, A)`. Its path interpretation is

\[
x_0\in P_A^k(B)
\quad\Longleftrightarrow\quad
\exists x_1,\ldots,x_k:
\begin{cases}
x_j\to x_{j+1},&0\leq j<k,\\
x_j\in A,&0\leq j<k,\\
x_k\in B.
\end{cases}
\]

The target state need not satisfy \(A\).

Unbounded reachability is the least fixed point

\[
\boxed{
\mathcal R(B;A)
=
\mu Z.\left(B\cup\operatorname{Pre}_A(Z)\right).
}
\]

The implementation starts with \(Z_0=B\) and repeats

\[
Z_{k+1}=B\cup\operatorname{Pre}_A(Z_k).
\]

Consequently,

\[
Z_k=\bigcup_{j=0}^{k}P_A^j(B).
\]

It stops when the next approximation is contained in the current one. Since the sequence is increasing, that establishes equality. This is `reach(B, A)`.

**Physical-time trajectories**

The timed operations use right-continuous, piecewise-constant trajectories. The represented universe is currently all of \(\mathbb R_{\geq0}\); there is no separate represented-time mask argument.

At anchor \(a\), the supported windows are

\[
W(a)=
\begin{cases}
[a,a+d),&\text{numeric duration }d,\\
[a,a+d],&\text{numeric duration with `closed=True`},\\
I\cap[a,\infty),&\text{absolute interval }I,\\
[a,\infty),&\text{omitted window}.
\end{cases}
\]

The target of `reach_timed(B, window, A, anchor=a)` is

\[
\left\{
x:
\exists\xi,\ \xi(a)=x,\
\exists\tau\in W(a):
\xi(\tau)\in B
\land
\forall t\in[a,\tau),\ \xi(t)\in A
\right\}.
\]

The computation depends on the timing model.

**Variable transition durations**

With `time_step=None`, every transition may take any positive duration. There is no positive minimum duration, and trajectories have finitely many changes on each bounded interval.

Therefore, any finite transition sequence can fit into any positive time budget. Define

\[
Q(B;A):=\operatorname{Pre}_A\bigl(\mathcal R(B;A)\bigr).
\]

This is the set admitting a satisfying witness at any prescribed positive offset. The initial state must lie in \(A\), because it persists for a positive time before the first transition.

Timed reachability is therefore

\[
\boxed{
\mathcal R_{W,a}(B;A)
=
\begin{cases}
B,&a\in W(a),\\
\varnothing,&a\notin W(a)
\end{cases}
\ \cup\
\begin{cases}
Q(B;A),&W(a)\cap(a,\infty)\ne\varnothing,\\
\varnothing,&\text{otherwise}.
\end{cases}
}
\]

This distinguishes an immediate witness from a delayed one, even when both use the same target state.

**Fixed transition duration**

With `time_step=h>0`, each query starts a fresh holding period at its anchor. Along a transition sequence \(x_0,x_1,\ldots\),

\[
\xi(t)=x_k
\qquad
\text{for }t\in J_k:=[a+kh,a+(k+1)h).
\]

Let \(e_k=a+kh\). For each holding period define

\[
B_k=
\begin{cases}
B,&e_k\in W(a),\\
A\cap B,&e_k\notin W(a)\text{ and }J_k\cap W(a)\ne\varnothing,\\
\varnothing,&J_k\cap W(a)=\varnothing.
\end{cases}
\]

Then

\[
\boxed{
\mathcal R_{W,a}(B;A)
=
\bigcup_{k\geq0}P_A^k(B_k).
}
\]

The distinction between the first two cases is essential:

- At an event edge, the witness state only needs to satisfy \(B\).
- Inside a holding period, that same state also occurs immediately before the witness, so it must satisfy \(A\cap B\).

The implementation derives the relevant holding-period indices from the interval endpoints, propagates predecessors, and stops early when those predecessor sets stabilize.

`pre_timed(B, d, A)` is the singleton-window case \(W(0)=\{d\}\).

**Existential invariance**

`invariant_timed(A, window, anchor=a)` computes

\[
\mathcal I_{W,a}(A)
=
\left\{
x:
\exists\xi,\ \xi(a)=x,\
\forall t\in W(a),\ \xi(t)\in A
\right\}.
\]

Both transition relations permit remaining in a state forever. Thus it suffices to reach \(A\) by the first inspected holding period and then stay there.

For fixed timing, if \(W(a)\ne\varnothing\), let

\[
k_*=\min\{k:J_k\cap W(a)\ne\varnothing\}.
\]

Then

\[
\boxed{\mathcal I_{W,a}(A)=P_X^{k_*}(A).}
\]

For variable timing,

\[
\boxed{
\mathcal I_{W,a}(A)=
\begin{cases}
X,&W(a)=\varnothing,\\
A,&W(a)\ne\varnothing\text{ and }\inf W(a)=a,\\
\mathcal R(A;X),&\inf W(a)>a.
\end{cases}
}
\]

Even an open window beginning immediately after \(a\) requires the initial state in \(A\), because the initial holding period has positive duration.

These computations implement existential reachability and invariance directly. In particular, existential invariance is **not** obtained by complementing existential reachability of the complement.

## pyspect API

The symbolic backend is available from `pyspect.impls.symbolic`. Construct a system by naming its signal coordinates and choosing an invariant, transition relation, and optional fixed transition duration:

```python
import portion as P

from pyspect.impls.symbolic import (
    AllDifferentExceptZero,
    OneVariableTransition,
    SymbolicSystem,
)

system = SymbolicSystem(
    variables=("job1", "job2"),
    invariant=AllDifferentExceptZero(),
    transition=OneVariableTransition(),
    time_step=None,  # arbitrary positive durations; use e.g. 0.5 for fixed timing
)
```

Construct state predicates with `states`. An integer fixes a coordinate; a `portion` interval specifies its admissible integer values. Unspecified coordinates range over \(\mathbb N_0\), subject to the invariant.

```python
X = system.universe()
B = system.states(job1=0, job2=0)  # both points free
A = ~system.states(job1=0)        # point 1 occupied
C = system.states(job2=P.closed(1, 4))

intersection = A & C
union = A | C
difference = A - C
assert (0, 0) in B
assert B.is_subset(X)
```

The untimed operations compute one-step predecessors, exactly \(k\) transition predecessors, and unbounded reachability:

```python
system.pre(B, constraints=A)
system.pre_k(B, steps=3, constraints=A)
system.reach(B, constraints=A)
```

Here `constraints=A` applies to the prefix before the target witness. Omitting it uses the whole admissible state space.

The timed operations inspect physical time:

```python
system.pre_timed(B, duration=2, constraints=A)  # witness at exactly time 2
system.reach_timed(B, window=2, constraints=A) # witness in [0, 2)
system.reach_timed(B, window=2, closed=True)   # witness in [0, 2]

system.reach_timed(
    B, window=P.closedopen(5, 8), constraints=A, anchor=3,
)  # A from time 3 until a B witness in [5, 8)

system.invariant_timed(
    B, window=P.closedopen(5, 8), anchor=6,
)  # some trajectory remains in B throughout [6, 8)
```

Numeric windows are relative durations; `portion` windows are absolute intervals clipped to the anchor’s future. An omitted window denotes the entire future. Every operation above returns a `StateSet`; reachability from an initial set `X0` succeeds when

```python
reachable = system.reach_timed(B, window=2)
success = not (X0 & reachable).is_empty
```

For the supported untimed TLT fragment, named predicates can instead be supplied through `SymbolicSet`:

```python
from pyspect import EVENTUALLY, ExactDiscLTL, TLT
from pyspect.impls.symbolic import SymbolicSet

tree = TLT(
    EVENTUALLY("both_free"),
    primitives=ExactDiscLTL,
    where={"both_free": SymbolicSet(job1=0, job2=0)},
)
reachable = tree.realize(system)
```

This last example computes `system.reach(B)`. The timed methods are currently called directly; they are not exposed through interval-parameterized TLT syntax.
