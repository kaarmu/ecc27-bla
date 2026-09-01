import unittest

import interval_logic as il
import portion as P

from interval_logic import (
    And,
    Proposition,
    Bool,
    Equal,
    Equivalent,
    ExistentialCondition,
    UniversalCondition,
    VacuousSelection,
    Implies,
    NaturalLiteral,
    Not,
    Or,
    ParseError,
    RestrictiveSelection,
    Signal,
    Xor,
    format_expression,
    parse,
    parse_expression,
)


class ParserTests(unittest.TestCase):
    def test_expression_slots_parse_string_inputs(self):
        p, q, r = Proposition("p"), Proposition("q"), Proposition("r")

        self.assertEqual(il.as_expr("p | q"), Or((p, q)))
        self.assertEqual(Not("p & q"), Not(And((p, q))))
        self.assertEqual(And(("p", "q | r")), And((p, Or((q, r)))))
        self.assertEqual(Or(("p", "q & r")), Or((p, And((q, r)))))
        self.assertEqual(RestrictiveSelection("[0,1]", "p | q"), RestrictiveSelection("[0,1]", Or((p, q))))
        self.assertEqual(VacuousSelection("[0,1]", "p & q"), VacuousSelection("[0,1]", And((p, q))))
        self.assertEqual(UniversalCondition("[0,1]", "p -> q"), UniversalCondition("[0,1]", Implies(p, q)))
        self.assertEqual(ExistentialCondition("[0,1]", "p xor q"), ExistentialCondition("[0,1]", Xor(p, q)))
        self.assertEqual(Implies("p & q", "r"), Implies(And((p, q)), r))
        self.assertEqual(Equivalent("p", "q"), Equivalent(p, q))
        self.assertEqual(Xor("p", "q"), Xor(p, q))
        self.assertEqual(p & "q | r", And((p, Or((q, r)))))
        self.assertEqual("q | r" & p, And((Or((q, r)), p)))

    def test_public_expression_apis_parse_string_inputs(self):
        p, q = Proposition("p"), Proposition("q")
        universe = P.closed(0, 2)
        valuation = {"p": P.closed(0, 1), "q": P.closed(1, 2)}

        self.assertEqual(il.format_expression("p & q"), "p ∧ q")
        self.assertEqual(il.expression_key("p"), il.expression_key(p))
        self.assertEqual(il.simplify("p & true"), p)
        self.assertEqual(il.lower_derived("p -> q"), Or((Not(p), q)))
        self.assertEqual(il.lower_derived(StringLowering()), And((p, q)))
        self.assertEqual(il.to_nnf("!(p | q)"), And((Not(p), Not(q))))
        self.assertIsInstance(
            il.partition_intervals("(forall[0,1]: p) & (forall[1,2]: q)"),
            And,
        )
        self.assertEqual(il.satisfying_anchors("p & q", valuation, universe), P.singleton(1))
        self.assertTrue(il.satisfies("p | q", valuation, 0, universe))
        self.assertEqual(il.timeline("p", valuation, universe).expression, p)
        self.assertEqual(p.replace(lambda _expression: "q"), q)

    def test_ascii_and_unicode_operators_construct_the_same_expression(self):
        expected = Equivalent(
            Implies(And((Proposition("p"), Not(Proposition("q")))), Proposition("r")),
            Xor(Proposition("s"), Bool(False)),
        )

        self.assertEqual(parse("(p & !q -> r) <-> s xor false"), expected)
        self.assertEqual(parse_expression("(p ∧ ¬q → r) ↔ s ⊕ ⊥"), expected)

    def test_precedence_and_associativity_match_pretty_printer(self):
        self.assertEqual(
            parse("p | q & r -> s -> t"),
            Implies(
                Or((Proposition("p"), And((Proposition("q"), Proposition("r"))))),
                Implies(Proposition("s"), Proposition("t")),
            ),
        )
        self.assertEqual(
            parse("p & q & r"), And((Proposition("p"), Proposition("q"), Proposition("r")))
        )
        self.assertEqual(
            parse("p | q | r"), Or((Proposition("p"), Proposition("q"), Proposition("r")))
        )

    def test_conditions_parse_full_scope_and_can_be_nested(self):
        self.assertEqual(
            parse("forall[0, 1): p | (exists(2, 3]: q & r)"),
            UniversalCondition(
                P.closedopen(0.0, 1.0),
                Or(
                    (
                        Proposition("p"),
                        ExistentialCondition(
                            P.openclosed(2.0, 3.0),
                            And((Proposition("q"), Proposition("r"))),
                        ),
                    )
                ),
            ),
        )

    def test_selections_support_connected_and_empty_intervals(self):
        self.assertEqual(
            parse("[0,1)_(p | q)"),
            RestrictiveSelection(
                P.closedopen(0.0, 1.0),
                Or((Proposition("p"), Proposition("q"))),
            ),
        )
        self.assertEqual(
            parse("(-inf,+inf)^(p)"),
            VacuousSelection(P.open(-P.inf, P.inf), Proposition("p")),
        )
        self.assertEqual(parse("()_(p)"), RestrictiveSelection(P.empty(), Proposition("p")))
    def test_absolute_parameters_reject_disconnected_intervals(self):
        sources = (
            "[0,1) | (2.5,3]_(p | q)",
            "[0,1) | (2.5,3]^(p | q)",
            "forall[0,1) | (2.5,3]: p | q",
            "exists[0,1) | (2.5,3]: p | q",
        )
        for source in sources:
            with self.subTest(source=source):
                with self.assertRaisesRegex(ParseError, "must be connected"):
                    parse(source)

    def test_equalities_distinguish_signals_from_propositions_and_naturals(self):
        self.assertEqual(parse("j_1 = 17"), Equal(Signal("j_1"), NaturalLiteral(17)))
        self.assertEqual(
            parse("`charging point 2` != j_1"),
            Not(Equal(Signal("charging point 2"), Signal("j_1"))),
        )
        self.assertEqual(parse("0 = 1"), Equal(NaturalLiteral(0), NaturalLiteral(1)))

    def test_quoted_names_unescape_backticks_and_backslashes(self):
        expression = Proposition("path `A` \\ ready")
        rendered = format_expression(expression, unicode=False)

        self.assertEqual(parse(rendered), expression)
        self.assertEqual(parse("`true`"), Proposition("true"))
        self.assertEqual(str(Proposition("forall")), "`forall`")

    def test_formatter_output_round_trips_for_builtin_nodes(self):
        p, q = Proposition("p"), Proposition("name with spaces")
        equality = Not(Equal(Signal("j"), NaturalLiteral(0)))
        expressions = (
            Bool(True),
            Bool(False),
            p,
            q,
            equality,
            Not(Not(equality)),
            And((p, Not(q), equality)),
            Or((p, And((q, equality)))),
            RestrictiveSelection(P.closedopen(0, 1), Or((p, q))),
            VacuousSelection(P.open(-P.inf, P.inf), p),
            UniversalCondition(P.closed(0, 1), Implies(p, q)),
            ExistentialCondition(P.empty(), Xor(p, q)),
            Implies(Implies(p, q), p),
            Equivalent(p, Xor(q, p)),
        )

        for expression in expressions:
            for unicode in (False, True):
                with self.subTest(expression=expression, unicode=unicode):
                    rendered = format_expression(expression, unicode=unicode)
                    self.assertEqual(parse(rendered), expression)

    def test_whitespace_is_ignored_between_tokens(self):
        self.assertEqual(
            parse(" \n forall [0,1] : ( p\t&\nq ) "),
            UniversalCondition(P.closed(0.0, 1.0), And((Proposition("p"), Proposition("q")))),
        )

    def test_parse_errors_include_stable_source_location(self):
        with self.assertRaises(ParseError) as caught:
            parse("p &\n  @")

        error = caught.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.position, 6)
        self.assertEqual(error.line, 2)
        self.assertEqual(error.column, 3)
        self.assertIn("line 2, column 3", str(error))

    def test_invalid_inputs_raise_parse_error(self):
        invalid = (
            "",
            "p q",
            "p &",
            "4",
            "forall[0,1] p",
            "forall: p",
            "[bad,1]_(p)",
            "[0,1] p",
            "`unterminated",
            "`bad\\escape`",
            "()",
            "(p",
        )

        for source in invalid:
            with self.subTest(source=source):
                with self.assertRaises(ParseError):
                    parse(source)

    def test_non_string_source_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "source must be a string"):
            parse_expression(None)


class StringLowering(il.DerivedExpression):
    @property
    def children(self):
        return ()

    def lower(self):
        return "p & q"


if __name__ == "__main__":
    unittest.main()
