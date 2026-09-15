from fractions import Fraction as F
from itertools import product
import unittest

import portion as P

import interval_logic as il


FULL = P.closedopen(0, P.inf)


class ContextSimplificationTests(unittest.TestCase):
    def setUp(self):
        self.p, self.q = il.Proposition('p'), il.Proposition('q')
        self.left = il.Always(self.p, P.closedopen(1, 5))
        self.right = il.Always(~self.p, P.closedopen(F(3, 2), 3))
        self.conflict = self.left & self.right

    def assert_observations(self, formula, trace, anchors, **context):
        reduced = il.simplify(formula, **context)
        self.assertEqual(reduced, formula.simplify(**context))
        self.assertEqual(reduced, reduced.simplify(**context))
        for anchor in anchors:
            with self.subTest(formula=str(formula), anchor=anchor, context=context):
                self.assertEqual(il.satisfies(formula, trace, anchor),
                                 il.satisfies(reduced, trace, anchor))
                self.assertEqual(il.denote(formula, trace, anchor),
                                 il.denote(reduced, trace, anchor))

    def test_four_context_modes(self):
        generic = self.conflict.simplify()
        self.assertIsInstance(generic, il.And)
        self.assertEqual(self.conflict.simplify(anchor=0), il.Boolean(False))
        self.assertEqual(self.conflict.simplify(universe=P.closed(0, 5)), generic)
        self.assertEqual(self.conflict.simplify(anchor=0, universe=P.closed(0, 5)),
                         il.Boolean(False))
        gap = P.closedopen(0, F(3, 2)) | P.closed(3, 5)
        self.assertEqual(self.conflict.simplify(anchor=0, universe=gap), self.left)
        self.assertEqual(self.conflict.simplify(anchor=3), self.left)
        self.assertEqual(self.conflict.simplify(anchor=5), il.Boolean(True))
        self.assertEqual(il.simplify(str(self.conflict), anchor=0), il.Boolean(False))
        self.assertEqual(self.conflict.simplify(anchor=None, universe=None), generic)

    def test_universe_only_has_no_default_anchor(self):
        # At 0 there is a conflict; at 3 both conditions have expired.
        f = il.Always(self.p, P.closedopen(0, 1)) & il.Always(~self.p, P.closedopen(0, 1))
        self.assertNotEqual(f.simplify(universe=P.closed(0, 3)), il.Boolean(False))
        expired = il.Always(self.p, P.closedopen(6, 8))
        self.assertEqual(expired.simplify(universe=P.closed(0, 5)), il.Boolean(True))
        # A common represented future point is guaranteed at every anchor here.
        f = il.Always(self.p, P.closed(1, 5)) & il.Always(~self.p, P.closed(2, 5))
        self.assertEqual(f.simplify(universe=P.closed(0, 5)), il.Boolean(False))
        # If the common upper endpoint is excluded, anchor 5 is a counterexample.
        f = il.Always(self.p, P.closedopen(1, 5)) & il.Always(~self.p, P.closedopen(2, 5))
        self.assertNotEqual(f.simplify(universe=P.closed(0, 5)), il.Boolean(False))

    def test_default_universe_is_full_time_with_unknown_anchor(self):
        f = il.Eventually(True, P.closed(1, 5))
        # Finite windows can still expire: no anchor is assumed by default.
        self.assertEqual(f.simplify(), f)
        future = P.closedopen(1, P.inf)
        eventually = il.Eventually(True, future)
        self.assertEqual(eventually.simplify(), il.Boolean(True))
        self.assertEqual(eventually.simplify(anchor=None, universe=None), il.Boolean(True))
        self.assertEqual(eventually.simplify(), eventually.simplify(universe=FULL))
        conflict = il.Always(self.p, future) & il.Always(~self.p, future)
        self.assertEqual(conflict.simplify(), il.Boolean(False))
        # Explicit universes still override the default, including empty ones.
        self.assertEqual(eventually.simplify(universe=P.singleton(0)), il.Boolean(False))
        self.assertEqual(conflict.simplify(universe=P.singleton(0)), il.Boolean(True))
        trace = il.Trace(FULL, {'p': P.closedopen(1, 5)})
        for formula in (f, eventually, conflict):
            self.assert_observations(formula, trace, [0, 1, 5, 10])
        # Relative nonempty windows include the represented anchor itself.
        f = il.Always(self.p, 1) & il.Always(~self.p, '0]')
        self.assertEqual(f.simplify(), il.Boolean(False))
        f = il.Always(self.p) & il.Always(~self.p, 1)
        self.assertEqual(f.simplify(), il.Boolean(False))

    def test_nnf_remains_universe_independent(self):
        future = P.closedopen(1, P.inf)
        formulas = (
            il.Eventually(True, future),
            il.Always(self.p, future) & il.Always(~self.p, future),
        )
        trace = il.Trace(P.singleton(0))
        for formula in formulas:
            nnf = il.to_nnf(formula)
            self.assertEqual(il.satisfies(nnf, trace, 0), il.satisfies(formula, trace, 0))
            self.assertEqual(il.denote(nnf, trace, 0), il.denote(formula, trace, 0))
            self.assertNotEqual(nnf, formula.simplify())

    def test_empty_windows_and_constants(self):
        for parameter, context in [
            (0, {}), (P.empty(), {}), (P.closedopen(1, 2), {'anchor': 2}),
            (P.closed(6, 7), {'universe': P.closed(0, 5)}),
            (None, {'universe': P.empty()}),
        ]:
            for constructor in (il.Always, il.Eventually, il.Until, il.Release):
                args = (self.p, self.q, parameter) if constructor in (il.Until, il.Release) else (self.p, parameter)
                self.assertEqual(constructor(*args).simplify(**context),
                                 il.Boolean(constructor in (il.Always, il.Release)))
        for context in ({}, {'anchor': 0}, {'universe': P.closed(0, 5)}):
            self.assertEqual(il.Always(True, P.closed(1, 2)).simplify(**context), il.Boolean(True))
            self.assertEqual(il.Eventually(False, P.closed(1, 2)).simplify(**context), il.Boolean(False))
        self.assertEqual(il.Eventually(True, 1).simplify(), il.Boolean(True))
        self.assertEqual(il.Always(False, 1).simplify(), il.Boolean(False))
        self.assertEqual(il.Eventually(True, P.singleton(1)).simplify(anchor=0), il.Boolean(True))
        self.assertIsInstance(il.Eventually(True, P.singleton(1)).simplify(), il.Eventually)

    def test_exact_overlap_endpoints(self):
        for left_interval, right_interval, contradiction in [
            (P.closedopen(1, 2), P.closedopen(2, 3), False),
            (P.closed(1, 2), P.closedopen(2, 3), True),
            (P.closed(1, 2), P.open(2, 3), False),
            (P.singleton(F(1, 3)), P.closed(F(1, 3), 1), True),
        ]:
            f = il.Always(self.p, left_interval) & il.Always(~self.p, right_interval)
            self.assertEqual(f.simplify(anchor=0) == il.Boolean(False), contradiction)

    def test_multiple_conditions_and_signal_assignments(self):
        j, k = il.Signal('j'), il.Signal('k')
        f = il.Always(j.equals(1), P.closedopen(1, 5)) & il.Always(il.Equal(2, j), P.closedopen(2, 3))
        self.assertEqual((self.q & f & il.Always(self.p, 10)).simplify(anchor=0), il.Boolean(False))
        self.assertEqual((j.equals(1) & il.Equal(2, j)).simplify(), il.Boolean(False))
        different_signals = il.Always(j.equals(1), 3) & il.Always(k.equals(2), 3)
        self.assertIsInstance(different_signals.simplify(anchor=0), il.And)
        unrelated = il.Always(self.p, 3) & il.Always(self.q, 3)
        self.assertIsInstance(unrelated.simplify(anchor=0), il.And)
        boolean_conflict = il.Always(self.p & self.q, 3) & il.Always(~self.p, 3)
        self.assertEqual(boolean_conflict.simplify(), il.Boolean(False))

    def test_redundant_always_requirements(self):
        stronger = il.Always(self.p, P.closed(1, 5))
        weaker = il.Always(self.p, P.closedopen(2, 3))
        self.assertEqual((stronger & weaker).simplify(), stronger)
        self.assertEqual((il.Always(self.p, 1) & il.Always(self.p, '1]')).simplify(),
                         il.Always(self.p, '1]'))
        self.assertEqual((il.Always(self.p) & il.Always(self.p, 5)).simplify(), il.Always(self.p))
        # Equal effective windows must leave one condition, not remove both.
        a, b = il.Always(self.p, P.closed(0, 3)), il.Always(self.p, P.closed(1, 3))
        reduced = (a & b).simplify(anchor=2)
        self.assertIsInstance(reduced, il.Always)
        self.assertEqual(reduced.simplify(anchor=2), reduced)
        mixed = il.Always(self.p, 3) & il.Always(self.p, P.closedopen(2, 5))
        self.assertIsInstance(mixed.simplify(), il.And)
        self.assertIsInstance(mixed.simplify(anchor=2), il.Always)

    def test_meeting_coverage_windows_rejoin(self):
        joined = il.Always(self.p, P.closedopen(1, 2)) & il.Always(self.p, P.closedopen(2, 3))
        self.assertEqual(joined.simplify(), il.Always(self.p, P.closedopen(1, 3)))
        overlapping = il.Always(self.p, P.closed(1, 4)) & il.Always(self.p, P.closedopen(3, 6))
        self.assertEqual(overlapping.simplify(), il.Always(self.p, P.closedopen(1, 6)))
        # A disconnected union stays grouped; a parameter must be connected.
        apart = il.Always(self.p, P.closedopen(1, 2)) & il.Always(self.p, P.closedopen(3, 4))
        self.assertEqual(apart.simplify(), apart)
        # Different bodies and relative parameters are untouched.
        bodies = il.Always(self.p, P.closedopen(1, 2)) & il.Always(self.q, P.closedopen(2, 3))
        self.assertEqual(bodies.simplify(), bodies)
        relative = il.Always(self.p, 2) & il.Always(self.p, P.closedopen(1, 2))
        self.assertEqual(relative.simplify(), relative)
        trace = il.Trace(FULL, {'p': P.closedopen(1, 3), 'q': P.closed(0, 9)})
        for formula in (joined, overlapping, apart, bodies, relative):
            self.assert_observations(formula, trace, [0, 1, 2, 4])

    def test_nested_operands_and_selection_masks_do_not_inherit_anchor(self):
        trace = il.Trace(P.closed(0, 5), {'p': P.closed(0, 5)})
        formulas = [
            il.Eventually(self.conflict, P.singleton(3)),
            il.Always(self.conflict, P.closed(3, 5)),
            il.Until(self.p, self.conflict, P.singleton(3)),
            il.Release(self.q, self.conflict, P.singleton(3)),
            il.Selection(self.conflict, self.q, P.closedopen(3, 4)),
            il.VacuousSelection(self.conflict, P.closedopen(3, 4)),
            il.RestrictiveSelection(self.conflict, P.closedopen(3, 4)),
            ~il.Selection(self.conflict, self.q, P.closedopen(3, 4)),
        ]
        for formula in formulas:
            self.assert_observations(formula, trace, [0], anchor=0, universe=trace.universe)
        self.assertTrue(il.satisfies(formulas[0], trace, 0))
        self.assertEqual(il.denote(formulas[6], trace, 0), P.closedopen(3, 4))

    def test_singleton_conditions_and_selections_keep_masks(self):
        trace = il.Trace(P.closed(0, 5), {'p': P.singleton(0), 'q': P.closed(1, 5)})
        for formula in (
            il.Always(self.p, '0]'), il.Eventually(self.p, P.singleton(0)),
            il.Until(self.q, self.p, '0]'), il.Release(self.q, self.p, '0]'),
            il.Selection(self.p, self.q, 1), il.VacuousSelection(self.p, 1),
            il.RestrictiveSelection(self.p, 1),
        ):
            self.assertEqual(formula.simplify(anchor=0, universe=trace.universe), formula)
            self.assert_observations(formula, trace, [0], anchor=0, universe=trace.universe)
        self.assertNotEqual(il.denote(il.Always(self.p, '0]'), trace, 0), il.denote(self.p, trace, 0))

    def test_observations_over_all_small_finite_valuations(self):
        universe = P.singleton(0) | P.singleton(1) | P.singleton(2)
        valuations = []
        for bits in product((False, True), repeat=3):
            valuations.append(P.empty())
            for t, present in enumerate(bits):
                if present:
                    valuations[-1] |= P.singleton(t)
        formulas = [
            self.conflict,
            il.Always(self.p, 1) & il.Always(~self.p, '0]'),
            il.Always(self.p, P.closed(0, 2)) & il.Always(self.p, P.singleton(2)),
            il.Eventually(il.Always(self.p, P.closedopen(0, 1)), P.closed(1, 2)),
            il.Selection(self.conflict, self.q, P.closed(1, 2)),
            ~il.RestrictiveSelection(self.conflict, 2),
            il.Always(False, P.open(0, 1)),
            il.Eventually(True, P.closed(1, 2)),
        ]
        for p_times, q_times in product(valuations, repeat=2):
            trace = il.Trace(universe, {'p': p_times, 'q': q_times})
            for formula in formulas:
                self.assert_observations(formula, trace, [0, 1, 2], universe=universe)
                for anchor in (0, 1, 2):
                    self.assert_observations(formula, trace, [anchor], anchor=anchor, universe=universe)

    def test_anchor_only_observations_on_full_time(self):
        for region in (P.empty(), FULL, P.closedopen(1, 5), P.singleton(3)):
            trace = il.Trace(FULL, {'p': region})
            for anchor in (0, F(3, 2), 3, 5):
                self.assert_observations(self.conflict, trace, [anchor], anchor=anchor)

    def test_context_validation_and_empty_universe(self):
        for anchor in (True, -1, float('nan'), float('inf'), '0'):
            with self.assertRaises((TypeError, ValueError)):
                self.p.simplify(anchor=anchor)
        for universe in ('[0,5]', P.closed(-1, 5), P.closed('0', '5')):
            with self.assertRaises((TypeError, ValueError)):
                self.p.simplify(universe=universe)
        for universe in (P.empty(), P.closed(1, 5)):
            with self.assertRaises(ValueError):
                self.p.simplify(anchor=0, universe=universe)
        self.assertEqual(self.p.simplify(universe=P.empty()), self.p)
        self.assertEqual(il.Eventually(self.p).simplify(universe=P.empty()), il.Boolean(False))
        self.assertEqual(il.Always(self.p).simplify(universe=P.empty()), il.Boolean(True))


    def test_duration_coverage_becomes_a_plain_region(self):
        cover = il.Always(il.Always(self.p, 1), P.closedopen(1, 5))
        self.assertEqual(cover.simplify(anchor=0), il.Always(self.p, P.closedopen(1, 6)))
        # The outer window decides which starts are represented.
        self.assertEqual(cover.simplify(anchor=3), il.Always(self.p, P.closedopen(3, 6)))
        self.assertEqual(cover.simplify(anchor=6), il.Boolean(True))
        self.assertEqual(cover.simplify(), cover)
        self.assertEqual(cover.simplify(universe=P.closed(0, 9)), cover)
        # A closed relative window attains the shifted upper bound.
        closed = il.Always(il.Always(self.p, '1]'), P.closed(1, 5))
        self.assertEqual(closed.simplify(anchor=0), il.Always(self.p, P.closed(1, 6)))
        self.assertEqual(il.Always(il.Always(self.p, 1), P.closed(1, 5)).simplify(anchor=0),
                         il.Always(self.p, P.closedopen(1, 6)))
        # A disconnected outer window groups as a conjunction, never one parameter.
        gap = P.closedopen(0, 2) | P.closed(4, 9)
        grouped = cover.simplify(anchor=0, universe=gap)
        self.assertEqual(grouped, il.Always(self.p, P.closedopen(1, 3))
                         & il.Always(self.p, P.closedopen(4, 6)))
        unbounded = il.Always(il.Always(self.p, 1), P.closedopen(1, P.inf))
        self.assertEqual(unbounded.simplify(anchor=0), il.Always(self.p, P.closedopen(1, P.inf)))
        trace = il.Trace(FULL, {'p': P.closedopen(1, 4)})
        self.assert_observations(cover, trace, [0], anchor=0)
        self.assert_observations(cover, trace, [3], anchor=3)

    def test_blocked_eventually_loses_the_denied_region(self):
        blocked = il.Always(~self.p, P.closedopen(2, 3)) & il.Eventually(self.p, P.closedopen(1, 6))
        pruned = (il.Eventually(self.p, P.closedopen(1, 2)) | il.Eventually(self.p, P.closedopen(3, 6))) \
            & il.Always(~self.p, P.closedopen(2, 3))
        self.assertEqual(blocked.simplify(anchor=0), pruned)
        # Pruning needs no anchor: a witness after the anchor is outside R anyway.
        self.assertEqual(blocked.simplify(), pruned)
        # Incompatible signal assignments block just as complementary bodies do.
        j = il.Signal('j')
        signals = il.Always(j.equals(1), P.closedopen(2, 3)) & il.Eventually(j.equals(2), P.closedopen(1, 3))
        self.assertEqual(signals.simplify(anchor=0),
                         il.Eventually(j.equals(2), P.closedopen(1, 2))
                         & il.Always(j.equals(1), P.closedopen(2, 3)))
        # A fully denied witness region is false, not an unreduced conjunction.
        self.assertEqual((il.Always(~self.p, P.closed(0, 9))
                          & il.Eventually(self.p, P.closedopen(1, 6))).simplify(anchor=0),
                         il.Boolean(False))
        # Compatible bodies and relative parameters are left alone.
        compatible = il.Eventually(self.p, P.closedopen(1, 6)) & il.Always(self.q, P.closedopen(2, 3))
        self.assertEqual(compatible.simplify(anchor=0), compatible)
        relative = il.Eventually(self.p, P.closedopen(1, 6)) & il.Always(~self.p, 2)
        self.assertEqual(relative.simplify(anchor=0), relative)
        # Grouped start windows are pruned alternative by alternative.
        grouped = (il.Eventually(self.p, P.closedopen(1, 2))
                   | il.Eventually(self.p, P.closedopen(2, 3))
                   | il.Eventually(self.p, P.closedopen(3, 4))) & il.Always(~self.p, P.closedopen(F(3, 2), 3))
        self.assertEqual(grouped.simplify(anchor=0),
                         (il.Eventually(self.p, P.closedopen(1, F(3, 2)))
                          | il.Eventually(self.p, P.closedopen(3, 4)))
                         & il.Always(~self.p, P.closedopen(F(3, 2), 3)))
        # Negations, selections, and temporal operands are never entered.
        for keep in (
            ~il.Eventually(self.p, P.closedopen(1, 6)),
            il.VacuousSelection(il.Eventually(self.p, P.closedopen(1, 6)), 2),
            il.Always(il.Eventually(self.p, P.closedopen(1, 6)), P.closed(0, 9)),
        ):
            untouched = keep & il.Always(~self.p, P.closedopen(2, 3))
            self.assertEqual(untouched.simplify(anchor=0), untouched)
        trace = il.Trace(FULL, {'p': P.closedopen(1, 4), 'q': P.closed(0, 9)})
        for formula in (blocked, grouped, compatible, relative):
            self.assert_observations(formula, trace, [0], anchor=0)
            self.assert_observations(formula, trace, [0, 1, 4], universe=FULL)

if __name__ == '__main__':
    unittest.main()
