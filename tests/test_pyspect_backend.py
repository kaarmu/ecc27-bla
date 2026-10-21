from fractions import Fraction as F
import unittest

import portion as P
try:
    from pyspect.impls.symbolic import (
        AllDifferent, AllDifferentExceptZero, OneVariableTransition,
        SymbolicSystem, UnrestrictedTransition,
    )
except ModuleNotFoundError as error:
    if error.name != 'pyspect' and not (error.name or '').startswith('pyspect.'):
        raise
    raise unittest.SkipTest('Optional pyspect symbolic backend is not installed') from error

import interval_logic as il

FULL = P.closedopen(0, P.inf)


def make_system(invariant=None, transition=None, step=None):
    return SymbolicSystem(('j', 'k'), invariant=invariant if invariant is not None else AllDifferentExceptZero(),
                          transition=transition if transition is not None else OneVariableTransition(), time_step=step)


class PyspectBackendTests(unittest.TestCase):
    def setUp(self):
        self.system = make_system()
        self.backend = il.PyspectBackend(self.system)

    def states(self, formula, backend=None, anchor=0, universe=FULL):
        if backend is None:
            backend = self.backend
        return il.existential_satisfying_states(formula, backend, anchor, universe)

    def test_state_set_protocol_and_ownership(self):
        a = il.PyspectStateSet(self.system.states(j=0))
        b = il.PyspectStateSet(self.system.states(k=0))
        self.assertIsInstance(a, il.StateSet)
        self.assertIsInstance(self.backend, il.ReachabilityBackend)
        self.assertIn((0, 0), a.intersection(b).native)
        self.assertNotIn((1, 1), a.union(b).complement().native)
        self.assertTrue(a.difference(a).is_empty())
        self.assertTrue(a.is_subset(self.backend.state_space))
        self.assertIs(a.normalize(), a)
        foreign = il.PyspectBackend(make_system()).state_space
        for operation in (a.intersection, a.union, a.difference, a.is_subset):
            with self.assertRaises(il.ReachabilityValidationError):
                operation(foreign)
        with self.assertRaises(il.ReachabilityValidationError):
            self.backend.constrained_reach(foreign, a, None, 0, FULL)

    def test_all_atomic_equalities_under_both_invariants(self):
        for invariant in (AllDifferentExceptZero(), AllDifferent()):
            backend = il.PyspectBackend(make_system(invariant=invariant))
            equal = self.states('j = k', backend)
            self.assertEqual((0, 0) in equal.native, isinstance(invariant, AllDifferentExceptZero))
            self.assertNotIn((1, 1), equal.native)
            if type(invariant) is AllDifferent:
                self.assertTrue(equal.is_empty())
            self.assertTrue(self.states('j = j', backend).is_subset(backend.state_space))
            self.assertEqual(self.states('2 = j', backend).native, self.states('j = 2', backend).native)
            self.assertTrue(self.states('1 = 2', backend).is_empty())
            self.assertEqual(self.states('1 = 1', backend).native, backend.state_space.native)
        for formula in ('missing = missing', 'missing = 0', 'unbound'):
            with self.assertRaises(il.ReachabilityValidationError):
                self.states(formula)

    def test_proposition_bindings_are_copied_and_validated(self):
        props = {'free': self.system.states(j=0, k=0)}
        backend = il.PyspectBackend(self.system, propositions=props)
        props.clear()
        self.assertIn((0, 0), self.states('free', backend).native)
        with self.assertRaises(il.ReachabilityValidationError):
            il.PyspectBackend(self.system, propositions={'free': make_system().universe()})

    def test_variable_positive_duration_and_delayed_witness(self):
        for transition in (OneVariableTransition(), UnrestrictedTransition()):
            for invariant in (AllDifferentExceptZero(), AllDifferent()):
                system = make_system(invariant, transition)
                backend = il.PyspectBackend(system)
                result = self.states(il.Eventually('j = 0', F(1, 10**30)), backend)
                self.assertIn((1, 2), result.native)
                delayed = il.Until('j != 0', 'j = 0', P.openclosed(0, F(1, 10)))
                result = self.states(delayed, backend)
                self.assertNotIn((0, 2), result.native)
                self.assertIn((1, 2), result.native)

    def test_fixed_event_edges_and_holding_interiors(self):
        for transition in (OneVariableTransition(), UnrestrictedTransition()):
            backend = il.PyspectBackend(make_system(transition=transition, step=0.1))
            formula = lambda parameter: il.Until('j != 0', 'j = 0', parameter)
            self.assertNotIn((1, 0), self.states(formula(0.1), backend).native)
            self.assertIn((1, 0), self.states(formula('0.1]'), backend).native)
            self.assertNotIn((1, 0), self.states(formula(P.singleton(F(3, 20))), backend).native)
            self.assertIn((1, 0), self.states(formula(P.singleton(F(1, 5))), backend).native)
            self.assertIn((1, 0), self.states(formula(P.singleton(F(3, 10))), backend).native)

    def test_absolute_windows_and_nonzero_fresh_anchors(self):
        backend = il.PyspectBackend(make_system(step=F(1, 2)))
        self.assertIn((1, 0), self.states('j != 0 until_[5,8) j = 0', backend, anchor=3).native)
        self.assertNotIn((0, 0), self.states('j != 0 until_[5,8) j = 0', backend, anchor=3).native)
        self.assertTrue(self.states('eventually_[5,8) j = 0', backend, anchor=8).is_empty())
        self.assertEqual(self.states('always_[5,8) j = 0', backend, anchor=8).native, backend.state_space.native)
        at = F(1, 4)
        self.assertNotIn((1, 0), self.states(il.Eventually('j = 0', F(1, 2)), backend, anchor=at).native)
        self.assertIn((1, 0), self.states(il.Eventually('j = 0', '0.5]'), backend, anchor=at).native)

    def test_invariance_is_existential_with_positive_initial_dwell(self):
        for step in (None, F(1, 2)):
            backend = il.PyspectBackend(make_system(step=step))
            self.assertNotIn((1, 0), self.states('always j = 0', backend).native)
            self.assertIn((1, 0), self.states('always_[1,2] j = 0', backend).native)
            self.assertNotIn((1, 0), self.states('always_(0,1] j = 0', backend).native)
            self.assertEqual(self.states('always_0 false', backend).native, backend.state_space.native)
            self.assertIn((1, 0), self.states('not always j = 0', backend).native)

    def test_masks_are_rejected_after_local_reductions(self):
        for universe in (P.closed(0, 3), P.singleton(0) | P.singleton(3)):
            for formula in ('eventually j = 0', 'always_[1,3] j = 0', 'j != 0 until j = 0'):
                with self.assertRaises(il.UnsupportedTemporalParameterError):
                    self.states(formula, universe=universe)
            self.assertIn((0, 0), self.states('j = 0', universe=universe).native)
            self.assertEqual(self.states('always_0 false', universe=universe).native, self.backend.state_space.native)
            self.assertEqual(self.states('eventually_0] j = 0', universe=universe).native, self.system.states(j=0))
            self.assertTrue(self.states('eventually_0 j = 0', universe=universe).is_empty())
        # The swap needs intermediate states outside A. A masked prefix could
        # permit them, while clipping only the witness window cannot.
        system = make_system(step=1)
        backend = il.PyspectBackend(system, propositions={'A': system.states(j=1, k=2), 'B': system.states(j=2, k=1)})
        self.assertNotIn((1, 2), self.states('A until_[3,3] B', backend).native)
        with self.assertRaises(il.UnsupportedTemporalParameterError):
            self.states('A until_[3,3] B', backend, universe=P.singleton(0) | P.singleton(3))

    def test_charging_station_initial_set_query(self):
        system = make_system(step=1)
        backend = il.PyspectBackend(system, propositions={'both_free': system.states(j=0, k=0)})
        initial = il.PyspectStateSet(system.states(j=1, k=2))
        result = self.states('eventually_2] both_free', backend)
        self.assertFalse(initial.intersection(result).is_empty())
        result = self.states('eventually_2 both_free', backend)
        self.assertTrue(initial.intersection(result).is_empty())

    def test_query_validation(self):
        for anchor in (-1, True, float('nan')):
            with self.assertRaises(il.ReachabilityValidationError):
                self.backend.existential_invariance(self.backend.state_space, None, anchor, FULL)
        with self.assertRaises(il.ReachabilityValidationError):
            self.states('j = 0', anchor=4, universe=P.closed(0, 3))

    def test_proven_temporal_contradictions_precede_propagation(self):
        formula = 'always_[1,5) j = 1 and always_[1.5,3) j = 2'
        self.assertTrue(self.states(formula).is_empty())
        # No temporal backend call is needed, even on a finite universe.
        self.assertTrue(self.states(formula, universe=P.closed(0, 5)).is_empty())
        self.assertFalse(self.states(formula, anchor=3).is_empty())
        unresolved = 'always_[1,2) j = 1 and always_[3,4) j = 2'
        with self.assertRaises(il.UnsupportedReachabilityError):
            self.states(unresolved)
        with self.assertRaises(il.ReachabilityValidationError):
            self.states(f'({formula}) and missing = 0')
        # NNF may expose contradictory Always conditions after initial rewriting.
        negated = 'not eventually_[1,5) j != 1 and always_[1.5,3) j = 2'
        self.assertTrue(self.states(negated).is_empty())
