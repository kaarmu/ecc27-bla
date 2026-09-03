# Interval-logic implementation contract

This document specifies the public Python model and interfaces that implement
[`LOGIC.md`](LOGIC.md). Authority flows in one direction:

```text
LOGIC.md -> CODE.md -> Python implementation
```

The implementation may optimize these interfaces internally, but it must not
change their mathematical meaning. Unsupported computations must fail
explicitly; they must never be assigned a different semantics for convenience.

## Common value and time types

The implementation uses `portion.Interval` for represented subsets of time.
The public aliases are:

```python
NaturalValue = int
TimeValue = Real
TimeSet = portion.Interval
```

`NaturalValue` values reject booleans and negative integers. Scalar times and
durations reject booleans, non-real values, infinities, NaN, and negative
values. Evaluation universes may be disconnected but must be contained in
$\mathbb R_{\geq0}$. `TimeSet` values may use an infinite endpoint to
represent an unbounded subset. Absolute temporal intervals must additionally
be connected.

Temporal parameters have explicit runtime types:

```python
@dataclass(frozen=True, slots=True)
class RelativeParameter:
    duration: float
    include_endpoint: bool = False

@dataclass(frozen=True, slots=True)
class AbsoluteParameter:
    interval: TimeSet

TemporalParameter = RelativeParameter | AbsoluteParameter | None
TemporalParameterInput = TemporalParameter | Real | TimeSet | str
```

`None` means genuine omission. Numeric inputs and bare numeric strings become
half-open `RelativeParameter` values. A string ending in `]` is closed and one
ending in `)` is half-open. Interval objects and interval strings become
`AbsoluteParameter` values. Formatting emits bare numbers for half-open
relative parameters, a trailing `]` for closed relative parameters, and no
suffix for omission.

The public helpers are:

```python
coerce_temporal_parameter(value: TemporalParameterInput | None) -> TemporalParameter
format_temporal_parameter(parameter: TemporalParameter) -> str
temporal_window(parameter: TemporalParameter, anchor: TimeValue, universe: TimeSet) -> TimeSet
```

`temporal_window()` implements the single represented temporal window
`W_rho(a)`. Relative, absolute, and omitted windows are future-directed and
clipped to the evaluation universe. In particular, an absolute parameter
resolves to `interval & [anchor, +inf) & universe`. Selection, until,
eventually, always, release, and weak until all use this helper.

## Formula and term model

All syntax nodes are immutable, hashable value objects. `Formula` and
`NumericTerm` are abstract bases with no Python truth value. Calling `bool()`
on either raises `TypeError`.

The canonical numeric-term classes are:

```python
class NumericTerm: ...

@dataclass(frozen=True, slots=True)
class NaturalLiteral(NumericTerm):
    value: NaturalValue

@dataclass(frozen=True, slots=True)
class Signal(NumericTerm):
    name: str
```

The canonical formula classes are:

```python
class Formula: ...

@dataclass(frozen=True, slots=True)
class Boolean(Formula):
    value: bool

@dataclass(frozen=True, slots=True)
class Proposition(Formula):
    name: str

@dataclass(frozen=True, slots=True)
class Equal(Formula):
    left: NumericTerm
    right: NumericTerm

@dataclass(frozen=True, slots=True)
class Not(Formula):
    operand: Formula

@dataclass(frozen=True, slots=True)
class And(Formula):
    operands: tuple[Formula, ...]

@dataclass(frozen=True, slots=True)
class Or(Formula):
    operands: tuple[Formula, ...]

@dataclass(frozen=True, slots=True)
class Implies(Formula):
    left: Formula
    right: Formula

@dataclass(frozen=True, slots=True)
class Equivalent(Formula):
    left: Formula
    right: Formula
```

Temporal nodes retain the user-facing derived forms so parsing and formatting
are lossless:

