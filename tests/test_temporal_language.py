import itertools
import unittest

import portion as P

import interval_logic as il


class TemporalParameterTests(unittest.TestCase):
    def test_parameter_kinds_resolution_and_default(self):
        absolute = il.coerce_temporal_parameter("[1,3)")
        relative = il.coerce_temporal_parameter("[1,3)+")

        self.assertIsInstance(absolute, P.Interval)
        self.assertEqual(il.resolve_window(absolute, 10), P.closedopen(1, 3))
        self.assertEqual(il.resolve_window(relative, 10), P.closedopen(11, 13))
        self.assertEqual(il.resolve_window("3]", 10), P.closed(10, 13))
        self.assertEqual(il.resolve_window("3)", 10), P.closedopen(10, 13))
        self.assertEqual(il.resolve_window(None, 10), P.closed(10, P.inf))

    def test_zero_endpoint_and_relative_validation(self):
        self.assertEqual(il.resolve_window("0]", 4), P.singleton(4))
        self.assertTrue(il.resolve_window("0)", 4).empty)
        with self.assertRaises(ValueError):
            il.RelativeInterval(P.empty())
        with self.assertRaises(ValueError):
            il.RelativeInterval(P.closed(-1, 2))
        with self.assertRaises(ValueError):
            il.RelativeInterval(P.closed(0, 1) | P.closed(2, 3))

    def test_span_discards_a_relative_lower_bound(self):
        self.assertEqual(
            il.span_parameter(il.RelativeInterval(P.closed(2, 5))),
            il.RelativeInterval(P.closed(0, 5)),
        )
        self.assertEqual(
            il.span_parameter(il.RelativeInterval(P.open(2, 5))),
            il.RelativeInterval(P.closedopen(0, 5)),
        )
        self.assertEqual(il.span_parameter("[2,5]"), P.closed(2, 5))


class CanonicalSyntaxTests(unittest.TestCase):
    def test_canonical_forms_parse_and_round_trip(self):
        p, q = il.Proposition("p"), il.Proposition("q")
        examples = {
            "⟨p,q⟩_[1,3]+": il.Selection(
                il.RelativeInterval(P.closed(1, 3)), p, q
            ),
            "⟨p⟩*_3)": il.RestrictiveSelection("3)", p),
            "□_[0,5]+ p": il.UniversalCondition(
                il.RelativeInterval(P.closed(0, 5)), p
            ),
            "◇p": il.ExistentialCondition(None, p),
            "p U_[1,3]+ q": il.Until(
                il.RelativeInterval(P.closed(1, 3)), p, q
            ),
            "p W q": il.WeakUntil(None, p, q),
            "p R_3] q": il.Release(3, p, q),
        }
        for source, expected in examples.items():
            with self.subTest(source=source):
                parsed = il.parse(source)
                self.assertEqual(parsed, expected)
                self.assertEqual(il.parse(str(parsed)), parsed)
                self.assertEqual(
                    il.parse(il.format_expression(parsed, unicode=False)), parsed
                )

    def test_until_is_right_associative_and_binds_above_conjunction(self):
        p, q, r = (il.Proposition(name) for name in "pqr")
        self.assertEqual(
            il.parse("p U q U r & p"),
            il.And((il.Until(None, p, il.Until(None, q, r)), p)),
        )

    def test_legacy_syntax_remains_accepted(self):
        p = il.Proposition("p")
        interval = P.closed(0, 2)
        self.assertEqual(il.parse("[0,2]_(p)"), il.RestrictiveSelection(interval, p))
        self.assertEqual(il.parse("[0,2]^(p)"), il.VacuousSelection(interval, p))
        self.assertEqual(il.parse("forall[0,2]: p"), il.UniversalCondition(interval, p))
        self.assertEqual(il.parse("exists[0,2]: p"), il.ExistentialCondition(interval, p))
        self.assertEqual(il.parse("F^2 p"), il.Eventually(2, p))

    def test_new_nodes_participate_in_replacement_and_ordering(self):
        p, q, r = (il.Proposition(name) for name in "pqr")
        expression = il.Selection(
            "2]",
            il.Until(None, p, q),
            il.Release("[1,3]+", q, p),
        )
        expected = il.Selection(
            "2]",
            il.Until(None, r, q),
            il.Release("[1,3]+", q, r),
        )
        self.assertEqual(expression.replace(lambda item: r if item == p else item), expected)
        self.assertNotEqual(il.expression_key(expression), il.expression_key(expected))

    def test_invalid_canonical_parameters_report_parse_errors(self):
        for source in (
            "◇_[1,1)+ p",
            "□_[-1,2]+ p",
            "p U_[0,2 q",
            "⟨p,q⟩*_2]",
        ):
            with self.subTest(source=source):
                with self.assertRaises(il.ParseError):
                    il.parse(source)


