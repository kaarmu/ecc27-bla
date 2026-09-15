"""Independent finite-trajectory oracle for the generic propagation contract."""

from dataclasses import dataclass
from fractions import Fraction as F
import unittest

import portion as P
import interval_logic as il

DOMAIN = frozenset({'start', 'p', 'q', 'dead'})
TIMES = (0, 1, 2)
UNIVERSE = P.singleton(0) | P.singleton(1) | P.singleton(2)


@dataclass(frozen=True)
class FiniteSet:
    values: frozenset

    def intersection(self, other):
        return FiniteSet(self.values & other.values)

    def union(self, other):
        return FiniteSet(self.values | other.values)

    def complement(self):
        return FiniteSet(DOMAIN - self.values)

    def difference(self, other):
        return FiniteSet(self.values - other.values)

    def is_empty(self):
        return not self.values

    def is_subset(self, other):
        return self.values <= other.values

    def normalize(self):
        return self


class FiniteBackend:
    # Two incompatible witnesses start from the same state. Dead has no path.
    paths = {
        'start': [('start', 'p', 'p'), ('start', 'q', 'q')],
        'p': [('p', 'p', 'p')],
        'q': [('q', 'q', 'q')],
        'dead': [],
    }

    def __init__(self):
        self.calls = []

    @property
    def state_space(self):
        return FiniteSet(DOMAIN)

    def atomic_states(self, atom):
        if isinstance(atom, il.Proposition) and atom.name in DOMAIN:
            return FiniteSet(frozenset({atom.name}))
        raise il.ReachabilityValidationError('unknown finite atom')

    def inspected(self, parameter, anchor, universe):
        # Independent parameter interpretation; no production window helper.
        times = [t for t in TIMES if t >= anchor and t in universe]
        if isinstance(parameter, il.RelativeParameter):
            end = anchor + parameter.duration
            times = [t for t in times if t <= end] if parameter.include_endpoint else [t for t in times if t < end]
        elif isinstance(parameter, il.AbsoluteParameter):
            times = [t for t in times if t in parameter.interval]
        return times

    def constrained_reach(self, target, constraint, parameter, anchor, universe):
        self.calls.append(('reach', target, constraint, parameter, anchor, universe))
        witnesses = self.inspected(parameter, anchor, universe)
        return FiniteSet(frozenset(
            state for state, paths in self.paths.items()
            if any(any(path[t] in target.values and all(
                path[u] in constraint.values for u in TIMES if anchor <= u < t and u in universe
            ) for t in witnesses) for path in paths)
        ))

    def existential_invariance(self, safe, parameter, anchor, universe):
        self.calls.append(('invariant', safe, parameter, anchor, universe))
        times = self.inspected(parameter, anchor, universe)
        return FiniteSet(frozenset(
            state for state, paths in self.paths.items()
            if any(all(path[t] in safe.values for t in times) for path in paths)
        ))


