"""Mathematical rendering preserves syntax, grouping, names and exact bounds."""
from fractions import Fraction as F
import unittest
from importlib.util import find_spec
import portion as P
import interval_logic as il


class LatexTests(unittest.TestCase):
    def test_notebook_representation_and_plain_text_are_separate(self):
        formula = il.Always(il.Signal('acc').equals(2), P.closedopen(1, 2))
        self.assertEqual(il.format_latex(formula), r'\square_{[1,2)} \mathit{acc} = 2')
        self.assertEqual(formula._repr_latex_(), r'$\displaystyle \square_{[1,2)} \mathit{acc} = 2$')
        self.assertEqual(il.parse_formula(str(formula)), formula)
        self.assertEqual(il.Signal('use')._repr_latex_(), r'$\mathit{use}$')
        self.assertEqual(il.NaturalLiteral(2)._repr_latex_(), '$2$')

    def test_precedence_and_boolean_connectives(self):
        p, q, r = map(il.Proposition, ('p', 'q', 'r'))
        self.assertEqual(il.format_latex((p | q) & r), r'\left(p \lor q\right) \land r')
        self.assertEqual(il.format_latex(~(p & q)), r'\neg \left(p \land q\right)')
        self.assertEqual(il.format_latex((p.implies(q)).implies(r)), r'\left(p \to q\right) \to r')
        self.assertEqual(il.format_latex(p.implies(q.implies(r))), r'p \to q \to r')
        self.assertEqual(il.format_latex(p.equivalent(q)), r'p \leftrightarrow q')
        self.assertEqual(il.format_latex(il.And(())), r'\top')
        self.assertEqual(il.format_latex(il.Or(())), r'\bot')
        self.assertEqual(il.format_latex(True), r'\top')
        self.assertEqual(il.format_latex('p'), 'p')
        self.assertEqual(il.format_latex(il.Signal('acc').not_equals(0)), r'\mathit{acc} \ne 0')

    def test_nested_durations_and_absolute_endpoints(self):
        formula = il.Eventually(il.Always('p', F(1, 3)), P.openclosed(F(2, 3), F(5, 3)))
        self.assertEqual(il.format_latex(formula),
                         r'\lozenge_{(\frac{2}{3},\frac{5}{3}]} \square_{\frac{1}{3})} p')
        for window, expected in ((P.singleton(F(1, 2)), r'\{\frac{1}{2}\}'),
                                 (P.empty(), r'\varnothing'),
                                 (P.closedopen(0, P.inf), r'[0,\infty)')):
            self.assertEqual(il.format_latex(il.Always('p', window)), r'\square_{' + expected + '} p')
        self.assertEqual(il.format_latex(il.Always('p', '2]')), r'\square_{2]} p')
        self.assertEqual(il.format_latex(il.Always('p')), r'\square p')

    def test_selections_and_temporal_infix_operators(self):
        self.assertEqual(il.format_latex(il.Selection('p', 'q', 2)), r'\langle p, q \rangle_{2)}')
        self.assertEqual(il.format_latex(il.VacuousSelection('p')), r'\langle p \rangle')
        self.assertEqual(il.format_latex(il.RestrictiveSelection('p', '2]')), r'\langle p \rangle_{2]}^{*}')
        self.assertEqual(il.format_latex(il.Until('p', 'q', 2)), r'p \mathbin{\mathrm{U}_{2)}} q')
        self.assertEqual(il.format_latex(il.Release('p', 'q')), r'p \mathbin{\mathrm{R}} q')
        self.assertIn(r'\left(p \lor q\right)', il.format_latex(il.Eventually(il.Or(('p', 'q')))))

    def test_names_are_escaped_as_literals(self):
        self.assertEqual(il.format_term_latex(il.Signal('charge_rate')), r'\mathit{charge\_rate}')
        name = r'a\input{x}_$%&#^~| b'
        latex = il.format_latex(il.Proposition(name))
        self.assertNotIn(r'\input', latex)
        for token in (r'\backslash{}', r'\{', r'\}', r'\_', r'\$', r'\%', r'\&', r'\#', r'\vert{}'):
            self.assertIn(token, latex)
        self.assertEqual(il.format_term_latex(5), '5')
        with self.assertRaises(TypeError):
            il.format_term_latex(True)

    @unittest.skipUnless(find_spec('IPython'), 'Rich display needs IPython')
    def test_ipython_registers_latex_mime_for_formulas_and_terms(self):
        from IPython.core.formatters import DisplayFormatter
        formatter = DisplayFormatter()
        for value in (il.Proposition('p'), il.Signal('acc'), il.NaturalLiteral(3)):
            data, _ = formatter.format(value)
            self.assertEqual(data['text/latex'], value._repr_latex_())
            self.assertIn('text/plain', data)

    def test_protocol_markdown_tables_use_inline_math(self):
        from protocol.presentation import fmt
        self.assertEqual(fmt(il.Always('p', 2)), r'$\square_{2)} p$')
        self.assertEqual(fmt(il.Signal('acc')), r'$\mathit{acc}$')
        self.assertEqual(fmt(P.closedopen(1, 2)), '[1,2)')


if __name__ == '__main__':
    unittest.main()
