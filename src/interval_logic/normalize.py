from __future__ import annotations

import portion as P

from .ast import (
    And,
    Proposition,
    Bool,
    Equal,
    Eventually,
    ExistentialCondition,
    Expression,
    Release,
    Selection,
    Until,
    UniversalCondition,
    VacuousSelection,
    Not,
    Or,
    RestrictiveSelection,
    _coerce_expression,
    expression_key,
)
from .errors import ExpansionLimitError
from .simplify import simplify
from .transform import _push_negation, lower_derived


def to_nnf(expression: Expression | str) -> Expression:
    """Lower derived operators and push negations through every temporal dual."""

    expression = _coerce_expression(expression, "expression")
    return simplify(_push_negation(lower_derived(expression), negated=False))


def partition_intervals(
    expression: Expression | str, *, max_nodes: int = 10_000
) -> Expression:
    """Rewrite absolute operators over a shared disjoint interval partition."""

    if type(max_nodes) is not int or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    normalized = to_nnf(expression)
    _check_budget(normalized, max_nodes)
    cells = _partition(_collect_intervals(normalized))
    return _rewrite_absolute_operators(normalized, cells, max_nodes)


def _collect_intervals(expression: Expression) -> list[P.Interval]:
    intervals: list[P.Interval] = []
    if (
        isinstance(
            expression,
            (
                RestrictiveSelection,
                VacuousSelection,
                UniversalCondition,
                ExistentialCondition,
            ),
        )
        and isinstance(expression.interval, P.Interval)
        and not expression.interval.empty
    ):
        intervals.append(expression.interval)
    if (
        isinstance(expression, (Selection, Until, Release))
        and isinstance(expression.parameter, P.Interval)
        and not expression.parameter.empty
    ):
        intervals.append(expression.parameter)
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


def _rewrite_absolute_operators(
    expression: Expression,
    cells: tuple[P.Interval, ...],
    max_nodes: int,
) -> Expression:
    match expression:
        case Bool() | Proposition() | Equal():
            result = expression
        case Not(operand=operand):
            result = Not(_rewrite_absolute_operators(operand, cells, max_nodes))
        case And(operands=operands):
            result = _canonical_variadic(
                And,
                [_rewrite_absolute_operators(item, cells, max_nodes) for item in operands],
            )
        case Or(operands=operands):
            result = _canonical_variadic(
                Or,
                [_rewrite_absolute_operators(item, cells, max_nodes) for item in operands],
            )
        case RestrictiveSelection(interval=interval, body=body):
            child = _rewrite_absolute_operators(body, cells, max_nodes)
            if isinstance(interval, P.Interval):
                pieces = [RestrictiveSelection(cell, child) for cell in cells if (cell - interval).empty]
                result = _canonical_variadic(Or, pieces, empty=Bool(False))
            else:
                result = RestrictiveSelection(interval, child)
        case VacuousSelection(interval=interval, body=body):
            child = _rewrite_absolute_operators(body, cells, max_nodes)
            if isinstance(interval, P.Interval):
                pieces = [VacuousSelection(cell, child) for cell in cells if (cell - interval).empty]
                result = _canonical_variadic(And, pieces, empty=Bool(True))
            else:
                result = VacuousSelection(interval, child)
        case Selection(parameter=parameter, inside=inside, outside=outside):
            selected_child = _rewrite_absolute_operators(inside, cells, max_nodes)
            outside_child = _rewrite_absolute_operators(outside, cells, max_nodes)
            if isinstance(parameter, P.Interval):
                selected_cells = [
                    cell for cell in cells if (cell - parameter).empty
                ]
                selected_part = _canonical_variadic(
                    Or,
                    [RestrictiveSelection(cell, selected_child) for cell in selected_cells],
                    empty=Bool(False),
                )
                outside_mask = _canonical_variadic(
                    And,
                    [VacuousSelection(cell, Bool(False)) for cell in selected_cells],
                    empty=Bool(True),
                )
                result = _canonical_variadic(
                    Or,
                    [selected_part, And((outside_child, outside_mask))],
                )
            else:
                result = Selection(parameter, selected_child, outside_child)
        case UniversalCondition(interval=interval, body=body):
            child = _rewrite_absolute_operators(body, cells, max_nodes)
            if isinstance(interval, P.Interval):
                pieces = [UniversalCondition(cell, child) for cell in cells if (cell - interval).empty]
                result = _canonical_variadic(And, pieces, empty=Bool(True))
            else:
                result = UniversalCondition(interval, child)
        case ExistentialCondition(interval=interval, body=body):
            child = _rewrite_absolute_operators(body, cells, max_nodes)
            if isinstance(interval, P.Interval):
                pieces = [ExistentialCondition(cell, child) for cell in cells if (cell - interval).empty]
                result = _canonical_variadic(Or, pieces, empty=Bool(False))
            else:
                result = ExistentialCondition(interval, child)
        case Eventually(parameter=parameter, body=body):
            result = Eventually(
                parameter, _rewrite_absolute_operators(body, cells, max_nodes)
            )
        case Until(parameter=parameter, left=left, right=right):
            left_child = _rewrite_absolute_operators(left, cells, max_nodes)
            right_child = _rewrite_absolute_operators(right, cells, max_nodes)
            if isinstance(parameter, P.Interval):
                selected_cells = sorted(
                    (cell for cell in cells if (cell - parameter).empty),
                    key=_interval_order_key,
                )
                branches = []
                for index, cell in enumerate(selected_cells):
                    prefix = [
                        UniversalCondition(previous, left_child)
                        for previous in selected_cells[:index]
                    ]
                    branches.append(
                        _canonical_variadic(
                            And,
                            [*prefix, Until(cell, left_child, right_child)],
                        )
                    )
                result = _canonical_variadic(Or, branches, empty=Bool(False))
            else:
                result = Until(parameter, left_child, right_child)
        case Release(parameter=parameter, left=left, right=right):
            left_child = _rewrite_absolute_operators(left, cells, max_nodes)
            right_child = _rewrite_absolute_operators(right, cells, max_nodes)
            if isinstance(parameter, P.Interval):
                dual = _rewrite_absolute_operators(
                    Until(parameter, Not(left_child), Not(right_child)),
                    cells,
                    max_nodes,
                )
                result = _push_negation(dual, negated=True)
            else:
                result = Release(parameter, left_child, right_child)
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


def _interval_order_key(interval: P.Interval):
    atom = next(iter(interval))
    return (atom.lower, atom.left.name != "CLOSED", atom.upper)


def _check_budget(expression: Expression, limit: int) -> None:
    if expression.node_count > limit:
        raise ExpansionLimitError(limit, expression.node_count)
