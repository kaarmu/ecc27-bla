# Interval logic

`interval_logic` provides immutable formulas with exact absolute- and
relative-time semantics. Proposition valuations and the evaluation universe
are represented by `portion.Interval` objects. `satisfying_anchors()` returns
the represented anchor times at which a formula is locally true, while
`anchored_denotation()` returns the full set-valued denotation at one anchor.

The language and its denotational semantics are defined in
[`LOGIC.md`](LOGIC.md), the canonical logic specification.

Every temporal operator uses the same parameter forms:

- a connected `portion.Interval` or ordinary interval string is absolute;
- `RelativeInterval(D)` or an interval string ending in `+` is relative;
- `d]` and `d)` mean `[0,d]+` and `[0,d)+`;
- a non-negative real is compatibility shorthand for `d]`;
- `None` means the omitted, unbounded parameter `[0,+inf)+`.

Relative intervals must be nonempty, connected, and non-negative. The special
one-sided parameter `0)` is the specified empty relative window.

```python
import portion as P

from interval_logic import (
    Bool,
    RelativeInterval,
    Proposition,
    Selection,
    Until,
    UniversalCondition,
    anchored_denotation,
    simplify,
    satisfying_anchors,
)

available = Proposition("available")
fault = Proposition("fault")
formula = Until("5]", available, fault)

truth = satisfying_anchors(
    formula,
    {
        "available": P.closedopen(0, 3),
        "fault": P.singleton(3),
    },
    universe=P.closed(0, 24),
)
assert truth == P.closed(0, 3)
```

The canonical parser and formatter mirror `LOGIC.md`:

```python
from interval_logic import parse_expression

assert str(parse_expression("<available, fault>_[1,3]+")) == "⟨available, fault⟩_[1,3]+"
assert str(parse_expression("always_5] eventually_2] available")) == "□_5] ◇_2] available"
assert str(parse_expression("available U_[1,3]+ fault")) == "available U_[1,3]+ fault"
```

Unary selections are the binary selector's `true`/`false` special cases.
`⟨p⟩_ρ` is true outside its window; `⟨p⟩*_ρ` is false outside it. Selection
operands retain the selection's anchor. Conditions (`□`, `◇`) and until instead
inspect their operands using local truth re-anchored at each inspected time.

Use `anchored_denotation()` when that distinction matters:

```python
mask = Selection(P.closed(0, 4), parse_expression("eventually_1] available"), Bool(False))
denotation = anchored_denotation(
    mask,
    {"available": P.singleton(1)},
    anchor=0,
    universe=P.closed(0, 6),
)
assert denotation == P.closed(0, 4)
```

`Eventually(delta, formula)` and `F^delta formula` remain compatibility forms
for a closed one-sided existential condition:

```python
from interval_logic import Eventually

soon = Eventually(2, available)
assert soon == available.eventually(2)
assert soon == parse_expression("F^2 available")
```

`WeakUntil(ρ,p,q)` lowers to `Until(ρ,p,q) | UniversalCondition(span(ρ),p)`;
`Release` uses the strong-until dual. Only represented times are inspected, so
temporal witnesses may cross gaps in a disconnected evaluation universe.

Formulas use mathematical notation with precedence-aware parentheses when
converted to strings:

```python
print(formula & available)  # available U_5] fault ∧ available
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
assert str(formula) == "□_[8,10] (`vehicle connected` → ¬fault)"
assert parse_expression(str(formula)) == formula
```

The parser accepts `true`/`false`, `!`, `&`, `|`, `xor`, `->`, and `<->`, as
well as their Unicode counterparts `⊤`/`⊥`, `¬`, `∧`, `∨`, `⊕`, `→`, and `↔`.
It also parses signal equalities (`j = 1`, `j != 0`), `□`/`◇`, `U`/`W`/`R`,
binary and unary selections, every temporal-parameter form, and the legacy
spellings shown above. Invalid input raises `ParseError`, whose `position`,
`line`, and `column` attributes locate the problem.

Anywhere the public API expects an `Expression`, the same notation can be
passed directly as a string. This includes expression constructors, derived
operators, rewriting and normalization functions, evaluation, formatting, and
timelines:

```python
formula = UniversalCondition("[8,10]", "available & !fault")
assert formula == parse_expression("forall[8,10]: available & !fault")
assert simplify("available & true") == Proposition("available")
```

`timeline(formula, valuation, universe)` displays an exact interval table and an
inline SVG Gantt chart for the valuation and formula's satisfying-anchor sweep.
Its plain `str()` form provides the same interval data in terminals.

## Non-negative-integer signals

Formulas can compare piecewise-constant natural-number signals. Signal regions
must be disjoint, and time outside those regions must either be covered
explicitly or assigned an explicit default.

```python
from interval_logic import UniversalCondition, NaturalSignal, Signal

universe = P.closed(0, 24)
j1, j2 = Signal("j_1"), Signal("j_2")
signals = {
    "j_1": NaturalSignal({17: P.closedopen(8, 10)}, default=0),
    "j_2": NaturalSignal({23: P.closedopen(9, 11)}, default=0),
}

no_duplicate_job = UniversalCondition(
    universe,
    j1.not_equals(j2) | (j1.equals(0) & j2.equals(0)),
)
assert satisfying_anchors(no_duplicate_job, {}, universe, signals=signals) == universe
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
formula = il.ExistentialCondition("[0, 4]", target | il.Signal("j").equals(2))

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

Use `simplify()` to lower derived operators, push supported negations to formula
leaves, recognize Boolean and condition complements, and apply compact Boolean
and interval rewrites. Negation normalization can grow a formula slightly;
speculative distribution and interval decomposition are kept only when the
final result is smaller. `max_nodes` bounds those speculative candidates, which
are skipped if they exceed the budget.

Condition implication depends on the evaluation universe. Pass it explicitly
to enable those contextual rules and effective-window reductions:

```python
p = Proposition("p")
left = P.closed(0, 1)
right = P.closed(1, 2)
universe = P.closed(0, 2)

formula = UniversalCondition(left, p) | ExistentialCondition(right, p)
assert simplify(formula) == formula  # conservative for every universe
assert simplify(formula, universe=universe) == ExistentialCondition(right, p)
assert formula.simplify(universe=universe, max_nodes=1_000) == ExistentialCondition(right, p)
```

A result simplified with `universe=...` is equivalent relative to that universe.
Known domain equivalences remain explicit replacements; a two-pass workflow lets
the replacement expose further cancellations:

```python
from interval_logic import Bool, Signal

job_one = Signal("j").equals(1)
q = Proposition("q")
formula_with_known_equivalence = UniversalCondition(left, job_one) | ExistentialCondition(left, ~q)

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
when its `max_nodes` budget is exceeded. NNF swaps `RestrictiveSelection` and
`VacuousSelection` under negation, negates binary selection componentwise,
swaps universal/existential conditions, and applies the until/release duality.

## Development

From this directory:

```text
uv sync
uv run python -m unittest discover -s tests
```
