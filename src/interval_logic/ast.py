from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Iterable

import portion as P

from .temporal import (
    RelativeInterval,
    TemporalParameter,
    TemporalParameterInput,
    coerce_temporal_parameter,
    span_parameter,
    temporal_parameter_key,
)

REAL_LINE = P.open(-P.inf, P.inf)

class Expression(ABC):
    """Base class for immutable interval-logic expressions."""

    @property
    @abstractmethod
    def children(self) -> tuple[Expression, ...]:
        """Immediate child expressions."""

    @property
    def depth(self) -> int:
        return 1 + max((child.depth for child in self.children), default=0)

    @property
    def node_count(self) -> int:
        return 1 + sum(child.node_count for child in self.children)

    def simplify(
        self,
        *,
        universe: P.Interval | None = None,
        max_nodes: int = 10_000,
    ) -> Expression:
        from .simplify import simplify

        return simplify(self, universe=universe, max_nodes=max_nodes)

    def replace(self, fn: Callable[[Expression], Expression | str], *fns: Callable[[Expression], Expression | str]) -> Expression:
        """Replace subexpressions bottom-up using ``fn``."""

        from .transform import replace

        new = replace(self, fn)
        return new.replace(*fns) if fns else new

    def __str__(self) -> str:
        from .pretty import format_expression

        return format_expression(self)

    def _repr_pretty_(self, printer: Any, cycle: bool) -> None:
        """Render bare expressions readably in IPython and Jupyter."""

        printer.text("..." if cycle else str(self))

    def __bool__(self) -> bool:
        raise TypeError(
            "logic expressions have no Python truth value; use satisfies() or satisfying_anchors()"
        )

    def __invert__(self) -> Expression:
        return Not(self)

    def __and__(self, other: Expression | bool | str) -> Expression:
        return And((self, as_expr(other)))

    def __rand__(self, other: Expression | bool | str) -> Expression:
        return And((as_expr(other), self))

    def __or__(self, other: Expression | bool | str) -> Expression:
        return Or((self, as_expr(other)))

    def __ror__(self, other: Expression | bool | str) -> Expression:
        return Or((as_expr(other), self))

    def eventually(self, parameter: TemporalParameterInput = None) -> Expression:
        return Eventually(parameter, self)

    def always(self, parameter: TemporalParameterInput = None) -> Expression:
        return UniversalCondition(parameter, self)

    def until(
        self,
        other: Expression | str,
        parameter: TemporalParameterInput = None,
    ) -> Expression:
        return Until(parameter, self, other)

    def weak_until(
        self,
        other: Expression | str,
        parameter: TemporalParameterInput = None,
    ) -> Expression:
        return WeakUntil(parameter, self, other)

    def release(
        self,
        other: Expression | str,
        parameter: TemporalParameterInput = None,
    ) -> Expression:
        return Release(parameter, self, other)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        """Rebuild this node with replacement children.

        The default supports derived expressions whose constructors accept
        their children as positional arguments. Expressions with additional
        constructor state can override this hook.
        """

        if len(children) != len(self.children):
            raise ValueError(
                f"{type(self).__name__} requires {len(self.children)} children, "
                f"got {len(children)}"
            )
        try:
            rebuilt = type(self)(*children)
        except TypeError as exc:
            raise TypeError(
                f"{type(self).__name__} cannot be rebuilt from replacement "
                "children; override _with_children()"
            ) from exc
        if not isinstance(rebuilt, Expression):
            raise TypeError(
                f"{type(self).__name__}._with_children() must return an Expression"
            )
        return rebuilt


class DerivedExpression(Expression, ABC):
    """Extension point for operators defined in terms of core expressions."""

    @abstractmethod
    def lower(self) -> Expression | str:
        """Return an equivalent expression using core or simpler derived nodes."""


class Term(ABC):
    """Base class for immutable natural-number terms."""

    def __str__(self) -> str:
        from .pretty import format_term

        return format_term(self)

    def __bool__(self) -> bool:
        raise TypeError("numeric terms have no Python truth value")

    def equals(self, other: Term | int) -> Expression:
        return Equal(self, other)

    def not_equals(self, other: Term | int) -> Expression:
        return Not(Equal(self, other))


@dataclass(frozen=True, slots=True)
class NaturalLiteral(Term):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise TypeError("NaturalLiteral value must be an integer")
        if self.value < 0:
            raise ValueError("NaturalLiteral value must be non-negative")


@dataclass(frozen=True, slots=True)
class Signal(Term):
    name: str

    def __post_init__(self) -> None:
        _require_name(self.name, "Signal")


