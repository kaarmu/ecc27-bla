from __future__ import annotations

import portion as P

from .ast import (
    And,
    Atom,
    Bool,
    Equal,
    Exists,
    Expression,
    ForAll,
    Guard,
    Not,
    Or,
    Restrict,
    expression_key,
)
from .errors import ExpansionLimitError
from .simplify import simplify
from .transform import lower_derived


def to_nnf(expression: Expression) -> Expression:
    """Lower derived operators and push negations down to atomic formulas."""

    return simplify(_push_negation(lower_derived(expression), negated=False))


def partition_intervals(
    expression: Expression, *, max_nodes: int = 10_000
) -> Expression:
    """Rewrite quantifiers over a shared disjoint interval partition."""

    if type(max_nodes) is not int or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    normalized = to_nnf(expression)
    _check_budget(normalized, max_nodes)
    cells = _partition(_collect_intervals(normalized))
    return _rewrite_quantifiers(normalized, cells, max_nodes)


def _push_negation(expression: Expression, negated: bool) -> Expression:
    match expression:
        case Bool(value=value):
            return Bool(not value if negated else value)
        case Atom() | Equal():
            return Not(expression) if negated else expression
        case Not(operand=operand):
            return _push_negation(operand, not negated)
        case And(operands=operands):
            operator = Or if negated else And
            return operator(_push_negation(item, negated) for item in operands)
        case Or(operands=operands):
            operator = And if negated else Or
            return operator(_push_negation(item, negated) for item in operands)
        case Restrict(interval=interval, body=body):
            operator = Guard if negated else Restrict
            return operator(interval, _push_negation(body, negated))
        case Guard(interval=interval, body=body):
            operator = Restrict if negated else Guard
            return operator(interval, _push_negation(body, negated))
        case ForAll(interval=interval, body=body):
            operator = Exists if negated else ForAll
            return operator(interval, _push_negation(body, negated))
        case Exists(interval=interval, body=body):
            operator = ForAll if negated else Exists
            return operator(interval, _push_negation(body, negated))
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _collect_intervals(expression: Expression) -> list[P.Interval]:
    intervals: list[P.Interval] = []
    if isinstance(expression, (Restrict, Guard, ForAll, Exists)) and not expression.interval.empty:
        intervals.append(expression.interval)
    for child in expression.children:
        intervals.extend(_collect_intervals(child))
    return intervals


def _partition(intervals: list[P.Interval]) -> tuple[P.Interval, ...]:
    cells: list[P.Interval] = []
    for interval in intervals:
        remaining = interval
        refined: list[P.Interval] = []
        for cell in cells:
            refined.extend(_atoms(cell - interval))
            refined.extend(_atoms(cell & interval))
            remaining -= cell
        refined.extend(_atoms(remaining))
        cells = _dedupe_intervals(refined)
    return tuple(sorted(cells, key=str))


def _rewrite_quantifiers(
    expression: Expression,
    cells: tuple[P.Interval, ...],
    max_nodes: int,
) -> Expression:
    match expression:
        case Bool() | Atom() | Equal():
            result = expression
        case Not(operand=operand):
            result = Not(_rewrite_quantifiers(operand, cells, max_nodes))
        case And(operands=operands):
            result = _canonical_variadic(
                And,
                [_rewrite_quantifiers(item, cells, max_nodes) for item in operands],
            )
        case Or(operands=operands):
            result = _canonical_variadic(
                Or,
                [_rewrite_quantifiers(item, cells, max_nodes) for item in operands],
            )
        case Restrict(interval=interval, body=body):
            child = _rewrite_quantifiers(body, cells, max_nodes)
            pieces = [Restrict(cell, child) for cell in cells if (cell - interval).empty]
            result = _canonical_variadic(Or, pieces, empty=Bool(False))
        case Guard(interval=interval, body=body):
            child = _rewrite_quantifiers(body, cells, max_nodes)
            pieces = [Guard(cell, child) for cell in cells if (cell - interval).empty]
            result = _canonical_variadic(And, pieces, empty=Bool(True))
        case ForAll(interval=interval, body=body):
            child = _rewrite_quantifiers(body, cells, max_nodes)
            pieces = [ForAll(cell, child) for cell in cells if (cell - interval).empty]
            result = _canonical_variadic(And, pieces, empty=Bool(True))
        case Exists(interval=interval, body=body):
            child = _rewrite_quantifiers(body, cells, max_nodes)
            pieces = [Exists(cell, child) for cell in cells if (cell - interval).empty]
            result = _canonical_variadic(Or, pieces, empty=Bool(False))
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")
    _check_budget(result, max_nodes)
    return result


def _canonical_variadic(
    operator: type[And] | type[Or],
    operands: list[Expression],
    *,
    empty: Expression | None = None,
) -> Expression:
    flattened: list[Expression] = []
    for operand in operands:
        if isinstance(operand, operator):
            flattened.extend(operand.operands)
        else:
            flattened.append(operand)
    values = sorted(set(flattened), key=expression_key)
    if not values:
        if empty is None:
            return Bool(operator is And)
        return empty
    if len(values) == 1:
        return values[0]
    return operator(values)


def _atoms(interval: P.Interval) -> list[P.Interval]:
    return [] if interval.empty else list(interval)


def _dedupe_intervals(intervals: list[P.Interval]) -> list[P.Interval]:
    result: list[P.Interval] = []
    for interval in intervals:
        if not interval.empty and interval not in result:
            result.append(interval)
    return result


def _check_budget(expression: Expression, limit: int) -> None:
    if expression.node_count > limit:
        raise ExpansionLimitError(limit, expression.node_count)
