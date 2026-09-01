# Interval logic definition

This file defines the interval-logic language and its trace-checking
semantics.

## Syntax

### Signals and atoms

A numeric term is either a natural-number literal or a signal name:

$$
\tau ::= n \mid j,
\qquad n\in\mathbb \Omega,
\quad j: \mathbb R_{\geq0} \rightarrow \Omega.
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
\rho ::= d] \mid d) \mid I \mid D^+,
\qquad d\in\mathbb R_{\geq0}.
$$

Here $I\subseteq\mathbb R$ is an absolute interval and
$D\subseteq\mathbb R_{\geq0}$ is a nonempty connected interval of relative
offsets. The $+$ is part of the relative-interval syntax, not a separate
operator. The one-sided relative forms are

$$
d]:=[0,d]^+,
\qquad
d):=[0,d)^+.
$$

Thus $d]$ includes the endpoint at offset $d$, whereas $d)$ excludes it.
A bare duration $d$, if retained by the concrete syntax for compatibility, is
shorthand for $d]$. Numeric signal literals remain natural numbers even
though temporal durations are real-valued.

An unmarked interval is absolute; an interval marked with $+$ is relative.
General $D^+$ parameters are convenient surface syntax. They resolve directly
in the semantics, although finite $D^+$ selections can also be reduced to the
one-sided forms as shown below.

A temporal parameter may be omitted. Omission is uniform syntactic sugar for
the unbounded relative interval

$$
\rho_{\mathrm{default}}=[0,\infty)^+.
$$

It therefore ranges from the current anchor through the represented future of
the trace. Omission is not a separate parameter kind.

### Formulas and temporal basis

The two fundamental temporal constructs have distinct roles:

| Construct | Syntax | Role |
| --- | --- | --- |
| Selection | $\langle\varphi,\psi\rangle_\rho$ | Uses $\varphi$ inside the window and $\psi$ outside it. |
| Progression | $\varphi\mathbin{\mathsf U_\rho}\psi$ | Requires a witness for $\psi$ and $\varphi$ along the preceding temporal prefix. |

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

Accordingly, $\langle\varphi\rangle_\rho$ follows $\varphi$ inside the
selected window and is true outside it, while
$\langle\varphi\rangle_\rho^*$ follows $\varphi$ inside and is false outside.

Existential and universal conditions are derived from strong until:

$$
\lozenge_\rho\varphi
:=\top\mathbin{\mathsf U_\rho}\varphi,
\qquad
\square_\rho\varphi
:=\neg\lozenge_\rho\neg\varphi.
$$

They are conditions rather than masks: for a fixed anchor their denotation is
either all of $\mathbb I$ or none of it. An implementation may retain
dedicated nodes for these derived forms.

Parameter omission applies uniformly. In particular,

$$
\begin{aligned}
\langle\varphi,\psi\rangle
&:=\langle\varphi,\psi\rangle_{[0,\infty)^+}, &
\varphi\mathbin{\mathsf U}\psi
&:=\varphi\mathbin{\mathsf U_{[0,\infty)^+}}\psi,\\
\square\varphi
&:=\square_{[0,\infty)^+}\varphi, &
\lozenge\varphi
&:=\lozenge_{[0,\infty)^+}\varphi.
\end{aligned}
$$

### Weak until and release

For the no-witness branch of bounded weak until, the left operand must hold
from the relative anchor through the upper bound, including or excluding that
bound as specified by $\rho$. Define $\operatorname{span}(\rho)$ as follows:

- $\operatorname{span}(I)=I$ for an absolute interval;
- $\operatorname{span}$ leaves the one-sided forms $d]$ and $d)$ unchanged;
- if $D^+$ has finite upper endpoint $d$, then
  $\operatorname{span}(D^+)$ is $d]$ or $d)$ according as $D$ includes or
  excludes $d$;
- if $D^+$ is unbounded above, then
  $\operatorname{span}(D^+)=[0,\infty)^+$.

Weak until (also called *unless*) and release are then abbreviations:

$$
\begin{aligned}
\varphi\mathbin{\mathsf W_\rho}\psi
&:= (\varphi\mathbin{\mathsf U_\rho}\psi)
   \lor\square_{\operatorname{span}(\rho)}\varphi,\\
