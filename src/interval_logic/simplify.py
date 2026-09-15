"""Semantics-preserving formula rewriting."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import portion as P

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
    Or,
    Release,
    RestrictiveSelection,
    Selection,
    Signal,
    VacuousSelection,
    Until,
    as_formula,
    formula_key,
)
from .temporal import (
    AbsoluteParameter, RelativeParameter, TemporalParameter, TimeSet, TimeValue,
    temporal_window, validate_nonnegative_interval, validate_time,
)


_FULL_TIME = P.closedopen(0, P.inf)


@dataclass(frozen=True)
class _Context:
    anchor: Fraction | None = None
    universe: TimeSet | None = None

    def reanchored(self) -> _Context:
        # Temporal operands and selection branches are inspected at other times.
        return _Context(universe=self.universe)

    def window(self, parameter: TemporalParameter) -> TimeSet:
        assert self.anchor is not None and self.universe is not None
        return temporal_window(parameter, self.anchor, self.universe)

    def absolute_region(self, parameter: AbsoluteParameter) -> TimeSet:
        region = parameter.interval
        return region if self.universe is None else region & self.universe

    def contains_anchor(self, parameter: TemporalParameter) -> bool:
        """Is every possible evaluation anchor inside its own window?"""
        if isinstance(parameter, AbsoluteParameter):
            domain = _FULL_TIME if self.universe is None else self.universe
            return (domain - parameter.interval).empty
        return parameter is None or parameter.duration > 0 or parameter.include_endpoint

    def future_exists(self, region: TimeSet) -> bool:
        """Does region contain a represented future witness at every anchor?"""
        if region.empty:
            return False
        if self.universe is None:
            # Unknown represented time might consist only of the anchor itself.
            return (_FULL_TIME - region).empty
        predecessors = P.Interval.from_atomic(P.CLOSED, 0, region.upper, region.right)
        return (self.universe - predecessors).empty

    def empty(self, parameter: TemporalParameter) -> bool:
        if self.anchor is not None:
            return self.window(parameter).empty
        if self.universe is not None and self.universe.empty:
            return True
        if isinstance(parameter, AbsoluteParameter):
            return self.absolute_region(parameter).empty
        return isinstance(parameter, RelativeParameter) and (
            parameter.duration == 0 and not parameter.include_endpoint
        )

    def nonempty(self, parameter: TemporalParameter) -> bool:
        if self.empty(parameter):
            return False
        if self.anchor is not None:
            return True
        if isinstance(parameter, AbsoluteParameter):
            return self.future_exists(self.absolute_region(parameter))
        return self.contains_anchor(parameter)

    def overlap(self, left: TemporalParameter, right: TemporalParameter) -> bool:
        if self.anchor is not None:
            return not (self.window(left) & self.window(right)).empty
        if self.empty(left) or self.empty(right):
            return False
        if self.contains_anchor(left) and self.contains_anchor(right):
            return True
        if isinstance(left, AbsoluteParameter) and isinstance(right, AbsoluteParameter):
            return self.future_exists(self.absolute_region(left) & self.absolute_region(right))
        return False  # Unknown is not evidence of overlap.

    def subset(self, left: TemporalParameter, right: TemporalParameter) -> bool:
        """Prove window containment; False also covers undecided cases."""
        if self.anchor is not None:
            return (self.window(left) - self.window(right)).empty
        if self.empty(left) or right is None or left == right:
            return True
        if isinstance(left, AbsoluteParameter) and isinstance(right, AbsoluteParameter):
            return (self.absolute_region(left) - self.absolute_region(right)).empty
        if not isinstance(left, AbsoluteParameter) and not isinstance(right, AbsoluteParameter):
            # These windows share their (unknown) origin; compare offsets only.
            return (temporal_window(left, 0, _FULL_TIME)
                    - temporal_window(right, 0, _FULL_TIME)).empty
        if isinstance(right, AbsoluteParameter):
            domain = _FULL_TIME if self.universe is None else self.universe
            return (domain - right.interval).empty
        return False


def simplify(
    formula: Formula | str, *, anchor: TimeValue | None = None,
    universe: TimeSet | None = None,
) -> Formula:
    """Preserve truth and masks within the supplied temporal context.

    An omitted universe (including None) defaults to [0, infinity). An omitted
    anchor stays unknown: rewrites must hold at every anchor in the universe.
    Retain the original formula for queries outside the simplification context.
    """
    anchor = None if anchor is None else validate_time(anchor, name="anchor")
    if universe is not None:
        universe = validate_nonnegative_interval(universe, name="universe")
    else:
        universe = _FULL_TIME
    if anchor is not None and anchor not in universe:
        raise ValueError("anchor must belong to the represented universe")
    return _simplify_in_context(as_formula(formula), _Context(anchor, universe))


def _simplify_in_context(result: Formula, context: _Context) -> Formula:
    while True:
        reduced = _simplify(result, context)
        if reduced == result:
            return reduced
        result = reduced


def expand_derived(formula: Formula | str) -> Formula:
    """Lower every abbreviation to the minimal grammar."""

    formula = as_formula(formula)
    match formula:
        case And(operands=()):
            return Boolean(True)
        case Boolean(value=False):
            return Not(Boolean(True))
        case Or(operands=operands):
            return Not(expand_derived(
                And(Not(expand_derived(operand)) for operand in operands)
            ))
        case Implies(left=left, right=right):
            return expand_derived(Or((Not(left), right)))
        case Equivalent(left=left, right=right):
            return expand_derived(
                And((Implies(left, right), Implies(right, left)))
            )
        case VacuousSelection(body=body, parameter=parameter):
            return Selection(expand_derived(body), Boolean(True), parameter)
        case RestrictiveSelection(body=body, parameter=parameter):
            return Selection(
                expand_derived(body), Not(Boolean(True)), parameter
            )
        case Eventually(body=body, parameter=parameter):
            return Until(Boolean(True), expand_derived(body), parameter)
        case Always(body=body, parameter=parameter):
            return expand_derived(Not(Eventually(Not(body), parameter)))
        case Release(left=left, right=right, parameter=parameter):
            return expand_derived(
                Not(Until(Not(left), Not(right), parameter))
            )
        case _:
            children = tuple(expand_derived(child) for child in formula.children)
            return formula._with_children(children) if children != formula.children else formula


def to_nnf(formula: Formula | str) -> Formula:
    """Push negation through every node for which ``LOGIC.md`` defines a dual."""

    # NNF is a universe-independent transformation. Do not inherit the public
    # simplifier's default full-time assumption here (e.g. for finite traces).
    return _simplify_in_context(_nnf(as_formula(formula), negated=False), _Context())


def _simplify(formula: Formula, context: _Context) -> Formula:
    match formula:
        case Boolean() | Equal():
            return _simplify_atom(formula)
        case Not(operand=operand):
            operand = _simplify(operand, context)
            if isinstance(operand, Boolean):
                return Boolean(not operand.value)
            if isinstance(operand, Not):
                return operand.operand
            if isinstance(operand, Selection):
                return Selection(
                    _simplify(Not(operand.inside), context.reanchored()),
                    _simplify(Not(operand.outside), context.reanchored()),
                    operand.parameter,
                )
            if isinstance(operand, VacuousSelection):
                return RestrictiveSelection(
                    _simplify(Not(operand.body), context.reanchored()), operand.parameter
                )
            if isinstance(operand, RestrictiveSelection):
                return VacuousSelection(
                    _simplify(Not(operand.body), context.reanchored()), operand.parameter
                )
            return Not(operand)
        case And(operands=operands):
            combined = _combine(And, (_simplify(item, context) for item in operands))
            return _simplify_always_conjunction(combined, context)
        case Or(operands=operands):
            return _combine(Or, (_simplify(item, context) for item in operands))
        case Implies(left=left, right=right):
            return _simplify(Or((Not(left), right)), context)
        case Equivalent(left=left, right=right):
            return _simplify(
                And((Implies(left, right), Implies(right, left))), context
            )
        case _:
            child_context = context.reanchored() if isinstance(formula, (
                Always, Eventually, Until, Release, Selection, VacuousSelection, RestrictiveSelection,
            )) else context
            children = tuple(_simplify(child, child_context) for child in formula.children)
            result = formula._with_children(children) if children != formula.children else formula
            if isinstance(result, (Always, Eventually, Until, Release)):
                if context.empty(result.parameter):
                    return Boolean(isinstance(result, (Always, Release)))
                if isinstance(result, (Always, Eventually)) and isinstance(result.body, Boolean):
                    unconditional = (
                        isinstance(result, Always) and result.body.value
                        or isinstance(result, Eventually) and not result.body.value
                    )
                    if unconditional or context.nonempty(result.parameter):
                        return result.body
            return result


def _simplify_always_conjunction(formula: Formula, context: _Context) -> Formula:
    if not isinstance(formula, And):
        return formula
    conditions = [item for item in formula.operands if isinstance(item, Always)]
    removed = set()
    for index, left in enumerate(conditions):
        if left in removed:
            continue
        for right in conditions[index + 1:]:
            if right in removed:
                continue
            if context.overlap(left.parameter, right.parameter):
                # Bodies are evaluated at a common inspected time, not the
                # outer anchor. This is syntactic contradiction detection only.
                both = _simplify(And((left.body, right.body)), context.reanchored())
                if both == Boolean(False):
                    return Boolean(False)
            if left.body == right.body:
                if context.subset(left.parameter, right.parameter):
                    removed.add(left)
                    break
                if context.subset(right.parameter, left.parameter):
                    removed.add(right)
    return _combine(And, (item for item in formula.operands if item not in removed))


def _simplify_atom(formula: Formula) -> Formula:
    if isinstance(formula, Equal):
        if formula.left == formula.right:
            return Boolean(True)
        if isinstance(formula.left, NaturalLiteral) and isinstance(
            formula.right, NaturalLiteral
        ):
            return Boolean(False)
    return formula


def _combine(node_type, operands) -> Formula:
    identity = node_type is And
    annihilator = not identity
    nested_type = And if identity else Or

    flattened: list[Formula] = []
    for operand in operands:
        if isinstance(operand, Boolean):
            if operand.value == annihilator:
                return Boolean(annihilator)
            continue
        if isinstance(operand, nested_type):
            flattened.extend(operand.operands)
        else:
            flattened.append(operand)

    unique = set(flattened)
    if node_type is And:
        assignments = {}
        for operand in unique:
            if not isinstance(operand, Equal):
                continue
            left, right = operand.left, operand.right
            if isinstance(right, Signal) and isinstance(left, NaturalLiteral):
                left, right = right, left
            if isinstance(left, Signal) and isinstance(right, NaturalLiteral):
                if left in assignments and assignments[left] != right:
                    return Boolean(False)
                assignments[left] = right
    for operand in tuple(unique):
        complement = operand.operand if isinstance(operand, Not) else Not(operand)
        if complement in unique:
            return Boolean(annihilator)

    opposite = Or if identity else And
    plain = {item for item in unique if not isinstance(item, opposite)}
    unique = {
        item
        for item in unique
        if not (
            isinstance(item, opposite)
            and any(candidate in item.operands for candidate in plain)
        )
    }

    compound = [item for item in unique if isinstance(item, opposite)]
    removed: set[Formula] = set()
    for left in compound:
        left_terms = set(left.operands)
        for right in compound:
            if left is right:
                continue
            if left_terms < set(right.operands):
                removed.add(right)
    unique -= removed

    ordered = tuple(sorted(unique, key=formula_key))
    if not ordered:
        return Boolean(identity)
    if len(ordered) == 1:
        return ordered[0]
    return node_type(ordered)


def _nnf(formula: Formula, negated: bool) -> Formula:
    match formula:
        case Boolean(value=value):
            return Boolean(not value if negated else value)
        case Not(operand=operand):
            return _nnf(operand, not negated)
        case And(operands=operands):
            node = Or if negated else And
            return node(_nnf(item, negated) for item in operands)
        case Or(operands=operands):
            node = And if negated else Or
            return node(_nnf(item, negated) for item in operands)
        case Implies(left=left, right=right):
            return _nnf(Or((Not(left), right)), negated)
        case Equivalent(left=left, right=right):
            return _nnf(
                And((Implies(left, right), Implies(right, left))), negated
            )
        case Selection(inside=inside, outside=outside, parameter=parameter):
            return Selection(
                _nnf(inside, negated), _nnf(outside, negated), parameter
            )
        case VacuousSelection(body=body, parameter=parameter):
            if negated:
                return RestrictiveSelection(_nnf(body, True), parameter)
            return VacuousSelection(_nnf(body, False), parameter)
        case RestrictiveSelection(body=body, parameter=parameter):
            if negated:
                return VacuousSelection(_nnf(body, True), parameter)
            return RestrictiveSelection(_nnf(body, False), parameter)
        case Eventually(body=body, parameter=parameter):
            node = Always if negated else Eventually
            return node(_nnf(body, negated), parameter)
        case Always(body=body, parameter=parameter):
            node = Eventually if negated else Always
            return node(_nnf(body, negated), parameter)
        case Until(left=left, right=right, parameter=parameter):
            node = Release if negated else Until
            return node(_nnf(left, negated), _nnf(right, negated), parameter)
        case Release(left=left, right=right, parameter=parameter):
            node = Until if negated else Release
            return node(_nnf(left, negated), _nnf(right, negated), parameter)
        case _:
            return Not(formula) if negated else formula