```python
@dataclass(frozen=True, slots=True)
class Selection(Formula):
    inside: Formula
    outside: Formula
    parameter: TemporalParameter = None

@dataclass(frozen=True, slots=True)
class VacuousSelection(Formula):
    body: Formula
    parameter: TemporalParameter = None

@dataclass(frozen=True, slots=True)
class RestrictiveSelection(Formula):
    body: Formula
    parameter: TemporalParameter = None

@dataclass(frozen=True, slots=True)
class Until(Formula):
    left: Formula
    right: Formula
    parameter: TemporalParameter = None

@dataclass(frozen=True, slots=True)
class Eventually(Formula):
    body: Formula
    parameter: TemporalParameter = None

@dataclass(frozen=True, slots=True)
class Always(Formula):
    body: Formula
    parameter: TemporalParameter = None

@dataclass(frozen=True, slots=True)
class Release(Formula):
    left: Formula
    right: Formula
    parameter: TemporalParameter = None

@dataclass(frozen=True, slots=True)
class WeakUntil(Formula):
    left: Formula
    right: Formula
    parameter: TemporalParameter = None
```

Operand arguments precede the optional temporal parameter in every
constructor. This mirrors formula syntax and prevents parameter values from
being confused with operands. Temporal-node constructors accept any
`TemporalParameterInput` and store its canonical `TemporalParameter` value.
The dataclass declarations above describe normalized stored fields. Public
constructors accept `Formula | str | bool` for formula-valued arguments,
`NumericTerm | int` for term-valued arguments, and iterables of formula inputs
for `And` and `Or`; construction immediately coerces them to the declared
stored types.

`Formula` supplies immutable convenience constructors and Boolean operators:

```python
~formula
formula & other
formula | other
formula.implies(other)
formula.equivalent(other)
formula.select(outside=True, parameter=None)
formula.select_vacuously(parameter=None)
formula.select_restrictively(parameter=None)
formula.until(other, parameter=None)
formula.eventually(parameter=None)
formula.always(parameter=None)
formula.release(other, parameter=None)
formula.weak_until(other, parameter=None)
formula.replace(*functions)
formula.simplify()
```

`NumericTerm.equals()` and `NumericTerm.not_equals()` construct equality and
inequality formulas for any pair of numeric terms.
`as_formula()` accepts a `Formula`, bool, or formula string. `as_term()` accepts
a `NumericTerm` or natural integer. Names must be nonempty strings.

The following semantic identities are mandatory regardless of retained node
types:

```text
VacuousSelection(body, rho)     ≡ Selection(body, true, rho)
RestrictiveSelection(body, rho) ≡ Selection(body, false, rho)
Eventually(body, rho)           ≡ Until(true, body, rho)
Always(body, rho)               ≡ not Eventually(not body, rho)
Release(left, right, rho)        ≡ not Until(not left, not right, rho)
```

Here `≡` means equal denotation and satisfaction, not structural Python
equality. Retained derived nodes remain distinct immutable values;
`expand_derived()` is the operation that lowers them to the corresponding
basis formulas.

`WeakUntil` remains an optional primitive with the direct horizon semantics in
`LOGIC.md`; it is not rewritten as `Until | Always` for absolute intervals.

## Parsing, formatting, rewriting, and traversal

The canonical public functions are:

```python
parse_formula(source: str) -> Formula
format_formula(formula: Formula | str, *, unicode: bool = True) -> str
format_term(term: NumericTerm | int, *, unicode: bool = True) -> str
replace(formula: Formula | str, *functions: Callable[[Formula], Formula | str]) -> Formula
simplify(formula: Formula | str) -> Formula
expand_derived(formula: Formula | str) -> Formula
to_nnf(formula: Formula | str) -> Formula
```

The parser accepts the Unicode notation in `LOGIC.md` and these ASCII words:
`true`, `false`, `not`, `and`, `or`, `implies`, `equivalent`, `select`,
`eventually`, `always`, `until`, `weak_until`, and `release`. It accepts `!`,
`&`, `|`, `->`, and `<->` as Boolean aliases. Temporal suffixes follow an
underscore, for example `always_5] p`, `eventually_[3,8) p`, or `p until q`
when the parameter is omitted. Canonical Unicode formatting uses `⊤`, `⊥`,
`¬`, `∧`, `∨`, angle selections, `◇`, `□`, `U`, `W`, and `R` as in
`LOGIC.md`; ASCII formatting uses the words above.

