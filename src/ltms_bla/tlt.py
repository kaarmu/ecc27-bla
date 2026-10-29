"""Generate pyspect TLTs from interpreted interval_logic formulas.

The contracts state physical predicates as interval_logic formulas over named
state atoms. ``compile_query`` translates the supported fragment into a pyspect
TLT: Boolean combinations of state atoms become one exactly realized set
(intersection and union of their interpretations), and each bounded until read
at a fixed anchor becomes a TLT until node. Anything else is refused rather
than approximated.
"""
import interval_logic as il
import portion as P
from interval_logic.temporal import AbsoluteParameter
from pyspect import TLT, UNTIL, ContLTL
from pyspect.set_builder import BoxSet, Inter, Union


def _time(value):
    return int(value) if value == int(value) else float(value)


def state_set(formula, interpretation):
    """The set builder of a Boolean combination of state atoms (exact, pointwise)."""
    if isinstance(formula, il.Proposition):
        if formula.name not in interpretation:
            raise ValueError(f'no interpretation for atom {formula.name}')
        return interpretation[formula.name]
    if isinstance(formula, (il.And, il.Or)):
        join = Inter if isinstance(formula, il.And) else Union
        parts = [state_set(child, interpretation) for child in formula.operands]
        result = parts[0]
        for part in parts[1:]:
            result = join(result, part)
        return result
    raise ValueError(f'not a state predicate: {formula}')


def compile_query(formula, anchor, interpretation):
    """The TLT for states at ``anchor`` admitting a trajectory that satisfies ``formula``.

    ``formula`` is ``left U_[a,b] right`` with state predicates ``left`` and
    ``right`` and a closed absolute window, a >= anchor. The solver's time axis
    starts at ``anchor``, so the target is ``right`` within t ∈ [a-anchor,
    b-anchor]. pyspect's until also intersects target and constraint at the
    witness time.
    """
    formula = il.as_formula(formula)
    if not (isinstance(formula, il.Until) and isinstance(formula.parameter, AbsoluteParameter)):
        raise ValueError(f'unsupported formula for TLT generation: {formula}')
    window = formula.parameter.interval
    if not (window.left == window.right == P.CLOSED) or window.lower < anchor:
        raise ValueError(f'unsupported until window {window} at anchor {anchor}')
    lo, hi = _time(window.lower - anchor), _time(window.upper - anchor)
    constraint = state_set(formula.left, interpretation)
    target = Inter(state_set(formula.right, interpretation), BoxSet(dict(t=(lo, hi)), axes=['t']))
    return TLT(UNTIL('constraint', 'target'), primitives=ContLTL,
               where=dict(constraint=constraint, target=target))
