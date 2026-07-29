"""Immutable interval logic with exact propositions and natural-number signals."""

from .ast import (
    ALL_TIME,
    And,
    Atom,
    Bool,
    DerivedExpression,
    Equal,
    Exists,
    Expression,
    ForAll,
    Guard,
    Natural,
    Not,
    Or,
    Restrict,
    Signal,
    Term,
    as_expr,
    as_term,
    expression_key,
)
from .derived import Equivalent, Implies, Xor
from .errors import (
    DerivedExpressionCycleError,
    DerivedExpressionError,
    ExpansionLimitError,
    IntervalLogicError,
)
from .normalize import partition_intervals, to_nnf
from .pretty import format_expression, format_term
from .semantics import NaturalSignal, SignalValuation, Valuation, denote, holds
from .simplify import simplify
from .transform import lower_derived
from .visualize import Timeline, TimelineRow, timeline

__all__ = [
    "And",
    "Atom",
    "Bool",
    "DerivedExpression",
    "DerivedExpressionCycleError",
    "DerivedExpressionError",
    "Equal",
    "Equivalent",
    "Exists",
    "ExpansionLimitError",
    "Expression",
    "ForAll",
    "Guard",
    "Implies",
    "IntervalLogicError",
    "Not",
    "Natural",
    "NaturalSignal",
    "Or",
    "Restrict",
    "Signal",
    "SignalValuation",
    "Term",
    "Valuation",
    "Xor",
    "Timeline",
    "TimelineRow",
    "as_expr",
    "as_term",
    "denote",
    "expression_key",
    "format_expression",
    "format_term",
    "holds",
    "lower_derived",
    "partition_intervals",
    "simplify",
    "to_nnf",
    "timeline",
]
