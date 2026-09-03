"""Precedence-aware formula formatting."""

from __future__ import annotations

from dataclasses import dataclass

from .ast import (
    Always,
    And,
    Boolean,
    Equal,
    Equivalent,
    Eventually,
    Formula,
    Implies,
    NaturalLiteral,
    Not,
    NumericTerm,
    Or,
    Proposition,
    Release,
    RestrictiveSelection,
    Selection,
    Signal,
    Until,
    VacuousSelection,
    WeakUntil,
    as_formula,
    as_term,
)
from .temporal import TemporalParameter, format_temporal_parameter


@dataclass(frozen=True, slots=True)
class _Symbols:
    true: str
    false: str
    not_: str
    and_: str
    or_: str
    implies: str
    equivalent: str
    equal: str
    not_equal: str


_UNICODE = _Symbols(
    "⊤", "⊥", "¬", " ∧ ", " ∨ ", " → ", " ↔ ", " = ", " ≠ "
)
_ASCII = _Symbols(
    "true", "false", "not ", " and ", " or ", " implies ",
    " equivalent ", " = ", " != "
)

_EQUIVALENT = 20
_IMPLIES = 30
_OR = 40
_AND = 50
_TEMPORAL = 60
_NOT = 70
_PRIMARY = 80


def format_formula(formula: Formula | str, *, unicode: bool = True) -> str:
    """Format a formula using canonical Unicode or ASCII notation."""

    symbols = _UNICODE if unicode else _ASCII
    return _format(as_formula(formula), symbols, 0)


def format_term(
    term: NumericTerm | int, *, unicode: bool = True
) -> str:
    """Format a numeric term (the Unicode flag is accepted for API symmetry)."""

    del unicode
    match as_term(term):
        case NaturalLiteral(value=value):
            return str(value)
        case Signal(name=name):
            return _format_name(name)
        case _:
            raise TypeError("term must be a NumericTerm or natural integer")


def _format(formula: Formula, symbols: _Symbols, parent: int) -> str:
    precedence = _precedence(formula)
    match formula:
        case Boolean(value=True):
            text = symbols.true
        case Boolean(value=False):
            text = symbols.false
        case Proposition(name=name):
            text = _format_name(name)
        case Equal(left=left, right=right):
            text = format_term(left) + symbols.equal + format_term(right)
        case Not(operand=Equal(left=left, right=right)):
            text = format_term(left) + symbols.not_equal + format_term(right)
        case Not(operand=operand):
            text = symbols.not_ + _format(operand, symbols, _NOT)
        case And(operands=()):
            text = symbols.true
        case And(operands=operands):
            text = symbols.and_.join(
                _format(item, symbols, _AND + 1) for item in operands
            )
        case Or(operands=()):
            text = symbols.false
        case Or(operands=operands):
            text = symbols.or_.join(
                _format(item, symbols, _OR + 1) for item in operands
            )
        case Implies(left=left, right=right):
            text = (
                _format(left, symbols, _IMPLIES + 1)
                + symbols.implies
                + _format(right, symbols, _IMPLIES)
            )
        case Equivalent(left=left, right=right):
            text = (
                _format(left, symbols, _EQUIVALENT + 1)
                + symbols.equivalent
                + _format(right, symbols, _EQUIVALENT + 1)
            )
        case Selection(inside=inside, outside=outside, parameter=parameter):
            if symbols is _UNICODE:
                text = (
                    f"⟨{_format(inside, symbols, 0)}, "
                    f"{_format(outside, symbols, 0)}⟩{_suffix(parameter)}"
                )
            else:
                text = (
                    f"select({_format(inside, symbols, 0)}, "
                    f"{_format(outside, symbols, 0)}){_suffix(parameter)}"
                )
        case VacuousSelection(body=body, parameter=parameter):
            if symbols is _UNICODE:
                text = f"⟨{_format(body, symbols, 0)}⟩{_suffix(parameter)}"
            else:
                text = f"select({_format(body, symbols, 0)}){_suffix(parameter)}"
        case RestrictiveSelection(body=body, parameter=parameter):
            if symbols is _UNICODE:
                text = f"⟨{_format(body, symbols, 0)}⟩*{_suffix(parameter)}"
            else:
                text = f"select({_format(body, symbols, 0)})*{_suffix(parameter)}"
        case Eventually(body=body, parameter=parameter):
            operator = "◇" if symbols is _UNICODE else "eventually"
            text = f"{operator}{_suffix(parameter)} {_format(body, symbols, _NOT)}"
        case Always(body=body, parameter=parameter):
            operator = "□" if symbols is _UNICODE else "always"
            text = f"{operator}{_suffix(parameter)} {_format(body, symbols, _NOT)}"
        case Until(left=left, right=right, parameter=parameter):
            text = _temporal_infix("U", "until", parameter, left, right, symbols)
        case WeakUntil(left=left, right=right, parameter=parameter):
            text = _temporal_infix(
                "W", "weak_until", parameter, left, right, symbols
            )
        case Release(left=left, right=right, parameter=parameter):
            text = _temporal_infix("R", "release", parameter, left, right, symbols)
        case _:
            raise TypeError(f"unsupported formula type: {type(formula).__name__}")
    return f"({text})" if precedence < parent else text


def _temporal_infix(
    unicode_operator: str,
    ascii_operator: str,
    parameter: TemporalParameter,
    left: Formula,
    right: Formula,
    symbols: _Symbols,
) -> str:
    operator = unicode_operator if symbols is _UNICODE else ascii_operator
    return (
        _format(left, symbols, _TEMPORAL + 1)
        + f" {operator}{_suffix(parameter)} "
        + _format(right, symbols, _TEMPORAL)
    )


def _precedence(formula: Formula) -> int:
    if isinstance(formula, Equivalent):
        return _EQUIVALENT
    if isinstance(formula, Implies):
        return _IMPLIES
    if isinstance(formula, Or):
        return _OR
    if isinstance(formula, And):
        return _AND
    if isinstance(formula, (Until, WeakUntil, Release)):
        return _TEMPORAL
    if isinstance(formula, (Not, Always, Eventually)):
        return _NOT
    return _PRIMARY


def _suffix(parameter: TemporalParameter) -> str:
    formatted = format_temporal_parameter(parameter)
    return "" if not formatted else "_" + formatted


def _format_name(name: str) -> str:
    reserved = {
        "true", "false", "not", "and", "or", "implies", "equivalent",
        "select", "always", "eventually", "until", "weak_until", "release",
        "U", "W", "R",
    }
    if name.isidentifier() and name not in reserved:
        return name
    escaped = name.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{escaped}`"
