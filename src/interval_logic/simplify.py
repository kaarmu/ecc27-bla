from __future__ import annotations

from collections.abc import Callable
from math import isfinite

import portion as P

from .ast import (
    ALL_TIME,
    And,
    Atom,
    Bool,
    Equal,
    Eventually,
    Exists,
    Expression,
    ForAll,
    Guard,
    Hold,
    Natural,
    Not,
    Or,
    Restrict,
    _coerce_expression,
    expression_key,
)
from .intervals import erode_forward, minkowski_forward
from .transform import _push_negation, lower_derived


def simplify(
    expression: Expression | str,
    *,
    universe: P.Interval | None = None,
    max_nodes: int = 10_000,
) -> Expression:
    """Return a compact equivalent expression using terminating local rules.

    If ``universe`` is supplied, contextual rewrites are equivalent relative to
    that universe. ``max_nodes`` bounds speculative distribution and interval
    decomposition; over-budget candidates are simply ignored.
    """

    expression = _coerce_expression(expression, "expression")
    if universe is not None and not isinstance(universe, P.Interval):
        raise TypeError("universe must be a portion.Interval or None")
    if type(max_nodes) is not int or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")

    normalized = _push_negation(lower_derived(expression))
    current = _simplify_fixed_point(
        normalized,
        universe=universe,
        max_nodes=max_nodes,
        allow_distribution=True,
    )

    while True:
        candidate = _try_interval_decomposition(
            current,
            universe=universe,
            max_nodes=max_nodes,
        )
        if candidate is None or candidate.node_count >= current.node_count:
            return current
        current = candidate


def _simplify_fixed_point(
    expression: Expression,
    *,
    universe: P.Interval | None,
    max_nodes: int,
    allow_distribution: bool,
) -> Expression:
    current = expression
    while True:
        rewritten = _simplify_once(
            current,
            universe=universe,
            max_nodes=max_nodes,
            allow_distribution=allow_distribution,
        )
        if rewritten == current:
            return rewritten
        current = rewritten


