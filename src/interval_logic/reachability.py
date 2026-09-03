"""Symbolic reachability backends and TLT-set propagation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .ast import (
    Always,
    And,
    Boolean,
    Equal,
    Eventually,
    Formula,
    Not,
    Or,
    Proposition,
    Release,
    RestrictiveSelection,
    Selection,
    Until,
    VacuousSelection,
    WeakUntil,
    as_formula,
)
from .errors import (
    UnsupportedReachabilityError,
    UnsupportedTemporalParameterError,
)
from .simplify import to_nnf
from .temporal import (
    AbsoluteParameter,
    RelativeParameter,
    TemporalParameter,
    TimeValue,
    validate_time,
)


@runtime_checkable
class StateSet(Protocol):
    """A symbolic subset of a backend's multidimensional admissible states."""

    def intersection(self, other: StateSet) -> StateSet: ...

    def union(self, other: StateSet) -> StateSet: ...

    def complement(self) -> StateSet: ...

    def difference(self, other: StateSet) -> StateSet: ...

    def is_empty(self) -> bool: ...

    def is_subset(self, other: StateSet) -> bool: ...

    def normalize(self) -> StateSet: ...


@dataclass(frozen=True, slots=True)
class ReachResult:
    """A computed TLT state set and its exactness certificate."""

    tlt_set: StateSet
    certified: bool

    def __post_init__(self) -> None:
        if not isinstance(self.tlt_set, StateSet):
            raise TypeError("ReachResult tlt_set must implement StateSet")
        if type(self.certified) is not bool:
            raise TypeError("ReachResult certified must be a bool")


@runtime_checkable
class ReachabilityBackend(Protocol):
    """Exact primitives bound to one semantic system ``(X_adm, Xi, V)``."""

    @property
    def admissible_states(self) -> StateSet: ...

    def atom(self, atom: Proposition | Equal) -> StateSet: ...

    def constrained_reach(
        self,
        target: StateSet,
        constraint: StateSet,
        parameter: TemporalParameter,
        anchor: TimeValue,
    ) -> StateSet: ...

    def existential_invariance(
        self,
        safe: StateSet,
        parameter: TemporalParameter,
        anchor: TimeValue,
    ) -> StateSet: ...

    def certify_conjunction(
        self,
        formula: And,
        operands: tuple[ReachResult, ...],
        anchor: TimeValue,
    ) -> bool: ...


@runtime_checkable
class EventReachabilityBackend(ReachabilityBackend, Protocol):
    """An untimed backend whose primitives are realized with predecessors."""

    def predecessor(self, states: StateSet) -> StateSet: ...


def reach(
    formula: Formula | str,
    backend: ReachabilityBackend,
    anchor: TimeValue,
) -> ReachResult:
    """Compute a TLT set and whether it equals true existential satisfaction."""

    if not isinstance(backend, ReachabilityBackend):
        raise TypeError("backend must implement ReachabilityBackend")
    anchor_number = validate_time(anchor, name="anchor")
    reduced = _reduce_exact_local_laws(
        as_formula(formula), anchor_number, future_position=False
    )
    normalized = to_nnf(reduced)
    return _reach_nnf(normalized, backend, anchor_number)


def _reduce_exact_local_laws(
    formula: Formula,
    anchor: float,
    *,
    future_position: bool,
) -> Formula:
    """Apply selector and zero-window laws before backend propagation."""

    match formula:
        case Boolean() | Proposition() | Equal():
            return formula
        case Not(operand=operand):
            return Not(
                _reduce_exact_local_laws(
                    operand, anchor, future_position=future_position
                )
            )
        case And(operands=operands):
            return And(
                _reduce_exact_local_laws(
                    item, anchor, future_position=future_position
                )
                for item in operands
            )
        case Or(operands=operands):
            return Or(
                _reduce_exact_local_laws(
                    item, anchor, future_position=future_position
                )
                for item in operands
            )
        case Selection(inside=inside, outside=outside, parameter=parameter):
            branch = _selection_branch(
                inside,
                outside,
                parameter,
                anchor,
                future_position=future_position,
            )
            return _reduce_exact_local_laws(
                branch, anchor, future_position=future_position
            )
        case VacuousSelection(body=body, parameter=parameter):
            branch = _selection_branch(
                body,
                Boolean(True),
                parameter,
                anchor,
                future_position=future_position,
            )
            return _reduce_exact_local_laws(
                branch, anchor, future_position=future_position
            )
        case RestrictiveSelection(body=body, parameter=parameter):
            branch = _selection_branch(
                body,
                Boolean(False),
                parameter,
                anchor,
                future_position=future_position,
            )
            return _reduce_exact_local_laws(
                branch, anchor, future_position=future_position
            )
        case Eventually(body=body, parameter=parameter) if _is_zero(parameter):
            if parameter.include_endpoint:
                return _reduce_exact_local_laws(
                    body, anchor, future_position=future_position
                )
            return Boolean(False)
        case Always(body=body, parameter=parameter) if _is_zero(parameter):
            if parameter.include_endpoint:
                return _reduce_exact_local_laws(
                    body, anchor, future_position=future_position
                )
            return Boolean(True)
        case Until(right=right, parameter=parameter) if _is_zero(parameter):
            if parameter.include_endpoint:
                return _reduce_exact_local_laws(
                    right, anchor, future_position=future_position
                )
            return Boolean(False)
        case Release(right=right, parameter=parameter) if _is_zero(parameter):
            if parameter.include_endpoint:
                return _reduce_exact_local_laws(
                    right, anchor, future_position=future_position
                )
            return Boolean(True)
        case WeakUntil(left=left, right=right, parameter=parameter) if _is_zero(
            parameter
        ):
            if parameter.include_endpoint:
                return _reduce_exact_local_laws(
                    Or((left, right)), anchor, future_position=future_position
                )
            return Boolean(True)
        case Eventually(body=body, parameter=parameter):
            return Eventually(
                _reduce_exact_local_laws(
                    body, anchor, future_position=True
                ),
                parameter,
            )
        case Always(body=body, parameter=parameter):
            return Always(
                _reduce_exact_local_laws(
                    body, anchor, future_position=True
                ),
                parameter,
            )
        case Until(left=left, right=right, parameter=parameter):
            return Until(
                _reduce_exact_local_laws(
                    left, anchor, future_position=True
                ),
                _reduce_exact_local_laws(
                    right, anchor, future_position=True
                ),
                parameter,
            )
        case Release(left=left, right=right, parameter=parameter):
            return Release(
                _reduce_exact_local_laws(
                    left, anchor, future_position=True
                ),
                _reduce_exact_local_laws(
                    right, anchor, future_position=True
                ),
                parameter,
            )
        case WeakUntil(left=left, right=right, parameter=parameter):
            return WeakUntil(
                _reduce_exact_local_laws(
                    left, anchor, future_position=True
                ),
                _reduce_exact_local_laws(
                    right, anchor, future_position=True
                ),
                parameter,
            )
        case _:
            children = tuple(
                _reduce_exact_local_laws(
                    child, anchor, future_position=future_position
                )
                for child in formula.children
            )
            return formula._with_children(children)


