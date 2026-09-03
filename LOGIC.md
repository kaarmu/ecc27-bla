# Interval logic definition

This file defines the interval-logic language and its semantics. There is one
fundamental satisfaction relation,

$$
(\xi,t)\models\varphi,
$$

where $\xi$ is a trajectory and $t$ is physical time. Trace checking asks where
a formula holds on one given trajectory. Reachability checking asks from which
states some admissible trajectory satisfies it:

$$
\boxed{
\text{trajectory satisfaction}
\longrightarrow
\begin{cases}
\text{truth times on one trajectory},\\
\text{initial states admitting a satisfying trajectory}.
\end{cases}
}
$$

The anchored mask denotation is retained as an additional observation because
selection is observational rather than temporal-condition-forming. Its window
constructs a time mask, but the duration and endpoint of a positive relative
window are not observable through local satisfaction. Temporal requirements
over a duration are expressed by conditions such as until, eventually, and
always. The anchored mask denotation is not a second satisfaction semantics.

## Syntax

### Signals and atoms

A numeric term is either a natural-number literal or a signal name:

$$
\tau ::= n \mid \textit{job},
\qquad n\in\mathbb N_0,
\quad \textit{job}:X\to\mathbb N_0.
$$

Atomic formulas are proposition names or equalities between numeric terms:

$$
\alpha ::= p \mid (\tau_1=\tau_2),
\qquad p\in\mathcal{AP}.
$$

Inequality is the shorthand
$\tau_1\neq\tau_2:=\neg(\tau_1=\tau_2)$.

### Temporal parameters

Every temporal operator accepts the same kinds of parameter:

$$
\rho ::= d] \mid d) \mid I,
\qquad d\in\mathbb R_{\geq0}.
$$

Here $I\subseteq\mathbb R_{\geq0}$ is an absolute interval. The one-sided
relative forms denote

$$
d]:=[0,d],
\qquad
d):=[0,d).
$$

Thus $d]$ includes the endpoint at offset $d$, whereas $d)$ excludes it. In a
temporal-parameter position, a bare duration $d$ is syntactic sugar for $d)$.
For example,

$$
\langle\varphi\rangle_3
:=\langle\varphi\rangle_{3)}.
$$

Numeric signal literals remain natural numbers even though temporal durations
are real-valued.

A temporal parameter may be omitted. Omission is meta-level sugar for the
represented future from the current anchor; it does not add another form to
the grammar.

### Formulas and temporal basis

The two fundamental temporal constructs have distinct roles:

| Construct | Syntax | Role |
| --- | --- | --- |
| Selection | $\langle\varphi,\psi\rangle_\rho$ | Constructs an anchored time mask, using $\varphi$ inside the parameter window and $\psi$ outside it. |
| Condition | $\varphi\mathbin{\mathsf U_\rho}\psi$ | Makes a temporal assertion, requiring a witness for $\psi$ and $\varphi$ along the preceding temporal prefix. |

A minimal grammar is

$$
\varphi ::= \top
  \mid \alpha
  \mid \neg\varphi
  \mid (\varphi\land\varphi)
  \mid \langle\varphi,\psi\rangle_\rho
  \mid \varphi\mathbin{\mathsf U_\rho}\psi.
$$

The usual Boolean operations are abbreviations:

$$
\begin{aligned}
\bot &:= \neg\top, &
\varphi\lor\psi &:= \neg(\neg\varphi\land\neg\psi),\\
\varphi\rightarrow\psi &:= \neg\varphi\lor\psi, &
\varphi\leftrightarrow\psi
&:=(\varphi\rightarrow\psi)\land(\psi\rightarrow\varphi).
\end{aligned}
$$

The unary vacuous and restrictive selections are the special cases

$$
\langle\varphi\rangle_\rho
:=\langle\varphi,\top\rangle_\rho,
\qquad
\langle\varphi\rangle_\rho^*
:=\langle\varphi,\bot\rangle_\rho.
$$

Existential and universal conditions are derived from strong until:

