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
from numbers import Real

NaturalValue = int
TimeValue = Real
TimeSet = portion.Interval
```

`NaturalValue` values reject booleans and negative integers. Scalar times and
durations reject booleans, non-real values, infinities, NaN, and negative
values. Evaluation universes may be disconnected but must be contained in
$\mathbb R_{\geq0}$. `TimeSet` values may use an infinite endpoint to
represent an unbounded subset. Absolute temporal intervals must additionally
be connected; empty intervals are allowed. Infinity is only a boundary, never
a represented time, so infinite endpoints must be open.

The finite interval-union representation and region-based signals below are
interface design choices; `LOGIC.md` does not restrict mathematical trajectories
or universes to those representable by `portion.Interval`. Inputs and outputs
must be exact, without silent sampling or rounding. Unsupported exact trace
computations raise `UnsupportedTraceError`. Empty universes are allowed:
`satisfying_times()` returns empty, while no local/anchored query has a valid
anchor.

Temporal parameters have explicit runtime types:

```python
@dataclass(frozen=True, slots=True)
class RelativeParameter:
    duration: TimeValue
    include_endpoint: bool = False

@dataclass(frozen=True, slots=True)
class AbsoluteParameter:
    interval: TimeSet

TemporalParameter = RelativeParameter | AbsoluteParameter | None
TemporalParameterInput = TemporalParameter | Real | TimeSet | str
```

`None` represents omitted syntax, not an additional logical parameter. Numeric
inputs and bare numeric strings become half-open `RelativeParameter` values.
A duration string ending in `]` is closed and one ending in `)` is half-open.
Interval objects and interval strings become `AbsoluteParameter` values;
two-bound interval syntax takes precedence over duration-suffix parsing. Formatting emits bare numbers for half-open
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
eventually, always, and release all use this helper. The helper requires an
anchor in the universe. Constructors validate natural values, Boolean fields,
and temporal bounds. As error-design choices, invalid standalone values raise
`ValueError`, inappropriate Python types raise `TypeError`, and trace and
reachability entry points use their domain-specific validation errors.
`format_temporal_parameter(None)` returns an empty string.

There is no weak-until node or prefix-horizon helper in this contract:
`LOGIC.md` §“Formulas and temporal basis” defines neither weak until nor
`H_rho(a)`. An extension requires an upstream definition.

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

Temporal nodes retain user-facing derived forms. Parsing and formatting preserve
canonical nodes and parameters, not original whitespace, aliases, or the
spelling distinction between bare durations and explicit `d)`:

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
formula.select_vac(parameter=None)
formula.select_res(parameter=None)
formula.until(other, parameter=None)
formula.eventually(parameter=None)
formula.always(parameter=None)
formula.release(other, parameter=None)
formula.replace(*functions)
formula.simplify(anchor=None, universe=None)
```

`NumericTerm.equals()` and `NumericTerm.not_equals()` construct equality and
inequality formulas for any pair of numeric terms.
`as_formula()` accepts a `Formula`, bool, or formula string. `as_term()` accepts
a `NumericTerm` or natural integer. `not_equals()` returns `Not(Equal(...))`,
as required by §“Signals and atoms”. Python equality and hashing compare syntax
values; `equals()` constructs logical equality. Names must be nonempty strings.

As interface choices, empty `And` is true, empty `Or` is false, and singleton
nodes have their operand's semantics. Variadic nodes represent the iterated
Boolean operations from §“Formulas and temporal basis”.

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

## Parsing, formatting, rewriting, and traversal

The canonical public functions are:

```python
parse_formula(source: str) -> Formula
format_formula(formula: Formula | str, *, unicode: bool = True) -> str
format_term(term: NumericTerm | int, *, unicode: bool = True) -> str
format_latex(formula: Formula | str | bool) -> str
format_term_latex(term: NumericTerm | int) -> str
replace(formula: Formula | str, *functions: Callable[[Formula], Formula | str]) -> Formula
simplify(formula: Formula | str, *, anchor: TimeValue | None = None,
         universe: TimeSet | None = None) -> Formula
expand_derived(formula: Formula | str) -> Formula
to_nnf(formula: Formula | str) -> Formula
```