`simplify()` is semantics-preserving. It may normalize commutative Boolean
operands, apply constants, complements, idempotence, absorption, double
negation, reflexive equality, and componentwise selection negation. It must
not treat a selection as a condition or replace weak until by an invalid
absolute-window identity.

`expand_derived()` recursively lowers every form that `LOGIC.md` defines as an
abbreviation: `false`, disjunction, implication, equivalence, unary
selections, eventually, always, and release. Its output contains only
`Boolean(True)`, atoms, `Not`, `And`, `Selection`, `Until`, and the optional
direct `WeakUntil` extension. `to_nnf()` uses Boolean and temporal dualities
to place negation at atoms where the available dual is defined; a negated
`WeakUntil` may remain opaque.

Every formula exposes:

```python
children: tuple[Formula, ...]
depth: int
node_count: int
```

`replace()` is deterministic, immutable, bottom-up, and applies its functions
in argument order.

## Complete-trajectory trace model and denotation

A complete known trajectory `w` is represented by `Trace`:

```python
@dataclass(frozen=True, slots=True)
class NaturalSignal:
    regions: Mapping[NaturalValue, TimeSet]
    default: NaturalValue | None = None

@dataclass(frozen=True, slots=True)
class Trace:
    universe: TimeSet
    propositions: Mapping[str, TimeSet] = field(default_factory=dict)
    signals: Mapping[str, NaturalSignal] = field(default_factory=dict)
```

Signal regions must be pairwise disjoint. A default value is required if the
explicit regions do not cover the trace universe. Missing propositions are
false. A referenced but missing signal is an error.

The canonical trace APIs are:

```python
denote(formula: Formula | str, trace: Trace, anchor: TimeValue) -> TimeSet
satisfies(formula: Formula | str, trace: Trace, at: TimeValue) -> bool
satisfying_times(formula: Formula | str, trace: Trace) -> TimeSet
```

`satisfies()` implements the fundamental relation `(w, at) satisfies formula`.
`satisfying_times()` returns `Sat_w(formula)`, re-anchoring every temporal
operand at each inspected time. `denote()` returns the additional anchored
denotation `[[formula]]_(w, anchor)`, which preserves a selector's complete
time mask. The diagonal agreement
`satisfies(formula, trace, t) == (t in denote(formula, trace, t))` is a required
consequence, not the definition of local satisfaction.

Every result is clipped to the trace universe. The `anchor` passed to
`denote()` and the `at` time passed to `satisfies()` must belong to
`trace.universe`; asking for local truth outside the represented trace raises
`TraceValidationError`.

The trace evaluator implements every node in the formula model, including
selection masks, strong until, derived eventually/always/release, and direct
weak until. Conditions return either the full universe or the empty set for a
fixed anchor. Exact zero-duration behavior must match the table in
`LOGIC.md`.

## Reachability interfaces

The semantic system in `LOGIC.md` is
`S = (X_adm, Xi, V)`: `Xi` is a family of physical-time trajectories and `V`
is the atomic valuation. The Python object below is a computational backend
bound to one such system; it is not itself the definition of trajectory
satisfaction. This distinction is reflected in its name.

Reachability operates on multidimensional symbolic sets. It does not use
`TimeSet` as a substitute for `StateSet`.

```python
class StateSet(Protocol):
    def intersection(self, other: StateSet) -> StateSet: ...
    def union(self, other: StateSet) -> StateSet: ...
    def complement(self) -> StateSet: ...
    def difference(self, other: StateSet) -> StateSet: ...
    def is_empty(self) -> bool: ...
    def is_subset(self, other: StateSet) -> bool: ...
    def normalize(self) -> StateSet: ...

@dataclass(frozen=True, slots=True)
class ReachResult:
    tlt_set: StateSet
    certified: bool
```

All `StateSet` complements are relative to the backend's `admissible_states`,
which denotes $X_{\mathrm{adm}}$. Implementations may use one-dimensional
intervals for coordinate domains, but unions must preserve correlations and
invariants must support relations such as uniqueness of nonzero signal values.