$$
\lozenge_\rho\varphi
:=\top\mathbin{\mathsf U_\rho}\varphi,
\qquad
\square_\rho\varphi
:=\neg\lozenge_\rho\neg\varphi.
$$

Release is the derived dual

$$
\varphi\mathbin{\mathsf R_\rho}\psi
:=\neg(\neg\varphi\mathbin{\mathsf U_\rho}\neg\psi).
$$

Weak until $\mathsf W$ (also called *unless*) is an optional convenience
extension. It permits the right operand never to occur. Its no-witness branch
uses an anchor-dependent horizon, so it is defined directly below rather than
rewritten generally as until-or-always.

Parameter omission applies uniformly to selection, until, the derived
conditions, release, and optional weak until.

## Common trajectory semantics

### Trajectories, states, and represented time

Let $X$ be a state domain. A trajectory is a physical-time function

$$
\xi:\mathbb R_{\geq0}\to X.
$$

For the signal language, a state carries the current signal values, so one may
write

$$
\xi(t)=(\textit{job}_1(t),\ldots,\textit{job}_n(t)).
$$

The atomic valuation maps each proposition to the states where it is true, and
each signal name denotes its projection
$\textit{job}:X\to\mathbb N_0$. Term evaluation along a trajectory is

$$
\llbracket n\rrbracket_{\xi,t}=n,
\qquad
\llbracket \textit{job}\rrbracket_{\xi,t}=\textit{job}(\xi(t)).
$$

For each trace or reachability query, fix a represented evaluation universe
$\mathbb I\subseteq\mathbb R_{\geq0}$. The same $\mathbb I$ is shared by every
trajectory considered by that query. Each trajectory remains defined on all
physical time, but only times in $\mathbb I$ are inspected. Local satisfaction
is queried only at $t\in\mathbb I$, and an anchored mask denotation is queried
only at $a\in\mathbb I$.

### Temporal windows

Every temporal construct uses the same represented, future-directed window:

$$
W_\rho(a)=
\begin{cases}
[a,a+d]\cap\mathbb I, & \rho=d],\\
[a,a+d)\cap\mathbb I, & \rho=d),\\
I\cap[a,\infty)\cap\mathbb I, & \rho=I.
\end{cases}
$$

When the parameter is omitted, use

$$
W(a):=[a,\infty)\cap\mathbb I.
$$

This is a convention for omitted syntax, not another value of $\rho$.
In particular,

$$
\boxed{W_I(a)=I\cap[a,\infty)\cap\mathbb I.}
$$

Absolute selection, until, eventually, always, release, and weak until all
therefore use the same *from now onward* interpretation. Historical trace
inspection is expressed by evaluating from an earlier anchor, not by giving
selection a backward-looking window.

The zero-duration windows are

$$
W_{0]}(a)=\{a\},
\qquad
W_{0)}(a)=\varnothing.
$$

Because a bare duration denotes $d)$, bare $0$ also denotes the empty window.

### Local satisfaction

Local truth is fundamental. Atoms and Boolean connectives satisfy

$$
\begin{aligned}
(\xi,t)&\models\top,\\
(\xi,t)&\models p
&&\Longleftrightarrow \xi(t)\in V(p),\\
(\xi,t)&\models\tau_1=\tau_2
&&\Longleftrightarrow
\llbracket\tau_1\rrbracket_{\xi,t}
=\llbracket\tau_2\rrbracket_{\xi,t},\\
(\xi,t)&\models\neg\varphi
&&\Longleftrightarrow (\xi,t)\not\models\varphi,\\
(\xi,t)&\models\varphi\land\psi
&&\Longleftrightarrow
(\xi,t)\models\varphi\ \land\ (\xi,t)\models\psi.
\end{aligned}
$$

The derived Boolean connectives have their usual truth conditions.

Selection chooses a branch at the time where its local truth is inspected:

$$
\boxed{
(\xi,t)\models\langle\varphi,\psi\rangle_\rho
\quad\Longleftrightarrow\quad
\begin{cases}
(\xi,t)\models\varphi, & t\in W_\rho(t),\\
(\xi,t)\models\psi, & t\notin W_\rho(t).
\end{cases}
}
$$