class AnchoredSemanticsTests(unittest.TestCase):
    def test_binary_selection_preserves_the_outer_anchor(self):
        universe = P.closed(0, 3)
        p = il.Proposition("p")
        expression = il.Selection(
            P.closed(0, 2),
            il.Eventually(1, p),
            il.Bool(False),
        )
        valuation = {"p": P.singleton(1)}

        self.assertEqual(
            il.anchored_denotation(expression, valuation, 0, universe),
            P.closed(0, 2),
        )
        self.assertEqual(
            il.satisfying_anchors(expression, valuation, universe),
            P.closed(0, 1),
        )

    def test_conditions_reanchor_their_operands(self):
        universe = P.closed(0, 5)
        expression = il.parse("□_2] ◇_1] p")
        self.assertEqual(
            il.satisfying_anchors(
                expression,
                {"p": P.closed(1, 4)},
                universe,
            ),
            P.closed(0, 2),
        )

    def test_conditions_and_until_have_global_fixed_anchor_values(self):
        universe = P.closed(0, 4)
        p, q = il.Proposition("p"), il.Proposition("q")
        valuation = {"p": P.closedopen(0, 2), "q": P.singleton(2)}
        condition = il.ExistentialCondition("2]", q)
        until = il.Until("2]", p, q)

        self.assertEqual(
            il.anchored_denotation(condition, valuation, 0, universe), universe
        )
        self.assertEqual(il.anchored_denotation(until, valuation, 0, universe), universe)
        self.assertEqual(il.anchored_denotation(until, valuation, 3, universe), P.empty())

    def test_empty_and_zero_duration_windows(self):
        universe = P.closed(0, 2)
        p = il.Proposition("p")
        self.assertEqual(
            il.satisfying_anchors(il.UniversalCondition("0)", p), {}, universe),
            universe,
        )
        self.assertEqual(
            il.satisfying_anchors(il.ExistentialCondition("0)", p), {}, universe),
            P.empty(),
        )
        self.assertEqual(
            il.satisfying_anchors(
                il.ExistentialCondition("0]", p),
                {"p": P.singleton(1)},
                universe,
            ),
            P.singleton(1),
        )

    def test_denotation_diagonal_matches_the_anchor_sweep(self):
        universe = P.closed(0, 4)
        p, q = il.Proposition("p"), il.Proposition("q")
        valuation = {"p": P.closedopen(0, 2), "q": P.closed(2, 3)}
        expressions = (
            il.Selection("[1,3]+", p, q),
            il.UniversalCondition("2]", p),
            il.ExistentialCondition("[1,2]+", q),
            il.Until("3]", p, q),
            il.Release("3]", p, q),
            il.WeakUntil("[1,3)+", p, q),
        )
        for expression in expressions:
            truth = il.satisfying_anchors(expression, valuation, universe)
            for anchor in (0, 0.5, 1, 2, 3, 4):
                with self.subTest(expression=expression, anchor=anchor):
                    denotation = il.anchored_denotation(
                        expression, valuation, anchor, universe
                    )
                    self.assertEqual(anchor in denotation, anchor in truth)


