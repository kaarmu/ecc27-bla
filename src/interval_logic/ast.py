"""Immutable abstract syntax for the interval logic in ``LOGIC.md``."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeAlias

from .temporal import (
    TemporalParameter,
    TemporalParameterInput,
    TimeSet,
    TimeValue,
    coerce_temporal_parameter,
    temporal_parameter_key,
)


NaturalValue: TypeAlias = int


class Formula(ABC):
    """Abstract base for immutable formula nodes."""

    @property
    @abstractmethod
    def children(self) -> tuple[Formula, ...]:
        raise NotImplementedError

    @property
    def depth(self) -> int:
        return 1 + max((child.depth for child in self.children), default=-1)

    @property
    def node_count(self) -> int:
        return 1 + sum(child.node_count for child in self.children)

    def __bool__(self) -> bool:
        raise TypeError(
            "logic formulas have no Python truth value; use satisfies() instead"
        )

    def __str__(self) -> str:
        from .pretty import format_formula

        return format_formula(self)

    def _repr_pretty_(self, printer: Any, cycle: bool) -> None:
        printer.text("..." if cycle else str(self))

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Formula):
            return NotImplemented
        return formula_key(self) < formula_key(other)

    def __invert__(self) -> Formula:
        return Not(self)

    def __and__(self, other: Formula | bool | str) -> Formula:
        return And((self, as_formula(other)))

    def __rand__(self, other: Formula | bool | str) -> Formula:
        return And((as_formula(other), self))

    def __or__(self, other: Formula | bool | str) -> Formula:
        return Or((self, as_formula(other)))

    def __ror__(self, other: Formula | bool | str) -> Formula:
        return Or((as_formula(other), self))

    def implies(self, other: Formula | bool | str) -> Formula:
        return Implies(self, other)

    def equivalent(self, other: Formula | bool | str) -> Formula:
        return Equivalent(self, other)

    def select(
        self,
        outside: Formula | bool | str = True,
        parameter: TemporalParameterInput = None,
    ) -> Formula:
        return Selection(self, outside, parameter)

    def select_vac(self, parameter: TemporalParameterInput = None) -> Formula:
        return VacuousSelection(self, parameter)

    def select_res(self, parameter: TemporalParameterInput = None) -> Formula:
        return RestrictiveSelection(self, parameter)

    def until(
        self,
        other: Formula | bool | str,
        parameter: TemporalParameterInput = None,
    ) -> Formula:
        return Until(self, other, parameter)

    def eventually(self, parameter: TemporalParameterInput = None) -> Formula:
        return Eventually(self, parameter)

    def always(self, parameter: TemporalParameterInput = None) -> Formula:
        return Always(self, parameter)

    def release(
        self,
        other: Formula | bool | str,
        parameter: TemporalParameterInput = None,
    ) -> Formula:
        return Release(self, other, parameter)

    def replace(
        self, *functions: Callable[[Formula], Formula | str]
    ) -> Formula:
        from .transform import replace

        return replace(self, *functions)

    def simplify(
        self, *, anchor: TimeValue | None = None, universe: TimeSet | None = None,
    ) -> Formula:
        from .simplify import simplify

        return simplify(self, anchor=anchor, universe=universe)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        if len(children) != len(self.children):
            raise ValueError(
                f"{type(self).__name__} requires {len(self.children)} children, "
                f"got {len(children)}"
            )
        return type(self)(*children)


class NumericTerm(ABC):
    """Abstract base for natural-valued terms."""

    @abstractmethod
    def __init__(self) -> None:
        """Concrete immutable terms supply their own value constructor."""

    def __bool__(self) -> bool:
        raise TypeError("numeric terms have no Python truth value")

    def __str__(self) -> str:
        from .pretty import format_term

        return format_term(self)

    def equals(self, other: NumericTerm | int) -> Formula:
        return Equal(self, other)

    def not_equals(self, other: NumericTerm | int) -> Formula:
        return Not(Equal(self, other))


@dataclass(frozen=True, slots=True)
class NaturalLiteral(NumericTerm):
    value: NaturalValue

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise TypeError("NaturalLiteral value must be an integer")
        if self.value < 0:
            raise ValueError("NaturalLiteral value must be non-negative")


@dataclass(frozen=True, slots=True)
class Signal(NumericTerm):
    name: str

    def __post_init__(self) -> None:
        _require_name(self.name, "Signal")


@dataclass(frozen=True, slots=True)
class Boolean(Formula):
    value: bool

    def __post_init__(self) -> None:
        if type(self.value) is not bool:
            raise TypeError("Boolean value must be a bool")

    @property
    def children(self) -> tuple[Formula, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class Proposition(Formula):
    name: str

    def __post_init__(self) -> None:
        _require_name(self.name, "Proposition")

    @property
    def children(self) -> tuple[Formula, ...]:
        return ()


@dataclass(frozen=True, slots=True, init=False)
class Equal(Formula):
    left: NumericTerm
    right: NumericTerm

    def __init__(self, left: NumericTerm | int, right: NumericTerm | int):
        left_term = as_term(left)
        right_term = as_term(right)
        if term_key(right_term) < term_key(left_term):
            left_term, right_term = right_term, left_term
        object.__setattr__(self, "left", left_term)
        object.__setattr__(self, "right", right_term)

    @property
    def children(self) -> tuple[Formula, ...]:
        return ()


@dataclass(frozen=True, slots=True, init=False)
class Not(Formula):
    operand: Formula

    def __init__(self, operand: Formula | str | bool):
        object.__setattr__(self, "operand", as_formula(operand))

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.operand,)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Not(children[0])


@dataclass(frozen=True, slots=True, init=False)
class And(Formula):
    operands: tuple[Formula, ...]

    def __init__(self, operands: Iterable[Formula | str | bool]):
        object.__setattr__(self, "operands", _formula_tuple(operands, "And operands"))

    @property
    def children(self) -> tuple[Formula, ...]:
        return self.operands

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return And(children)


@dataclass(frozen=True, slots=True, init=False)
class Or(Formula):
    operands: tuple[Formula, ...]

    def __init__(self, operands: Iterable[Formula | str | bool]):
        object.__setattr__(self, "operands", _formula_tuple(operands, "Or operands"))

    @property
    def children(self) -> tuple[Formula, ...]:
        return self.operands

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Or(children)


@dataclass(frozen=True, slots=True, init=False)
class Implies(Formula):
    left: Formula
    right: Formula

    def __init__(
        self,
        left: Formula | str | bool,
        right: Formula | str | bool,
    ) -> None:
        object.__setattr__(self, "left", as_formula(left))
        object.__setattr__(self, "right", as_formula(right))

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.left, self.right)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Implies(*children)


@dataclass(frozen=True, slots=True, init=False)
class Equivalent(Formula):
    left: Formula
    right: Formula

    def __init__(
        self,
        left: Formula | str | bool,
        right: Formula | str | bool,
    ) -> None:
        object.__setattr__(self, "left", as_formula(left))
        object.__setattr__(self, "right", as_formula(right))

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.left, self.right)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Equivalent(*children)


@dataclass(frozen=True, slots=True, init=False)
class Selection(Formula):
    inside: Formula
    outside: Formula
    parameter: TemporalParameter

    def __init__(
        self,
        inside: Formula | str | bool,
        outside: Formula | str | bool,
        parameter: TemporalParameterInput = None,
    ) -> None:
        object.__setattr__(self, "inside", as_formula(inside))
        object.__setattr__(self, "outside", as_formula(outside))
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(parameter)
        )

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.inside, self.outside)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Selection(*children, self.parameter)


@dataclass(frozen=True, slots=True, init=False)
class VacuousSelection(Formula):
    body: Formula
    parameter: TemporalParameter

    def __init__(
        self,
        body: Formula | str | bool,
        parameter: TemporalParameterInput = None,
    ) -> None:
        object.__setattr__(self, "body", as_formula(body))
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(parameter)
        )

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return VacuousSelection(children[0], self.parameter)


@dataclass(frozen=True, slots=True, init=False)
class RestrictiveSelection(Formula):
    body: Formula
    parameter: TemporalParameter

    def __init__(
        self,
        body: Formula | str | bool,
        parameter: TemporalParameterInput = None,
    ) -> None:
        object.__setattr__(self, "body", as_formula(body))
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(parameter)
        )

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return RestrictiveSelection(children[0], self.parameter)


@dataclass(frozen=True, slots=True, init=False)
class Until(Formula):
    left: Formula
    right: Formula
    parameter: TemporalParameter

    def __init__(
        self,
        left: Formula | str | bool,
        right: Formula | str | bool,
        parameter: TemporalParameterInput = None,
    ) -> None:
        object.__setattr__(self, "left", as_formula(left))
        object.__setattr__(self, "right", as_formula(right))
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(parameter)
        )

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.left, self.right)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Until(*children, self.parameter)


@dataclass(frozen=True, slots=True, init=False)
class Eventually(Formula):
    body: Formula
    parameter: TemporalParameter

    def __init__(
        self,
        body: Formula | str | bool,
        parameter: TemporalParameterInput = None,
    ) -> None:
        object.__setattr__(self, "body", as_formula(body))
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(parameter)
        )

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Eventually(children[0], self.parameter)


@dataclass(frozen=True, slots=True, init=False)
class Always(Formula):
    body: Formula
    parameter: TemporalParameter

    def __init__(
        self,
        body: Formula | str | bool,
        parameter: TemporalParameterInput = None,
    ) -> None:
        object.__setattr__(self, "body", as_formula(body))
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(parameter)
        )

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.body,)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Always(children[0], self.parameter)


@dataclass(frozen=True, slots=True, init=False)
class Release(Formula):
    left: Formula
    right: Formula
    parameter: TemporalParameter

    def __init__(
        self,
        left: Formula | str | bool,
        right: Formula | str | bool,
        parameter: TemporalParameterInput = None,
    ) -> None:
        object.__setattr__(self, "left", as_formula(left))
        object.__setattr__(self, "right", as_formula(right))
        object.__setattr__(
            self, "parameter", coerce_temporal_parameter(parameter)
        )

    @property
    def children(self) -> tuple[Formula, ...]:
        return (self.left, self.right)

    def _with_children(self, children: tuple[Formula, ...]) -> Formula:
        return Release(*children, self.parameter)


TEMPORAL_NODE_TYPES = (
    Selection,
    VacuousSelection,
    RestrictiveSelection,
    Until,
    Eventually,
    Always,
    Release,
)


def as_formula(value: Formula | bool | str) -> Formula:
    if isinstance(value, Formula):
        return value
    if type(value) is bool:
        return Boolean(value)
    if isinstance(value, str):
        from .parser import parse_formula

        return parse_formula(value)
    raise TypeError(
        "expected Formula, formula string, or bool, "
        f"got {type(value).__name__}"
    )


def as_term(value: NumericTerm | int) -> NumericTerm:
    if isinstance(value, NumericTerm):
        return value
    if type(value) is int:
        return NaturalLiteral(value)
    raise TypeError(f"expected NumericTerm or int, got {type(value).__name__}")


def term_key(term: NumericTerm) -> tuple[Any, ...]:
    match term:
        case Signal(name=name):
            return (0, name)
        case NaturalLiteral(value=value):
            return (1, value)
        case _:
            raise TypeError(f"unsupported term type: {type(term).__name__}")


def formula_key(formula: Formula | str) -> tuple[Any, ...]:
    formula = as_formula(formula)
    match formula:
        case Boolean(value=value):
            return (0, value)
        case Proposition(name=name):
            return (1, name)
        case Equal(left=left, right=right):
            return (2, term_key(left), term_key(right))
        case Not(operand=operand):
            return (3, formula_key(operand))
        case And(operands=operands):
            return (4, tuple(formula_key(item) for item in operands))
        case Or(operands=operands):
            return (5, tuple(formula_key(item) for item in operands))
        case Implies(left=left, right=right):
            return (6, formula_key(left), formula_key(right))
        case Equivalent(left=left, right=right):
            return (7, formula_key(left), formula_key(right))
        case Selection(inside=inside, outside=outside, parameter=parameter):
            return (8, temporal_parameter_key(parameter), formula_key(inside), formula_key(outside))
        case VacuousSelection(body=body, parameter=parameter):
            return (9, temporal_parameter_key(parameter), formula_key(body))
        case RestrictiveSelection(body=body, parameter=parameter):
            return (10, temporal_parameter_key(parameter), formula_key(body))
        case Until(left=left, right=right, parameter=parameter):
            return (11, temporal_parameter_key(parameter), formula_key(left), formula_key(right))
        case Eventually(body=body, parameter=parameter):
            return (12, temporal_parameter_key(parameter), formula_key(body))
        case Always(body=body, parameter=parameter):
            return (13, temporal_parameter_key(parameter), formula_key(body))
        case Release(left=left, right=right, parameter=parameter):
            return (14, temporal_parameter_key(parameter), formula_key(left), formula_key(right))
        case _:
            raise TypeError(f"unsupported formula type: {type(formula).__name__}")


def _require_name(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} name must be a string")
    if not value:
        raise ValueError(f"{label} name must not be empty")


def _formula_tuple(
    values: Iterable[Formula | str | bool], label: str
) -> tuple[Formula, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be an iterable of formulas")
    try:
        result = tuple(values)
    except TypeError as error:
        raise TypeError(f"{label} must be iterable") from error
    return tuple(as_formula(value) for value in result)
