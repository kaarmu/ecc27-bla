# interval-logic

`interval-logic` implements the language defined by [`LOGIC.md`](LOGIC.md).
[`CODE.md`](CODE.md) is the corresponding Python interface contract. One
trajectory-satisfaction relation feeds two distinct query domains:

- complete-trace checking returns represented physical-time sets;
- reachability checking returns symbolic, multidimensional state sets.

## Formula construction

```python
from interval_logic import Proposition, Signal

available = Proposition("available")
fault = Proposition("fault")
job = Signal("job")

formula = (available & ~fault).always("5]")
assignment = job.equals(3).eventually()
```

Temporal constructors take operands first and the optional parameter last.
Bare durations are half-open, a trailing `]` closes the endpoint, and
`None` means that the parameter is genuinely omitted.

```python
from interval_logic import Eventually, RelativeParameter, Until

Eventually(available, 3) == Eventually(
    available, RelativeParameter(3, include_endpoint=False)
)
Until(available, assignment, "3]")
```

## Parsing and formatting

```python
from interval_logic import format_formula, parse_formula

formula = parse_formula("always_5] (available implies not fault)")
assert str(formula) == "□_5] (available → ¬fault)"
assert format_formula(formula, unicode=False) == (
    "always_5] (available implies not fault)"
)
assert parse_formula(str(formula)) == formula
```

The parser also accepts `⊤`, `⊥`, `¬`, `∧`, `∨`, `→`, `↔`, selections,
`◇`, `□`, `U`, `W`, and `R` from `LOGIC.md`.

## Complete-trace checking

```python
import portion as P

from interval_logic import NaturalSignal, Trace, satisfying_times

trace = Trace(
    P.closed(0, 10),
    propositions={"available": P.closedopen(2, 8)},
    signals={
        "job": NaturalSignal(
            {0: P.closedopen(0, 4), 3: P.closed(4, 10)}
        )
    },
)

assert satisfying_times("eventually_2] available", trace) == P.closedopen(0, 8)
```

Use `denote(formula, trace, anchor)` for a formula's complete anchored
denotation, `satisfies(formula, trace, at)` for local truth, and
`satisfying_times(formula, trace)` to sweep the anchor. Selection masks and
conditions retain their distinct roles, but every temporal parameter uses the
same future-directed window. In particular, an absolute interval is clipped
at the current anchor for selection as well as for conditions.

## Symbolic reachability

Implement `ReachabilityBackend` with a genuine multidimensional `StateSet`,
then call `reach(formula, backend, anchor)`. The returned `ReachResult` contains
the computed TLT set as `tlt_set` and a `certified` flag. Temporal conjunctions
remain uncertified unless the backend proves that the operands share a
satisfying trajectory. Untimed backends must reject positive-duration and
absolute conditions instead of interpreting seconds as transition counts.
