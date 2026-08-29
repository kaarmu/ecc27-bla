import unittest

import interval_logic as il
import portion as P

from interval_logic import (
    ALL_TIME,
    And,
    Atom,
    Bool,
    Eventually,
    Exists,
    ForAll,
    Hold,
    Implies,
    Not,
    Or,
    ParseError,
    format_expression,
    parse,
)


class TemporalConstructionTests(unittest.TestCase):
    def test_constructors_and_fluent_methods_coerce_the_body(self):
        p, q = Atom("p"), Atom("q")
        self.assertEqual(Hold(2, "p & q"), Hold(2.0, And((p, q))))
        self.assertEqual(Eventually(2, "p | q"), Eventually(2.0, Or((p, q))))
        self.assertEqual(p.hold(1.5), Hold(1.5, p))
        self.assertEqual(p.eventually(1.5), Eventually(1.5, p))
        self.assertEqual(Hold(2, p).children, (p,))
        self.assertEqual(Eventually(2, p).depth, 2)

    def test_temporal_nodes_are_immutable_hashable_and_replaceable(self):
        p, q = Atom("p"), Atom("q")
        for expression, expected in (
            (Hold(2, p), Hold(2, q)),
            (Eventually(2, p), Eventually(2, q)),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(hash(expression), hash(type(expression)(2, p)))
                self.assertEqual(
                    expression.replace(lambda node: q if node is p else node),
                    expected,
                )

    def test_duration_must_be_finite_and_non_negative(self):
        p = Atom("p")
        for operator in (Hold, Eventually):
            for delta in (True, "1", None):
                with self.subTest(operator=operator, delta=delta):
                    with self.assertRaises(TypeError):
                        operator(delta, p)
            for delta in (-1, float("inf"), float("-inf"), float("nan")):
                with self.subTest(operator=operator, delta=delta):
                    with self.assertRaises(ValueError):
                        operator(delta, p)


class TemporalParserAndFormattingTests(unittest.TestCase):
    def test_requested_parenthesized_syntax_parses(self):
        self.assertEqual(parse("( H^2 p )"), Hold(2, Atom("p")))
        self.assertEqual(parse("( F^2 p )"), Eventually(2, Atom("p")))

    def test_temporal_operators_have_unary_precedence(self):
        p, q = Atom("p"), Atom("q")
        self.assertEqual(parse("H^2 p & q"), And((Hold(2, p), q)))
        self.assertEqual(parse("F^2 p | q"), Or((Eventually(2, p), q)))
        self.assertEqual(parse("H^2 (p | q)"), Hold(2, Or((p, q))))
        self.assertEqual(parse("!F^.5 p"), Not(Eventually(0.5, p)))
        self.assertEqual(parse("H^1e-3 !p"), Hold(0.001, Not(p)))
        self.assertEqual(parse("H"), Atom("H"))
        self.assertEqual(parse("F"), Atom("F"))

    def test_formatter_is_compact_and_round_trips(self):
        p, q = Atom("p"), Atom("q")
        expressions = (
            Hold(2, p),
            Eventually(1.5, Or((p, q))),
            Hold(0.1234567890123456, p),
            Not(Eventually(0.25, p)),
            Hold(3, Implies(p, q)),
        )
        self.assertEqual(str(expressions[0]), "H^2 p")
        self.assertEqual(str(expressions[1]), "F^1.5 (p ∨ q)")
        for expression in expressions:
            for unicode in (False, True):
                with self.subTest(expression=expression, unicode=unicode):
                    rendered = format_expression(expression, unicode=unicode)
                    self.assertEqual(parse(rendered), expression)

    def test_invalid_durations_raise_parse_errors(self):
        for prefix in ("H", "F"):
            for source in (
                f"{prefix}^-1 p",
                f"{prefix}^inf p",
                f"{prefix}^1e p",
                f"{prefix}^ p",
                f"{prefix}^2",
            ):
                with self.subTest(source=source):
                    with self.assertRaises(ParseError):
                        parse(source)


class HoldSemanticsTests(unittest.TestCase):
    def test_hold_is_closed_forward_erosion_with_exact_endpoints(self):
        universe = P.closed(0, 5)
        p = Atom("p")
        for truth, expected in (
            (P.closed(1, 4), P.closed(1, 3)),
            (P.openclosed(1, 4), P.openclosed(1, 3)),
            (P.closedopen(1, 4), P.closedopen(1, 3)),
            (P.open(1, 4), P.open(1, 3)),
        ):
            with self.subTest(truth=truth):
                self.assertEqual(il.denote(Hold(1, p), {"p": truth}, universe), expected)

    def test_failure_at_right_endpoint_invalidates_the_hold(self):
        universe = P.closed(0, 4)
        valuation = {"p": universe - P.singleton(2)}
        self.assertEqual(
            il.denote(Hold(0.5, Atom("p")), valuation, universe),
            P.closedopen(0, 1.5) | P.openclosed(2, 3.5),
        )

    def test_hold_does_not_clip_at_the_universe_boundary(self):
        universe = P.closed(0, 2)
        self.assertEqual(
            il.denote(Hold(100, Atom("p")), {"p": universe}, universe),
            P.empty(),
        )
        self.assertEqual(
            il.denote(Hold(1, Bool(True)), {}, universe),
            P.closed(0, 1),
        )

    def test_hold_cannot_cross_a_gap_in_the_universe(self):
        universe = P.closed(0, 1) | P.closed(3, 4)
        self.assertEqual(il.denote(Hold(3, Bool(True)), {}, universe), P.empty())

    def test_zero_duration_is_the_body(self):
        universe = P.closed(0, 4)
        truth = P.open(1, 3)
        self.assertEqual(
            il.denote(Hold(0, Atom("p")), {"p": truth}, universe),
            truth,
        )

    def test_hold_example_and_short_components(self):
        universe = P.closed(0, 10)
        p = Atom("p")
        self.assertEqual(
            il.denote(Hold(2, p), {"p": P.closed(2, 7)}, universe),
            P.closed(2, 5),
        )
        self.assertEqual(
            il.denote(Hold(2, p), {"p": P.closed(2, 3)}, universe),
            P.empty(),
        )

    def test_hold_preserves_unbounded_endpoint_topology(self):
        p = Atom("p")
        self.assertEqual(
            il.denote(Hold(5, p), {"p": P.closed(2, P.inf)}, ALL_TIME),
            P.closed(2, P.inf),
        )
        self.assertEqual(
            il.denote(Hold(2, p), {"p": P.open(-P.inf, 4)}, ALL_TIME),
            P.open(-P.inf, 2),
        )

    def test_forall_hold_matches_closed_minkowski_sum_when_represented(self):
        universe = P.closed(0, 6)
        p = Atom("p")
        left = ForAll(P.closed(1, 3), Hold(2, p))
        right = ForAll(P.closed(1, 5), p)
        for truth in (
            universe,
            P.closed(1, 5),
            P.closedopen(1, 5),
            P.closed(2, 5),
            P.closed(1, 5) - P.singleton(2.5),
        ):
            with self.subTest(truth=truth):
                valuation = {"p": truth}
                self.assertEqual(
                    il.denote(left, valuation, universe),
                    il.denote(right, valuation, universe),
                )


class EventuallySemanticsTests(unittest.TestCase):
    def test_eventually_is_closed_backward_dilation(self):
        universe = P.closed(0, 5)
        self.assertEqual(
            il.denote(
                Eventually(1, Atom("p")),
                {"p": P.openclosed(2, 3)},
                universe,
            ),
            P.openclosed(1, 3),
        )

    def test_eventually_zero_is_the_body_and_true_has_a_current_witness(self):
        universe = P.closed(0, 4)
        truth = P.open(1, 3)
        self.assertEqual(
            il.denote(Eventually(0, Atom("p")), {"p": truth}, universe),
            truth,
        )
        self.assertEqual(il.denote(Eventually(100, Bool(True)), {}, universe), universe)

    def test_eventually_can_witness_across_an_unrepresented_gap(self):
        universe = P.closed(0, 1) | P.closed(3, 4)
        self.assertEqual(
            il.denote(
                Eventually(2, Atom("p")),
                {"p": P.singleton(3)},
                universe,
            ),
            P.singleton(1) | P.singleton(3),
        )

    def test_duality_holds_on_fully_represented_start_times_only(self):
        universe = P.closed(0, 6)
        valid_starts = P.closed(0, 4)
        p = Atom("p")
        valuation = {"p": universe}
        negated_hold = il.denote(Not(Hold(2, p)), valuation, universe)
        eventual_negation = il.denote(Eventually(2, Not(p)), valuation, universe)
        self.assertEqual(negated_hold & valid_starts, eventual_negation & valid_starts)
        self.assertNotEqual(negated_hold, eventual_negation)


class TemporalTransformationTests(unittest.TestCase):
    def test_lowering_and_partitioning_recurse_through_temporal_nodes(self):
        p, q = Atom("p"), Atom("q")
        self.assertEqual(
            il.lower_derived(Hold(2, Implies(p, q))),
            Hold(2, Or((Not(p), q))),
        )
        self.assertEqual(
            il.lower_derived(Eventually(2, Implies(p, q))),
            Eventually(2, Or((Not(p), q))),
        )
        self.assertEqual(
            il.partition_intervals(Hold(2, ForAll(P.closed(0, 1), p))),
            Hold(2, ForAll(P.closed(0, 1), p)),
        )

    def test_universe_independent_nnf_retains_temporal_negations(self):
        p = Atom("p")
        self.assertEqual(il.to_nnf(Not(Hold(2, p))), Not(Hold(2, p)))
        self.assertEqual(
            il.to_nnf(Not(Eventually(2, p))),
            Not(Eventually(2, p)),
        )

    def test_simplification_handles_identities_booleans_and_nesting(self):
        p = Atom("p")
        finite = P.closed(0, 4)
        self.assertEqual(il.simplify(Hold(0, p)), p)
        self.assertEqual(il.simplify(Eventually(0, p)), p)
        self.assertEqual(il.simplify(Hold(2, Bool(False))), Bool(False))
        self.assertEqual(il.simplify(Eventually(2, Bool(False))), Bool(False))
        self.assertEqual(il.simplify(Eventually(2, Bool(True))), Bool(True))
        self.assertEqual(il.simplify(Hold(2, Bool(True))), Hold(2, Bool(True)))
        self.assertEqual(
            il.simplify(Hold(2, Bool(True)), universe=finite),
            Hold(2, Bool(True)),
        )
        self.assertEqual(
            il.simplify(Hold(2, Bool(True)), universe=ALL_TIME),
            Bool(True),
        )
        self.assertEqual(il.simplify(Hold(2, Hold(3, p))), Hold(5, p))
        self.assertEqual(
            il.simplify(Eventually(2, Eventually(3, p)), universe=finite),
            Eventually(5, p),
        )

    def test_distribution_duration_ordering_and_hold_contradiction(self):
        p, q = Atom("p"), Atom("q")
        universe = P.closed(0, 10)
        self.assertEqual(
            il.simplify(Hold(2, And((p, q)))),
            And((Hold(2, p), Hold(2, q))),
        )
        self.assertEqual(
            il.simplify(Eventually(2, Or((p, q)))),
            Or((Eventually(2, p), Eventually(2, q))),
        )
        self.assertEqual(
            il.simplify(And((Hold(2, p), Hold(5, p)))), Hold(5, p)
        )
        self.assertEqual(
            il.simplify(Or((Hold(2, p), Hold(5, p)))), Hold(2, p)
        )
        self.assertEqual(
            il.simplify(And((Eventually(2, p), Eventually(5, p)))),
            Eventually(2, p),
        )
        self.assertEqual(
            il.simplify(Or((Eventually(2, p), Eventually(5, p)))),
            Eventually(5, p),
        )
        self.assertEqual(
            il.simplify(And((Hold(2, p), Hold(3, Not(p)))), universe=universe),
            Bool(False),
        )

    def test_contextual_quantifier_and_duality_rewrites(self):
        p = Atom("p")
        universe = P.closed(0, 6)
        self.assertEqual(
            il.simplify(ForAll(P.closed(1, 3), Hold(2, p)), universe=universe),
            ForAll(P.closed(1, 5), p),
        )
        self.assertEqual(
            il.simplify(Exists(P.closed(1, 3), Eventually(2, p)), universe=universe),
            Exists(P.closed(1, 5), p),
        )
        self.assertEqual(
            il.simplify(ForAll(P.closed(4, 5), Hold(2, p)), universe=universe),
            ForAll(P.closed(4, 5), Hold(2, p)),
        )
        self.assertEqual(
            il.simplify(Not(Hold(2, p)), universe=ALL_TIME),
            Eventually(2, Not(p)),
        )
        self.assertEqual(
            il.simplify(Not(Eventually(2, p)), universe=ALL_TIME),
            Hold(2, Not(p)),
        )

    def test_minkowski_rewrite_preserves_union_endpoint_topology(self):
        p = Atom("p")
        universe = P.closed(0, 10)
        starts = P.openclosed(1, 2) | P.closedopen(4, 5)
        expanded = P.openclosed(1, 3) | P.closedopen(4, 6)
        self.assertEqual(
            il.simplify(ForAll(starts, Hold(1, p)), universe=universe),
            ForAll(expanded, p),
        )

    def test_important_non_rules_are_not_applied(self):
        p, q = Atom("p"), Atom("q")
        self.assertEqual(il.simplify(Hold(2, Or((p, q)))), Hold(2, Or((p, q))))
        self.assertEqual(
            il.simplify(Eventually(2, And((p, q)))),
            Eventually(2, And((p, q))),
        )

    def test_temporal_simplification_is_idempotent(self):
        p, q = Atom("p"), Atom("q")
        universe = P.closed(0, 10)
        formulas = (
            Hold(2, And((p, Hold(3, q)))),
            Eventually(2, Or((p, Eventually(3, q)))),
            ForAll(P.closed(1, 3), Hold(2, p)),
            Exists(P.closed(1, 3), Eventually(2, q)),
        )
        for formula in formulas:
            with self.subTest(formula=formula):
                result = il.simplify(formula, universe=universe)
                self.assertEqual(il.simplify(result, universe=universe), result)


if __name__ == "__main__":
    unittest.main()
