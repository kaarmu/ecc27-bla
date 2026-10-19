"""Exact scalars and interval/formula component utilities (private)."""
from numbers import Real
from dataclasses import dataclass
from fractions import Fraction as F
import portion as P
import interval_logic as il

FULL = P.closedopen(0, P.inf)
acc, use = il.Signal("acc"), il.Signal("use")
TRUE, FALSE = il.Boolean(True), il.Boolean(False)

def rational(value, name='value'):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f'{name} must be a finite real number')
    try:
        return value if isinstance(value, F) else F(str(value))
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError(f'{name} must be finite') from error

def time(value):
    return il.RelativeParameter(value).duration

def region(value, *, bounded=False):
    if not isinstance(value, P.Interval):
        raise TypeError('expected a portion interval region')
    result = P.empty()
    for component in value:
        canonical = il.AbsoluteParameter(component).interval
        if bounded and canonical.upper == P.inf:
            raise ValueError('the region must be bounded')
        result |= canonical
    return result

def terms(formula, kind):
    return formula.operands if isinstance(formula, kind) else (formula,)

def grouped(operator, body, window):
    connective = il.And if operator is il.Always else il.Or
    return connective(operator(body, component) for component in window)
