from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Any, Iterable

import portion as P

ALL_TIME = P.open(-P.inf, P.inf)

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
            "logic expressions have no Python truth value; use holds() or denote()"
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

    def restrict(self, interval: P.Interval | str) -> Expression:
        return Restrict(interval, self)

    def guard(self, interval: P.Interval | str) -> Expression:
        return Guard(interval, self)
    
    def forall(self, interval: P.Interval) -> Expression:
        return ForAll(interval, self)
    
    def exists(self, interval: P.Interval) -> Expression:
        return Exists(interval, self)

    def hold(self, delta: Real) -> Expression:
        return Hold(delta, self)

    def eventually(self, delta: Real) -> Expression:
        return Eventually(delta, self)

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
class Natural(Term):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise TypeError("Natural value must be an integer")
        if self.value < 0:
            raise ValueError("Natural value must be non-negative")


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
class Atom(Expression):
    name: str

    def __post_init__(self) -> None:
        _require_name(self.name, "Atom")

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
class Restrict(Expression):
    interval: P.Interval | str
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "interval", _coerce_interval(self.interval))
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "Restrict body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Restrict(self.interval, children[0])


@dataclass(frozen=True, slots=True)
class Guard(Expression):
    interval: P.Interval | str
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "interval", _coerce_interval(self.interval))
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "Guard body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Guard(self.interval, children[0])


@dataclass(frozen=True, slots=True)
class ForAll(Expression):
    interval: P.Interval | str
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "interval", _coerce_interval(self.interval))
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "ForAll body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return ForAll(self.interval, children[0])


@dataclass(frozen=True, slots=True)
class Exists(Expression):
    interval: P.Interval | str
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "interval", _coerce_interval(self.interval))
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "Exists body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Exists(self.interval, children[0])


@dataclass(frozen=True, slots=True)
class Hold(Expression):
    """Require ``body`` throughout the closed window ``[now, now + delta]``."""

    delta: float
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "delta", _coerce_duration(self.delta, "Hold"))
        object.__setattr__(self, "body", _coerce_expression(self.body, "Hold body"))

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Hold(self.delta, children[0])


@dataclass(frozen=True, slots=True)
class Eventually(Expression):
    """Require ``body`` at some time in ``[now, now + delta]``."""

    delta: float
    body: Expression | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "delta", _coerce_duration(self.delta, "Eventually")
        )
        object.__setattr__(
            self, "body", _coerce_expression(self.body, "Eventually body")
        )

    @property
    def children(self) -> tuple[Expression, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Expression, ...]) -> Expression:
        return Eventually(self.delta, children[0])


CoreExpression = (
    Bool
    | Atom
    | Equal
    | Not
    | And
    | Or
    | Restrict
    | Guard
    | ForAll
    | Exists
    | Hold
    | Eventually
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
        return Natural(value)
    raise TypeError(f"expected Term or int, got {type(value).__name__}")


def term_key(term: Term) -> tuple[Any, ...]:
    """A deterministic ordering key for canonical equality expressions."""

    match term:
        case Signal(name=name):
            return (0, name)
        case Natural(value=value):
            return (1, value)
        case _:
            raise TypeError(f"unsupported term type: {type(term).__name__}")


def expression_key(expression: Expression | str) -> tuple[Any, ...]:
    """A deterministic ordering key for canonical commutative expressions."""

    expression = _coerce_expression(expression, "expression")

    match expression:
        case Bool(value=value):
            return (0, value)
        case Atom(name=name):
            return (1, name)
        case Equal(left=left, right=right):
            return (2, term_key(left), term_key(right))
        case Not(operand=operand):
            return (3, expression_key(operand))
        case And(operands=operands):
            return (4, tuple(expression_key(item) for item in operands))
        case Or(operands=operands):
            return (5, tuple(expression_key(item) for item in operands))
        case Restrict(interval=interval, body=body):
            return (6, _interval_key(interval), expression_key(body))
        case Guard(interval=interval, body=body):
            return (7, _interval_key(interval), expression_key(body))
        case ForAll(interval=interval, body=body):
            return (8, _interval_key(interval), expression_key(body))
        case Exists(interval=interval, body=body):
            return (9, _interval_key(interval), expression_key(body))
        case Hold(delta=delta, body=body):
            return (10, delta, expression_key(body))
        case Eventually(delta=delta, body=body):
            return (11, delta, expression_key(body))
        case DerivedExpression():
            return (
                12,
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


def _coerce_duration(value: Real, operator: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{operator} delta must be a real number")
    delta = float(value)
    if not isfinite(delta):
        raise ValueError(f"{operator} delta must be finite")
    if delta < 0:
        raise ValueError(f"{operator} delta must be non-negative")
    return 0.0 if delta == 0 else delta


def _require_name(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} name must be a string")
    if not value:
        raise ValueError(f"{label} name must not be empty")


def _coerce_interval(value: P.Interval | str) -> P.Interval:
    if isinstance(value, P.Interval):
        return value
    if isinstance(value, str):
        return P.from_string(value, float)
    raise TypeError("interval must be a portion.Interval or string")


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
