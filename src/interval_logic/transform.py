from __future__ import annotations

from collections.abc import Callable

from .ast import (
    And,
    Proposition,
    Bool,
    DerivedExpression,
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
)
from .errors import DerivedExpressionCycleError, DerivedExpressionError, ParseError


def replace(
    expression: Expression | str,
    fn: Callable[[Expression], Expression | str],
) -> Expression:
    """Replace expression nodes bottom-up using ``fn``."""

    expression = _coerce_expression(expression, "expression")
    if not callable(fn):
        raise TypeError("replacement function must be callable")
    return _replace(expression, fn)


def _replace(
    expression: Expression,
    fn: Callable[[Expression], Expression | str],
) -> Expression:
    children = expression.children
    replaced_children = tuple(_replace(child, fn) for child in children)
    if any(
        replacement is not original
        for original, replacement in zip(children, replaced_children)
    ):
        candidate = expression._with_children(replaced_children)
        if not isinstance(candidate, Expression):
            raise TypeError(
                f"{type(expression).__name__}._with_children() must return "
                "an Expression"
            )
    else:
        candidate = expression

    result = fn(candidate)
    if isinstance(result, str):
        result = _coerce_expression(result, "replacement function result")
    if not isinstance(result, Expression):
        raise TypeError(
            "replacement function must return an Expression, "
            f"got {type(result).__name__}"
        )
    return result


def lower_derived(expression: Expression | str) -> Expression:
    expression = _coerce_expression(expression, "expression")
    return _lower(expression, set(), 0)


def _push_negation(expression: Expression, negated: bool = False) -> Expression:
    """Return ``expression`` in negation normal form without simplifying it."""

    match expression:
        case Bool(value=value):
            return Bool(not value if negated else value)
        case Proposition() | Equal():
            return Not(expression) if negated else expression
        case Not(operand=operand):
            return _push_negation(operand, not negated)
        case And(operands=operands):
            operator = Or if negated else And
            return operator(_push_negation(item, negated) for item in operands)
        case Or(operands=operands):
            operator = And if negated else Or
            return operator(_push_negation(item, negated) for item in operands)
        case RestrictiveSelection(interval=interval, body=body):
            operator = VacuousSelection if negated else RestrictiveSelection
            return operator(interval, _push_negation(body, negated))
        case VacuousSelection(interval=interval, body=body):
            operator = RestrictiveSelection if negated else VacuousSelection
            return operator(interval, _push_negation(body, negated))
        case Selection(parameter=parameter, inside=inside, outside=outside):
            return Selection(
                parameter,
                _push_negation(inside, negated),
                _push_negation(outside, negated),
            )
        case UniversalCondition(interval=interval, body=body):
            operator = ExistentialCondition if negated else UniversalCondition
            return operator(interval, _push_negation(body, negated))
        case ExistentialCondition(interval=interval, body=body):
            operator = UniversalCondition if negated else ExistentialCondition
            return operator(interval, _push_negation(body, negated))
        case Eventually(parameter=parameter, body=body):
            operator = UniversalCondition if negated else Eventually
            return operator(parameter, _push_negation(body, negated))
        case Until(parameter=parameter, left=left, right=right):
            operator = Release if negated else Until
            return operator(
                parameter,
                _push_negation(left, negated),
                _push_negation(right, negated),
            )
        case Release(parameter=parameter, left=left, right=right):
            operator = Until if negated else Release
            return operator(
                parameter,
                _push_negation(left, negated),
                _push_negation(right, negated),
            )
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _lower(expression: Expression, active: set[int], derived_depth: int) -> Expression:
    if isinstance(expression, DerivedExpression):
        if derived_depth >= 256:
            raise DerivedExpressionCycleError(
                "derived-expression lowering did not converge within 256 expansions"
            )
        identity = id(expression)
        if identity in active:
            raise DerivedExpressionCycleError(
                f"cycle while lowering {type(expression).__name__}"
            )
        active.add(identity)
        try:
            lowered = expression.lower()
            try:
                lowered = _coerce_expression(
                    lowered, f"{type(expression).__name__}.lower() result"
                )
            except (ParseError, TypeError) as error:
                raise DerivedExpressionError(
                    f"{type(expression).__name__}.lower() must return an "
                    "Expression or expression string"
                ) from error
            return _lower(lowered, active, derived_depth + 1)
        finally:
            active.remove(identity)

    match expression:
        case Bool() | Proposition() | Equal():
            return expression
        case Not(operand=operand):
            return Not(_lower(operand, active, derived_depth))
        case And(operands=operands):
            return And(_lower(item, active, derived_depth) for item in operands)
        case Or(operands=operands):
            return Or(_lower(item, active, derived_depth) for item in operands)
        case RestrictiveSelection(interval=interval, body=body):
            return RestrictiveSelection(interval, _lower(body, active, derived_depth))
        case VacuousSelection(interval=interval, body=body):
            return VacuousSelection(interval, _lower(body, active, derived_depth))
        case Selection(parameter=parameter, inside=inside, outside=outside):
            return Selection(
                parameter,
                _lower(inside, active, derived_depth),
                _lower(outside, active, derived_depth),
            )
        case UniversalCondition(interval=interval, body=body):
            return UniversalCondition(interval, _lower(body, active, derived_depth))
        case ExistentialCondition(interval=interval, body=body):
            return ExistentialCondition(interval, _lower(body, active, derived_depth))
        case Eventually(parameter=parameter, body=body):
            return Eventually(parameter, _lower(body, active, derived_depth))
        case Until(parameter=parameter, left=left, right=right):
            return Until(
                parameter,
                _lower(left, active, derived_depth),
                _lower(right, active, derived_depth),
            )
        case Release(parameter=parameter, left=left, right=right):
            return Release(
                parameter,
                _lower(left, active, derived_depth),
                _lower(right, active, derived_depth),
            )
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")