`Formula` and `NumericTerm` implement `_repr_latex_()` for native notebook
math display, without requiring IPython at runtime. `format_latex` and
`format_term_latex` return LaTeX without dollar delimiters for embedding in
Markdown (for example, `"$" + format_latex(formula) + "$"`). Rendering preserves
operator precedence, exact rational bounds, interval endpoint inclusion and
omitted parameters; relative durations explicitly show `d)` or `d]`. Names are
escaped as literal identifiers. LaTeX is a display format, not parser input;
`str`, `repr` and Unicode/ASCII formatting retain their existing behavior.

The parser accepts the Unicode notation in `LOGIC.md` and these ASCII words:
`true`, `false`, `not`, `and`, `or`, `implies`, `equivalent`, `select`,
`eventually`, `always`, `until`, and `release`. It accepts `!`,
`&`, `|`, `->`, and `<->` as Boolean aliases. Temporal suffixes follow an
underscore, for example `always_5] p`, `eventually_[3,8) p`, or `p until q`
when the parameter is omitted. Canonical Unicode formatting uses `⊤`, `⊥`,
`¬`, `∧`, `∨`, angle selections, `◇`, `□`, `U`, and `R` as in
`LOGIC.md`; ASCII formatting uses the words above. Both modes support `=` and
inequality (`!=` or `≠`), binary selection, both unary selections including `*`,
and all parameters on all temporal constructs. As an ASCII interface choice,
selection is `select(p, q)_rho`, `select(p)_rho`, or `select(p)_rho*`, with
suffix omitted for omission. Formatting parenthesizes compound operands to
preserve scope. Names outside the unquoted identifier grammar, including
reserved words, use JSON-style double-quoted names; context distinguishes
propositions from signal terms. These quoting conventions are design choices.
Canonical formatting round-trips syntax up to normalization of empty,
singleton, and grouped variadic Boolean nodes, while retaining derived temporal
forms. Inequality is represented by `Not(Equal(...))`; these normalizations
preserve both local truth and anchored masks.

`simplify()` preserves both local satisfaction and anchored mask denotation
within the supplied temporal context. `Formula.simplify()` accepts the same
keyword-only arguments. An omitted `universe` (including `None`) defaults to
`[0, +inf)`; an omitted `anchor` (including `None`) remains unknown:

| Context supplied | Required scope of equivalence |
| --- | --- |
| Neither | Every anchor in the full nonnegative universe `[0, +inf)`; no particular anchor is assumed. |
| `anchor` only | That anchor, with the full nonnegative universe `[0, +inf)`. |
| `universe` only | Every represented anchor in that universe; no default anchor is chosen. |
| Both | That anchor and that exact universe. |

Times and finite universe endpoints use the existing exact rational validation.
Invalid argument types raise `TypeError`; invalid values, negative/nonfinite
anchors, or anchors outside the universe raise `ValueError`. Disconnected
universes are allowed, and an empty universe is allowed without an anchor.
The result is an ordinary formula, without attached context: retain the original
formula when queries may use different anchors or universes.

The simplifier normalizes commutative Boolean operands and applies constants,
complements, idempotence, absorption, double negation, reflexive equality,
incompatible literal assignments to the same signal, and componentwise selection
negation. It also uses provable temporal-window emptiness and nonemptiness:
empty windows make always/release true and eventually/until false;
`Always(True)` and `Eventually(False)` simplify unconditionally;
`Always(False)` and `Eventually(True)` simplify when the window is known nonempty.

Conjoined `Always` conditions become false when their windows provably share a
represented time and their bodies are syntactically contradictory. This includes
complementary bodies, Boolean contradictions, and incompatible signal-literal
assignments. Conditions with identical bodies can be removed when their window
is contained in another conjunct's window, and conjoined absolute windows over
one body rejoin into the single condition `always_(A | B) body` whenever that
union is connected. These rules are repeated with Boolean simplification until
stable. They do not decide arbitrary satisfiability or
extract availability from arbitrary formulas. An unreduced formula is not
evidence of consistency.