`ReachResult.tlt_set` denotes the computed set
`widehat(Sat)_S^exists(formula, anchor)`. It must not be named or documented as
though it were automatically the true existential satisfaction set.
`certified` is true exactly when the computation establishes
`tlt_set == Sat_S^exists(formula, anchor)`. A false value means that equality
was not established; it does not assert that the two sets are unequal or
imply an under- or over-approximation direction.

The canonical reachability names map directly to `LOGIC.md`:

| Logical object | Python interface |
| --- | --- |
| $X_{\mathrm{adm}}$ | `backend.admissible_states` |
| $V(\alpha)$ | `backend.atom(alpha)` |
| $\mathcal R_{\rho,a}(B;A)$ | `backend.constrained_reach(B, A, parameter, anchor)` |
| $\mathcal I_{\rho,a}(A)$ | `backend.existential_invariance(A, parameter, anchor)` |
| $\widehat{\operatorname{Sat}}_{\mathcal S}^{\exists}(\varphi,a)$ | `reach(...).tlt_set` |
| Equality with $\operatorname{Sat}_{\mathcal S}^{\exists}(\varphi,a)$ established | `reach(...).certified` |

The backend primitives corresponding to the trajectory definitions are:

```python
class ReachabilityBackend(Protocol):
    @property
    def admissible_states(self) -> StateSet: ...

    def atom(self, atom: Proposition | Equal) -> StateSet: ...

    def constrained_reach(
        self,
        target: StateSet,
        constraint: StateSet,
        parameter: TemporalParameter,
        anchor: TimeValue,
    ) -> StateSet: ...

    def existential_invariance(
        self,
        safe: StateSet,
        parameter: TemporalParameter,
        anchor: TimeValue,
    ) -> StateSet: ...

    def certify_conjunction(
        self,
        formula: And,
        operands: tuple[ReachResult, ...],
        anchor: TimeValue,
    ) -> bool: ...
```

The public computation is:

```python
reach(
    formula: Formula | str,
    backend: ReachabilityBackend,
    anchor: TimeValue,
) -> ReachResult
```

The backend is responsible for ensuring that `admissible_states`, `atom()`,
`constrained_reach()`, and `existential_invariance()` use one consistent
`(X_adm, Xi, V)`. Primitive calls that the backend accepts are exact for that
system. A primitive that cannot preserve the requested physical-time
semantics raises `UnsupportedTemporalParameterError`; another unsupported
reachability computation raises `UnsupportedReachabilityError`. A separate
`supports(parameter)` query is not part of the contract because support may
differ between constrained reachability and existential invariance even for
the same parameter.

Before backend propagation, `reach()` applies the exact local-selection and
zero-duration laws from `LOGIC.md`, then converts the remaining formula to the
supported negation-normal form. This ordering reduces every `0]` and `0)` case
without asking an untimed backend to interpret elapsed time. In particular,
zero-duration `Release` and `WeakUntil` formulas are reduced before the
generic unsupported-node check.

Negation may be complemented only at state-level leaves; it must not
complement an existential temporal result as though it were another
existential result. After the exact reductions, the initial generic
propagation supports atoms, Boolean conjunction/disjunction, locally reducible
selections, until, eventually, and always. Remaining release, weak-until, or
negated temporal nodes raise `UnsupportedReachabilityError`.

For this contract, a state predicate is a temporal-free Boolean combination
of proposition and equality atoms, after applying any selector reduction that
is independent of future time. It denotes one fixed `StateSet`. A formula
whose truth depends on a future witness, a future prefix, or an absolute-time
branch is not a state predicate merely because a recursive call has produced
a `StateSet` for it.

Disjunction unions computed results. Conjunction intersects them, but the
intersection is certified only when all operand results are certified and the
conjunction is state-local, or when `certify_conjunction()` establishes a
common-trajectory argument. Temporal primitives are directly certified for
state-predicate operands. If an operand already denotes a temporal goal, a
recursive TLT computation may still produce a set, but it remains uncertified
unless the backend establishes the missing common-trajectory argument. The
generic interface supplies no such temporal-composition certificate, so it
must conservatively return `certified=False` in that case.