\varphi\mathbin{\mathsf R_\rho}\psi
&:=\neg(\neg\varphi\mathbin{\mathsf U_\rho}\neg\psi).
\end{aligned}
$$

For a relative interval with a positive lower bound, the use of
$\operatorname{span}(\rho)$ is essential: the no-witness branch starts at the
anchor, not at that lower bound. The unparameterized forms use
$[0,\infty)^+$.

### Finite $D^+$ selections as surface syntax

Let $0\leq d_0\leq d$. All four endpoint variants of a finite relative
selection can be constructed from one-sided selections:

$$
\begin{aligned}
\langle\varphi\rangle_{[d_0,d]^+}
&\equiv
\langle\varphi\rangle_{d]}
\lor\langle\top\rangle^*_{d_0)},\\
\langle\varphi\rangle_{[d_0,d)^+}
&\equiv
\langle\varphi\rangle_{d)}
\lor\langle\top\rangle^*_{d_0)},\\
\langle\varphi\rangle_{(d_0,d]^+}
&\equiv
\langle\varphi\rangle_{d]}
\lor\langle\top\rangle^*_{d_0]},\\
\langle\varphi\rangle_{(d_0,d)^+}
&\equiv
\langle\varphi\rangle_{d)}
\lor\langle\top\rangle^*_{d_0]}.
\end{aligned}
$$

The upper endpoint is supplied by $d]$ or $d)$; the lower prefix uses the
complementary endpoint type. Every operator in each identity keeps the same
anchor.

These are selection identities only. In particular, a condition over $D^+$
must resolve $D^+$ directly. Masking a larger condition, for example with an
expression of the form
$\square_{d]}\langle\varphi\rangle_{D^+}$, is not equivalent because the
condition re-anchors its operand at every inspected time.

## Trace-checking semantics

The syntax does not prescribe a single verification method. The denotational
semantics in this section checks a formula against a complete, known trace $w\in W$.
Verification over symbolic or partially known behavior may use a different
semantic domain while retaining the language.

Fix an evaluation universe $\mathbb I\subseteq\mathbb R$, possibly dependent on $w$. The trace assigns
each proposition $p$ a truth set $V_w(p)\subseteq\mathbb I$ and each numeric
signal $j$ a piecewise-constant function
$j:\mathbb I\to\mathbb N_0$.

There are two distinct time roles:

- $a\in\mathbb I$ is the **anchor time**, from which relative temporal
  parameters are resolved;
- $t\in\mathbb I$ is the **evaluation time** of a subformula.

Every formula has an anchored denotation
$\llbracket\varphi\rrbracket_a\subseteq\mathbb I$. Local truth is the
diagonal of this family of denotations:

$$
t\models\varphi
\quad\Longleftrightarrow\quad
t\in\llbracket\varphi\rrbracket_t.
$$

The diagonal definition is what makes a relative temporal operator nested
inside a condition resolve from each time inspected by that condition.

### Temporal-parameter resolution

At anchor $a$, a temporal parameter resolves to

$$
W_\rho(a)=
\begin{cases}
[a,a+d] & \rho=d],\\
[a,a+d) & \rho=d),\\
I & \rho=I,\\
a+D=\{a+s\mid s\in D\} & \rho=D^+.
\end{cases}
$$

For example,

$$
\begin{aligned}
W_{3]}(a)&=[a,a+3], &
W_{3)}(a)&=[a,a+3),\\
W_{[b,c]}(a)&=[b,c], &
W_{(d_0,d]^+}(a)&=(a+d_0,a+d].
\end{aligned}
$$

Only represented times are inspected, so every use of a resolved window below
intersects it with $\mathbb I$. For an omitted parameter,

$$
W_{[0,\infty)^+}(a)=[a,\infty).
$$

Endpoint types are preserved by relative translation.

### Atoms and Boolean connectives

Time is implicit in an equality: signals are read at the evaluation time, and
a literal is constant, so $n(t)=n$. Thus

