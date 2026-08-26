import unittest

import interval_logic as il
import portion as P

from interval_logic import (
    And,
    Atom,
    Bool,
    ForAll,
    Hold,
    Implies,
    Not,
    Or,
    ParseError,
    format_expression,
    parse,
)


class HoldConstructionTests(unittest.TestCase):
    def test_constructor_and_fluent_method_coerce_the_body(self):
        p, q = Atom("p"), Atom("q")

        self.assertEqual(Hold(2, "p & q"), Hold(2.0, And((p, q))))
        self.assertEqual(p.hold(1.5), Hold(1.5, p))
        self.assertEqual(Hold(2, p).children, (p,))
        self.assertEqual(Hold(2, p).depth, 2)

    def test_hold_is_immutable_hashable_and_replaceable(self):
        p, q = Atom("p"), Atom("q")
        expression = Hold(2, p)

        self.assertEqual(hash(expression), hash(Hold(2, p)))
        self.assertEqual(
            expression.replace(lambda node: q if node is p else node),
            Hold(2, q),
        )

    def test_duration_must_be_finite_and_non_negative(self):
        p = Atom("p")

        for delta in (True, "1", None):
            with self.subTest(delta=delta):
                with self.assertRaises(TypeError):
                    Hold(delta, p)
        for delta in (-1, float("inf"), float("-inf"), float("nan")):
            with self.subTest(delta=delta):
                with self.assertRaises(ValueError):
                    Hold(delta, p)


class HoldParserAndFormattingTests(unittest.TestCase):
    def test_requested_parenthesized_syntax_parses(self):
        self.assertEqual(parse("( H^2 p )"), Hold(2, Atom("p")))

    def test_hold_is_a_prefix_operator_with_unary_precedence(self):
        p, q = Atom("p"), Atom("q")

        self.assertEqual(parse("H^2 p & q"), And((Hold(2, p), q)))
        self.assertEqual(parse("H^2 (p | q)"), Hold(2, Or((p, q))))
        self.assertEqual(parse("!H^.5 p"), Not(Hold(0.5, p)))
        self.assertEqual(parse("H^1e-3 !p"), Hold(0.001, Not(p)))
        self.assertEqual(parse("H"), Atom("H"))

    def test_formatter_is_compact_and_round_trips(self):
        p, q = Atom("p"), Atom("q")
        expressions = (
            Hold(2, p),
            Hold(1.5, Or((p, q))),
            Hold(0.1234567890123456, p),
            Not(Hold(0.25, p)),
            Hold(3, Implies(p, q)),
        )

        self.assertEqual(str(expressions[0]), "H^2 p")
        self.assertEqual(str(expressions[1]), "H^1.5 (p ∨ q)")
        for expression in expressions:
            for unicode in (False, True):
                with self.subTest(expression=expression, unicode=unicode):
                    rendered = format_expression(expression, unicode=unicode)
                    self.assertEqual(parse(rendered), expression)

    def test_invalid_durations_raise_parse_errors(self):
        for source in ("H^-1 p", "H^inf p", "H^1e p", "H^ p", "H^2"):
            with self.subTest(source=source):
                with self.assertRaises(ParseError):
                    parse(source)


class HoldSemanticsTests(unittest.TestCase):
    def test_hold_erodes_truth_to_the_left_with_exact_endpoints(self):
        universe = P.closed(0, 5)
        valuation = {"p": P.openclosed(1, 4)}

        self.assertEqual(
            il.denote(Hold(1, Atom("p")), valuation, universe),
            P.openclosed(1, 3),
        )

    def test_half_open_hold_window_excludes_its_right_endpoint(self):
        universe = P.closed(0, 4)
        valuation = {"p": universe - P.singleton(2)}

        self.assertEqual(
            il.denote(Hold(0.5, Atom("p")), valuation, universe),
            P.closed(0, 1.5) | P.openclosed(2, 4),
        )

    def test_hold_windows_are_clipped_to_the_evaluation_universe(self):
        universe = P.closed(0, 2)

        self.assertEqual(
            il.denote(Hold(100, Atom("p")), {"p": universe}, universe),
            universe,
        )

    def test_hold_spans_gaps_in_a_disconnected_universe(self):
        universe = P.closed(0, 1) | P.closed(3, 4)
        valuation = {"p": universe - P.singleton(3)}

        self.assertEqual(
            il.denote(Hold(3, Atom("p")), valuation, universe),
            P.singleton(0) | P.openclosed(3, 4),
        )

    def test_zero_duration_is_vacuously_true(self):
        universe = P.closed(0, 4)
        valuation = {"p": P.open(1, 3)}
        p = Atom("p")

        self.assertEqual(
            il.denote(Hold(0, p), valuation, universe),
            universe,
        )

    def test_forall_hold_matches_extended_forall_interval(self):
        universe = P.closed(0, 6)
        p = Atom("p")
        left = ForAll(P.closed(1, 3), Hold(2, p))
        right = ForAll(P.closedopen(1, 5), p)
        truth_sets = (
            universe,
            P.closed(1, 5),
            P.closedopen(1, 5),
            P.closed(2, 5),
            P.closed(1, 5) - P.singleton(2.5),
        )

        for truth in truth_sets:
            with self.subTest(truth=truth):
                valuation = {"p": truth}
                self.assertEqual(
                    il.denote(left, valuation, universe),
                    il.denote(right, valuation, universe),
                )


class HoldTransformationTests(unittest.TestCase):
    def test_lowering_and_partitioning_recurse_through_hold(self):
        p, q = Atom("p"), Atom("q")

        self.assertEqual(
            il.lower_derived(Hold(2, Implies(p, q))),
            Hold(2, Or((Not(p), q))),
        )
        self.assertEqual(
            il.partition_intervals(Hold(2, ForAll(P.closed(0, 1), p))),
            Hold(2, ForAll(P.closed(0, 1), p)),
        )

    def test_simplification_handles_identity_and_boolean_holds(self):
        p = Atom("p")

        self.assertEqual(il.simplify(Hold(0, p)), Bool(True))
        self.assertEqual(il.simplify(Hold(2, Bool(True))), Bool(True))
        self.assertEqual(il.simplify(Hold(2, Bool(False))), Bool(False))
        self.assertEqual(il.simplify(Not(Hold(2, p))), Not(Hold(2, p)))


if __name__ == "__main__":
    unittest.main()
