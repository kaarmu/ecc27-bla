"""Exact existential propagation over one common family of trajectories."""

from __future__ import annotations

from fractions import Fraction
from typing import Protocol, runtime_checkable

import portion as P

from .ast import (
    Always, And, Boolean, Equal, Eventually, Formula, Not, Or, Proposition,
    Release, RestrictiveSelection, Selection, Until, VacuousSelection, as_formula,
)
from .errors import ReachabilityValidationError, UnsupportedReachabilityError
from .simplify import simplify, to_nnf
from .temporal import (
    AbsoluteParameter, RelativeParameter, TemporalParameter, TimeSet, TimeValue,
    temporal_window, validate_nonnegative_interval, validate_time,
)


@runtime_checkable
class StateSet(Protocol):
    def intersection(self, other: StateSet) -> StateSet: ...
    def union(self, other: StateSet) -> StateSet: ...
    def complement(self) -> StateSet: ...
    def difference(self, other: StateSet) -> StateSet: ...
    def is_empty(self) -> bool: ...
    def is_subset(self, other: StateSet) -> bool: ...
    def normalize(self) -> StateSet: ...


@runtime_checkable
class ReachabilityBackend(Protocol):
    @property
    def state_space(self) -> StateSet: ...

    def atomic_states(self, atom: Proposition | Equal) -> StateSet: ...

    def constrained_reach(
        self, target: StateSet, constraint: StateSet,
        parameter: TemporalParameter, anchor: TimeValue, universe: TimeSet,
    ) -> StateSet: ...

    def existential_invariance(
        self, safe: StateSet, parameter: TemporalParameter,
        anchor: TimeValue, universe: TimeSet,
    ) -> StateSet: ...


def existential_satisfying_states(
    formula: Formula | str, backend: ReachabilityBackend,
    anchor: TimeValue, universe: TimeSet,
) -> StateSet:
    """Return exactly the states admitting a trajectory satisfying the formula.

    Unsupported formulas fail rather than combine independently chosen temporal
    witnesses. Local reductions are scoped to the time at which they apply.
    """
    formula = as_formula(formula)
    try:
        anchor = validate_time(anchor, name="anchor")
        universe = validate_nonnegative_interval(universe, name="universe")
        if anchor not in universe:
            raise ValueError("anchor must belong to the represented universe")
    except (TypeError, ValueError) as error:
        raise ReachabilityValidationError(str(error)) from error
    if not isinstance(backend, ReachabilityBackend):
        raise ReachabilityValidationError("backend must implement ReachabilityBackend")
    context = _Propagation(backend, anchor, universe)
    # Validate all referenced atoms even if a reduction makes a branch vacuous.
    pending = [formula]
    while pending:
        node = pending.pop()
        if isinstance(node, (Proposition, Equal)):
            context.atoms[node] = backend.atomic_states(node)
        pending.extend(node.children)
    reduced = to_nnf(_reduce_local(formula, anchor, universe))
    return context.evaluate(reduced).normalize()