$$
\begin{aligned}
\llbracket p\rrbracket_a &= V(p),\\
\llbracket\tau_1=\tau_2\rrbracket_a
&=\{t\in\mathbb I\mid\tau_1(t)=\tau_2(t)\}.
\end{aligned}
$$

The Boolean clauses are the usual set operations:

$$
\begin{aligned}
\llbracket\top\rrbracket_a &= \mathbb I, &
\llbracket\bot\rrbracket_a &= \varnothing,\\
\llbracket\neg\varphi\rrbracket_a
&=\mathbb I\setminus\llbracket\varphi\rrbracket_a, &
\llbracket\varphi\land\psi\rrbracket_a
&=\llbracket\varphi\rrbracket_a
  \cap\llbracket\psi\rrbracket_a,\\
\llbracket\varphi\lor\psi\rrbracket_a
&=\llbracket\varphi\rrbracket_a
  \cup\llbracket\psi\rrbracket_a.
\end{aligned}
$$

### Selection: an anchor-preserving mask

The binary selector uses its first operand inside the represented window and
its second operand outside it:

$$
\begin{aligned}
\llbracket\langle\varphi,\psi\rangle_\rho\rrbracket_a
={}&\bigl(W_\rho(a)\cap\mathbb I
          \cap\llbracket\varphi\rrbracket_a\bigr)\\
&\cup\bigl((\mathbb I\setminus W_\rho(a))
          \cap\llbracket\psi\rrbracket_a\bigr).
\end{aligned}
$$

Selection preserves the anchor: its operands use
$\llbracket\varphi\rrbracket_a$ and
$\llbracket\psi\rrbracket_a$. It does not re-anchor them separately at every
point of the mask.

The unary cases are therefore

$$
\begin{aligned}
\llbracket\langle\varphi\rangle_\rho\rrbracket_a
&=(\mathbb I\setminus W_\rho(a))
  \cup\bigl(W_\rho(a)\cap\mathbb I
            \cap\llbracket\varphi\rrbracket_a\bigr),\\
\llbracket\langle\varphi\rangle_\rho^*\rrbracket_a
&=W_\rho(a)\cap\mathbb I
  \cap\llbracket\varphi\rrbracket_a.
\end{aligned}
$$

For an absolute interval $I$, these reduce to a mask by
$I\cap\mathbb I$. In particular, $\langle\varphi\rangle_I$ is true outside
$I$; it is not a global assertion that $\varphi$ holds throughout $I$.

### Conditions: global values with re-anchored operands

The universal condition is globally true exactly when its operand is locally
true at every represented time in the window:

$$
\llbracket\square_\rho\varphi\rrbracket_a=
\begin{cases}
\mathbb I
& \forall t\in W_\rho(a)\cap\mathbb I:\ t\models\varphi,\\
\varnothing & \text{otherwise.}
\end{cases}
$$

Likewise,

$$
\llbracket\lozenge_\rho\varphi\rrbracket_a=
\begin{cases}
\mathbb I
& \exists t\in W_\rho(a)\cap\mathbb I:\ t\models\varphi,\\
\varnothing & \text{otherwise.}
\end{cases}
$$

The result remains global for the fixed anchor, but the operand is re-anchored
at each inspected $t$. For example,

$$
\square_{5]}\lozenge_{2]}p
$$

means

$$
\forall t\in[a,a+5]\ \exists u\in[t,t+2]:\ u\models p.
$$

For an absolute interval $I$, the outer anchor disappears from the condition:

$$
\llbracket\square_I\varphi\rrbracket_a=\mathbb I
\quad\Longleftrightarrow\quad
\forall t\in I\cap\mathbb I:\ t\models\varphi.
$$

Consequently, if the absolute condition holds, then

$$
\llbracket p\land\square_I q\rrbracket_a
=\llbracket p\rrbracket_a,
$$

including at evaluation times before $I$. This works because
$\square_I q$ is a global value, not an interval mask. The corresponding
global assertion is simply $\square_I\varphi$, not
$\langle\square_I\varphi\rangle_I$.

An empty window makes $\square_\rho\varphi$ true and
$\lozenge_\rho\varphi$ false. The closed zero-duration window $0]$ contains
the anchor; the half-open zero-duration window $0)$ is empty.

### Strong until