For example, `always_[1,5) p and always_[1.5,3) not p` simplifies to false
with `anchor=0`, but not with neither argument or just `universe=[0,5]`.
At anchor 3 the second conjunct expires; at anchor 5 both expire. If the supplied
universe excludes `[1.5,3)`, it contains no conflicting times.
By contrast, `eventually_[1,+inf) true` simplifies to true even without arguments:
its window is nonempty at every anchor in the default full-time universe. With
the explicit universe `{0}`, it simplifies to false instead. Always pass the
actual universe when specializing a formula for a finite or disconnected trace.

Three region rewrites relate a temporal parameter to the region an operand
actually constrains. Both preserve local truth and anchored masks, because a
temporal condition is globally valued at its anchor.

**Duration coverage.** Requiring a relative window at every start of an absolute
window requires the body throughout the union of those windows:

```text
always_I always_d body  ->  always_(I + [0,d)) body
```

The Minkowski sum uses the outer window `W_I(a)`, so this rewrite requires a
known anchor; starts outside the represented universe or before the anchor
impose nothing. A half-open `d)` always yields an open upper bound, `d]` keeps
the start component's bound, and an unbounded start component is unchanged.
The outer parameter must be absolute and the inner one relative.

**Blocked existential pruning.** A conjoined universal condition removes the
times at which an existential witness is impossible:

```text
always_R psi and eventually_E phi  ->  always_R psi and eventually_(E \ R) phi
```

The rewrite applies when `psi and phi` is syntactically contradictory under the
same re-anchored test used for conjoined coverage. Both parameters must be
absolute; it needs no anchor, since a witness in `W_E(a)` lies outside `R`
exactly when it lies outside `W_R(a)`.

Blockers are the conjunction's own `Always` operands, and they prune every
`Eventually` reachable through nested conjunction and disjunction, so a grouped
disjunction of start windows loses the blocked times alternative by alternative.
Only that monotone Boolean structure is entered: never a negation, a selection,
or a temporal operand, whose occurrences are inspected at other anchors. The
rewrite does not apply to `Until`.

**Blocked duration-start pruning.** A positive half-open duration request loses
starts whose duration window would overlap a contradictory reservation:

```text
always_R psi and eventually_J always_d phi
    -> always_R psi and eventually_(J_effective \ (R_effective + (-d,0])) always_d phi
```

Here `d` is a positive half-open relative parameter, both `R` and `J` are
absolute parameters, and `psi and phi` must be syntactically contradictory under
the same re-anchored body test. `R_effective` and `J_effective` are their windows
at the supplied anchor. The reservation stays conjoined: pruning cannot make
the resulting request forget existing obligations. Further Boolean reduction
may make a completely blocked conjunction false.

This rewrite requires a known anchor and the full nonnegative universe
`[0,+inf)`. It does not apply to closed or zero durations, finite or disconnected
universes, an unknown anchor, or unsupported nested temporal shapes. Those
contexts retain the original duration request. The full-universe restriction
matters because a gap in represented time can remove a conflict that the
ordinary Minkowski sum would otherwise predict. For a blocker `[b,e)`, forbidden
starts are `(b-d,e)`: a booking ending exactly at `b` or starting exactly at `e`
remains allowed. Other endpoint types retain their exact interval arithmetic.
Different values of one signal contradict; equal assignments and assignments
to different signals do not block one another.

As with direct existential pruning, blockers are retained across monotone
conjunction and disjunction, and the rewrite does not enter negation, selection
or another temporal operand. This is a sound formula rewrite, not a new
general satisfiability API. The sibling `protocol` package separately validates
and decides its restricted fixed-access-plus-one-duration-request fragment;
unreduced formulas outside that fragment are explicitly unsupported.

None of these rewrites introduces a disconnected temporal parameter. A disconnected
result is spelled as the grouping `LOGIC.md` allows for a single parameter: a
conjunction of universal conditions, or a disjunction of existential ones, over
the region's connected components. An empty region gives that connective's
identity, so a fully blocked existential becomes false.