def _simplify_once(
    expression: Expression,
    *,
    universe: P.Interval | None,
    max_nodes: int,
    allow_distribution: bool,
) -> Expression:
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
            child = _simplify_once(
                operand,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
            if universe is not None and isinstance(child, Hold):
                if erode_forward(universe, child.delta) == universe:
                    return Eventually(
                        child.delta, _push_negation(child.body, negated=True)
                    )
            if universe is not None and isinstance(child, Eventually):
                if erode_forward(universe, child.delta) == universe:
                    return Hold(
                        child.delta, _push_negation(child.body, negated=True)
                    )
            return _push_negation(Not(child))
        case And(operands=operands):
            return _simplify_variadic(
                And,
                operands,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
        case Or(operands=operands):
            return _simplify_variadic(
                Or,
                operands,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
        case Restrict(interval=interval, body=body):
            if interval.empty:
                return Bool(False)
            if universe is not None:
                effective = interval & universe
                if effective.empty:
                    return Bool(False)
            child = _simplify_once(
                body,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
            if child == Bool(False):
                return child
            if interval == ALL_TIME:
                return child
            if universe is not None and (universe - interval).empty:
                return child
            if isinstance(child, Restrict):
                return Restrict(interval & child.interval, child.body)
            return Restrict(interval, child)
        case Guard(interval=interval, body=body):
            if interval.empty:
                return Bool(True)
            if universe is not None:
                effective = interval & universe
                if effective.empty:
                    return Bool(True)
            child = _simplify_once(
                body,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
            if child == Bool(True):
                return child
            if interval == ALL_TIME:
                return child
            if universe is not None and (universe - interval).empty:
                return child
            if isinstance(child, Guard):
                return Guard(interval & child.interval, child.body)
            return Guard(interval, child)
        case ForAll(interval=interval, body=body):
            if interval.empty:
                return Bool(True)
            effective = interval if universe is None else interval & universe
            if universe is not None and effective.empty:
                return Bool(True)
            child = _simplify_once(
                body,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
            if child == Bool(True):
                return child
            if universe is not None and child == Bool(False):
                return Bool(False)
            if isinstance(child, Guard):
                return ForAll(interval & child.interval, child.body)
            if universe is not None and isinstance(child, Hold):
                expanded = minkowski_forward(effective, child.delta)
                if (expanded - universe).empty:
                    return ForAll(expanded, child.body)
            return ForAll(interval, child)
        case Exists(interval=interval, body=body):
            if interval.empty:
                return Bool(False)
            effective = interval if universe is None else interval & universe
            if universe is not None and effective.empty:
                return Bool(False)
            child = _simplify_once(
                body,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
            if child == Bool(False):
                return child
            if universe is not None and child == Bool(True):
                return Bool(True)
            if isinstance(child, Restrict):
                return Exists(interval & child.interval, child.body)
            if universe is not None and isinstance(child, Eventually):
                expanded = minkowski_forward(effective, child.delta)
                return Exists(expanded, child.body)
            return Exists(interval, child)
        case Hold(delta=delta, body=body):
            child = _simplify_once(
                body,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
            if delta == 0:
                return child
            if child == Bool(False):
                return child
            if child == Bool(True):
                if universe is not None and erode_forward(universe, delta) == universe:
                    return child
                return Hold(delta, child)
            if isinstance(child, Hold):
                combined = delta + child.delta
                if isfinite(combined):
                    return Hold(combined, child.body)
            if isinstance(child, And):
                candidate = And(Hold(delta, item) for item in child.operands)
                if candidate.node_count <= max_nodes:
                    return candidate
            if isinstance(child, (ForAll, Exists)):
                if universe is not None and erode_forward(universe, delta) == universe:
                    return child
            return Hold(delta, child)
        case Eventually(delta=delta, body=body):
            child = _simplify_once(
                body,
                universe=universe,
                max_nodes=max_nodes,
                allow_distribution=allow_distribution,
            )
            if delta == 0:
                return child
            if isinstance(child, Bool):
                return child
            if (
                isinstance(child, Eventually)
                and universe is not None
                and len(list(universe)) <= 1
            ):
                combined = delta + child.delta
                if isfinite(combined):
                    return Eventually(combined, child.body)
            if isinstance(child, Or):
                candidate = Or(Eventually(delta, item) for item in child.operands)
                if candidate.node_count <= max_nodes:
                    return candidate
            if isinstance(child, (ForAll, Exists)):
                return child
            return Eventually(delta, child)
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _simplify_variadic(
    operator: type[And] | type[Or],
    operands: tuple[Expression, ...],
    *,
    universe: P.Interval | None,
    max_nodes: int,
    allow_distribution: bool,
) -> Expression:
    is_and = operator is And
    flattened: list[Expression] = []
    for operand in operands:
        child = _simplify_once(
            operand,
            universe=universe,
            max_nodes=max_nodes,
            allow_distribution=allow_distribution,
        )
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
    if _contains_complements(unique):
        return Bool(annihilator)
    if is_and and _contains_incompatible_holds(unique):
        return Bool(False)

    unique = _apply_absorption(unique, is_and)
    unique = _merge_interval_operators(unique, is_and)
    unique = _merge_temporal_operators(unique, is_and)
    unique = _apply_quantifier_implication(unique, is_and, universe)
    unique = _unique_sorted(unique)

    if _contains_complements(unique):
        return Bool(annihilator)
    if not unique:
        return Bool(identity)
    if len(unique) == 1:
        return unique[0]

    result = operator(unique)
    factored = _factor_common_terms(result, is_and)
    if factored.node_count < result.node_count:
        return factored

    if allow_distribution:
        distributed = _try_distribution(
            result,
            universe=universe,
            max_nodes=max_nodes,
        )
        if distributed is not None:
            return distributed
    return result


def _contains_complements(operands: list[Expression]) -> bool:
    values = set(operands)
    return any(_negate_nnf(operand) in values for operand in operands)


def _negate_nnf(expression: Expression) -> Expression:
    match expression:
        case Bool(value=value):
            return Bool(not value)
        case Not(operand=operand):
            return operand
        case Atom() | Equal():
            return Not(expression)
        case And(operands=operands):
            return _make_variadic(Or, [_negate_nnf(item) for item in operands])
        case Or(operands=operands):
            return _make_variadic(And, [_negate_nnf(item) for item in operands])
        case Restrict(interval=interval, body=body):
            return Guard(interval, _negate_nnf(body))
        case Guard(interval=interval, body=body):
            return Restrict(interval, _negate_nnf(body))
        case ForAll(interval=interval, body=body):
            return Exists(interval, _negate_nnf(body))
        case Exists(interval=interval, body=body):
            return ForAll(interval, _negate_nnf(body))
        case Hold() | Eventually():
            return Not(expression)
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _apply_absorption(operands: list[Expression], is_and: bool) -> list[Expression]:
    nested_type: type[Or] | type[And] = Or if is_and else And
    terms = [
        frozenset(operand.operands)
        if isinstance(operand, nested_type)
        else frozenset((operand,))
        for operand in operands
    ]
    return [
        operand
        for index, operand in enumerate(operands)
        if not any(
            other_index != index and other_terms < terms[index]
            for other_index, other_terms in enumerate(terms)
        )
    ]


def _factor_common_terms(expression: And | Or, is_and: bool) -> Expression:
    nested_type: type[Or] | type[And] = Or if is_and else And
    operator: type[And] | type[Or] = And if is_and else Or
    branches = [
        frozenset(operand.operands)
        if isinstance(operand, nested_type)
        else frozenset((operand,))
        for operand in expression.operands
    ]
    factors = _unique_sorted(
        [
            term
            for branch in branches
            for term in branch
            if sum(term in other for other in branches) >= 2
        ]
    )
    candidates: list[Expression] = []
    for factor in factors:
        selected = [index for index, branch in enumerate(branches) if factor in branch]
        if any(len(branches[index]) == 1 for index in selected):
            continue
        remainders = [
            _make_variadic(nested_type, list(branches[index] - {factor}))
            for index in selected
        ]
        grouped = _make_variadic(operator, remainders)
        factored = _make_variadic(nested_type, [factor, grouped])
        unselected = [
            operand
            for index, operand in enumerate(expression.operands)
            if index not in selected
        ]
        candidates.append(_make_variadic(operator, [*unselected, factored]))
    if not candidates:
        return expression
    return min(candidates, key=lambda item: (item.node_count, expression_key(item)))


def _try_distribution(
    expression: And | Or,
    *,
    universe: P.Interval | None,
    max_nodes: int,
) -> Expression | None:
    operator: type[And] | type[Or] = type(expression)
    nested_type: type[Or] | type[And] = Or if operator is And else And
    candidates: list[Expression] = []
    for index, operand in enumerate(expression.operands):
        if not isinstance(operand, nested_type):
            continue
        rest = [
            other
            for other_index, other in enumerate(expression.operands)
            if other_index != index
        ]
        estimated = 1 + sum(
            1 + sum(item.node_count for item in rest) + part.node_count
            for part in operand.operands
        )
        if estimated > max_nodes:
            continue
        distributed = _make_variadic(
            nested_type,
            [_make_variadic(operator, [*rest, item]) for item in operand.operands],
        )
        if distributed.node_count > max_nodes:
            continue
        simplified = _simplify_fixed_point(
            distributed,
            universe=universe,
            max_nodes=max_nodes,
            allow_distribution=False,
        )
        if simplified.node_count < expression.node_count:
            candidates.append(simplified)
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item.node_count, expression_key(item)))


def _merge_interval_operators(
    operands: list[Expression], is_and: bool
) -> list[Expression]:
    operands = _merge_windows(operands, Restrict, is_and)
    operands = _merge_windows(operands, Guard, is_and)
    if is_and:
        return _merge_forall(operands)
    return _merge_exists(operands)


def _merge_temporal_operators(
    operands: list[Expression], is_and: bool
) -> list[Expression]:
    others = [
        item for item in operands if not isinstance(item, (Hold, Eventually))
    ]
    holds = [item for item in operands if isinstance(item, Hold)]
    eventualities = [item for item in operands if isinstance(item, Eventually)]

    for body, group in _group_by(holds, lambda item: item.body):
        deltas = [item.delta for item in group]
        others.append(Hold(max(deltas) if is_and else min(deltas), body))
    for body, group in _group_by(eventualities, lambda item: item.body):
        deltas = [item.delta for item in group]
        others.append(Eventually(min(deltas) if is_and else max(deltas), body))
    return others


def _contains_incompatible_holds(operands: list[Expression]) -> bool:
    holds = [item for item in operands if isinstance(item, Hold)]
    return any(
        _negate_nnf(left.body) == right.body
        for index, left in enumerate(holds)
        for right in holds[index + 1 :]
    )


def _apply_quantifier_implication(
    operands: list[Expression],
    is_and: bool,
    universe: P.Interval | None,
) -> list[Expression]:
    if universe is None:
        return operands
    universals = [item for item in operands if isinstance(item, ForAll)]
    existentials = [item for item in operands if isinstance(item, Exists)]
    if is_and:
        return [
            item
            for item in operands
            if not (
                isinstance(item, Exists)
                and any(
                    universal.body == item.body
                    and not (universal.interval & item.interval & universe).empty
                    for universal in universals
                )
            )
        ]
    return [
        item
        for item in operands
        if not (
            isinstance(item, ForAll)
            and any(
                existential.body == item.body
                and not (item.interval & existential.interval & universe).empty
                for existential in existentials
            )
        )
    ]


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


def _try_interval_decomposition(
    expression: Expression,
    *,
    universe: P.Interval | None,
    max_nodes: int,
) -> Expression | None:
    intervals = _collect_quantifier_intervals(expression)
    if len(intervals) < 2 and all(len(list(interval)) < 2 for interval in intervals):
        return None
    if expression.node_count >= max_nodes:
        return None

    from .normalize import _partition

    cells = _partition(intervals)
    try:
        candidate = _decompose_quantifiers(expression, cells, max_nodes)
    except _CandidateTooLarge:
        return None
    if candidate == expression or candidate.node_count > max_nodes:
        return None
    simplified = _simplify_fixed_point(
        candidate,
        universe=universe,
        max_nodes=max_nodes,
        allow_distribution=True,
    )
    return simplified if simplified.node_count < expression.node_count else None


def _collect_quantifier_intervals(expression: Expression) -> list[P.Interval]:
    intervals: list[P.Interval] = []
    if isinstance(expression, (ForAll, Exists)) and not expression.interval.empty:
        intervals.append(expression.interval)
    for child in expression.children:
        intervals.extend(_collect_quantifier_intervals(child))
    return intervals


def _decompose_quantifiers(
    expression: Expression,
    cells: tuple[P.Interval, ...],
    max_nodes: int,
) -> Expression:
    if not expression.children:
        return expression
    children = tuple(
        _decompose_quantifiers(child, cells, max_nodes)
        for child in expression.children
    )
    if isinstance(expression, ForAll):
        selected = [cell for cell in cells if (cell - expression.interval).empty]
        _check_candidate_size(len(selected), children[0], max_nodes)
        result = _make_variadic(
            And,
            [ForAll(cell, children[0]) for cell in selected],
        )
        return result
    if isinstance(expression, Exists):
        selected = [cell for cell in cells if (cell - expression.interval).empty]
        _check_candidate_size(len(selected), children[0], max_nodes)
        result = _make_variadic(
            Or,
            [Exists(cell, children[0]) for cell in selected],
        )
        return result
    if isinstance(expression, And):
        result = _make_variadic(And, list(children))
    elif isinstance(expression, Or):
        result = _make_variadic(Or, list(children))
    elif any(new is not old for old, new in zip(expression.children, children)):
        result = expression._with_children(children)
    else:
        result = expression
    if result.node_count > max_nodes:
        raise _CandidateTooLarge
    return result


class _CandidateTooLarge(Exception):
    pass


def _check_candidate_size(
    piece_count: int,
    body: Expression,
    max_nodes: int,
) -> None:
    if piece_count == 0:
        estimated = 1
    elif piece_count == 1:
        estimated = 1 + body.node_count
    else:
        estimated = 1 + piece_count * (1 + body.node_count)
    if estimated > max_nodes:
        raise _CandidateTooLarge


def _make_variadic(
    operator: type[And] | type[Or], operands: list[Expression]
) -> Expression:
    flattened: list[Expression] = []
    for operand in operands:
        if isinstance(operand, operator):
            flattened.extend(operand.operands)
        else:
            flattened.append(operand)
    values = _unique_sorted(flattened)
    if not values:
        return Bool(operator is And)
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