Strong until is also globally valued. Its right operand supplies a witness,
and both operands are evaluated locally at the times where their truth is
required.

For a witness $u\in W_\rho(a)\cap\mathbb I$, define the preceding obligation
set

$$
P_\rho(a,u)=
\begin{cases}
[a,u)\cap\mathbb I
& \rho\text{ is relative},\\
I\cap(-\infty,u)\cap\mathbb I
& \rho=I\text{ is absolute}.
\end{cases}
$$

The absolute case orders points within the absolute interval itself. The
relative case uses the anchor, not the lower endpoint of the witness window.
Now

$$
\llbracket\varphi\mathbin{\mathsf U_\rho}\psi\rrbracket_a=
\begin{cases}
\mathbb I
& \begin{aligned}
  \exists u\in W_\rho(a)\cap\mathbb I:\quad
  &u\models\psi\ \land{}\\[-2pt]
  &\forall t\in P_\rho(a,u):\ t\models\varphi,
  \end{aligned}\\
\varnothing & \text{otherwise.}
\end{cases}
$$

The witness itself need not satisfy $\varphi$. For a relative bounded until

$$
\varphi\mathbin{\mathsf U_{[d_0,d]^+}}\psi,
$$

the witness lies in $[a+d_0,a+d]$, but $\varphi$ must hold throughout
$[a,u)\cap\mathbb I$. The lower bound $d_0$ restricts the witness time; it
does not postpone the left-operand obligation. In particular, this is not
equivalent to
$\varphi\mathbin{\mathsf U}\lozenge_{[d_0,d]^+}\psi$.

The definition immediately gives

$$
\top\mathbin{\mathsf U_\rho}\varphi
\equiv\lozenge_\rho\varphi.
$$

For weak until, the no-witness branch uses
$\operatorname{span}(\rho)$ as defined above. Consequently,

$$
\varphi\mathbin{\mathsf W_\rho}\bot
\equiv\square_{\operatorname{span}(\rho)}\varphi,
\qquad
\bot\mathbin{\mathsf R_\rho}\varphi
\equiv\square_\rho\varphi.
$$

### Satisfaction and normalization

A formula is checked from anchor $a$ by evaluating its local truth there:

$$
a\models\varphi
\quad\Longleftrightarrow\quad
a\in\llbracket\varphi\rrbracket_a.
$$

Sweeping the anchor over the trace produces the local truth set
$\{a\in\mathbb I\mid a\models\varphi\}$. The full anchored denotation remains
useful because selections are set-valued masks, whereas conditions and until
formulas return only $\mathbb I$ or $\varnothing$ for a fixed anchor.

Negation passes through the binary selector componentwise. The unary
selection, condition, and until/release dualities follow:

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

## Charging-station example

Consider one charging station with two charging points. Let

$$
j_1,j_2:\mathbb I\to\mathbb N_0
$$

be their job-allocation signals, where $0$ means *no job* and every positive
number is a job ID. Time is implicit in an atomic equality:

$$
\llbracket j_1=0\rrbracket_a
=\{t\in\mathbb I\mid j_1(t)=0\}.
$$

Thus $t\models j_1=0$ says exactly that charging point 1 is unallocated at
time $t$. For example,

$$
\begin{aligned}
\langle j_1=0\rangle_I
&\quad\text{requires point 1 to be free inside }I
\text{ and is true outside }I,\\
\langle j_1=0\rangle_I^*
&\quad\text{selects the times in }I\text{ when point 1 is free},\\
\lozenge_I(j_1=0)
&\quad\text{means point 1 is free sometime during }I,\\
(j_1\neq0)\mathbin{\mathsf U_I}(j_1=0)
&\quad\text{means point 1 remains occupied within }I
\text{ until it becomes free there},\\
\square_I((j_1=0)\land(j_2=0))
&\quad\text{means both points are free throughout }I,\\
\square_I\bigl((j_1\neq j_2)\lor((j_1=0)\land(j_2=0))\bigr)
&\quad\text{forbids assigning the same nonzero job to both points during }I.
\end{aligned}
$$

The first formula is deliberately a mask. The global assertion that point 1
is free throughout $I$ is $\square_I(j_1=0)$.