def _reach_nnf(
    formula: Formula, backend: ReachabilityBackend, anchor: float
) -> ReachResult:
    admissible = backend.admissible_states
    match formula:
        case Boolean(value=True):
            return ReachResult(admissible.normalize(), True)
        case Boolean(value=False):
            return ReachResult(admissible.difference(admissible).normalize(), True)
        case Proposition() | Equal():
            return ReachResult(backend.atom(formula).normalize(), True)
        case Not(operand=(Proposition() | Equal()) as atom):
            return ReachResult(backend.atom(atom).complement().normalize(), True)
        case And(operands=operands):
            results = tuple(_reach_nnf(item, backend, anchor) for item in operands)
            tlt_set = admissible
            for result in results:
                tlt_set = tlt_set.intersection(result.tlt_set)
            local = all(_is_current_state_local(item) for item in operands)
            certified = all(result.certified for result in results) and (
                local or backend.certify_conjunction(formula, results, anchor)
            )
            return ReachResult(tlt_set.normalize(), certified)
        case Or(operands=operands):
            results = tuple(_reach_nnf(item, backend, anchor) for item in operands)
            tlt_set = admissible.difference(admissible)
            for result in results:
                tlt_set = tlt_set.union(result.tlt_set)
            return ReachResult(
                tlt_set.normalize(), all(result.certified for result in results)
            )
        case Until(left=left, right=right, parameter=parameter):
            left_result = _reach_nnf(left, backend, anchor)
            right_result = _reach_nnf(right, backend, anchor)
            tlt_set = backend.constrained_reach(
                right_result.tlt_set, left_result.tlt_set, parameter, anchor
            ).normalize()
            certified = (
                left_result.certified
                and right_result.certified
                and _is_uniform_state_predicate(left)
                and _is_uniform_state_predicate(right)
            )
            return ReachResult(tlt_set, certified)
        case Eventually(body=body, parameter=parameter):
            body_result = _reach_nnf(body, backend, anchor)
            tlt_set = backend.constrained_reach(
                body_result.tlt_set, admissible, parameter, anchor
            ).normalize()
            return ReachResult(
                tlt_set,
                body_result.certified and _is_uniform_state_predicate(body),
            )
        case Always(body=body, parameter=parameter):
            body_result = _reach_nnf(body, backend, anchor)
            tlt_set = backend.existential_invariance(
                body_result.tlt_set, parameter, anchor
            ).normalize()
            return ReachResult(
                tlt_set,
                body_result.certified and _is_uniform_state_predicate(body),
            )
        case Release() | WeakUntil():
            raise UnsupportedReachabilityError(
                f"the generic reachability algorithm does not implement "
                f"{type(formula).__name__}"
            )
        case Not():
            raise UnsupportedReachabilityError(
                "negated temporal formulas require a supported NNF dual"
            )
        case _:
            raise UnsupportedReachabilityError(
                f"unsupported reachability formula: {type(formula).__name__}"
            )


def _selection_branch(
    inside: Formula,
    outside: Formula,
    parameter: TemporalParameter,
    anchor: float,
    *,
    future_position: bool,
) -> Formula:
    if parameter is None:
        return inside
    if isinstance(parameter, RelativeParameter):
        if parameter.duration > 0 or parameter.include_endpoint:
            return inside
        return outside
    if isinstance(parameter, AbsoluteParameter):
        if future_position:
            raise UnsupportedTemporalParameterError(
                "an absolute selector evaluated at future positions requires "
                "a timed trajectory-aware backend operation"
            )
        return inside if anchor in parameter.interval else outside
    raise TypeError(f"unsupported temporal parameter: {type(parameter).__name__}")


def _is_zero(parameter: TemporalParameter) -> bool:
    return isinstance(parameter, RelativeParameter) and parameter.duration == 0


def _is_current_state_local(formula: Formula) -> bool:
    match formula:
        case Boolean() | Proposition() | Equal():
            return True
        case Not(operand=operand):
            return _is_current_state_local(operand)
        case And(operands=operands) | Or(operands=operands):
            return all(_is_current_state_local(item) for item in operands)
        case _:
            return False


def _is_uniform_state_predicate(formula: Formula) -> bool:
    return _is_current_state_local(formula)
