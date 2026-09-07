import unittest

import portion as P

import interval_logic as il


class FormulaApiTests(unittest.TestCase):
    def setUp(self):
        self.p = il.Proposition("p")
        self.q = il.Proposition("q")

    def test_temporal_parameters_are_explicit(self):
        self.assertEqual(il.coerce_temporal_parameter(3), il.RelativeParameter(3))
        self.assertEqual(
            il.coerce_temporal_parameter("3]"), il.RelativeParameter(3, True)
        )
        absolute = il.coerce_temporal_parameter("[2,5)")
        self.assertEqual(absolute, il.AbsoluteParameter(P.closedopen(2, 5)))
        self.assertIsNone(il.coerce_temporal_parameter(None))

    def test_single_temporal_window_is_future_directed(self):
        universe = P.closed(0, 10)
        absolute = il.AbsoluteParameter(P.closed(2, 8))
        self.assertEqual(il.temporal_window(absolute, 5, universe), P.closed(5, 8))
        self.assertEqual(il.temporal_window(absolute, 9, universe), P.empty())
        self.assertEqual(
            il.temporal_window(il.RelativeParameter(0), 5, universe), P.empty()
        )
        self.assertEqual(
            il.temporal_window(il.RelativeParameter(0, True), 5, universe),
            P.closed(5, 5),
        )

    def test_operand_first_constructors_and_methods(self):
        self.assertEqual(il.Eventually(self.p, "2]"), self.p.eventually("2]"))
        self.assertEqual(il.Always(self.p, 2), self.p.always(2))
        self.assertEqual(il.Until(self.p, self.q, 2), self.p.until(self.q, 2))
        self.assertEqual(
            il.Selection(self.p, self.q, 2), self.p.select(self.q, 2)
        )
        self.assertEqual(self.p.implies(self.q), il.Implies(self.p, self.q))
        self.assertEqual(
            self.p.equivalent(self.q), il.Equivalent(self.p, self.q)
        )
        self.assertEqual(self.p.select_vac(2), il.VacuousSelection(self.p, 2))
        self.assertEqual(
            self.p.select_res(2), il.RestrictiveSelection(self.p, 2)
        )
        self.assertFalse(hasattr(self.p, "select_vacuously"))
        self.assertFalse(hasattr(self.p, "select_restrictively"))

    def test_round_trip_unicode_and_ascii(self):
        formulas = (
            il.Boolean(True),
            ~self.p,
            self.p & self.q,
            self.p.implies(self.q),
            self.p.equivalent(self.q),
            il.Selection(self.p, self.q, "3]"),
            il.VacuousSelection(self.p, 0),
            il.RestrictiveSelection(self.p, P.closedopen(2, 5)),
            il.Eventually(self.p, "2]"),
            il.Always(self.p),
            il.Until(self.p, self.q, 4),
            il.Release(self.p, self.q, 4),
        )
        for formula in formulas:
            with self.subTest(formula=formula):
                self.assertEqual(il.parse_formula(il.format_formula(formula)), formula)
                self.assertEqual(
                    il.parse_formula(il.format_formula(formula, unicode=False)), formula
                )

    def test_traversal_validation_and_no_python_truth(self):
        formula = il.Eventually(self.p & self.q, 2)
        self.assertEqual(formula.depth, 2)
        self.assertEqual(formula.node_count, 4)
        with self.assertRaises(TypeError):
            bool(formula)
        with self.assertRaises(TypeError):
            il.NaturalLiteral(True)
        with self.assertRaises(ValueError):
            il.Signal("")
        with self.assertRaises(il.FormulaSyntaxError):
            il.parse_formula("always_")

    def test_public_surface_has_no_legacy_names(self):
        for legacy in (
            "Bool",
            "DurationParameter",
            "Expression",
            "Term",
            "ExistentialCondition",
            "UniversalCondition",
            "parse_expression",
            "format_expression",
            "anchored_denotation",
            "satisfying_anchors",
            "to_boolean_nnf",
            "selection_window",
            "condition_window",
            "future_window",
            "parameter_window",
            "ReachabilitySystem",
            "EventReachabilitySystem",
            "EventReachabilityBackend",
            "ReachResult",
            "reach",
        ):
            self.assertFalse(hasattr(il, legacy), legacy)

        for removed in ("WeakUntil", "temporal_horizon"):
            self.assertFalse(hasattr(il, removed), removed)


if __name__ == "__main__":
    unittest.main()