class UntilSemanticsTests(unittest.TestCase):
    def test_relative_until_prefix_and_witness_rules(self):
        universe = P.closed(0, 5)
        p, q = il.Proposition("p"), il.Proposition("q")

        self.assertEqual(
            il.satisfying_anchors(
                il.Until("3]", p, q),
                {"p": P.closedopen(0, 2), "q": P.singleton(2)},
                universe,
            ),
            P.closed(0, 2),
        )
        self.assertEqual(
            il.satisfying_anchors(
                il.Until("[2,3]+", p, q),
                {"p": P.closedopen(0, 2), "q": P.singleton(2)},
                universe,
            ),
            P.singleton(0),
        )

    def test_absolute_until_orders_only_points_in_its_interval(self):
        universe = P.closed(0, 4)
        p, q = il.Proposition("p"), il.Proposition("q")
        expression = il.Until(P.closed(1, 3), p, q)
        self.assertEqual(
            il.satisfying_anchors(
                expression,
                {"p": P.closedopen(1, 2), "q": P.singleton(2)},
                universe,
            ),
            universe,
        )
        self.assertEqual(
            il.satisfying_anchors(
                expression,
                {"p": P.singleton(1), "q": P.singleton(2)},
                universe,
            ),
            P.empty(),
        )

    def test_weak_until_span_release_and_eventual_identity(self):
        universe = P.closed(0, 5)
        p, q = il.Proposition("p"), il.Proposition("q")
        valuation = {"p": P.closedopen(0, 3), "q": P.empty()}
        weak = il.WeakUntil("[2,3)+", p, q)
        no_witness = il.UniversalCondition("3)", p)
        self.assertEqual(
            il.satisfying_anchors(weak, valuation, universe),
            il.satisfying_anchors(no_witness, valuation, universe),
        )

        release = il.Release("3]", p, q)
        dual = ~il.Until("3]", ~p, ~q)
        self.assertEqual(
            il.satisfying_anchors(release, valuation, universe),
            il.satisfying_anchors(dual, valuation, universe),
        )

        eventual = il.ExistentialCondition("[1,3]+", p)
        until = il.Until("[1,3]+", il.Bool(True), p)
        self.assertEqual(
            il.satisfying_anchors(eventual, valuation, universe),
            il.satisfying_anchors(until, valuation, universe),
        )

    def test_relative_until_sweep_matches_a_finite_oracle(self):
        points = range(4)
        universe = P.empty()
        for point in points:
            universe |= P.singleton(point)
        p, q = il.Proposition("p"), il.Proposition("q")
        parameters = ("2]", "2)", "[1,2]+")

        for left_bits in itertools.product((False, True), repeat=4):
            left = _point_set(points, left_bits)
            for right_bits in itertools.product((False, True), repeat=4):
                right = _point_set(points, right_bits)
                valuation = {"p": left, "q": right}
                for parameter in parameters:
                    expression = il.Until(parameter, p, q)
                    expected = P.empty()
                    for anchor in points:
                        window = il.resolve_window(parameter, anchor) & universe
                        for witness in points:
                            if witness not in window or witness not in right:
                                continue
                            prefix = universe & P.closedopen(anchor, witness)
                            if (prefix - left).empty:
                                expected |= P.singleton(anchor)
                                break
                    self.assertEqual(
                        il.satisfying_anchors(expression, valuation, universe),
                        expected,
                    )


class TemporalTransformationTests(unittest.TestCase):
    def test_nnf_uses_all_temporal_duals(self):
        p, q = il.Proposition("p"), il.Proposition("q")
        self.assertEqual(
            il.to_nnf(~il.ExistentialCondition("2]", p)),
            il.UniversalCondition("2]", ~p),
        )
        self.assertEqual(
            il.to_nnf(~il.Until("2]", p, q)),
            il.Release("2]", ~p, ~q),
        )
        self.assertEqual(
            il.to_nnf(~il.Selection("2]", p, q)),
            il.Selection("2]", ~p, ~q),
        )

    def test_absolute_until_partitioning_preserves_semantics(self):
        universe = P.closed(0, 4)
        p, q = il.Proposition("p"), il.Proposition("q")
        expression = il.And(
            (
                il.Until(P.closed(0, 4), p, q),
                il.UniversalCondition(P.closed(1, 3), p),
            )
        )
        partitioned = il.partition_intervals(expression)
        valuation = {"p": P.closed(0, 3), "q": P.singleton(3)}
        self.assertEqual(
            il.satisfying_anchors(expression, valuation, universe),
            il.satisfying_anchors(partitioned, valuation, universe),
        )

    def test_simplifier_does_not_globalize_future_only_empty_windows(self):
        universe = P.closed(0, 1)
        universal = il.UniversalCondition("[1,2]+", il.Bool(False))
        existential = il.ExistentialCondition("[1,2]+", il.Bool(True))

        for expression in (universal, existential):
            with self.subTest(expression=expression):
                simplified = il.simplify(expression, universe=universe)
                self.assertEqual(
                    il.satisfying_anchors(expression, {}, universe),
                    il.satisfying_anchors(simplified, {}, universe),
                )


class RelativeSelectionIdentityTests(unittest.TestCase):
    def test_all_finite_relative_selection_identities(self):
        universe = P.closed(-1, 6)
        p = il.Proposition("p")
        valuation = {"p": P.closedopen(1, 4)}
        cases = (
            (P.closed(2, 4), "4]", "2)"),
            (P.closedopen(2, 4), "4)", "2)"),
            (P.openclosed(2, 4), "4]", "2]"),
            (P.open(2, 4), "4)", "2]"),
        )
        for offsets, upper, lower_prefix in cases:
            with self.subTest(offsets=offsets):
                left = il.VacuousSelection(il.RelativeInterval(offsets), p)
                right = il.Or(
                    (
                        il.VacuousSelection(upper, p),
                        il.RestrictiveSelection(lower_prefix, il.Bool(True)),
                    )
                )
                for anchor in (0, 1):
                    self.assertEqual(
                        il.anchored_denotation(left, valuation, anchor, universe),
                        il.anchored_denotation(right, valuation, anchor, universe),
                    )


def _point_set(points, bits):
    result = P.empty()
    for point, enabled in zip(points, bits):
        if enabled:
            result |= P.singleton(point)
    return result


if __name__ == "__main__":
    unittest.main()
