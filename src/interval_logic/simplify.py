"""Semantics-preserving formula rewriting."""

from __future__ import annotations

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
    VacuousSelection,
    Until,
    as_formula,
    formula_key,
)


def simplify(formula: Formula | str) -> Formula:
    """Apply sound constants, complements, idempotence, and absorption."""

    return _simplify(as_formula(formula))


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

    return simplify(_nnf(as_formula(formula), negated=False))


def _simplify(formula: Formula) -> Formula:
    match formula:
        case Boolean() | Equal():
            return _simplify_atom(formula)
        case Not(operand=operand):
            operand = _simplify(operand)
            if isinstance(operand, Boolean):
                return Boolean(not operand.value)
            if isinstance(operand, Not):
                return operand.operand
            if isinstance(operand, Selection):
                return Selection(
                    _simplify(Not(operand.inside)),
                    _simplify(Not(operand.outside)),
                    operand.parameter,
                )
            if isinstance(operand, VacuousSelection):
                return RestrictiveSelection(
                    _simplify(Not(operand.body)), operand.parameter
                )
            if isinstance(operand, RestrictiveSelection):
                return VacuousSelection(
                    _simplify(Not(operand.body)), operand.parameter
                )
            return Not(operand)
        case And(operands=operands):
            return _combine(And, (_simplify(item) for item in operands))
        case Or(operands=operands):
            return _combine(Or, (_simplify(item) for item in operands))
        case Implies(left=left, right=right):
            return _simplify(Or((Not(left), right)))
        case Equivalent(left=left, right=right):
            return _simplify(
                And((Implies(left, right), Implies(right, left)))
            )
        case _:
            children = tuple(_simplify(child) for child in formula.children)
            return formula._with_children(children) if children != formula.children else formula


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