The omitted form uses $W(t)=[t,\infty)\cap\mathbb I$ and therefore selects the
inside operand. The same local clause applies whenever a selector is nested
inside a temporal condition: it is re-anchored at the inspected time $t$.

Strong until uses the temporal window:

$$
\boxed{
(\xi,a)\models\varphi\mathbin{\mathsf U_\rho}\psi
\quad\Longleftrightarrow\quad
\exists \tau\in W_\rho(a):
\left(
(\xi,\tau)\models\psi
\land
\forall t\in[a,\tau)\cap\mathbb I:\ (\xi,t)\models\varphi
\right).
}
$$

The parameter restricts the witness time. The left operand is required from
the anchor up to, but not including, the witness; the witness itself need not
satisfy the left operand. For omission, use $W(a)$.

The derived conditions therefore satisfy

$$
\begin{aligned}
(\xi,a)\models\lozenge_\rho\varphi
&\Longleftrightarrow
\exists t\in W_\rho(a):\ (\xi,t)\models\varphi,\\
(\xi,a)\models\square_\rho\varphi
&\Longleftrightarrow
\forall t\in W_\rho(a):\ (\xi,t)\models\varphi.
\end{aligned}
$$

An empty temporal window makes $\square_\rho\varphi$ true and
$\lozenge_\rho\varphi$ false.

For optional weak until, define the prefix horizon

$$
H_\rho(a)
:=\left\{
t\in\mathbb I:
\exists \tau\in W_\rho(a),\ a\leq t\leq \tau
\right\}.
$$

Then

$$
\boxed{
(\xi,a)\models\varphi\mathbin{\mathsf W_\rho}\psi
\quad\Longleftrightarrow\quad
(\xi,a)\models\varphi\mathbin{\mathsf U_\rho}\psi
\lor
\forall t\in H_\rho(a):\ (\xi,t)\models\varphi.
}
$$

For $d]$ and $d)$, the horizon is respectively
$[a,a+d]\cap\mathbb I$ and $[a,a+d)\cap\mathbb I$. For an absolute interval,
it extends from $a$ to the upper edge of $W_I(a)$, with that interval's
endpoint convention. For omission,
$H(a)=[a,\infty)\cap\mathbb I$.

For a relative closed window only, the familiar convenience law holds:

$$
\varphi\mathbin{\mathsf W_{d]}}\psi
\equiv
(\varphi\mathbin{\mathsf U_{d]}}\psi)
\lor\square_{d]}\varphi.
$$

The analogous absolute-interval rewrite is generally false. If $a=3$ and
$I=[5,8)$, the no-witness branch requires $\varphi$ throughout
$[3,8)\cap\mathbb I$, not merely throughout $W_I(3)$.

### Anchored mask denotation

For one trajectory, define its local truth-time set

$$
\operatorname{Sat}_\xi(\varphi)
:=\{t\in\mathbb I:(\xi,t)\models\varphi\}.
$$

The anchored mask denotation
$\llbracket\varphi\rrbracket_{\xi,a}\subseteq\mathbb I$ additionally preserves
the time mask produced by selection. Atoms and Boolean operators use the usual
set operations:

$$
\begin{aligned}
\llbracket\top\rrbracket_{\xi,a}&=\mathbb I, &
\llbracket\bot\rrbracket_{\xi,a}&=\varnothing,\\
\llbracket p\rrbracket_{\xi,a}&=\operatorname{Sat}_\xi(p), &
\llbracket\tau_1=\tau_2\rrbracket_{\xi,a}
&=\operatorname{Sat}_\xi(\tau_1=\tau_2),\\
\llbracket\neg\varphi\rrbracket_{\xi,a}
&=\mathbb I\setminus\llbracket\varphi\rrbracket_{\xi,a}, &
\llbracket\varphi\land\psi\rrbracket_{\xi,a}
&=\llbracket\varphi\rrbracket_{\xi,a}
\cap\llbracket\psi\rrbracket_{\xi,a}.
\end{aligned}
$$

The anchored mask denotation of a binary selector is

