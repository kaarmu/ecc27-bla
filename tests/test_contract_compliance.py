from fractions import Fraction as F
import unittest

import portion as P
import interval_logic as il


class ContractComplianceTests(unittest.TestCase):
    def test_exact_temporal_round_trips(self):
        values = (F(1, 3), F(1, 10), F(1, 8), F(7, 20), 10**30, 0.1,
                  F(12345678901234567890123456789, 100000000))
        for value in values:
            for closed in (False, True):
                parameter = il.RelativeParameter(value, closed)
                expected = value if isinstance(value, F) else F(str(value))
                self.assertEqual(parameter.duration, expected)
                spelling = il.format_temporal_parameter(parameter)
                self.assertEqual(il.coerce_temporal_parameter(spelling), parameter)
                formula = il.Eventually('p', parameter)
                self.assertEqual(il.parse_formula(str(formula)), formula)
        for interval in (P.empty(), P.singleton(F(1, 3)), P.openclosed(F(1, 3), F(7, 4)),
                         P.closedopen(F(1, 3), P.inf)):
            formula = il.Always('p', interval)
            self.assertEqual(il.parse_formula(str(formula)), formula)
        self.assertEqual(il.format_temporal_parameter(il.RelativeParameter(F(1, 8))), '0.125')

    def test_quoted_names_and_selection_scope(self):
        for name in ('always', 'job one', 'a"b\\c\n', '日本語', 'a`b'):
            for formula in (il.Proposition(name), il.Signal(name).equals(2)):
                for unicode in (True, False):
                    self.assertEqual(il.parse_formula(il.format_formula(formula, unicode=unicode)), formula)
        for formula in (
            il.Selection(il.VacuousSelection('p', 3), 'q', 4),
            il.VacuousSelection(il.VacuousSelection('p', 3), 4),
            il.RestrictiveSelection('p', 3),
            il.Always(il.RestrictiveSelection('p', F(1, 3)), 2),
            il.RestrictiveSelection(il.Eventually('p', 3), 4),
        ):
            for unicode in (True, False):
                text = il.format_formula(formula, unicode=unicode)
                self.assertEqual(il.parse_formula(text), formula, text)
        self.assertEqual(il.format_formula(il.RestrictiveSelection('p', 3), unicode=False), 'select(p)_3*')
        self.assertEqual(il.parse_formula('select(p)*_3'), il.RestrictiveSelection('p', 3))
        self.assertEqual(il.parse_formula('`legacy name`'), il.Proposition('legacy name'))

    def test_explicit_half_open_durations_inside_groups(self):
        pairs = (
            ('select(select(p)_3))_4', il.VacuousSelection(il.VacuousSelection('p', 3), 4)),
            ('(select(p)_3))', il.VacuousSelection('p', 3)),
            ('select(select(select(p)_3))_4)_5',
             il.VacuousSelection(il.VacuousSelection(il.VacuousSelection('p', 3), 4), 5)),
            ('always_3) p', il.Always('p', 3)),
            ('(select(p)_3) and q', il.VacuousSelection('p', 3) & il.Proposition('q')),
        )
        for source, formula in pairs:
            self.assertEqual(il.parse_formula(source), formula)

    def test_time_and_trace_validation(self):
        for value in (True, -1, float('inf'), float('nan'), '1'):
            with self.assertRaises((TypeError, ValueError)):
                il.RelativeParameter(value)
            with self.assertRaises(il.TraceValidationError):
                il.satisfies('p', il.Trace(P.closed(0, 1)), value)
        for interval in (P.closed(-1, 2), P.closed('0', '1')):
            with self.assertRaises((TypeError, ValueError)):
                il.AbsoluteParameter(interval)
        with self.assertRaises(ValueError):
            il.temporal_window(None, 2, P.closed(0, 1))
        for kwargs in ({'propositions': {'p': P.closed(0, 2)}},
                       {'signals': {'j': il.NaturalSignal({0: P.closed(0, 2)})}}):
            with self.assertRaises(il.TraceValidationError):
                il.Trace(P.closed(0, 1), **kwargs)
        trace = il.Trace(P.closed(0, 1))
        for formula in (il.Signal('missing').equals(il.Signal('missing')),
                        il.Eventually(il.Signal('missing').equals(0), 0),
                        il.Boolean(False) & il.Signal('missing').equals(0)):
            for query in (lambda: il.satisfies(formula, trace, 0),
                          lambda: il.denote(formula, trace, 0),
                          lambda: il.satisfying_times(formula, trace)):
                with self.assertRaises(il.TraceValidationError):
                    query()

    def test_defaults_copying_and_signal_equality(self):
        regions = {0: P.closedopen(0, 1)}
        signal = il.NaturalSignal(regions, default=2)
        regions.clear()
        props = {'p': P.singleton(0)}
        signals = {'j': signal, 'k': il.NaturalSignal({2: P.closed(0, 2)})}
        trace = il.Trace(P.closed(0, 2), props, signals)
        props.clear()
        signals.clear()
        self.assertEqual(il.satisfying_times('j = k', trace), P.closed(1, 2))
        self.assertTrue(il.satisfies('p', trace, 0))

    def test_exact_decimal_and_large_boundaries(self):
        trace = il.Trace(P.closed(0, 0.3), {'p': P.singleton(0.3)})
        self.assertEqual(trace.universe, P.closed(0, F(3, 10)))
        self.assertEqual(il.satisfying_times('eventually_0.1] p', trace), P.closed(F(1, 5), F(3, 10)))
        big = 10**30
        trace = il.Trace(P.closed(big, big+1), {'p': P.singleton(big+1)})
        self.assertTrue(il.satisfies('eventually_1] p', trace, big))
        self.assertFalse(il.satisfies('eventually_1 p', trace, big))
        self.assertEqual(il.satisfying_times('eventually_1 p', trace), P.openclosed(big, big+1))

    def test_empty_universe_and_past_windows(self):
        trace = il.Trace(P.empty())
        self.assertEqual(il.satisfying_times('always p', trace), P.empty())
        with self.assertRaises(il.TraceValidationError):
            il.denote('true', trace, 0)
        trace = il.Trace(P.closed(0, 4))
        for source, expected in [('always_[0,1) p', True), ('eventually_[0,1) p', False),
                                 ('p until_[0,1) p', False), ('p release_[0,1) p', True)]:
            self.assertEqual(il.satisfies(source, trace, 3), expected)

    def test_masks_and_rewrites_are_distinct_from_local_reductions(self):
        trace = il.Trace(P.closed(0, 2), {'p': P.closed(0, 1), 'q': P.singleton(2)})
        self.assertEqual(il.denote('eventually_0] p', trace, 0), trace.universe)
        self.assertEqual(il.denote('p', trace, 0), P.closed(0, 1))
        formulas = [il.Eventually('p', '0]'), il.Until('q', 'p', '0]'),
                    il.Release('q', 'p', '0]'), il.Selection('p', 'q', 1),
                    ~il.RestrictiveSelection(il.Eventually('p', 1), 1),
                    il.And(()), il.Or(())]
        for formula in formulas:
            for transform in (il.simplify, il.expand_derived, il.to_nnf):
                rewritten = transform(formula)
                self.assertEqual(il.satisfying_times(formula, trace), il.satisfying_times(rewritten, trace))
                for anchor in (0, F(1, 2), 1, 2):
                    self.assertEqual(il.denote(formula, trace, anchor), il.denote(rewritten, trace, anchor))

    def test_disconnected_prefix_and_absolute_selector_reanchoring(self):
        universe = P.closed(0, 1) | P.closed(3, 10)
        trace = il.Trace(universe, {'p': P.closedopen(5, 8), 'q': P.closedopen(3, 5) | P.closed(8, 10),
                                    'left': P.closed(0, 1), 'right': P.singleton(3)})
        self.assertTrue(il.satisfies('left until_[3,4) right', trace, 0))
        self.assertTrue(il.satisfies('always_[3,10] select(p,q)_[5,8)', trace, 0))
        self.assertEqual(il.satisfying_times('always_5] select(p)_3', trace),
                         il.satisfying_times('always_5] p', trace))
        full = il.Trace(P.closed(0, 4), {'left': P.closed(0, 1), 'right': P.singleton(3)})
        self.assertFalse(il.satisfies('left until_[3,4) right', full, 0))

    def test_traversal_and_exports(self):
        for base in (il.Formula, il.NumericTerm):
            with self.assertRaises(TypeError):
                base()
        self.assertEqual(il.And(()).depth, 0)
        self.assertEqual(il.Proposition('p').depth, 0)
        for name in il.__all__:
            self.assertTrue(hasattr(il, name), name)
        self.assertEqual(il.expand_derived(il.Or(())), il.Not(il.Boolean(True)))
        for source in ('p weak_until q', 'p W q'):
            with self.assertRaises(il.FormulaSyntaxError):
                il.parse_formula(source)