@dataclass(frozen=True, slots=True)
class Bool(Expression):
    value: bool

    def __post_init__(self) -> None:
        if type(self.value) is not bool:
            raise TypeError("Bool value must be a bool")

    @property
    def children(self) -> tuple[Expression, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class Proposition(Expression):
    name: str

    def __post_init__(self) -> None:
        _require_name(self.name, "Proposition")

    @property
    def children(self) -> tuple[Expression, ...]:
        return ()


@dataclass(frozen=True, slots=True, init=False)
class Equal(Expression):
    left: Term
    right: Term

    def __init__(self, left: Term | int, right: Term | int):
        left_term = as_term(left)
        right_term = as_term(right)
        if term_key(right_term) < term_key(left_term):
            left_term, right_term = right_term, left_term
        object.__setattr__(self, "left", left_term)
        object.__setattr__(self, "right", right_term)

    @property
    def children(self) -> tuple[Expression, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class Not(Expression):
    operand: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "operand", _coerce_expression(self.operand, "Not operand")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.operand,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Not(children[0])


@dataclass(frozen=True, slots=True, init=False)
class And(Expression):
    operands: tuple[Expression, ...]

    def __init__(self, operands: Iterable[Expression | str]):
        values = _expression_tuple(operands, "And operands")
        object.__setattr__(self, "operands", values)

    @property
    def children(self) -> tuple[Expression, ...]:
        return self.operands

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return And(children)


@dataclass(frozen=True, slots=True, init=False)
class Or(Expression):
    operands: tuple[Expression, ...]

    def __init__(self, operands: Iterable[Expression | str]):
        values = _expression_tuple(operands, "Or operands")
        object.__setattr__(self, "operands", values)

    @property
    def children(self) -> tuple[Expression, ...]:
        return self.operands

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Or(children)


@dataclass(frozen=True, slots=True)
class RestrictiveSelection(Expression):
    interval: TemporalParameterInput
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "interval", coerce_temporal_parameter(self.interval)
        )
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "RestrictiveSelection body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return RestrictiveSelection(self.interval, children[0])

    @property
    def parameter(self) -> TemporalParameter:
        return self.interval


@dataclass(frozen=True, slots=True)
class VacuousSelection(Expression):
    interval: TemporalParameterInput
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "interval", coerce_temporal_parameter(self.interval)
        )
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "VacuousSelection body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return VacuousSelection(self.interval, children[0])

    @property
    def parameter(self) -> TemporalParameter:
        return self.interval


@dataclass(frozen=True, slots=True)
class Selection(Expression):
    parameter: TemporalParameterInput
    inside: Expression | str
    outside: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(self.parameter)
        )
        object.__setattr__(
            self, "inside", _coerce_expression(self.inside, "Selection inside operand")
        )
        object.__setattr__(
            self,
            "outside",
            _coerce_expression(self.outside, "Selection outside operand"),
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.inside, self.outside)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Selection(self.parameter, children[0], children[1])


@dataclass(frozen=True, slots=True)
class UniversalCondition(Expression):
    interval: TemporalParameterInput
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "interval", coerce_temporal_parameter(self.interval)
        )
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "UniversalCondition body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return UniversalCondition(self.interval, children[0])

    @property
    def parameter(self) -> TemporalParameter:
        return self.interval


@dataclass(frozen=True, slots=True)
class ExistentialCondition(Expression):
    interval: TemporalParameterInput
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "interval", coerce_temporal_parameter(self.interval)
        )
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "ExistentialCondition body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return ExistentialCondition(self.interval, children[0])

    @property
    def parameter(self) -> TemporalParameter:
        return self.interval


@dataclass(frozen=True, slots=True)
class Eventually(Expression):
    """Require ``body`` at some time in the resolved parameter window."""

    parameter: TemporalParameterInput
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(self.parameter)
        )
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "Eventually body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Eventually(self.parameter, children[0])

    @property
    def delta(self) -> float | None:
        """Compatibility duration for a finite closed one-sided parameter."""

        if not isinstance(self.parameter, RelativeInterval):
            return None
        atoms = list(self.parameter.offsets)
        if len(atoms) != 1:
            return None
        atom = atoms[0]
        if (
            atom.lower == 0
            and atom.left.name == "CLOSED"
            and atom.right.name == "CLOSED"
            and atom.upper != P.inf
        ):
            return float(atom.upper)
        return None


@dataclass(frozen=True, slots=True)
class Until(Expression):
    parameter: TemporalParameterInput
    left: Expression | str
    right: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(self.parameter)
        )
        object.__setattr__(
            self, "left", _coerce_expression(self.left, "Until left operand")
        )
        object.__setattr__(
            self, "right", _coerce_expression(self.right, "Until right operand")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Until(self.parameter, children[0], children[1])


@dataclass(frozen=True, slots=True)
class Release(Expression):
    parameter: TemporalParameterInput
    left: Expression | str
    right: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(self.parameter)
        )
        object.__setattr__(
            self, "left", _coerce_expression(self.left, "Release left operand")
        )
        object.__setattr__(
            self, "right", _coerce_expression(self.right, "Release right operand")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Release(self.parameter, children[0], children[1])


@dataclass(frozen=True, slots=True)
class WeakUntil(DerivedExpression):
    parameter: TemporalParameterInput
    left: Expression | str
    right: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(self.parameter)
        )
        object.__setattr__(
            self, "left", _coerce_expression(self.left, "WeakUntil left operand")
        )
        object.__setattr__(
            self,
            "right",
            _coerce_expression(self.right, "WeakUntil right operand"),
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.left, self.right)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return WeakUntil(self.parameter, children[0], children[1])

    def lower(self) -> Expression:
        return Or(
            (
                Until(self.parameter, self.left, self.right),
                UniversalCondition(span_parameter(self.parameter), self.left),
            )
        )