$$
\boxed{
\llbracket\langle\varphi,\psi\rangle_\rho\rrbracket_{\xi,a}
=
\bigl(W_\rho(a)\cap\operatorname{Sat}_\xi(\varphi)\bigr)
\cup
\bigl((\mathbb I\setminus W_\rho(a))
\cap\operatorname{Sat}_\xi(\psi)\bigr).
}
$$

The unary cases are

$$
\begin{aligned}
\llbracket\langle\varphi\rangle_\rho\rrbracket_{\xi,a}
&=(\mathbb I\setminus W_\rho(a))
\cup(W_\rho(a)\cap\operatorname{Sat}_\xi(\varphi)),\\
\llbracket\langle\varphi\rangle_\rho^*\rrbracket_{\xi,a}
&=W_\rho(a)\cap\operatorname{Sat}_\xi(\varphi).
\end{aligned}
$$

Every temporal condition $C$ is globally valued at a fixed anchor:

$$
\llbracket C\rrbracket_{\xi,a}
=
\begin{cases}
\mathbb I, & (\xi,a)\models C,\\
\varnothing, & (\xi,a)\not\models C.
\end{cases}
$$

Strong until, eventually, always, release, and optional weak until are
conditions. Boolean combinations are evaluated compositionally by the set
clauses above, so a Boolean formula containing a selector need not be globally
valued.

The anchored mask denotation is consistent with the fundamental satisfaction
relation on its diagonal:

$$
(\xi,t)\models\varphi
\quad\Longleftrightarrow\quad
t\in\llbracket\varphi\rrbracket_{\xi,t}.
$$

This is a consequence of the clauses, not the definition of local truth.

## Trace checking

Trace checking fixes one complete known trajectory $\xi$. Its two outputs are

$$
\begin{aligned}
\operatorname{satisfying\_times}(\varphi,\xi)
&=\operatorname{Sat}_\xi(\varphi),\\
\operatorname{denote}(\varphi,\xi,a)
&=\llbracket\varphi\rrbracket_{\xi,a}.
\end{aligned}
$$

The first answers where the formula is locally true. The second returns the
formula's anchored mask denotation and therefore preserves a selector's
complete anchored time mask.

### Selection and re-anchoring

Absolute selection uses the same future-directed window as every temporal
construct. At anchor $a$, $\langle\varphi\rangle_I$ follows $\varphi$ on
$I\cap[a,\infty)\cap\mathbb I$ and is true elsewhere. It remains a mask rather
than a persistence requirement; that requirement is $\square_I\varphi$.

For every $d>0$, the anchor lies in both $W_{d)}(a)$ and $W_{d]}(a)$. Hence,
under local satisfaction,

$$
\boxed{
d>0
\quad\Longrightarrow\quad
\langle\varphi,\psi\rangle_{d)}
\equiv
\langle\varphi,\psi\rangle_{d]}
\equiv
\varphi.
}
$$

The duration and endpoint still change the full anchored mask denotation, but
they cannot be observed through local satisfaction. Selection constructs a
mask; it does not assert persistence over that mask. Consequently, trace and
reachability queries derived from local satisfaction cannot distinguish the
positive relative durations either. For example,

$$
\begin{aligned}
\langle p\rangle_{1)}&\equiv\langle p\rangle_{100)},\\
\square_{5]}\langle p\rangle_{3)}&\equiv\square_{5]}p,\\
\lozenge_{5]}\langle p\rangle_{3)}&\equiv\lozenge_{5]}p.
\end{aligned}
$$

The nested examples work because the selector is re-anchored at every
inspected time. An absolute selector may likewise choose different branches
at different inspected times. If the outer anchor precedes $3$, then

$$
\square_{[3,10]}\langle p,q\rangle_{[5,8)}
$$

requires $q$ on $[3,5)$, $p$ on $[5,8)$, and $q$ on $[8,10]$, restricted in
each case to represented time.

### Absolute windows

Every absolute temporal construct uses $W_I(a)$. Thus
$\square_{[5,8)}\varphi$ at $a=6$ checks $[6,8)\cap\mathbb I$, while at $a=3$
it checks $[5,8)\cap\mathbb I$. If $a\geq8$, the temporal window is empty and
the universal condition is vacuously true.

