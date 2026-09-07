"""Adapter for pyspect's symbolic, physical-time state-predicate operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import portion as P
from pyspect.impls.symbolic import (
    AllDifferent, AllDifferentExceptZero, OneVariableTransition,
    StateSet as NativeStateSet, SymbolicSystem, UnrestrictedTransition,
)

from ..ast import Equal, NaturalLiteral, Proposition, Signal
from ..errors import ReachabilityValidationError, UnsupportedTemporalParameterError
from ..temporal import (
    TemporalParameter, TimeSet, TimeValue, temporal_window,
    validate_nonnegative_interval, validate_time,
)

_FULL_TIME = P.closedopen(0, P.inf)


@dataclass(frozen=True, slots=True, eq=False)
class PyspectStateSet:
    """A normalized native set with the named StateSet protocol operations."""

    native: NativeStateSet

    def __post_init__(self) -> None:
        if not isinstance(self.native, NativeStateSet):
            raise ReachabilityValidationError("expected a native pyspect StateSet")

    def _other(self, other: PyspectStateSet) -> NativeStateSet:
        if not isinstance(other, PyspectStateSet) or other.native.system is not self.native.system:
            raise ReachabilityValidationError("state sets must belong to the same symbolic system")
        return other.native

    def intersection(self, other: PyspectStateSet) -> PyspectStateSet:
        return PyspectStateSet(self.native & self._other(other))

    def union(self, other: PyspectStateSet) -> PyspectStateSet:
        return PyspectStateSet(self.native | self._other(other))

    def complement(self) -> PyspectStateSet:
        return PyspectStateSet(~self.native)

    def difference(self, other: PyspectStateSet) -> PyspectStateSet:
        return PyspectStateSet(self.native - self._other(other))

    def is_empty(self) -> bool:
        return self.native.is_empty

    def is_subset(self, other: PyspectStateSet) -> bool:
        return self.native.is_subset(self._other(other))

    def normalize(self) -> PyspectStateSet:
        # Every native constructor and operation already normalizes regions.
        return self


class PyspectBackend:
    """Bind one configured SymbolicSystem and its proposition valuation.

    Treat system configuration as fixed for this adapter's lifetime. Native
    timed queries start a fresh holding period at the query anchor. Arbitrary
    represented-time masks require additional algorithms and are rejected.
    """

    def __init__(
        self, system: SymbolicSystem, *, propositions: Mapping[str, NativeStateSet] | None = None
    ) -> None:
        if not isinstance(system, SymbolicSystem):
            raise ReachabilityValidationError("expected a pyspect SymbolicSystem")
        if type(system.invariant) not in (AllDifferentExceptZero, AllDifferent):
            raise ReachabilityValidationError("unsupported symbolic invariant")
        if type(system.transition) not in (OneVariableTransition, UnrestrictedTransition):
            raise ReachabilityValidationError("unsupported symbolic transition relation")
        propositions = {} if propositions is None else propositions
        if not isinstance(propositions, Mapping):
            raise ReachabilityValidationError("propositions must be a mapping")
        bindings = {}
        for name, states in propositions.items():
            if not isinstance(name, str) or not name:
                raise ReachabilityValidationError("proposition names must be nonempty strings")
            if not isinstance(states, NativeStateSet) or states.system is not system:
                raise ReachabilityValidationError("proposition sets must belong to this system")
            bindings[name] = states
        self.system = system
        self.propositions = MappingProxyType(bindings)

    @property
    def state_space(self) -> PyspectStateSet:
        return PyspectStateSet(self.system.universe())

    def atomic_states(self, atom: Proposition | Equal) -> PyspectStateSet:
        if isinstance(atom, Proposition):
            try:
                return PyspectStateSet(self.propositions[atom.name])
            except KeyError as error:
                raise ReachabilityValidationError(f"unbound proposition {atom.name!r}") from error
        if not isinstance(atom, Equal):
            raise ReachabilityValidationError("expected a proposition or equality atom")
        left, right = atom.left, atom.right
        for term in (left, right):
            if isinstance(term, Signal) and term.name not in self.system.variables:
                raise ReachabilityValidationError(f"unknown signal {term.name!r}")
        if left == right:
            return self.state_space
        if isinstance(left, NaturalLiteral) and isinstance(right, NaturalLiteral):
            result = self.system.empty()
        elif isinstance(left, NaturalLiteral):
            result = self.system.states(**{right.name: left.value})
        elif isinstance(right, NaturalLiteral):
            result = self.system.states(**{left.name: right.value})
        elif isinstance(self.system.invariant, AllDifferentExceptZero):
            result = self.system.states(**{left.name: 0, right.name: 0})
        else:
            result = self.system.empty()
        return PyspectStateSet(result)

    def _native(self, states: PyspectStateSet) -> NativeStateSet:
        if not isinstance(states, PyspectStateSet) or states.native.system is not self.system:
            raise ReachabilityValidationError("state set must belong to this backend's system")
        return states.native

    @staticmethod
    def _query(parameter: TemporalParameter, anchor: TimeValue, universe: TimeSet):
        try:
            anchor = validate_time(anchor, name="anchor")
            universe = validate_nonnegative_interval(universe, name="universe")
            window = temporal_window(parameter, anchor, universe)
        except (TypeError, ValueError) as error:
            raise ReachabilityValidationError(str(error)) from error
        return anchor, universe, window

    @staticmethod
    def _require_full_time(universe: TimeSet) -> None:
        if universe != _FULL_TIME:
            raise UnsupportedTemporalParameterError(
                "pyspect temporal propagation requires the full nonnegative time universe"
            )

    def constrained_reach(
        self, target: PyspectStateSet, constraint: PyspectStateSet,
        parameter: TemporalParameter, anchor: TimeValue, universe: TimeSet,
    ) -> PyspectStateSet:
        target_native, constraint_native = self._native(target), self._native(constraint)
        anchor, universe, window = self._query(parameter, anchor, universe)
        if window.empty:
            return PyspectStateSet(self.system.empty())
        if window == P.singleton(anchor):
            return target
        self._require_full_time(universe)
        try:
            result = self.system.reach_timed(
                target_native, window=window, constraints=constraint_native, anchor=anchor
            )
        except (TypeError, ValueError) as error:
            raise ReachabilityValidationError(str(error)) from error
        return PyspectStateSet(result)

    def existential_invariance(
        self, safe: PyspectStateSet, parameter: TemporalParameter,
        anchor: TimeValue, universe: TimeSet,
    ) -> PyspectStateSet:
        native = self._native(safe)
        anchor, universe, window = self._query(parameter, anchor, universe)
        if window.empty:
            return self.state_space  # Both transition relations can wait forever.
        if window == P.singleton(anchor):
            return safe
        self._require_full_time(universe)
        try:
            result = self.system.invariant_timed(native, window=window, anchor=anchor)
        except (TypeError, ValueError) as error:
            raise ReachabilityValidationError(str(error)) from error
        return PyspectStateSet(result)
