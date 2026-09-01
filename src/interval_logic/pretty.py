from __future__ import annotations

from dataclasses import dataclass

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
    WeakUntil,
    NaturalLiteral,
    Not,
    Or,
    RestrictiveSelection,
    Signal,
    Term,
    _coerce_expression,
)
from .derived import Equivalent, Implies, Xor
from .temporal import DEFAULT_TEMPORAL_PARAMETER, format_temporal_parameter


@dataclass(frozen=True, slots=True)
class _Symbols:
    true: str
    false: str
    not_: str
    and_: str
    or_: str
    forall: str
    exists: str
    selection_left: str
    selection_right: str
    implies: str
    equivalent: str
    xor: str
    equal: str
    not_equal: str


_UNICODE = _Symbols(
    "⊤", "⊥", "¬", " ∧ ", " ∨ ", "□", "◇", "⟨", "⟩", " → ", " ↔ ", " ⊕ ", " = ", " ≠ "
)
_ASCII = _Symbols(
    "true",
    "false",
    "!",
    " & ",
    " | ",
    "forall",
    "exists",
    "<",
    ">",
    " -> ",
    " <-> ",
    " xor ",
    " = ",
    " != ",
)

_EQUIVALENT = 20
_IMPLIES = 30
_XOR = 40
_OR = 50
_AND = 60
_TEMPORAL = 65
_NOT = 70
_PRIMARY = 80


def format_expression(expression: Expression | str, *, unicode: bool = True) -> str:
    """Format a formula with precedence-aware mathematical notation."""

    expression = _coerce_expression(expression, "expression")
    symbols = _UNICODE if unicode else _ASCII
    return _format(expression, symbols, parent_precedence=0)


def format_term(term: Term) -> str:
    """Format a natural-number term."""

    match term:
        case NaturalLiteral(value=value):
            return str(value)
        case Signal(name=name):
            return _format_name(name)
        case _:
            raise TypeError("term must be a Term")


def _format(
    expression: Expression,
    symbols: _Symbols,
    parent_precedence: int,
) -> str:
    precedence = _precedence(expression)

    match expression:
        case Bool(value=True):
            text = symbols.true
        case Bool(value=False):
            text = symbols.false
        case Proposition(name=name):
            text = _format_name(name)
        case Equal(left=left, right=right):
            text = format_term(left) + symbols.equal + format_term(right)
        case Not(operand=Equal(left=left, right=right)):
            text = format_term(left) + symbols.not_equal + format_term(right)
        case Not(operand=operand):
            rendered = _format(operand, symbols, _NOT)
            if isinstance(operand, Not) and isinstance(operand.operand, Equal):
                rendered = f"({rendered})"
            text = symbols.not_ + rendered
        case And(operands=()):
            text = symbols.true
        case And(operands=operands):
            text = symbols.and_.join(_format(item, symbols, _AND) for item in operands)
        case Or(operands=()):
            text = symbols.false
        case Or(operands=operands):
            text = symbols.or_.join(_format(item, symbols, _OR) for item in operands)
        case RestrictiveSelection(interval=interval, body=body):
            text = (
                f"{symbols.selection_left}{_format(body, symbols, 0)}"
                f"{symbols.selection_right}*{_parameter_suffix(interval)}"
            )
        case VacuousSelection(interval=interval, body=body):
            text = (
                f"{symbols.selection_left}{_format(body, symbols, 0)}"
                f"{symbols.selection_right}{_parameter_suffix(interval)}"
            )
        case Selection(parameter=parameter, inside=inside, outside=outside):
            text = (
                f"{symbols.selection_left}{_format(inside, symbols, 0)}, "
                f"{_format(outside, symbols, 0)}{symbols.selection_right}"
                f"{_parameter_suffix(parameter)}"
            )
        case UniversalCondition(interval=interval, body=body):
            operator = "□" if symbols is _UNICODE else "always"
            text = f"{operator}{_parameter_suffix(interval)} {_format(body, symbols, _NOT)}"
        case ExistentialCondition(interval=interval, body=body):
            operator = "◇" if symbols is _UNICODE else "eventually"
            text = f"{operator}{_parameter_suffix(interval)} {_format(body, symbols, _NOT)}"
        case Eventually(parameter=parameter, body=body):
            if expression.delta is not None:
                text = f"F^{_format_delta(expression.delta)} {_format(body, symbols, _NOT)}"
            else:
                text = f"F{_parameter_suffix(parameter)} {_format(body, symbols, _NOT)}"
        case Until(parameter=parameter, left=left, right=right):
            text = (
                _format(left, symbols, _TEMPORAL + 1)
                + f" U{_parameter_suffix(parameter)} "
                + _format(right, symbols, _TEMPORAL)
            )
        case WeakUntil(parameter=parameter, left=left, right=right):
            text = (
                _format(left, symbols, _TEMPORAL + 1)
                + f" W{_parameter_suffix(parameter)} "
                + _format(right, symbols, _TEMPORAL)
            )
        case Release(parameter=parameter, left=left, right=right):
            text = (
                _format(left, symbols, _TEMPORAL + 1)
                + f" R{_parameter_suffix(parameter)} "
                + _format(right, symbols, _TEMPORAL)
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
        case Xor(left=left, right=right):
            text = (
                _format(left, symbols, _XOR + 1)
                + symbols.xor
                + _format(right, symbols, _XOR + 1)
            )
        case DerivedExpression():
            arguments = ", ".join(_format(child, symbols, 0) for child in expression.children)
            text = f"{type(expression).__name__}({arguments})"
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")

    return f"({text})" if precedence < parent_precedence else text


def _precedence(expression: Expression) -> int:
    match expression:
        case Equivalent():
            return _EQUIVALENT
        case Implies():
            return _IMPLIES
        case Xor():
            return _XOR
        case Or():
            return _OR
        case Until() | WeakUntil() | Release():
            return _TEMPORAL
        case And():
            return _AND
        case Not() | Eventually() | UniversalCondition() | ExistentialCondition():
            return _NOT
        case Bool() | Proposition() | Equal() | RestrictiveSelection() | VacuousSelection() | Selection() | DerivedExpression():
            return _PRIMARY
        case _:
            raise TypeError(f"unsupported expression type: {type(expression).__name__}")


def _format_name(name: str) -> str:
    if name.isidentifier() and name not in {
        "true",
        "false",
        "forall",
        "exists",
        "always",
        "eventually",
    }:
        return name
    escaped = name.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{escaped}`"


def _format_delta(delta: float) -> str:
    text = repr(delta)
    return text[:-2] if text.endswith(".0") else text


def _parameter_suffix(parameter) -> str:
    if parameter == DEFAULT_TEMPORAL_PARAMETER:
        return ""
    return "_" + format_temporal_parameter(parameter)
