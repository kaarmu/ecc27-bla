# Interval logic

`interval_logic` provides immutable formulas over absolute time intervals. Atom
valuations and the evaluation universe are represented by `portion.Interval`
objects. Supplied valuations and all interval operators are clipped to that
universe during evaluation.

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

Formulas use mathematical notation with precedence-aware parentheses when
converted to strings:

```python
print(formula & available)  # (∀[8,10]: available) ∧ available
```

Use `format_expression(formula, unicode=False)` for ASCII-only logs. `repr()`
retains the full dataclass representation for debugging.

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

Use `simplify()` for compact, size-nonincreasing rewrites after derived operators
are lowered, `to_nnf()` to push negations to atoms, and
`partition_intervals()` when a shared disjoint interval partition is required.
The partitioner accepts a `max_nodes` budget because it may expand a formula.
NNF swaps `Restrict` and `Guard` under negation, preserving the guarantee that
negations only wrap propositions or equalities.

Examples are available in
[`notebooks/interval_logic_examples.ipynb`](notebooks/interval_logic_examples.ipynb).

## Development

From this directory:

```text
uv sync
uv run python -m unittest discover -s tests
```