At $a=6$, an absolute selector with parameter $[5,8)$ similarly masks only
$[6,8)\cap\mathbb I$; represented times before $6$ take its outside branch.
To inspect the earlier part of an absolute interval, evaluate from an earlier
anchor.

For strong until, if $a=3$ and $I=[5,8)$, then
$\varphi\mathbin{\mathsf U_I}\psi$ requires a $\psi$ witness in
$[5,8)\cap\mathbb I$ and requires $\varphi$ from $3$ until that witness.

### Zero-duration laws

The endpoint convention yields

$$
\begin{array}{c|cc}
 & 0] & 0) \\ \hline
\lozenge_\rho\varphi
 & \varphi & \bot \\
\square_\rho\varphi
 & \varphi & \top \\
\varphi\mathbin{\mathsf U_\rho}\psi
 & \psi & \bot \\
\varphi\mathbin{\mathsf R_\rho}\psi
 & \psi & \top
\end{array}
$$

For optional weak until,

$$
\varphi\mathbin{\mathsf W_{0]}}\psi
\equiv\varphi\lor\psi,
\qquad
\varphi\mathbin{\mathsf W_{0)}}\psi
\equiv\top.
$$

For selection at its own anchor,

$$
\begin{aligned}
(\xi,a)\models\langle\varphi,\psi\rangle_{0]}
&\Longleftrightarrow (\xi,a)\models\varphi,\\
(\xi,a)\models\langle\varphi,\psi\rangle_{0)}
&\Longleftrightarrow (\xi,a)\models\psi.
\end{aligned}
$$

### Negation dualities

Negation passes through a binary selector componentwise. The unary selection,
condition, and until/release dualities are

$$
\begin{aligned}
\neg\langle\varphi,\psi\rangle_\rho
&\equiv\langle\neg\varphi,\neg\psi\rangle_\rho,\\
\neg\langle\varphi\rangle_\rho
&\equiv\langle\neg\varphi\rangle_\rho^*, &
\neg\langle\varphi\rangle_\rho^*
&\equiv\langle\neg\varphi\rangle_\rho,\\
\neg\square_\rho\varphi
&\equiv\lozenge_\rho\neg\varphi, &
\neg\lozenge_\rho\varphi
&\equiv\square_\rho\neg\varphi,\\
\neg(\varphi\mathbin{\mathsf U_\rho}\psi)
&\equiv\neg\varphi\mathbin{\mathsf R_\rho}\neg\psi, &
\neg(\varphi\mathbin{\mathsf R_\rho}\psi)
&\equiv\neg\varphi\mathbin{\mathsf U_\rho}\neg\psi.
\end{aligned}
$$

## Reachability checking

### Systems and existential state satisfaction

Let

$$
\Sigma=(X,\Xi,V),
$$

where $X$ is the invariant-constrained state space, $V$ is the atomic
interpretation used above, and $\Xi(x,a)$ is the family of system trajectories
with $\xi(a)=x$. Reachability quantifies over the same trajectories and the
same satisfaction relation:

$$
\boxed{
\operatorname{Sat}_{\Sigma}^{\exists}(\varphi,a)
:=
\left\{
x\in X:
\exists \xi\in\Xi(x,a),\ (\xi,a)\models\varphi
\right\}.
}
$$

This is the true existential state satisfaction set. For a queried initial
set $X_0\subseteq X$, existential reachability succeeds exactly when

$$
X_0\cap\operatorname{Sat}_{\Sigma}^{\exists}(\varphi,a)
\neq\varnothing.
$$

A future universal extension may analogously quantify over every trajectory,
but it is not part of the first backend.

A `StateSet` denotes a subset of $X$. It is fundamentally multidimensional and
may preserve relations between signal coordinates. A
one-dimensional time interval is not a general `StateSet`. All state-set
operations are relative to $X$.

The output domains are distinct: `denote` returns an anchored mask denotation
as a `TimeSet`, whereas existential state satisfaction returns a `StateSet`:

$$
\begin{aligned}
\operatorname{denote}(\varphi,\xi,a)&\longrightarrow\mathrm{TimeSet},\\
\operatorname{Sat}_{\Sigma}^{\exists}(\varphi,a)
&\in\mathrm{StateSet}.
\end{aligned}
$$

### Reachability operators for state predicates

For state sets $A,B\subseteq X$, define constrained backward reachability by

$$
\boxed{
\mathcal R_{\rho,a}(B;A)
:=
\left\{
x\in X:
\begin{array}{l}
\exists \xi\in\Xi(x,a),\\
\exists \tau\in W_\rho(a) : \xi(\tau)\in B,\\
\forall t\in[a,\tau)\cap\mathbb I:\ \xi(t)\in A
\end{array}
\right\}.
}
$$

Define existential invariance by

$$
\boxed{
\mathcal I_{\rho,a}(A)
:=
\left\{
x\in X:
\exists \xi\in\Xi(x,a),
\forall t\in W_\rho(a) :\ \xi(t)\in A
\right\}.
}
$$

For an omitted temporal parameter, write $\mathcal R_a(B;A)$ and
$\mathcal I_a(A)$ and use the omitted window $W(a)$.

For state predicates $\alpha,\beta$ with truth sets $A,B$, the core TLT
correspondence is

$$
\begin{array}{c|c}
\text{formula} & \text{trajectory-defined state set} \\ \hline
\alpha\mathbin{\mathsf U_\rho}\beta
& \mathcal R_{\rho,a}(B;A) \\
\lozenge_\rho\beta
& \mathcal R_{\rho,a}(B;X) \\
\square_\rho\alpha
& \mathcal I_{\rho,a}(A)
\end{array}
$$

These are computational correspondences derived from the common satisfaction
relation; they do not redefine until, eventually, or always. For temporal
operands, the defining state satisfaction set still quantifies over one common
trajectory. Replacing operands prematurely by independently computed state
sets may lose that correlation.

## Charging-station example
Consider one charging station with $n$ charging points. Its state space is

$$
X
=\left\{
x\in\mathbb N_0^n:
\bigwedge_{1\leq i<k\leq n}
\left(
x_i\neq x_k
\lor
((x_i=0)\land(x_k=0))
\right)
\right\}.
$$

This is an all-different constraint on nonzero values, not strict
`AllDifferent`: a state with several zero coordinates belongs to $X$.

An allocation trajectory is the vector-valued signal

$$
\xi=(\textit{job}_1,\ldots,\textit{job}_n):
\mathbb R_{\geq0}\to X\subseteq\mathbb N_0^n,
$$

where $\textit{job}_i(t)=0$ means that charging point $i$ is unallocated at
time $t$, and every positive value is a job ID. The state observation denoted
by $\textit{job}_i$ is the coordinate map $x\mapsto x_i$. Hence

$$
(\xi,t)\models \textit{job}_1=0
\quad\Longleftrightarrow\quad
\textit{job}_1(t)=0,
$$

so charging point 1 is unallocated at $t$. Examples include

$$
\begin{aligned}
\langle \textit{job}_1=0\rangle_I
&\quad\text{follows }\textit{job}_1=0\text{ inside }W_I(a)
\text{ and is true outside }W_I(a),\\
\langle \textit{job}_1=0\rangle_I^*
&\quad\text{selects the represented times in }W_I(a)
\text{ when point 1 is free},\\
\lozenge_I(\textit{job}_1=0)
&\quad\text{requires point 1 to be free sometime in }W_I(a),\\
(\textit{job}_1\neq0)\mathbin{\mathsf U_I}(\textit{job}_1=0)
&\quad\text{requires point 1 to stay occupied until it becomes free},\\
\square_I((\textit{job}_1=0)\land(\textit{job}_2=0))
&\quad\text{requires both points to be free throughout }W_I(a).
\end{aligned}
$$

For reachability, let

$$
B_1:=\{x\in X:x_1=0\}.
$$

Then

$$
\operatorname{Sat}_{\Sigma}^{\exists}
(\lozenge(\textit{job}_1=0),a)
=
\mathcal R_a(B_1;X).
$$
