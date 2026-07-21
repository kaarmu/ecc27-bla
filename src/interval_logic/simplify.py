from __future__ import annotations

from collections.abc import Callable

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
    Natural,
    Not,
    Or,
    Restrict,
    expression_key,
)
from .transform import lower_derived


_ALL_TIME = P.open(-P.inf, P.inf)


def simplify(expression: Expression) -> Expression:
    """Return a compact equivalent expression using terminating local rules."""

    current = lower_derived(expression)
    while True:
        rewritten = _simplify_once(current)
        if rewritten == current:
            return rewritten
        current = rewritten


def _simplify_once(expression: Expression) -> Expression:
    match expression:
        case Bool() | Atom():
            return expression
        case Equal(left=left, right=right):
            if left == right:
                return Bool(True)
            if isinstance(left, Natural) and isinstance(right, Natural):
                return Bool(left.value == right.value)
            return expression
        case Not(operand=operand):
            child = _simplify_once(operand)
            if isinstance(child, Bool):
                return Bool(not child.value)
            if isinstance(child, Not):
                return child.operand
            return Not(child)
        case And(operands=operands):
            return _simplify_variadic(And, operands)
        case Or(operands=operands):
            return _simplify_variadic(Or, operands)
        case Restrict(interval=interval, body=body):
            if interval.empty:
                return Bool(False)
            child = _simplify_once(body)
            if interval == _ALL_TIME or child == Bool(False):
                return child
            if isinstance(child, Restrict):
                return Restrict(interval & child.interval, child.body)
            return Restrict(interval, child)
        case Guard(interval=interval, body=body):
            if interval.empty:
                return Bool(True)
            child = _simplify_once(body)
            if interval == _ALL_TIME or child == Bool(True):
                return child
            if isinstance(child, Guard):
                return Guard(interval & child.interval, child.body)
            return Guard(interval, child)
        case ForAll(interval=interval, body=body):
            if interval.empty:
                return Bool(True)
            child = _simplify_once(body)
            if child == Bool(True):
                return child
            if isinstance(child, Guard):
                return ForAll(interval & child.interval, child.body)
            return ForAll(interval, child)
        case Exists(interval=interval, body=body):
            if interval.empty:
                return Bool(False)
            child = _simplify_once(body)
            if child == Bool(False):
                return child
            if isinstance(child, Restrict):
                return Exists(interval & child.interval, child.body)
            return Exists(interval, child)
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _simplify_variadic(
    operator: type[And] | type[Or], operands: tuple[Expression, ...]
) -> Expression:
    is_and = operator is And
    flattened: list[Expression] = []
    for operand in operands:
        child = _simplify_once(operand)
        if isinstance(child, operator):
            flattened.extend(child.operands)
        else:
            flattened.append(child)

    identity = True if is_and else False
    annihilator = not identity
    retained: list[Expression] = []
    for operand in flattened:
        if isinstance(operand, Bool):
            if operand.value is annihilator:
                return Bool(annihilator)
            continue
        retained.append(operand)

    unique = _unique_sorted(retained)
    positive = {item for item in unique if not isinstance(item, Not)}
    negative = {item.operand for item in unique if isinstance(item, Not)}
    if positive & negative:
        return Bool(annihilator)

    unique = _apply_absorption(unique, is_and)
    unique = _merge_interval_operators(unique, is_and)
    unique = _unique_sorted(unique)

    if not unique:
        return Bool(identity)
    if len(unique) == 1:
        return unique[0]
    return operator(unique)


def _apply_absorption(
    operands: list[Expression], is_and: bool
) -> list[Expression]:
    nested_type: type[Or] | type[And] = Or if is_and else And
    direct = set(operands)
    return [
        operand
        for operand in operands
        if not (
            isinstance(operand, nested_type)
            and any(item in direct for item in operand.operands)
        )
    ]


def _merge_interval_operators(
    operands: list[Expression], is_and: bool
) -> list[Expression]:
    operands = _merge_windows(operands, Restrict, is_and)
    operands = _merge_windows(operands, Guard, is_and)
    if is_and:
        return _merge_forall(operands)
    return _merge_exists(operands)


def _merge_windows(
    operands: list[Expression],
    window_type: type[Restrict] | type[Guard],
    is_and: bool,
) -> list[Expression]:
    others = [item for item in operands if not isinstance(item, window_type)]
    windows = [item for item in operands if isinstance(item, window_type)]
    body_operator: type[And] | type[Or] = And if is_and else Or

    by_interval = _group_by(windows, lambda item: item.interval)
    combined = [
        window_type(
            interval,
            _make_variadic(body_operator, [item.body for item in group]),
        )
        for interval, group in by_interval
    ]

    by_body = _group_by(combined, lambda item: item.body)
    for body, group in by_body:
        intervals = [item.interval for item in group]
        if window_type is Restrict:
            interval = _intersection(intervals) if is_and else _union(intervals)
        else:
            interval = _union(intervals) if is_and else _intersection(intervals)
        others.append(window_type(interval, body))
    return others


def _merge_forall(operands: list[Expression]) -> list[Expression]:
    others = [item for item in operands if not isinstance(item, ForAll)]
    quantified = [item for item in operands if isinstance(item, ForAll)]
    by_interval = _group_by(quantified, lambda item: item.interval)
    combined = [
        ForAll(interval, _make_variadic(And, [item.body for item in group]))
        for interval, group in by_interval
    ]
    by_body = _group_by(combined, lambda item: item.body)
    others.extend(
        ForAll(_union(item.interval for item in group), body)
        for body, group in by_body
    )
    return others


def _merge_exists(operands: list[Expression]) -> list[Expression]:
    others = [item for item in operands if not isinstance(item, Exists)]
    quantified = [item for item in operands if isinstance(item, Exists)]
    by_interval = _group_by(quantified, lambda item: item.interval)
    combined = [
        Exists(interval, _make_variadic(Or, [item.body for item in group]))
        for interval, group in by_interval
    ]
    by_body = _group_by(combined, lambda item: item.body)
    others.extend(
        Exists(_union(item.interval for item in group), body)
        for body, group in by_body
    )
    return others


def _make_variadic(
    operator: type[And] | type[Or], operands: list[Expression]
) -> Expression:
    values = _unique_sorted(operands)
    if len(values) == 1:
        return values[0]
    return operator(values)


def _unique_sorted(operands: list[Expression]) -> list[Expression]:
    return sorted(set(operands), key=expression_key)


def _group_by(items: list, key: Callable) -> list[tuple[object, list]]:
    groups: list[tuple[object, list]] = []
    for item in items:
        item_key = key(item)
        for existing_key, group in groups:
            if existing_key == item_key:
                group.append(item)
                break
        else:
            groups.append((item_key, [item]))
    return groups


def _union(intervals) -> P.Interval:
    result = P.empty()
    for interval in intervals:
        result |= interval
    return result


def _intersection(intervals) -> P.Interval:
    iterator = iter(intervals)
    result = next(iterator)
    for interval in iterator:
        result &= interval
    return result
