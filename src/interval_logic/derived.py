from __future__ import annotations

from dataclasses import dataclass

from .ast import And, DerivedExpression, Expression, Not, Or, _require_expression


@dataclass(frozen=True, slots=True)
class Implies(DerivedExpression):
    left: Expression
    right: Expression

    def __post_init__(self) -> None:
        _require_expression(self.left, "Implies left operand")
        _require_expression(self.right, "Implies right operand")

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    def lower(self) -> Expression:
        return Or((Not(self.left), self.right))


@dataclass(frozen=True, slots=True)
class Equivalent(DerivedExpression):
    left: Expression
    right: Expression

    def __post_init__(self) -> None:
        _require_expression(self.left, "Equivalent left operand")
        _require_expression(self.right, "Equivalent right operand")

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    def lower(self) -> Expression:
        return Or(
            (
                And((self.left, self.right)),
                And((Not(self.left), Not(self.right))),
            )
        )


@dataclass(frozen=True, slots=True)
class Xor(DerivedExpression):
    left: Expression
    right: Expression

    def __post_init__(self) -> None:
        _require_expression(self.left, "Xor left operand")
        _require_expression(self.right, "Xor right operand")

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    def lower(self) -> Expression:
        return Or(
            (
                And((self.left, Not(self.right))),
                And((Not(self.left), self.right)),
            )
        )
