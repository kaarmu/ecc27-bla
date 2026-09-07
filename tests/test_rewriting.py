import unittest

import interval_logic as il


class RewritingTests(unittest.TestCase):
    def setUp(self):
        self.p = il.Proposition("p")
        self.q = il.Proposition("q")

    def test_boolean_simplification(self):
        self.assertEqual(il.simplify(il.And(())), il.Boolean(True))
        self.assertEqual(il.simplify(il.Or(())), il.Boolean(False))
        self.assertEqual(il.simplify(self.p & ~self.p), il.Boolean(False))
        self.assertEqual(il.simplify(self.p | ~self.p), il.Boolean(True))
        self.assertEqual(il.simplify((self.p & True) | (self.p & self.q)), self.p)
        self.assertEqual(il.simplify(il.Equal(1, 1)), il.Boolean(True))

    def test_selection_negation_is_componentwise(self):
        binary = il.Selection(self.p, self.q, 3)
        self.assertEqual(
            il.simplify(~binary), il.Selection(~self.p, ~self.q, 3)
        )
        self.assertEqual(
            il.simplify(~il.VacuousSelection(self.p, 3)),
            il.RestrictiveSelection(~self.p, 3),
        )

    def test_expand_derived_uses_logic_definitions(self):
        self.assertEqual(
            il.expand_derived(il.Eventually(self.p, 3)),
            il.Until(il.Boolean(True), self.p, 3),
        )
        self.assertEqual(
            il.expand_derived(il.VacuousSelection(self.p, 3)),
            il.Selection(self.p, il.Boolean(True), 3),
        )
        self.assertEqual(il.expand_derived(il.And(())), il.Boolean(True))

    def test_expand_derived_reaches_the_minimal_grammar(self):
        source = il.Equivalent(
            il.RestrictiveSelection(self.p | False, 3),
            il.Release(self.p, il.Always(self.q, 2), 4),
        )
        expanded = il.expand_derived(source)
        allowed = (
            il.Boolean,
            il.Proposition,
            il.Equal,
            il.Not,
            il.And,
            il.Selection,
            il.Until,
        )
        pending = [expanded]
        while pending:
            node = pending.pop()
            self.assertIsInstance(node, allowed)
            if isinstance(node, il.Boolean):
                self.assertTrue(node.value)
            pending.extend(node.children)

    def test_nnf_uses_temporal_dualities(self):
        self.assertEqual(
            il.to_nnf(~il.Always(self.p, 3)), il.Eventually(~self.p, 3)
        )
        self.assertEqual(
            il.to_nnf(~il.Until(self.p, self.q, 3)),
            il.Release(~self.p, ~self.q, 3),
        )

    def test_replace_is_bottom_up_and_ordered(self):
        result = (self.p & self.q).replace(
            lambda node: il.Boolean(True) if node == self.q else node,
            il.simplify,
        )
        self.assertEqual(result, self.p)


if __name__ == "__main__":
    unittest.main()