For a queried initial set `initial_states`, semantic existential reachability
holds exactly when

$$
\texttt{initial\_states}
\cap\operatorname{Sat}_{\mathcal S}^{\exists}(\varphi,a)
\neq\varnothing.
$$

The same check on `ReachResult.tlt_set` establishes true existential
reachability only when `ReachResult.certified` is true. An uncertified
intersection is a TLT computation result, not proof that one common
trajectory satisfies the formula.

### Selection during reachability propagation

A selector has no reachability primitive. At the anchor where its local truth
is requested, propagation chooses one operand according to the laws in
`LOGIC.md`:

```text
d] with d >= 0  -> inside
d) with d > 0   -> inside
0)              -> outside
omitted          -> inside
absolute I       -> inside exactly when anchor is in I
```

This reduction is applied at the selector's own current anchor. A relative
selector therefore remains reducible when it is re-anchored beneath a
temporal condition. An absolute selector beneath a temporal condition may
choose different branches at different inspected times even though its window
is also future-directed. The generic state-set-only primitives cannot replace
it once at the outer anchor; such a formula requires a timed,
trajectory-aware backend operation or must be rejected. At top level, or
under Boolean connectives evaluated at the queried anchor, an absolute
selector is locally reducible because that anchor is known.

An untimed event backend may implement unparameterized reachability with:

```python
class EventReachabilityBackend(ReachabilityBackend, Protocol):
    def predecessor(self, states: StateSet) -> StateSet: ...
```

Its constrained reachability, backward reachability, and invariance use the
least/greatest fixed points specified in `LOGIC.md`. It supports omitted
parameters and syntactically reducible zero-duration cases. Positive durations
and absolute temporal conditions raise `UnsupportedTemporalParameterError`.
The first backend returns only exactly converged fixed points; failure to
establish exact convergence is an unsupported computation, not a certified
widened result.
An absolute selector at a known current anchor remains reducible without a
time model, but an absolute selector inspected at future positions does not.
A timed backend must retain physical-time durations and use the same resolved
temporal windows as trace checking. Transition counts and minimum dwell-time
bounds are not substitutes for physical time unless the represented state
contains the clocks or residual timing needed to make them exact.

## Errors and package exports

The public exception hierarchy is:

```python
class IntervalLogicError(Exception): ...
class FormulaSyntaxError(IntervalLogicError, ValueError): ...
class TraceValidationError(IntervalLogicError, ValueError): ...
class UnsupportedReachabilityError(IntervalLogicError, NotImplementedError): ...
class UnsupportedTemporalParameterError(UnsupportedReachabilityError): ...
```

The package root exports every public type and function named in this
document. It does not export internal parser tokens, evaluator contexts,
normalization helpers, or backend implementation details.

## Verification requirements

The test suite must cover:

- construction, validation, hashing, traversal, parsing, and formatting of
  every syntax node;
- half-open defaults, closed endpoints, absolute intervals, omission, and
  the single future-directed `temporal_window()` resolution;
- the fundamental local satisfaction relation and its diagonal agreement with
  anchored denotation;
- complete `expand_derived()` lowering to the minimal grammar, apart from the
  optional direct `WeakUntil` extension;
- exact atom and Boolean trace denotation;
- re-anchored selection, until, eventually, always, release, weak until, and
  every zero-duration law;
- the common future restriction of absolute selection and absolute
  conditions;
- distinct `TimeSet` and multidimensional `StateSet` output domains;
- the `ReachabilityBackend`/semantic-system distinction and the
  `ReachResult.tlt_set`/true-satisfaction-set distinction;
- existential initial-set checks, exact primitive fixed points, unsupported
  quantitative rejection, and every local selector reduction;
- reachability reduction of all `0]` and `0)` laws before unsupported temporal
  operators are rejected;
- rejection of future-position absolute selection by a backend without the
  required timed trajectory operation;
- certified state-local conjunction and uncertified leaking temporal
  conjunction;
- public exports and the absence of legacy names from canonical examples.