def _reduce_local(formula: Formula, anchor: Fraction | None, universe: TimeSet) -> Formula:
    """None marks an unknown future inspection time, not omitted syntax."""
    if isinstance(formula, (VacuousSelection, RestrictiveSelection)):
        formula = Selection(formula.body, Boolean(isinstance(formula, VacuousSelection)),
                            formula.parameter)
    if isinstance(formula, Selection):
        parameter = formula.parameter
        if not isinstance(parameter, AbsoluteParameter):
            inside = parameter is None or parameter.include_endpoint or parameter.duration > 0
        elif parameter.interval.empty:
            inside = False
        elif anchor is not None:
            inside = anchor in parameter.interval
        else:
            left = _reduce_local(formula.inside, None, universe)
            right = _reduce_local(formula.outside, None, universe)
            # Only a local reduction: branch masks could differ from their Sat sets.
            return left if left == right else Selection(left, right, parameter)
        return _reduce_local(formula.inside if inside else formula.outside, anchor, universe)

    if isinstance(formula, (Until, Eventually, Always, Release)):
        parameter = formula.parameter
        empty = isinstance(parameter, AbsoluteParameter) and parameter.interval.empty
        immediate = False
        if isinstance(parameter, RelativeParameter) and parameter.duration == 0:
            immediate = parameter.include_endpoint
            empty = not immediate
        elif anchor is not None:
            window = temporal_window(parameter, anchor, universe)
            empty = window.empty
            immediate = window == P.singleton(anchor)
        if empty:
            return Boolean(isinstance(formula, (Always, Release)))
        if immediate:
            operand = formula.right if isinstance(formula, (Until, Release)) else formula.body
            return _reduce_local(operand, anchor, universe)
        # A temporal operator changes the inspection time. Never carry the
        # outer anchor into a selector in its operands.
        children = tuple(_reduce_local(child, None, universe) for child in formula.children)
    else:
        children = tuple(_reduce_local(child, anchor, universe) for child in formula.children)
    rebuilt = formula._with_children(children) if children != formula.children else formula
    return simplify(rebuilt)


def _is_state_predicate(formula: Formula) -> bool:
    if isinstance(formula, (Boolean, Proposition, Equal)):
        return True
    return isinstance(formula, (Not, And, Or)) and all(
        _is_state_predicate(child) for child in formula.children
    )


class _Propagation:
    def __init__(self, backend: ReachabilityBackend, anchor: Fraction, universe: TimeSet):
        self.backend, self.anchor, self.universe = backend, anchor, universe
        self.space = backend.state_space
        self.atoms: dict[Formula, StateSet] = {}
        self._admissible: StateSet | None = None

    def admissible(self) -> StateSet:
        if self._admissible is None:
            self._admissible = self.backend.existential_invariance(
                self.space, RelativeParameter(0), self.anchor, self.universe
            )
        return self._admissible

    def valuation(self, formula: Formula) -> StateSet:
        match formula:
            case Boolean(value=True):
                return self.space
            case Boolean(value=False):
                return self.space.difference(self.space)
            case Proposition() | Equal():
                return self.atoms[formula]
            case Not(operand=operand):
                return self.valuation(operand).complement()
            case And(operands=operands):
                result = self.space
                for operand in operands:
                    result = result.intersection(self.valuation(operand))
                return result
            case Or(operands=operands):
                result = self.space.difference(self.space)
                for operand in operands:
                    result = result.union(self.valuation(operand))
                return result
            case _:
                raise UnsupportedReachabilityError("operand is not a state predicate")

    def evaluate(self, formula: Formula) -> StateSet:
        if _is_state_predicate(formula):
            states = self.valuation(formula)
            return states if states.is_empty() else states.intersection(self.admissible())
        if isinstance(formula, Or):
            result = self.space.difference(self.space)
            for operand in formula.operands:
                result = result.union(self.evaluate(operand))
            return result
        if isinstance(formula, And):
            temporal = [item for item in formula.operands if not _is_state_predicate(item)]
            if len(temporal) > 1:
                raise UnsupportedReachabilityError(
                    "conjunction requires multiple correlated temporal witnesses"
                )
            result = self.evaluate(temporal[0])
            for item in formula.operands:
                if _is_state_predicate(item):
                    result = result.intersection(self.valuation(item))
            return result
        if isinstance(formula, (Until, Eventually, Always)) and all(
            _is_state_predicate(child) for child in formula.children
        ):
            if isinstance(formula, Always):
                return self.backend.existential_invariance(
                    self.valuation(formula.body), formula.parameter, self.anchor, self.universe
                )
            target = self.valuation(formula.right if isinstance(formula, Until) else formula.body)
            constraint = self.valuation(formula.left) if isinstance(formula, Until) else self.space
            return self.backend.constrained_reach(
                target, constraint, formula.parameter, self.anchor, self.universe
            )
        raise UnsupportedReachabilityError(
            f"unsupported exact reachability formula: {type(formula).__name__}"
        )