class GenericReachabilityTests(unittest.TestCase):
    def setUp(self):
        self.backend = FiniteBackend()

    def states(self, formula, universe=UNIVERSE):
        return il.existential_satisfying_states(formula, self.backend, 0, universe).values

    def test_state_valuation_is_restricted_to_trajectory_existence(self):
        self.assertEqual(self.states('true'), DOMAIN - {'dead'})
        self.assertEqual(self.states('dead'), frozenset())
        self.assertEqual(self.states('not dead'), DOMAIN - {'dead'})
        self.assertEqual(self.states('not p'), frozenset({'start', 'q'}))
        self.assertEqual(self.states('false'), frozenset())
        self.assertEqual(self.states('dead or start'), frozenset({'start'}))

    def test_common_trajectory_disjunction_and_conjunction(self):
        self.assertEqual(self.states('eventually p or eventually q'), DOMAIN - {'dead'})
        self.assertEqual(self.states('start and eventually p'), frozenset({'start'}))
        self.assertEqual(self.states('start and not dead'), frozenset({'start'}))
        self.assertEqual(self.states('start and (eventually p or eventually q)'), frozenset({'start'}))
        with self.assertRaises(il.UnsupportedReachabilityError):
            self.states('eventually p and eventually q')

    def test_interval_contradiction_needs_no_temporal_backend_call(self):
        formula = 'always_[0,2] p and always_[1,2] not p'
        self.assertEqual(self.states(formula), frozenset())
        self.assertEqual(self.backend.calls, [])
        with self.assertRaises(il.ReachabilityValidationError):
            self.states(f'({formula}) and missing')

    def test_negation_is_not_complement_of_existential_results(self):
        self.assertEqual(self.states('eventually p'), frozenset({'start', 'p'}))
        self.assertEqual(self.states('not eventually p'), frozenset({'start', 'q'}))
        self.assertEqual(self.states('always p'), frozenset({'p'}))
        self.assertEqual(self.states('not always p'), frozenset({'start', 'q'}))
        self.assertEqual(self.states('not (p release q)'), self.states('not p until not q'))

    def test_primitive_operands_are_unrestricted_valuation_sets(self):
        self.states('eventually dead')
        reach = next(call for call in self.backend.calls if call[0] == 'reach')
        self.assertEqual(reach[1].values, frozenset({'dead'}))
        self.assertEqual(reach[2].values, DOMAIN)
        self.states('always (not p)')
        call = self.backend.calls[-1]
        self.assertIn('dead', call[1].values)

    def test_zero_duration_precedes_unsupported_checks(self):
        for constructor in (il.Eventually, il.Always):
            self.assertEqual(self.states(constructor('p', '0]')), frozenset({'p'}))
        for constructor in (il.Until, il.Release):
            self.assertEqual(self.states(constructor('p', 'q', '0]')), frozenset({'q'}))
        self.assertEqual(self.states(il.Release(il.Eventually('p'), il.Eventually('q'), 0)), DOMAIN - {'dead'})
        self.assertEqual(self.states(il.Release('p', il.Eventually('q'), '0]')), self.states('eventually q'))
        self.assertEqual(self.states('always_0 dead'), DOMAIN - {'dead'})
        self.assertEqual(self.states('eventually_0 p'), frozenset())
        self.assertEqual(self.states('p until_0 q'), frozenset())

    def test_selection_reductions_respect_scope(self):
        for parameter in (None, 1, '1]', '0]'):
            selector = il.Selection('p', 'q', parameter)
            self.assertEqual(self.states(selector), frozenset({'p'}))
            self.assertEqual(self.states(il.Eventually(selector)), self.states('eventually p'))
        self.assertEqual(self.states(il.Selection('p', 'q', 0)), frozenset({'q'}))
        absolute = il.Selection('p', 'q', P.closed(1, 2))
        self.assertEqual(self.states(absolute), frozenset({'q'}))
        self.assertEqual(self.states(il.Always(absolute, '0]')), frozenset({'q'}))
        with self.assertRaises(il.UnsupportedReachabilityError):
            self.states(il.Eventually(absolute))
        identical = il.Selection('p', 'p', P.closed(1, 2))
        self.assertEqual(self.states(il.Eventually(identical)), self.states('eventually p'))

    def test_unsupported_nodes_and_validation(self):
        for formula in ('p release q', 'eventually always p', 'always eventually p', 'not (p until q)'):
            with self.assertRaises(il.UnsupportedReachabilityError):
                self.states(formula)
        for anchor in (F(1, 2), True, -1):
            with self.assertRaises(il.ReachabilityValidationError):
                il.existential_satisfying_states('p', self.backend, anchor, UNIVERSE)
        with self.assertRaises(il.ReachabilityValidationError):
            self.states('always_0 missing')

    def test_common_universe_for_relative_absolute_and_omitted(self):
        for parameter in (None, 2, '2]', P.closed(1, 2)):
            self.states(il.Until('start', 'p', parameter))
            self.states(il.Always('p', parameter))
        for call in self.backend.calls:
            self.assertEqual(call[-1], UNIVERSE)
            self.assertEqual(call[-2], 0)
        self.assertEqual(self.states('start until_[1,2] p'), frozenset({'start'}))
