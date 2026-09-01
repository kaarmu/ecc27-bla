import unittest

import interval_logic as il
import portion as P

from interval_logic import (
    And,
    Bool,
    Eventually,
    ExistentialCondition,
    Implies,
    Not,
    Or,
    ParseError,
    Proposition,
    UniversalCondition,
    format_expression,
    parse,
)


class EventuallyConstructionTests(unittest.TestCase):
    def test_constructor_and_fluent_method_coerce_the_body(self):
        p, q = Proposition("p"), Proposition("q")
        self.assertEqual(Eventually(2, "p | q"), Eventually(2.0, Or((p, q))))
        self.assertEqual(p.eventually(1.5), Eventually(1.5, p))
        self.assertEqual(Eventually(2, p).children, (p,))
        self.assertEqual(Eventually(2, p).depth, 2)

    def test_node_is_immutable_hashable_and_replaceable(self):
        p, q = Proposition("p"), Proposition("q")
        expression = Eventually(2, p)
        self.assertEqual(hash(expression), hash(Eventually(2, p)))
        self.assertEqual(
            expression.replace(lambda node: q if node is p else node),
            Eventually(2, q),
        )

    def test_duration_must_be_finite_and_non_negative(self):
        p = Proposition("p")
        with self.assertRaises(TypeError):
            Eventually(True, p)
        with self.assertRaises(ValueError):
            Eventually("1", p)
        self.assertEqual(Eventually(None, p), Eventually(il.DEFAULT_TEMPORAL_PARAMETER, p))
        for delta in (-1, float("inf"), float("-inf"), float("nan")):
            with self.subTest(delta=delta):
                with self.assertRaises(ValueError):
                    Eventually(delta, p)


class EventuallyParserAndFormattingTests(unittest.TestCase):
    def test_parenthesized_syntax_and_precedence(self):
        p, q = Proposition("p"), Proposition("q")
        self.assertEqual(parse("( F^2 p )"), Eventually(2, p))
        self.assertEqual(parse("F^2 p | q"), Or((Eventually(2, p), q)))
        self.assertEqual(parse("!F^.5 p"), Not(Eventually(0.5, p)))
        self.assertEqual(parse("H"), Proposition("H"))
        self.assertEqual(parse("F"), Proposition("F"))
        with self.assertRaises(ParseError):
            parse("H^2 p")

    def test_formatter_is_compact_and_round_trips(self):
        p, q = Proposition("p"), Proposition("q")
        expressions = (
            Eventually(1.5, Or((p, q))),
            Not(Eventually(0.25, p)),
            Eventually(3, Implies(p, q)),
        )
        self.assertEqual(str(expressions[0]), "F^1.5 (p ∨ q)")
        for expression in expressions:
            for unicode in (False, True):
                with self.subTest(expression=expression, unicode=unicode):
                    rendered = format_expression(expression, unicode=unicode)
                    self.assertEqual(parse(rendered), expression)

    def test_invalid_durations_raise_parse_errors(self):
        for source in ("F^-1 p", "F^inf p", "F^1e p", "F^ p", "F^2"):
            with self.subTest(source=source):
                with self.assertRaises(ParseError):
                    parse(source)


class EventuallySemanticsTests(unittest.TestCase):
    def test_closed_backward_dilation_preserves_endpoints(self):
        universe = P.closed(0, 5)
        self.assertEqual(
            il.satisfying_anchors(
                Eventually(1, Proposition("p")),
                {"p": P.openclosed(2, 3)},
                universe,
            ),
            P.openclosed(1, 3),
        )

    def test_zero_is_the_body_and_true_has_a_current_witness(self):
        universe = P.closed(0, 4)
        truth = P.open(1, 3)
        self.assertEqual(
            il.satisfying_anchors(Eventually(0, Proposition("p")), {"p": truth}, universe),
            truth,
        )
        self.assertEqual(
            il.satisfying_anchors(Eventually(100, Bool(True)), {}, universe),
            universe,
        )

    def test_witness_can_cross_an_unrepresented_gap(self):
        universe = P.closed(0, 1) | P.closed(3, 4)
        self.assertEqual(
            il.satisfying_anchors(
                Eventually(2, Proposition("p")),
                {"p": P.singleton(3)},
                universe,
            ),
            P.singleton(1) | P.singleton(3),
        )


class EventuallyTransformationTests(unittest.TestCase):
    def test_lowering_partitioning_and_nnf_recurse(self):
        p, q = Proposition("p"), Proposition("q")
        self.assertEqual(
            il.lower_derived(Eventually(2, Implies(p, q))),
            Eventually(2, Or((Not(p), q))),
        )
        self.assertEqual(
            il.partition_intervals(
                Eventually(2, UniversalCondition(P.closed(0, 1), p))
            ),
            UniversalCondition(P.closed(0, 1), p),
        )
        self.assertEqual(
            il.to_nnf(Not(Eventually(2, p))),
            UniversalCondition(2, Not(p)),
        )

    def test_simplification_identities_distribution_and_nesting(self):
        p, q = Proposition("p"), Proposition("q")
        universe = P.closed(0, 4)
        self.assertEqual(il.simplify(Eventually(0, p)), p)
        self.assertEqual(il.simplify(Eventually(2, Bool(False))), Bool(False))
        self.assertEqual(il.simplify(Eventually(2, Bool(True))), Bool(True))
        self.assertEqual(
            il.simplify(Eventually(2, Eventually(3, p)), universe=universe),
            Eventually(5, p),
        )
        self.assertEqual(
            il.simplify(Eventually(2, Or((p, q)))),
            Or((Eventually(2, p), Eventually(2, q))),
        )
        self.assertEqual(
            il.simplify(And((Eventually(2, p), Eventually(5, p)))),
            Eventually(2, p),
        )
        self.assertEqual(
            il.simplify(Or((Eventually(2, p), Eventually(5, p)))),
            Eventually(5, p),
        )

    def test_absolute_existential_expansion_requires_connected_result(self):
        p = Proposition("p")
        interval = P.closed(0, 5)
        formula = ExistentialCondition(interval, Eventually(1, p))

        connected_universe = P.closed(0, 6)
        self.assertEqual(
            il.simplify(formula, universe=connected_universe),
            ExistentialCondition(P.closed(0, 6), p),
        )

        disconnected_universe = P.closed(0, 1) | P.closed(4, 5)
        self.assertEqual(
            il.simplify(formula, universe=disconnected_universe),
            formula,
        )

    def test_important_non_rule_and_idempotence(self):
        p, q = Proposition("p"), Proposition("q")
        universe = P.closed(0, 10)
        formula = Eventually(2, And((p, q)))
        self.assertEqual(il.simplify(formula), formula)

        nested = Eventually(2, Or((p, Eventually(3, q))))
        result = il.simplify(nested, universe=universe)
        self.assertEqual(il.simplify(result, universe=universe), result)


if __name__ == "__main__":
    unittest.main()
