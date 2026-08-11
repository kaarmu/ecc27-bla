from __future__ import annotations

from dataclasses import dataclass

from .ast import And, DerivedExpression, Expression, Not, Or, _coerce_expression


@dataclass(frozen=True, slots=True)
class Implies(DerivedExpression):
    left: Expression | str
    right: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "left", _coerce_expression(self.left, "Implies left operand")
        )
        object.__setattr__(
            self, "right", _coerce_expression(self.right, "Implies right operand")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    def lower(self) -> Expression:
        return Or((Not(self.left), self.right))


@dataclass(frozen=True, slots=True)
class Equivalent(DerivedExpression):
    left: Expression | str
    right: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "left", _coerce_expression(self.left, "Equivalent left operand")
        )
        object.__setattr__(
            self,
            "right",
            _coerce_expression(self.right, "Equivalent right operand"),
        )

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
    left: Expression | str
    right: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "left", _coerce_expression(self.left, "Xor left operand")
        )
        object.__setattr__(
            self, "right", _coerce_expression(self.right, "Xor right operand")
        )

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