CoreExpression = (
    Bool
    | Proposition
    | Equal
    | Not
    | And
    | Or
    | RestrictiveSelection
    | VacuousSelection
    | Selection
    | UniversalCondition
    | ExistentialCondition
    | Eventually
    | Until
    | Release
)


def as_expr(value: Expression | bool | str) -> Expression:
    if isinstance(value, Expression):
        return value
    if type(value) is bool:
        return Bool(value)
    if isinstance(value, str):
        from .parser import parse_expression

        return parse_expression(value)
    raise TypeError(
        "expected Expression, expression string, or bool, "
        f"got {type(value).__name__}"
    )


def as_term(value: Term | int) -> Term:
    if isinstance(value, Term):
        return value
    if type(value) is int:
        return NaturalLiteral(value)
    raise TypeError(f"expected Term or int, got {type(value).__name__}")


def term_key(term: Term) -> tuple[Any, ...]:
    """A deterministic ordering key for canonical equality expressions."""

    match term:
        case Signal(name=name):
            return (0, name)
        case NaturalLiteral(value=value):
            return (1, value)
        case _:
            raise TypeError(f"unsupported term type: {type(term).__name__}")


def expression_key(expression: Expression | str) -> tuple[Any, ...]:
    """A deterministic ordering key for canonical commutative expressions."""

    expression = _coerce_expression(expression, "expression")

    match expression:
        case Bool(value=value):
            return (0, value)
        case Proposition(name=name):
            return (1, name)
        case Equal(left=left, right=right):
            return (2, term_key(left), term_key(right))
        case Not(operand=operand):
            return (3, expression_key(operand))
        case And(operands=operands):
            return (4, tuple(expression_key(item) for item in operands))
        case Or(operands=operands):
            return (5, tuple(expression_key(item) for item in operands))
        case RestrictiveSelection(interval=interval, body=body):
            return (6, temporal_parameter_key(interval), expression_key(body))
        case VacuousSelection(interval=interval, body=body):
            return (7, temporal_parameter_key(interval), expression_key(body))
        case Selection(parameter=parameter, inside=inside, outside=outside):
            return (
                8,
                temporal_parameter_key(parameter),
                expression_key(inside),
                expression_key(outside),
            )
        case UniversalCondition(interval=interval, body=body):
            return (9, temporal_parameter_key(interval), expression_key(body))
        case ExistentialCondition(interval=interval, body=body):
            return (10, temporal_parameter_key(interval), expression_key(body))
        case Eventually(parameter=parameter, body=body):
            return (11, temporal_parameter_key(parameter), expression_key(body))
        case Until(parameter=parameter, left=left, right=right):
            return (
                12,
                temporal_parameter_key(parameter),
                expression_key(left),
                expression_key(right),
            )
        case Release(parameter=parameter, left=left, right=right):
            return (
                13,
                temporal_parameter_key(parameter),
                expression_key(left),
                expression_key(right),
            )
        case DerivedExpression():
            return (
                14,
                type(expression).__module__,
                type(expression).__qualname__,
                repr(expression),
            )
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _coerce_expression(value: Expression | str, label: str) -> Expression:
    if isinstance(value, Expression):
        return value
    if isinstance(value, str):
        from .parser import parse_expression

        return parse_expression(value)
    raise TypeError(f"{label} must be an Expression or expression string")


def _require_name(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} name must be a string")
    if not value:
        raise ValueError(f"{label} name must not be empty")


def _coerce_interval(value: P.Interval | str) -> P.Interval:
    interval = coerce_temporal_parameter(value)
    if not isinstance(interval, P.Interval):
        raise TypeError("expected an absolute temporal parameter")
    return interval


def _expression_tuple(
    values: Iterable[Expression | str], label: str
) -> tuple[Expression, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(
            f"{label} must be an iterable of Expression objects or strings"
        )
    try:
        result = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{label} must be iterable") from exc
    return tuple(_coerce_expression(value, label) for value in result)


def _interval_key(interval: P.Interval) -> tuple[Any, ...]:
    return tuple(
        (repr(atom.lower), repr(atom.upper), atom.left.name, atom.right.name)
        for atom in interval
    )
