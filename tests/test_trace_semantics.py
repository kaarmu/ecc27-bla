import unittest

import portion as P

import interval_logic as il


class TraceSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.universe = P.closed(0, 10)
        self.trace = il.Trace(
            self.universe,
            propositions={
                "p": P.closed(2, 6),
                "q": P.closed(5, 8),
            },
            signals={
                "job": il.NaturalSignal(
                    {
                        0: P.closedopen(0, 4),
                        2: P.closed(4, 10),
                    }
                )
            },
        )

    def test_atoms_booleans_and_signals(self):
        self.assertEqual(
            il.satisfying_times("p and not q", self.trace), P.closedopen(2, 5)
        )
        self.assertEqual(
            il.satisfying_times(il.Signal("job").equals(2), self.trace),
            P.closed(4, 10),
        )
        self.assertEqual(
            il.satisfying_times(il.Proposition("missing"), self.trace), P.empty()
        )
        with self.assertRaises(il.TraceValidationError):
            il.satisfying_times(il.Signal("missing").equals(0), self.trace)

    def test_selection_keeps_anchored_mask_and_reanchors_operands(self):
        formula = il.Selection("p", "q", P.closed(1, 7))
        local_expected = P.closed(2, 6) | P.openclosed(7, 8)
        self.assertEqual(il.denote(formula, self.trace, 9), P.closed(5, 8))
        self.assertEqual(
            il.denote(formula, self.trace, 6),
            P.closed(5, 6) | P.openclosed(7, 8),
        )
        self.assertEqual(
            il.satisfying_times(formula, self.trace), local_expected
        )

        relative = il.Selection("eventually_0] p", False, 4)
        self.assertEqual(il.denote(relative, self.trace, 1), P.closedopen(2, 5))

    def test_eventually_always_and_absolute_future_truncation(self):
        target_trace = il.Trace(self.universe, {"p": P.closed(5, 6)})
        self.assertEqual(
            il.satisfying_times("eventually_2] p", target_trace), P.closed(3, 6)
        )
        self.assertEqual(
            il.satisfying_times("eventually_2 p", target_trace), P.openclosed(3, 6)
        )
        truncated_trace = il.Trace(self.universe, {"p": P.closedopen(5, 6)})
        absolute = il.Always("p", P.closed(5, 6))
        self.assertFalse(il.satisfies(absolute, truncated_trace, 4))
        self.assertFalse(il.satisfies(absolute, truncated_trace, 6))
        self.assertTrue(il.satisfies(absolute, truncated_trace, 7))

    def test_until_uses_one_witness_and_left_prefix(self):
        trace = il.Trace(
            self.universe,
            {"left": P.closedopen(0, 5), "right": P.closed(5, 5)},
        )
        self.assertTrue(il.satisfies("left U_5] right", trace, 0))
        self.assertFalse(il.satisfies("left U_4] right", trace, 0))
        self.assertTrue(il.satisfies("left U_0] right", trace, 5))

    def test_relative_windows_respect_disconnected_universe_boundaries(self):
        universe = P.closed(4, 6) | P.closed(10, 11)
        trace = il.Trace(universe, {"p": P.closed(4, 6)})
        self.assertEqual(
            il.satisfying_times("always_5] p", trace), P.closedopen(4, 5)
        )

    def test_release(self):
        trace = il.Trace(self.universe, {"p": P.closedopen(0, 4)})
        for at in (0, 3, 8):
            self.assertEqual(
                il.satisfies("false R_2] p", trace, at),
                il.satisfies("always_2] p", trace, at),
            )

    def test_local_satisfaction_agrees_with_anchored_denotation(self):
        formulas = (
            "p and not q",
            il.Selection("p", "q", P.closedopen(3, 7)),
            il.Eventually(il.Selection("p", "q", 2), "3]"),
            il.Until("p", "q", "4]"),
        )
        for formula in formulas:
            for at in (0, 3, 5, 7, 10):
                with self.subTest(formula=formula, at=at):
                    self.assertEqual(
                        il.satisfies(formula, self.trace, at),
                        at in il.denote(formula, self.trace, at),
                    )

    def test_until_release_negation_duality(self):
        until = il.Until("p", "q", "3]")
        release = il.Release(~il.Proposition("p"), ~il.Proposition("q"), "3]")
        for at in (0, 3, 5, 7, 10):
            with self.subTest(at=at):
                self.assertEqual(
                    not il.satisfies(until, self.trace, at),
                    il.satisfies(release, self.trace, at),
                )

    def test_expanding_abbreviations_preserves_both_trace_queries(self):
        formulas = (
            il.Boolean(False),
            il.Proposition("p") | il.Proposition("q"),
            il.Implies("p", "q"),
            il.Equivalent("p", "q"),
            il.VacuousSelection("p", "[2,8)"),
            il.RestrictiveSelection("q", 3),
            il.Eventually("p", "3]"),
            il.Always("q", "[4,9)"),
            il.Release("p", "q", "4]"),
        )
        for formula in formulas:
            expanded = il.expand_derived(formula)
            with self.subTest(formula=formula, query="satisfying_times"):
                self.assertEqual(
                    il.satisfying_times(formula, self.trace),
                    il.satisfying_times(expanded, self.trace),
                )
            for anchor in (0, 5, 10):
                with self.subTest(formula=formula, query="denote", anchor=anchor):
                    self.assertEqual(
                        il.denote(formula, self.trace, anchor),
                        il.denote(expanded, self.trace, anchor),
                    )

    def test_zero_duration_laws(self):
        for at in (1, 5, 9):
            p = il.satisfies("p", self.trace, at)
            q = il.satisfies("q", self.trace, at)
            checks = {
                "eventually_0] p": p,
                "eventually_0 p": False,
                "always_0] p": p,
                "always_0 p": True,
                "p U_0] q": q,
                "p U_0 q": False,
                "p R_0] q": q,
                "p R_0 q": True,
                "<p,q>_0]": p,
                "<p,q>_0": q,
            }
            for source, expected in checks.items():
                with self.subTest(at=at, source=source):
                    self.assertEqual(il.satisfies(source, self.trace, at), expected)

    def test_trace_validation(self):
        with self.assertRaises(il.TraceValidationError):
            il.NaturalSignal({0: P.closed(0, 2), 1: P.closed(2, 3)})
        with self.assertRaises(il.TraceValidationError):
            il.Trace(
                P.closed(0, 3),
                signals={"j": il.NaturalSignal({0: P.closed(0, 1)})},
            )
        with self.assertRaises(il.TraceValidationError):
            il.denote("p", self.trace, 11)


if __name__ == "__main__":
    unittest.main()
