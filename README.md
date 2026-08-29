# Interval logic

`interval_logic` provides immutable formulas over absolute time intervals. Atom
valuations and the evaluation universe are represented by `portion.Interval`
objects. Supplied valuations and all interval operators are clipped to that
universe during evaluation, except that `Hold` conservatively rejects a start
whose complete requested horizon is not represented.

Interval operators accept either `portion.Interval` objects or interval strings.
Strings are parsed with `portion.from_string(value, float)`, so, for example,
`Exists("[1, 2)", Atom("p"))` is equivalent to
`Exists(P.closedopen(1.0, 2.0), Atom("p"))`.

```python
import portion as P

from interval_logic import Atom, Exists, ForAll, Guard, Restrict, denote, simplify

available = Atom("available")
window = P.closed(8, 10)
formula = ForAll(window, available)

truth = denote(
    formula,
    {"available": P.closed(7, 11)},
    universe=P.closed(0, 24),
)
assert truth == P.closed(0, 24)
assert simplify(formula & True) == formula
```

Restrictive windows are false outside their interval; guarded windows are
vacuously true outside it:

```python
restricted = Restrict(window, available)  # also: available.restrict(window)
guarded = Guard(window, available)        # also: available.guard(window)

assert str(restricted) == "[8,10]_(available)"
assert str(guarded) == "[8,10]^(available)"
```

`Hold(delta, formula)` requires a formula to remain true throughout the closed
interval `[t, t + delta]`, where `t` is the current time. Its bounded
existential counterpart, `Eventually(delta, formula)`, requires one true time
in that same relative window. They can also be constructed fluently or parsed
using `H^delta formula` and `F^delta formula`:

```python
from interval_logic import Eventually, Hold

stable = Hold(2, available)
assert stable == available.hold(2)
assert stable == parse_expression("H^2 available")
assert str(stable) == "H^2 available"

soon = Eventually(2, available)
assert soon == available.eventually(2)
assert soon == parse_expression("F^2 available")
```

Durations are finite, non-negative real numbers, and both zero-duration
operators are identities. `Hold` does not shorten its obligation at an
evaluation-universe boundary: it can be true at `t` only when the whole closed
window `[t, t + delta]` is represented. `Eventually` may use any represented
witness in its window.

When the expanded interval is represented, the absolute/relative identities
are
`ForAll(I, Hold(delta, phi)) == ForAll(I + [0,delta], phi)` and
`Exists(I, Eventually(delta, phi)) == Exists(I + [0,delta], phi)`. The
simplifier applies these contextual rewrites when an explicit universe proves
them safe. The familiar Boolean duality between `Hold` and `Eventually` also
holds on start times whose complete horizon is represented; it is not applied
blindly at finite-universe boundaries.

Formulas use mathematical notation with precedence-aware parentheses when
converted to strings:

```python
print(formula & available)  # (∀[8,10]: available) ∧ available
```

Use `format_expression(formula, unicode=False)` for ASCII-only logs. `repr()`
retains the full dataclass representation for debugging.

The same notation can be parsed from either ASCII or Unicode. Operator
precedence matches the formatter, and quoted names allow spaces and punctuation:

```python
from interval_logic import parse_expression

formula = parse_expression(
    "forall[8,10]: `vehicle connected` -> !fault"
)
assert str(formula) == "∀[8,10]: `vehicle connected` → ¬fault"
assert parse_expression(str(formula)) == formula
```

The parser accepts `true`/`false`, `!`, `&`, `|`, `xor`, `->`, and `<->`, as
well as their Unicode counterparts `⊤`/`⊥`, `¬`, `∧`, `∨`, `⊕`, `→`, and `↔`.
It also parses signal equalities (`j = 1`, `j != 0`), quantifiers, bounded
temporal operators, and the restrict/guard forms emitted by the formatter. Invalid input raises
`ParseError`, whose `position`, `line`, and `column` attributes locate the
problem.

Anywhere the public API expects an `Expression`, the same notation can be
passed directly as a string. This includes expression constructors, derived
operators, rewriting and normalization functions, evaluation, formatting, and
timelines:

```python
formula = ForAll("[8,10]", "available & !fault")
assert formula == parse_expression("forall[8,10]: available & !fault")
assert simplify("available & true") == Atom("available")
```

In a notebook, `timeline(formula, valuation, universe)` displays an exact
interval table and an inline SVG Gantt chart for the valuation and formula
denotation. Its plain `str()` form provides the same interval data in terminals.

