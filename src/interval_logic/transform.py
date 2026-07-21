from __future__ import annotations

from .ast import (
    And,
    Atom,
    Bool,
    DerivedExpression,
    Equal,
    Exists,
    Expression,
    ForAll,
    Guard,
    Not,
    Or,
    Restrict,
)
from .errors import DerivedExpressionCycleError, DerivedExpressionError


def lower_derived(expression: Expression) -> Expression:
    if not isinstance(expression, Expression):
        raise TypeError("expression must be an Expression")
    return _lower(expression, set(), 0)


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
            if not isinstance(lowered, Expression):
                raise DerivedExpressionError(
                    f"{type(expression).__name__}.lower() must return an Expression"
                )
            return _lower(lowered, active, derived_depth + 1)
        finally:
            active.remove(identity)

    match expression:
        case Bool() | Atom() | Equal():
            return expression
        case Not(operand=operand):
            return Not(_lower(operand, active, derived_depth))
        case And(operands=operands):
            return And(_lower(item, active, derived_depth) for item in operands)
        case Or(operands=operands):
            return Or(_lower(item, active, derived_depth) for item in operands)
        case Restrict(interval=interval, body=body):
            return Restrict(interval, _lower(body, active, derived_depth))
        case Guard(interval=interval, body=body):
            return Guard(interval, _lower(body, active, derived_depth))
        case ForAll(interval=interval, body=body):
            return ForAll(interval, _lower(body, active, derived_depth))
        case Exists(interval=interval, body=body):
            return Exists(interval, _lower(body, active, derived_depth))
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")