Known context propagates through Boolean operators. Inside temporal operands and
selection branches, the outer anchor is discarded, while known universe
information is retained. These operands may be inspected at other times. With
unknown anchor, the simplifier uses only facts valid at every represented
anchor. The supplied or default universe determines which future points are
represented. Outside the region rewrites above, original temporal parameters
are retained unless their operator is removed. Disconnected temporal parameters
are never introduced.

The simplifier must not treat a selection as a condition. The local laws in §“Selection and
re-anchoring” and §“Zero-duration laws” are not unrestricted mask rewrites:
`Eventually(p, RelativeParameter(0, True))` has a globally valued mask and
cannot generally simplify to `p`; positive relative selection cannot generally
simplify to its inside operand. Local-only reductions belong to satisfaction
and reachability evaluation with anchor scope respected. They must not mutate
the syntax used by `denote()`. In particular, supplying an anchor does not permit
replacing a singleton temporal condition by its operand when their full masks
differ.

`expand_derived()` and `to_nnf()` preserve both observations for every universe;
they do not inherit `simplify()`'s default full-time assumption. User-directed
`replace()` has no semantic-preservation guarantee.

`expand_derived()` recursively lowers every form that `LOGIC.md` defines as an
abbreviation: `false`, disjunction, implication, equivalence, unary
selections, eventually, always, and release. Its output contains only
`Boolean(True)`, atoms, `Not`, `And`, `Selection`, and `Until`. Variadic `And`
may represent iterated binary conjunction; empty conjunction lowers to true.
`to_nnf()` uses §“Negation dualities” and Boolean dualities to leave negation
only at atoms, with constants unnegated. It may retain `Or`, unary selections,
`Eventually`, `Always`, and `Release`; NNF is not minimal-basis expansion.
In particular, reachability preprocessing retains supported `Always` nodes
rather than forcing them into negated until.

Every formula exposes:

```python
children: tuple[Formula, ...]
depth: int
node_count: int
```

`replace()` is deterministic, immutable, bottom-up, and applies its functions
in argument order. As traversal design choices, `children` lists immediate
formula operands in stored order, excluding numeric terms. Leaves (including
empty variadic nodes) have depth zero and count one; otherwise depth is one
plus maximum child depth and count is one plus the sum of child counts.
Replacements run once per visited node on rebuilt children; returned subtrees
are not revisited in the same pass.

## Complete-trajectory trace model and denotation

`Trace` represents the restriction of one complete known trajectory $\xi$ to
its evaluation universe. The physical trajectory remains defined on
$\mathbb R_{\geq0}$, as required by `LOGIC.md`; only its represented
restriction is needed for trace checking:

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
explicit regions do not cover the trace universe. Keys and defaults must be
natural values. As representation choices, all regions must be subsets of the
universe, and constructors copy mappings to prevent later caller mutation from
changing the trace. Invalid regions, overlap, incomplete coverage without a
default, or referenced missing signals raise `TraceValidationError`. Missing
propositions are false: this is a closed-world valuation convention, not a
logical law. Values outside represented time need not be materialized. These
requirements implement §“Signals and atoms” and §“Trajectories, states, and
represented time”.

The canonical trace APIs are:

```python
denote(formula: Formula | str, trace: Trace, anchor: TimeValue) -> TimeSet
satisfies(formula: Formula | str, trace: Trace, at: TimeValue) -> bool
satisfying_times(formula: Formula | str, trace: Trace) -> TimeSet
```

`satisfies()` implements the fundamental relation
$(\xi,\texttt{at})\models\varphi$. `satisfying_times()` returns
$\operatorname{Sat}_{\xi}(\varphi)$, re-anchoring every temporal operand at
each inspected time. `denote()` returns the additional anchored denotation
$\llbracket\varphi\rrbracket_{\xi,\texttt{anchor}}$, which preserves a
selector's complete time mask. The diagonal agreement
`satisfies(formula, trace, t) == (t in denote(formula, trace, t))` is a required
consequence, not the definition of local satisfaction.

In particular, anchored selection uses the operands' local truth-time sets:

```python
window = temporal_window(selection.parameter, anchor, trace.universe)
inside_times = satisfying_times(selection.inside, trace)
outside_times = satisfying_times(selection.outside, trace)
result = ((window & inside_times)
          | ((trace.universe - window) & outside_times))
```