## Natural-number signals

Formulas can compare piecewise-constant natural-number signals. Signal regions
must be disjoint, and time outside those regions must either be covered
explicitly or assigned an explicit default.

```python
from interval_logic import ForAll, NaturalSignal, Signal

universe = P.closed(0, 24)
j1, j2 = Signal("j_1"), Signal("j_2")
signals = {
    "j_1": NaturalSignal({17: P.closedopen(8, 10)}, default=0),
    "j_2": NaturalSignal({23: P.closedopen(9, 11)}, default=0),
}

no_duplicate_job = ForAll(
    universe,
    j1.not_equals(j2) | (j1.equals(0) & j2.equals(0)),
)
assert denote(no_duplicate_job, {}, universe, signals=signals) == universe
```

Use `.equals()` and `.not_equals()` to construct formulas. Python `==` remains
structural equality so expressions and terms stay safely hashable.

## Replacing subexpressions

Every expression provides `replace(fn)` for immutable, bottom-up rewriting.
Children are replaced from left to right before `fn` receives their rebuilt
parent. Structural equality makes exact subexpressions easy to select:

```python
import interval_logic as il

target = il.Signal("j").equals(1)
formula = il.Exists("[0, 4]", target | il.Signal("j").equals(2))

def negate_other_equalities(expression):
    if isinstance(expression, il.Equal):
        return expression if expression == target else il.Not(expression)
    return expression

rewritten = formula.replace(negate_other_equalities)
```

The callback must return an `Expression`. Terms inside `Equal` nodes are not
visited, and expressions returned by the callback are not traversed again.

## Custom derived operators

Derived operators only need to describe how they lower into the core language.
The evaluator, simplifier, and normalizers lower them automatically.
`Implies`, `Equivalent`, and `Xor` are included.

```python
from dataclasses import dataclass

from interval_logic import And, DerivedExpression, Expression, Not

@dataclass(frozen=True, slots=True)
class Nand(DerivedExpression):
    left: Expression
    right: Expression

    @property
    def children(self):
        return (self.left, self.right)

    def lower(self):
        return Not(And((self.left, self.right)))
```

`replace()` preserves derived operators and normally rebuilds them by passing
their replacement children to the constructor positionally. A derived operator
with additional constructor state can preserve it by overriding the protected
hook:

```python
def _with_children(self, children):
    return type(self)(self.label, *children)
```

Use `simplify()` to lower derived operators, push negations to atoms, recognize
Boolean and quantified complements, and apply compact Boolean and interval
rewrites. Negation normalization can grow a formula slightly; speculative
distribution and interval decomposition are kept only when the final result is
smaller. `max_nodes` bounds those speculative candidates, which are skipped if
they exceed the budget.

Quantifier implication depends on the evaluation universe. Pass it explicitly
to enable those contextual rules and effective-window reductions:

```python
p = Atom("p")
left = P.closed(0, 1)
right = P.closed(1, 2)
universe = P.closed(0, 2)

formula = ForAll(left, p) | Exists(right, p)
assert simplify(formula) == formula  # conservative for every universe
assert simplify(formula, universe=universe) == Exists(right, p)
assert formula.simplify(universe=universe, max_nodes=1_000) == Exists(right, p)
```

A result simplified with `universe=...` is equivalent relative to that universe.
Known domain equivalences remain explicit replacements; a two-pass workflow lets
the replacement expose further cancellations:

```python
from interval_logic import Bool, Signal

job_one = Signal("j").equals(1)
q = Atom("q")
formula_with_known_equivalence = ForAll(left, job_one) | Exists(left, ~q)

def domain_rewrite(expression):
    return q if expression == job_one else expression

partly_simplified = simplify(formula_with_known_equivalence)
substituted = partly_simplified.replace(domain_rewrite)
final = simplify(substituted, universe=universe)
assert final == Bool(True)
```

Use `to_nnf()` when only an explicit negation-normal result is needed, and
`partition_intervals()` when a shared disjoint interval partition must be
retained even if it is larger. The partitioner raises `ExpansionLimitError`
when its `max_nodes` budget is exceeded. NNF swaps `Restrict` and `Guard` under
negation. Universe-independent NNF retains negated `Hold` and `Eventually`
nodes because their ordinary duality is conditional at a finite-universe
boundary.

Examples are available in
[`notebooks/tutorial.ipynb`](notebooks/tutorial.ipynb).

## Development

From this directory:

```text
uv sync
uv run python -m unittest discover -s tests
```
