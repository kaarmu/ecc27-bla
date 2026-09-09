# Contract protocol v2

## Inputs

Let $C^{\mathrm{cmt}}=\langle\top\mid K\rangle$ be the existing commitment,
$k$ the requested job, $d>0$ its duration, and $h\geq0$ the start horizon. Set

$$
\begin{aligned}
I&:=\left\{\frac{n}{10}:n=1,\ldots,\lfloor10h\rfloor\right\},\\
J_s&:=[s,s+d),\qquad s\in I,\\
E&:=\bigcup_{s\in I}J_s=I\oplus[0,d),\\
p_k&:=(\textit{job}=k).
\end{aligned}
$$

Evaluate at anchor $0$, with represented time containing $E$ and the
commitment intervals. Duration windows and the envelope are half-open, as in
the notebook implementation. The horizon bounds starts, not completion times.

The flexible request is

$$
\boxed{
C^{\mathrm{req}}
=\left\langle
\top\;\middle|\;
\lozenge_{I}\square_{d)}p_k
\right\rangle.
}
$$

If $I=\varnothing$, return $\mathcal O=\varnothing$.


## 1. Project to the requested job

Apply the scheduler projection

$$
\pi_k(\psi)=
\begin{cases}
p,&\psi\equiv(n=k),\\
\neg p,&\psi\equiv(n\neq k),\\
\psi,&\text{otherwise},
\end{cases}
\qquad
\bar C^{\mathrm{cmt}}
:=\pi_k(C^{\mathrm{cmt}})
=\langle\top\mid\bar K\rangle.
$$

This forgets the identity of other jobs; it is not a generic logical
equivalence. Let $U$ be the union of intervals unavailable to job $k$.
For the notebook's explicit reservations, $\bar K=\square_U\neg p$.

## 2. Strengthen and probe

Replace the choice of one admissible start by all admissible starts:

$$
\begin{aligned}
\widehat C^{\mathrm{req}}
&:=\left\langle
\top\;\middle|\;
\bigwedge_{s\in I}\lozenge_{[s,s]}\square_{d)}p
\right\rangle
\equiv\langle\top\mid\square_Ep\rangle,\\
C^{\mathrm{cand}}
&:=\bar C^{\mathrm{cmt}}\bullet\widehat C^{\mathrm{req}}
=\langle\top\mid\bar K\land\square_Ep\rangle.
\end{aligned}
$$

Test consistency. For explicit occupied intervals,

$$
C^{\mathrm{cand}}\text{ consistent}
\quad\Longleftrightarrow\quad
E\cap U=\varnothing.
$$

On success, set $J:=E$ and proceed to Step 4. On failure, repair the
availability in Step 3. General commitments require a scheduler satisfiability
check; the notebook supplies the interval-intersection check above.

## 3. Repair availability

Weaken the strengthened envelope, separate from the existing commitment,
then merge back:

$$
\begin{aligned}
C^w&:=\langle\top\mid\lozenge_Ep\rangle,\\
C^s&:=C^w\div\bar C^{\mathrm{cmt}},\\
C^{ms}&:=C^s\bullet\bar C^{\mathrm{cmt}}.
\end{aligned}
$$

For $C^{ms}=\langle A^{ms}\mid G^{ms}\rangle$, postprocess

$$
C^{\mathrm{post}}
:=\langle\top\mid G^{ms}\land A^{ms}\rangle,
$$

apply $\pi_k$, and simplify overlaps using

$$
\square_B\neg p\land\lozenge_Dp
\equiv
\square_B\neg p\land\lozenge_{D\setminus B}p.
$$

The scheduler then extracts the surviving availability:

$$
\boxed{
J:=E\setminus U,
\qquad
C^{\mathrm{avail}}:=\langle\top\mid\lozenge_Jp\rangle.
}
$$

This extraction retains availability for offer generation. It is not a
logical equivalence that discards the existing commitment.

## 4. Concretize offers

Enumerate the original start grid and retain full duration windows:

$$
\boxed{
\mathcal O
:=\left\{
\left\langle\top\mid\square_{J_s}(j=k)\right\rangle
:s\in I,\quad J_s=[s,s+d),\quad J_s\subseteq J
\right\}.
}
$$

On probe success, every $s\in I$ yields an offer. After repair, retain only
windows wholly contained in the surviving availability; do not shorten or
shift them off the grid. If no window survives, return $\mathcal O=\varnothing$.

Offers are alternatives, each refining the original request. A nonempty
$J$ alone does not guarantee an offer of duration $d$.