It must not recursively combine `denote(selection.inside, trace, anchor)` and
`denote(selection.outside, trace, anchor)`. Conditions nested in either branch
are therefore re-anchored at every time whose local truth is inspected, as in
the definition of $\operatorname{Sat}_{\xi}$.

Every result is clipped to the trace universe. The `anchor` passed to
`denote()` and the `at` time passed to `satisfies()` must belong to
`trace.universe`; asking for local truth outside the represented trace raises
`TraceValidationError`.

The trace evaluator implements every node in the formula model, including
selection masks, strong until, and derived eventually/always/release. Conditions
return either the full universe or the empty set at a fixed anchor. Boolean
combinations use set operations on anchored masks; those containing selections
need not be globally valued (§“Anchored mask denotation”).

Strong until requires a right-operand witness `tau` in `temporal_window()` and
the left operand at every represented time in `[anchor, tau)`, including any
prefix before an absolute window starts. The witness need not satisfy the left
operand. Gaps in the universe impose no obligations. Each inspected operand
uses local satisfaction at that time (§“Local satisfaction”).

The exact local zero-duration laws are:

| Construct | `0]` | `0)` (also bare `0`) |
| --- | --- | --- |
| `Eventually(body)` | `body` | false |
| `Always(body)` | `body` | true |
| `Until(left, right)` | `right` | false |
| `Release(left, right)` | `right` | true |
| `Selection(inside, outside)` | `inside` | `outside` |

Any empty window makes until/eventually false and always/release true.
Omitted and positive relative selectors locally choose the inside branch;
absolute selectors choose it exactly when the inspected time is in the
absolute interval. These are local laws, not general mask simplifications
(§“Zero-duration laws” and §“Selection and re-anchoring”).

As concrete checks from §“Selection and re-anchoring”, the formulas
`always_5] select(p)_3` and `always_5] p` have identical local truth: selection
does not require three units of persistence. At an outer anchor before 3,
`always_[3,10] select(p, q)_[5,8)` requires `q` on `[3,5)`, `p` on `[5,8)`,
and `q` on `[8,10]`, each restricted to represented time.

For the mask counterexample in §“Zero-duration laws”, if the universe is
`[0,2]` and proposition `p` holds on `[0,1]`, then
`denote("eventually_0] p", trace, 0)` is `[0,2]`, whereas
`denote("p", trace, 0)` is `[0,1]`.

## Reachability interfaces

The semantic system in `LOGIC.md` is
$\Sigma=(X,\Xi,V)$: $X$ is the invariant-constrained state space, $\Xi$ is a
family of physical-time trajectories, and $V$ is the atomic valuation. The
Python object below is a computational backend bound to one such system; it is
not itself the definition of trajectory satisfaction.

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
```

All `StateSet` operations use the same backend's `state_space`, denoting $X$;
complement is relative to $X$, not a coordinate bounding box. Incompatible
state spaces raise `ReachabilityValidationError`, an interface choice.
`normalize()` preserves the represented set. Implementations may use
one-dimensional intervals for coordinate domains, but unions must preserve correlations and invariants must support
relations such as uniqueness of nonzero signal values. In §“Charging-station
example”, repeated zeros are allowed and repeated positive job IDs are
forbidden; this invariant belongs to that system's $X$, not to every trace or
state set. Equality between signals must preserve coordinate relations.

The canonical reachability names map directly to `LOGIC.md`:

| Logical object | Python interface |
| --- | --- |
| $X$ | `backend.state_space` |
| $V(\alpha)$ | `backend.atomic_states(alpha)` |
| $\mathcal R_{\rho,a}(B;A)$ | `backend.constrained_reach(B, A, parameter, anchor, universe)` |
| $\mathcal I_{\rho,a}(A)$ | `backend.existential_invariance(A, parameter, anchor, universe)` |
| $\operatorname{Sat}_{\Sigma}^{\exists}(\varphi,a)$ | `existential_satisfying_states(...)` |

`constrained_reach` is backward reachability: its result contains initial states
admitting a constrained trajectory to `target`, not states reached forward from
it (§“Reachability operators for state predicates”). The compatible existing
name is retained; the direction is part of its contract. `atomic_states()`
returns an atom's valuation set, evaluating both terms for equality; it does
not itself quantify over trajectories.

The backend primitives corresponding to the trajectory definitions are:

```python
class ReachabilityBackend(Protocol):
    @property
    def state_space(self) -> StateSet: ...

    def atomic_states(self, atom: Proposition | Equal) -> StateSet: ...

    def constrained_reach(
        self,
        target: StateSet,
        constraint: StateSet,
        parameter: TemporalParameter,
        anchor: TimeValue,
        universe: TimeSet,
    ) -> StateSet: ...

    def existential_invariance(
        self,
        safe: StateSet,
        parameter: TemporalParameter,
        anchor: TimeValue,
        universe: TimeSet,
    ) -> StateSet: ...
```

The public computation is:

```python
existential_satisfying_states(
    formula: Formula | str,
    backend: ReachabilityBackend,
    anchor: TimeValue,
    universe: TimeSet,
) -> StateSet
```

The returned set is exactly
$\operatorname{Sat}_{\Sigma}^{\exists}(\varphi,a)$. There is no separate
approximate result or alternative reachability denotation. If the generic
propagation and backend primitives cannot establish that exact set, the call
raises `UnsupportedReachabilityError`.

The evaluation universe must be a represented subset of
$\mathbb R_{\geq0}$, and the anchor must belong to it. An anchor outside the
universe raises `ReachabilityValidationError`. The same universe is passed to
every primitive involved in the query, so all trajectories use the common
$\mathbb I$ required by `LOGIC.md`.

The backend is responsible for ensuring that `state_space`, `atomic_states()`,
`constrained_reach()`, and `existential_invariance()` use one consistent
$\Sigma=(X,\Xi,V)$. Primitive calls that the backend accepts are exact for
that system and the supplied evaluation universe. A primitive that cannot
preserve the requested physical-time
semantics raises `UnsupportedTemporalParameterError`; another unsupported
reachability computation raises `UnsupportedReachabilityError`. A separate
`supports(parameter)` query is not part of the contract because support may
differ between constrained reachability and existential invariance even for
the same parameter.

Before backend propagation, `existential_satisfying_states()` validates all atoms
in the original formula, even if a subsequent reduction removes them. It then
simplifies using the actual query anchor and universe, applies the exact
local-selection and zero-duration laws from `LOGIC.md`, and converts the
remaining formula to the supported negation-normal form. Context-aware
simplification is also applied after NNF and within local reductions with their
proper anchor scope. This ordering
reduces every `0]` and `0)` case before backend support is considered. In
particular, zero-duration `Release` formulas are reduced before
the generic unsupported-node check. A provable overlapping `Always` contradiction
returns an empty state set without temporal propagation, including when the
backend would not support the original conjunction or represented-time mask.
Unresolved correlated conjunctions and unsupported temporal nesting continue
to raise unsupported errors; simplification does not delegate general solving
to pyspect.

Negation may be complemented only at state-level leaves; it must not
complement an existential temporal result as though it were another
existential result. After the exact reductions, generic propagation supports
atoms, Boolean conjunction/disjunction where the common-trajectory rules below
permit them, locally reducible selections, and until, eventually, and always
with state-predicate operands. Remaining release or temporally nested operands
raise `UnsupportedReachabilityError`. Negated temporal formulas converted by
NNF into supported conditions are accepted. This supported fragment and its
explicit rejection policy are backend design choices, not limits of the logic.

For this contract, a state predicate is a temporal-free Boolean combination
of constants, proposition atoms, and equality atoms, after applying local
reductions valid throughout the operand's evaluation scope. It denotes one
fixed `StateSet`. A formula whose truth depends on a future witness, a future prefix, or an absolute-time
branch is not a state predicate merely because a recursive call has produced
a `StateSet` for it.

§“Systems and existential state satisfaction” does not assert that $\Xi(x,a)$
is nonempty for every state. Let $D_a=\{x\in X:\Xi(x,a)\ne\varnothing\}$.
A state predicate with valuation set $A$ has existential satisfaction set
$A\cap D_a$; `true` has set $D_a$, not necessarily $X$. The existing primitive
can compute $D_a$ exactly via
`backend.existential_invariance(backend.state_space, RelativeParameter(0), anchor, universe)`:
the empty window leaves only trajectory existence. Reusing this primitive is
a design choice; if it cannot compute the set, raise an unsupported error
rather than assume $D_a=X$.

Primitive targets, constraints, and invariance operands are valuation sets
$A\subseteq X$, not existential satisfaction sets. Complement state valuations
before restriction to $D_a$. Zero-duration reductions to `true` or a state
predicate still require trajectory existence; reducing syntax does not
promise that a backend can compute the resulting set.

Disjunction is computed by exact union because existential quantification
distributes over disjunction. Conjunction is computed by exact intersection
of valuation sets followed by restriction to $D_a$ when every operand is a
state predicate. It is also exact when exactly one
operand is trajectory-dependent and every other operand is an anchor-local
state predicate: those state predicates depend only on the common initial
state. If two or more operands are trajectory-dependent, independently
intersecting their existential state sets could combine different witness
trajectories, so the generic interface raises `UnsupportedReachabilityError`.

The temporal correspondences are used only in their domain from `LOGIC.md`:
`Until(left, right, parameter)` calls `constrained_reach()` only when both
operands are state predicates; `Eventually(body, parameter)` does so only when
its body is a state predicate; and `Always(body, parameter)` calls
`existential_invariance()` only when its body is a state predicate. A recursive
call returning a `StateSet` does not turn a temporal operand into a state
predicate.

For a queried initial set `initial_states`, semantic existential reachability
holds exactly when

$$
\texttt{initial\_states}
\cap\operatorname{Sat}_{\Sigma}^{\exists}(\varphi,a)
\neq\varnothing.
$$

Accordingly, reachability succeeds when
`not initial_states.intersection(result).is_empty()` for the exact `StateSet`
returned by `existential_satisfying_states()`.

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
it once at the outer anchor. Unless an exact local simplification eliminates
the time dependence (for example, identical branches), the current protocol has no exact trajectory-aware
operation for that case and the formula is rejected. At top
level, or under Boolean connectives evaluated at the queried anchor, an
absolute selector is locally reducible because that anchor is known.

## Errors and package exports

The public exception hierarchy is:

```python
class IntervalLogicError(Exception): ...
class FormulaSyntaxError(IntervalLogicError, ValueError): ...
class TraceValidationError(IntervalLogicError, ValueError): ...
class UnsupportedTraceError(IntervalLogicError, NotImplementedError): ...
class ReachabilityValidationError(IntervalLogicError, ValueError): ...
class UnsupportedReachabilityError(IntervalLogicError, NotImplementedError): ...
class UnsupportedTemporalParameterError(UnsupportedReachabilityError): ...
```

The package root exports package-defined public types, aliases, exceptions,
and module-level functions specified here. Methods remain on their classes;
imported dependencies such as `Real`, `Mapping`, `Protocol`, and `portion`
need not be re-exported (an interface design choice). Internal parser tokens,
evaluator contexts, normalization helpers, and backend implementation details
are not exported.

## Verification requirements

The test suite must cover:

- construction, validation, hashing, traversal, parsing, and formatting of
  every syntax node;
- half-open defaults, closed endpoints, absolute intervals, omission, and
  the single future-directed `temporal_window()` resolution;
- the fundamental local satisfaction relation and its diagonal agreement with
  anchored denotation;
- complete `expand_derived()` lowering and atom-only negation in NNF; these
  transforms and `simplify()` preserve local truth and masks, including
  zero-duration conditions and positive relative selectors;
- blocked duration-start pruning against an independent interval oracle,
  including half-open adjacency, exact fits, singleton and disconnected start
  components, fully blocked requests, nonzero anchors, same-client reservations,
  and preservation in unsupported temporal contexts;
- exact atom and Boolean trace denotation;
- anchored selection through operand-local truth sets, including an operand
  containing a temporal condition, plus until, eventually, always, release,
  and every zero-duration law;
- the common future restriction of absolute selection and absolute conditions,
  positive-relative selector equivalence under conditions, and the concrete
  re-anchoring and mask-counterexample formulas above;
- distinct `TimeSet` and multidimensional `StateSet` output domains;
- the `ReachabilityBackend`/semantic-system distinction and exact
  `existential_satisfying_states()` results;
- propagation of one reachability evaluation universe through relative,
  absolute, and omitted temporal operations, including rejection of an anchor
  outside that universe;
- existential initial-set checks, unsupported exact computations, and every
  local selector reduction;
- reachability reduction of all `0]` and `0)` laws before unsupported temporal
  operators are rejected;
- rejection of future-position absolute selection with unresolved time-dependent
  branches, and acceptance when exact local simplification eliminates them;
- exact state-local and state-plus-one-temporal conjunction, and rejection of
  conjunctions with multiple independently computed temporal operands;
- empty and nonempty trajectory families: state-local results and zero-duration
  reductions account for $D_a$, while primitive operands remain valuation sets;
  existential temporal results must never be negated by complement;
- until witnesses at the anchor, excluded endpoints, left-false witnesses, and
  prefixes before absolute windows, including disconnected universes;
- empty windows from absolute intervals in the past, omitted windows, empty
  universes, and exact continuous-time evaluation without sampling;
- natural-value validation, default coverage, missing signals, signal-to-signal
  equality, quoted-name round trips, and unsupported exact trace computations;
- charging-station invariants permitting repeated zeros and rejecting repeated
  positive IDs, with multidimensional relations preserved;
- public exports and consistent canonical names throughout the contract.


## Upstream basis and remaining scope

This revision uses the following specific upstream requirements. Added
verification cases enforce the corresponding rules, not implementation history.

| Substantive change | Basis in `LOGIC.md` |
| --- | --- |
| Remove weak-until nodes, methods, notation, horizon helper, and tests | §“Formulas and temporal basis” defines strong until and derived release, but neither weak until nor `H_rho(a)`. An extension cannot claim an upstream definition that is absent. |
| Clarify omission, canonical formatting, equality sugar, and numeric validation | §“Temporal parameters” distinguishes real durations, absolute intervals, and omitted syntax; §“Signals and atoms” defines natural terms and inequality as negated equality. Coercion, quoting, traversal, and variadic Boolean conventions are interface choices. |
| Preserve masks as well as truth in general rewrites | §“Anchored mask denotation”, §“Selection and re-anchoring”, and the explicit counterexample in §“Zero-duration laws” distinguish the two observations. |
| Complete trace representation, strong-until prefix, re-anchoring, and empty-window requirements | §“Trajectories, states, and represented time”, §“Temporal windows”, §“Local satisfaction”, and §“Absolute windows”. Region storage and error behavior are design choices implementing exact represented-time semantics. |
| Distinguish atom valuation, backward reachability, and existential output; handle trajectory existence | §“Systems and existential state satisfaction” explicitly quantifies over $\Xi(x,a)$ without asserting nonemptiness. §“Reachability operators for state predicates” defines backward initial-state sets and implies the empty-window invariance computation of $D_a$. Reusing that primitive is a design choice. |
| Clarify NNF support and the scope of local selector reductions | §“Negation dualities” supplies NNF laws; §“Local satisfaction” re-anchors operands; §“Reachability operators for state predicates” requires one common trajectory. The limited exact backend fragment is a design choice. |
| Require state-space consistency and nonzero-only uniqueness | §“Systems and existential state satisfaction” makes all state-set operations relative to $X$; §“Charging-station example” explicitly permits repeated zero coordinates. |

No contradictory upstream definition was found in these clauses. The absence
of a trajectory-nonemptiness axiom is handled by the explicit existential
quantifier, without adding that axiom. Weak until remains outside this contract
pending an upstream definition; its dependent semantics are not chosen here.
Arbitrary time sets/trajectories outside the interval-region representation and
a general exact solver for all temporal formulas remain coverage limits of the
chosen interfaces, with explicit failure rather than altered semantics.
Universal trajectory quantification remains outside the first backend, as
specified in §“Systems and existential state satisfaction”.
