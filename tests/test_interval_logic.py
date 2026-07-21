import itertools
import unittest
from dataclasses import FrozenInstanceError

import portion as P

from interval_logic import (
    And,
    Atom,
    Bool,
    DerivedExpression,
    DerivedExpressionCycleError,
    DerivedExpressionError,
    Equal,
    Equivalent,
    Exists,
    ExpansionLimitError,
    ForAll,
    Guard,
    Implies,
    Natural,
    NaturalSignal,
    Not,
    Or,
    Restrict,
    Signal,
    Xor,
    as_expr,
    as_term,
    denote,
    format_expression,
    holds,
    lower_derived,
    partition_intervals,
    simplify,
    timeline,
    to_nnf,
)


POINTS = (-1, 0, 1)
UNIVERSE = P.closed(-1, 1)


def finite_oracle(expression, valuation, at, signals=None):
    """Independent discrete interpretation used to verify rewrite equivalence."""

    signals = {} if signals is None else signals

    match expression:
        case Bool(value=value):
            return value
        case Atom(name=name):
            return at in valuation[name]
        case Equal(left=left, right=right):
            return finite_term(left, signals, at) == finite_term(right, signals, at)
        case Not(operand=operand):
            return not finite_oracle(operand, valuation, at, signals)
        case And(operands=operands):
            return all(finite_oracle(item, valuation, at, signals) for item in operands)
        case Or(operands=operands):
            return any(finite_oracle(item, valuation, at, signals) for item in operands)
        case Restrict(interval=interval, body=body):
            return at in interval and finite_oracle(body, valuation, at, signals)
        case Guard(interval=interval, body=body):
            return at not in interval or finite_oracle(body, valuation, at, signals)
        case ForAll(interval=interval, body=body):
            return all(
                finite_oracle(body, valuation, point, signals)
                for point in POINTS
                if point in interval
            )
        case Exists(interval=interval, body=body):
            return any(
                finite_oracle(body, valuation, point, signals)
                for point in POINTS
                if point in interval
            )
        case _:
            raise TypeError(type(expression).__name__)


def finite_term(term, signals, at):
    match term:
        case Natural(value=value):
            return value
        case Signal(name=name):
            return signals[name][at]
        case _:
            raise TypeError(type(term).__name__)


def all_valuations(*names):
    subsets = [
        frozenset(point for point, included in zip(POINTS, mask) if included)
        for mask in itertools.product((False, True), repeat=len(POINTS))
    ]
    for choices in itertools.product(subsets, repeat=len(names)):
        yield dict(zip(names, choices))


def portion_from_points(points):
    result = P.empty()
    for point in points:
        result |= P.singleton(point)
    return result


def natural_signal_from_points(values):
    regions = {}
    for point, value in zip(POINTS, values):
        regions[value] = regions.get(value, P.empty()) | P.singleton(point)
    return NaturalSignal(regions)


class ConstructionTests(unittest.TestCase):
    def test_nodes_are_structurally_equal_hashable_and_immutable(self):
        left = And((Atom("p"), Atom("q")))
        right = And((Atom("p"), Atom("q")))

        self.assertEqual(left, right)
        self.assertEqual(hash(left), hash(right))
        with self.assertRaises(FrozenInstanceError):
            left.operands = ()

    def test_depth_and_node_count_include_all_descendants(self):
        expression = Not(And((Atom("p"), Not(Atom("q")))))

        self.assertEqual(expression.depth, 4)
        self.assertEqual(expression.node_count, 5)

    def test_python_operators_and_boolean_coercion_construct_formulas(self):
        p = Atom("p")

        self.assertEqual(~p, Not(p))
        self.assertEqual(p & True, And((p, Bool(True))))
        self.assertEqual(False | p, Or((Bool(False), p)))
        self.assertEqual(as_expr(True), Bool(True))

    def test_fluent_window_methods_construct_immutable_nodes(self):
        p = Atom("p")
        interval = P.closed(0, 1)

        self.assertEqual(p.restrict(interval), Restrict(interval, p))
        self.assertEqual(p.guard(interval), Guard(interval, p))
        self.assertEqual(hash(p.restrict(interval)), hash(Restrict(interval, p)))

    def test_natural_terms_and_equality_are_immutable_and_canonical(self):
        j1, j2 = Signal("j_1"), Signal("j_2")

        self.assertEqual(as_term(0), Natural(0))
        self.assertEqual(j1.equals(0), Equal(j1, Natural(0)))
        self.assertEqual(j1.not_equals(j2), Not(Equal(j1, j2)))
        self.assertEqual(Equal(j2, j1), Equal(j1, j2))
        self.assertEqual(hash(Equal(j2, j1)), hash(Equal(j1, j2)))
        self.assertEqual(Equal(1, 0), Equal(0, 1))

    def test_expression_has_no_python_truth_value(self):
        with self.assertRaisesRegex(TypeError, "holds.*denote"):
            bool(Atom("p"))

    def test_constructors_reject_invalid_values(self):
        with self.assertRaises(TypeError):
            Bool(1)
        with self.assertRaises(ValueError):
            Atom("")
        with self.assertRaises(TypeError):
            Not(True)
        with self.assertRaises(TypeError):
            ForAll((0, 1), Atom("p"))
        with self.assertRaises(TypeError):
            And((Atom("p"), True))
        with self.assertRaises(TypeError):
            Restrict((0, 1), Atom("p"))
        with self.assertRaises(TypeError):
            Guard(P.closed(0, 1), True)
        with self.assertRaises(TypeError):
            Natural(True)
        with self.assertRaises(ValueError):
            Natural(-1)
        with self.assertRaises(ValueError):
            Signal("")
        with self.assertRaises(TypeError):
            Equal(Signal("j"), True)
        with self.assertRaises(TypeError):
            bool(Signal("j"))


class PrettyPrintingTests(unittest.TestCase):
    def test_str_uses_compact_unicode_notation(self):
        p, q, r = Atom("p"), Atom("q"), Atom("r")

        self.assertEqual(str(Bool(True)), "⊤")
        self.assertEqual(str(Bool(False)), "⊥")
        self.assertEqual(str(Not(p)), "¬p")
        self.assertEqual(str(And((p, Or((q, r))))), "p ∧ (q ∨ r)")
        self.assertEqual(str(Or((And((p, q)), r))), "p ∧ q ∨ r")

    def test_quantifiers_make_scope_explicit(self):
        p, q = Atom("p"), Atom("q")
        interval = P.closedopen(0, 1)

        self.assertEqual(str(ForAll(interval, Or((p, q)))), "∀[0,1): p ∨ q")
        self.assertEqual(
            str(And((p, Exists(interval, q)))), "p ∧ (∃[0,1): q)"
        )
        self.assertEqual(str(Not(ForAll(interval, p))), "¬(∀[0,1): p)")

    def test_derived_operator_precedence(self):
        p, q, r = Atom("p"), Atom("q"), Atom("r")

        self.assertEqual(str(Implies(And((p, q)), r)), "p ∧ q → r")
        self.assertEqual(str(Implies(p, Implies(q, r))), "p → q → r")
        self.assertEqual(str(Implies(Implies(p, q), r)), "(p → q) → r")
        self.assertEqual(str(Equivalent(p, Xor(q, r))), "p ↔ q ⊕ r")

    def test_ascii_output_and_quoted_atom_names(self):
        expression = ForAll(
            P.closed(0, 1),
            Implies(Atom("vehicle connected"), Not(Atom("fault"))),
        )

        self.assertEqual(
            format_expression(expression, unicode=False),
            "forall[0,1]: `vehicle connected` -> !fault",
        )

    def test_numeric_equalities_use_formula_notation(self):
        j1, j2 = Signal("j_1"), Signal("charging point 2")

        self.assertEqual(str(j1), "j_1")
        self.assertEqual(str(j1.equals(17)), "j_1 = 17")
        self.assertEqual(str(j1.not_equals(j2)), "`charging point 2` ≠ j_1")
        self.assertEqual(
            format_expression(j1.not_equals(0), unicode=False), "j_1 != 0"
        )
        self.assertEqual(str(Not(j1.not_equals(0))), "¬(j_1 ≠ 0)")
        self.assertEqual(
            str(j1.not_equals(j2) | (j1.equals(0) & j2.equals(0))),
            "`charging point 2` ≠ j_1 ∨ j_1 = 0 ∧ `charging point 2` = 0",
        )

    def test_repr_remains_unambiguous_debug_output(self):
        expression = And((Atom("p"), Atom("q")))

        self.assertEqual(str(expression), "p ∧ q")
        self.assertIn("And(operands=", repr(expression))

    def test_ipython_pretty_output_uses_formula_notation(self):
        printer = RecordingPrinter()

        And((Atom("p"), Atom("q")))._repr_pretty_(printer, cycle=False)

        self.assertEqual(printer.value, "p ∧ q")

    def test_custom_derived_operator_has_readable_fallback(self):
        self.assertEqual(str(Nand(Atom("p"), Atom("q"))), "Nand(p, q)")

    def test_windows_use_notebook_notation_with_explicit_scope(self):
        p, q = Atom("p"), Atom("q")
        interval = P.closedopen(0, 1)

        self.assertEqual(str(Restrict(interval, Or((p, q)))), "[0,1)_(p ∨ q)")
        self.assertEqual(str(Guard(interval, And((p, q)))), "[0,1)^(p ∧ q)")
        self.assertEqual(
            format_expression(Restrict(interval, Not(p)), unicode=False),
            "[0,1)_(!p)",
        )
        self.assertEqual(
            str(Restrict(interval, Guard(P.closed(1, 2), p))),
            "[0,1)_([1,2]^(p))",
        )


class TimelineTests(unittest.TestCase):
    def test_timeline_contains_universe_valuation_and_formula_rows(self):
        p, q = Atom("p"), Atom("q")
        valuation = {"q": P.closed(1, 3), "p": P.closedopen(0, 2)}

        result = timeline(And((p, q)), valuation, P.closed(0, 4))

        self.assertEqual([row.label for row in result.rows[:3]], ["Universe", "p", "q"])
        self.assertEqual(result.rows[-1].label, "φ = p ∧ q")
        self.assertEqual(result.rows[-1].interval, P.closedopen(1, 2))
        self.assertEqual(result.rows[-1].kind, "formula")

    def test_timeline_plain_text_is_an_exact_interval_table(self):
        result = timeline(
            Atom("p"), {"p": P.closed(1, 2)}, P.closed(0, 3), formula_label="result"
        )

        text = str(result)
        self.assertIn("row       holds on", text)
        self.assertIn("Universe  [0,3]", text)
        self.assertIn("p         [1,2]", text)
        self.assertIn("result    [1,2]", text)

    def test_finite_numeric_timeline_renders_inline_svg_and_html_table(self):
        result = timeline(
            Atom("<ready>"),
            {"<ready>": P.openclosed(1, 2)},
            P.closed(0, 3),
        )

        html = result._repr_html_()
        self.assertIn("<svg", html)
        self.assertIn("<table", html)
        self.assertIn("&lt;ready&gt;", html)
        self.assertIn("(1,2]", html)
        self.assertIn("#2e9d57", html)

    def test_unbounded_timeline_falls_back_to_exact_table(self):
        result = timeline(Atom("p"), {"p": P.open(-P.inf, P.inf)}, P.open(-P.inf, P.inf))

        html = result._repr_html_()
        self.assertNotIn("<svg", html)
        self.assertIn("finite numeric universe", html)
        self.assertIn("(-inf,+inf)", html)

    def test_timeline_validates_display_options(self):
        with self.assertRaises(ValueError):
            timeline(Atom("p"), {"p": P.empty()}, UNIVERSE, width=200)
        with self.assertRaises(ValueError):
            timeline(Atom("p"), {"p": P.empty()}, UNIVERSE, formula_label="")

    def test_timeline_visualizes_window_formula_denotation(self):
        p, q = Atom("p"), Atom("q")
        expression = And(
            (
                Restrict(P.closed(0, 1), p),
                Guard(P.closed(0.5, 1.5), q),
            )
        )
        valuation = {"p": P.closed(0, 1), "q": P.closed(0.75, 1.5)}

        result = timeline(expression, valuation, P.closed(0, 2))

        self.assertEqual(
            result.rows[-1].interval,
            P.closedopen(0, 0.5) | P.closed(0.75, 1),
        )
        self.assertIn("[0,1]_(p)", result.rows[-1].label)
        self.assertIn("<svg", result._repr_html_())

    def test_timeline_includes_piecewise_signal_values(self):
        j = Signal("j_1")
        signal = NaturalSignal({17: P.closed(1, 2)}, default=0)

        result = timeline(j.equals(17), {}, P.closed(0, 3), signals={"j_1": signal})

        self.assertEqual(
            [(row.label, row.interval) for row in result.rows[1:-1]],
            [
                ("j_1 = 0", P.closedopen(0, 1) | P.openclosed(2, 3)),
                ("j_1 = 17", P.closed(1, 2)),
            ],
        )
        self.assertEqual(result.rows[-1].interval, P.closed(1, 2))
        self.assertIn("#d9822b", result._repr_html_())


class SemanticsTests(unittest.TestCase):
    def test_atoms_are_clipped_to_universe_and_missing_atoms_fail(self):
        p = Atom("p")

        self.assertEqual(
            denote(p, {"p": P.closed(-10, 10)}, UNIVERSE), UNIVERSE
        )
        with self.assertRaisesRegex(KeyError, "missing valuation.*p"):
            denote(p, {}, UNIVERSE)
        with self.assertRaises(TypeError):
            denote(p, {"p": {0, 1}}, UNIVERSE)

    def test_natural_signals_validate_values_regions_and_coverage(self):
        with self.assertRaises(TypeError):
            NaturalSignal({True: P.closed(0, 1)})
        with self.assertRaises(ValueError):
            NaturalSignal({-1: P.closed(0, 1)})
        with self.assertRaises(TypeError):
            NaturalSignal({0: {0, 1}})
        with self.assertRaises(ValueError):
            NaturalSignal(
                {0: P.closed(0, 1), 1: P.closed(1, 2)},
            )
        with self.assertRaises(ValueError):
            NaturalSignal({0: P.closed(-1, 0)}).parts(UNIVERSE)

        self.assertEqual(
            NaturalSignal({7: P.singleton(0)}, default=0).parts(UNIVERSE),
            (
                (0, P.closedopen(-1, 0) | P.openclosed(0, 1)),
                (7, P.singleton(0)),
            ),
        )

    def test_pointwise_equality_compares_literals_and_signals_exactly(self):
        j1, j2 = Signal("j_1"), Signal("j_2")
        signals = {
            "j_1": NaturalSignal({7: P.singleton(0)}, default=0),
            "j_2": NaturalSignal({7: P.closed(0, 1)}, default=0),
        }

        self.assertEqual(denote(Equal(1, 1), {}, UNIVERSE), UNIVERSE)
        self.assertEqual(denote(Equal(1, 2), {}, UNIVERSE), P.empty())
        self.assertEqual(
            denote(j1.equals(0), {}, UNIVERSE, signals=signals),
            P.closedopen(-1, 0) | P.openclosed(0, 1),
        )
        self.assertEqual(
            denote(j1.equals(j2), {}, UNIVERSE, signals=signals),
            P.closed(-1, 0),
        )
        self.assertTrue(holds(j1.equals(7), {}, 0, UNIVERSE, signals=signals))
        self.assertFalse(holds(j1.equals(7), {}, 1, UNIVERSE, signals=signals))

    def test_signal_evaluation_reports_missing_or_malformed_values(self):
        formula = Signal("j").equals(0)

        with self.assertRaisesRegex(KeyError, "missing valuation.*j"):
            denote(formula, {}, UNIVERSE)
        with self.assertRaisesRegex(TypeError, "NaturalSignal"):
            denote(formula, {}, UNIVERSE, signals={"j": P.closed(0, 1)})

    def test_job_allocation_formula_detects_duplicate_nonzero_jobs(self):
        universe = P.closed(0, 2)
        j1, j2 = Signal("j_1"), Signal("j_2")
        formula = ForAll(
            universe,
            j1.not_equals(j2) | (j1.equals(0) & j2.equals(0)),
        )
        conflict = {
            "j_1": NaturalSignal({5: P.closed(0, 1)}, default=0),
            "j_2": NaturalSignal({5: P.closed(0.5, 1.5)}, default=0),
        }
        no_conflict = {
            "j_1": NaturalSignal({5: P.closed(0, 1)}, default=0),
            "j_2": NaturalSignal({6: P.closed(0.5, 1.5)}, default=0),
        }

        self.assertEqual(denote(formula, {}, universe, signals=conflict), P.empty())
        self.assertEqual(denote(formula, {}, universe, signals=no_conflict), universe)

    def test_equality_evaluator_agrees_with_independent_finite_oracle(self):
        discrete_universe = portion_from_points(POINTS)
        j1, j2 = Signal("j_1"), Signal("j_2")
        formulas = (
            j1.equals(0),
            j1.equals(j2),
            j1.not_equals(j2),
            j1.not_equals(j2) | (j1.equals(0) & j2.equals(0)),
            ForAll(
                discrete_universe,
                j1.not_equals(j2) | (j1.equals(0) & j2.equals(0)),
            ),
        )
        value_sequences = tuple(itertools.product(range(3), repeat=len(POINTS)))
        for left_values, right_values in itertools.product(value_sequences, repeat=2):
            oracle_signals = {
                "j_1": dict(zip(POINTS, left_values)),
                "j_2": dict(zip(POINTS, right_values)),
            }
            signals = {
                "j_1": natural_signal_from_points(left_values),
                "j_2": natural_signal_from_points(right_values),
            }
            for formula in formulas:
                for point in POINTS:
                    with self.subTest(
                        formula=formula,
                        left=left_values,
                        right=right_values,
                        at=point,
                    ):
                        self.assertEqual(
                            holds(
                                formula,
                                {},
                                point,
                                discrete_universe,
                                signals=signals,
                            ),
                            finite_oracle(formula, {}, point, oracle_signals),
                        )

    def test_boolean_denotation_respects_open_and_closed_endpoints(self):
        p = Atom("p")
        valuation = {"p": P.openclosed(0, 1)}

        self.assertFalse(holds(p, valuation, 0, UNIVERSE))
        self.assertTrue(holds(p, valuation, 1, UNIVERSE))
        self.assertEqual(denote(Not(p), valuation, UNIVERSE), P.closed(-1, 0))

    def test_empty_quantifiers_have_standard_vacuous_semantics(self):
        p = Atom("p")

        self.assertEqual(denote(ForAll(P.empty(), p), {}, UNIVERSE), UNIVERSE)
        self.assertTrue(denote(Exists(P.empty(), p), {}, UNIVERSE).empty)

    def test_quantifier_intervals_are_restricted_to_universe(self):
        p = Atom("p")
        outside_and_inside = P.closed(-100, 0)

        self.assertEqual(
            denote(ForAll(outside_and_inside, p), {"p": P.closed(-1, 0)}, UNIVERSE),
            UNIVERSE,
        )
        self.assertEqual(
            denote(Exists(P.open(2, P.inf), p), {"p": UNIVERSE}, UNIVERSE),
            P.empty(),
        )

    def test_continuous_quantifier_semantics(self):
        p = Atom("p")

        self.assertEqual(
            denote(ForAll(P.closed(0, 1), p), {"p": P.closed(0, 1)}, UNIVERSE),
            UNIVERSE,
        )

    def test_restrictive_and_guarded_window_denotations(self):
        p = Atom("p")
        interval = P.closedopen(0, 1)
        valuation = {"p": P.openclosed(0, 2)}

        self.assertEqual(
            denote(Restrict(interval, p), valuation, UNIVERSE), P.open(0, 1)
        )
        self.assertEqual(
            denote(Guard(interval, p), valuation, UNIVERSE),
            P.closedopen(-1, 0) | P.openclosed(0, 1),
        )

    def test_windows_clip_to_universe_and_short_circuit_empty_domains(self):
        p = Atom("p")
        outside = P.open(2, P.inf)

        self.assertEqual(denote(Restrict(outside, p), {}, UNIVERSE), P.empty())
        self.assertEqual(denote(Guard(outside, p), {}, UNIVERSE), UNIVERSE)
        self.assertEqual(denote(Restrict(P.empty(), p), {}, UNIVERSE), P.empty())
        self.assertEqual(denote(Guard(P.empty(), p), {}, UNIVERSE), UNIVERSE)

    def test_full_and_disconnected_windows(self):
        p = Atom("p")
        all_time = P.open(-P.inf, P.inf)
        disconnected = P.closed(-1, -0.5) | P.openclosed(0.5, 1)
        valuation = {"p": P.closed(-0.75, 0.75)}

        self.assertEqual(denote(Restrict(all_time, p), valuation, UNIVERSE), valuation["p"])
        self.assertEqual(denote(Guard(all_time, p), valuation, UNIVERSE), valuation["p"])
        self.assertEqual(
            denote(Restrict(disconnected, p), valuation, UNIVERSE),
            P.closed(-0.75, -0.5) | P.openclosed(0.5, 0.75),
        )

    def test_window_duality_and_quantifier_definitions(self):
        p = Atom("p")
        interval = P.closed(0, 1)
        for values in all_valuations("p"):
            valuation = {"p": portion_from_points(values["p"])}
            restricted = denote(Restrict(interval, p), valuation, UNIVERSE)
            guarded = denote(Guard(interval, p), valuation, UNIVERSE)

            self.assertEqual(
                denote(Not(Restrict(interval, p)), valuation, UNIVERSE),
                denote(Guard(interval, Not(p)), valuation, UNIVERSE),
            )
            self.assertEqual(
                denote(Not(Guard(interval, p)), valuation, UNIVERSE),
                denote(Restrict(interval, Not(p)), valuation, UNIVERSE),
            )
            self.assertEqual(
                denote(Exists(interval, p), valuation, UNIVERSE),
                UNIVERSE if not restricted.empty else P.empty(),
            )
            self.assertEqual(
                denote(ForAll(interval, p), valuation, UNIVERSE),
                UNIVERSE if guarded == UNIVERSE else P.empty(),
            )
        self.assertTrue(
            denote(
                ForAll(P.closed(0, 1), p),
                {"p": P.closedopen(0, 1)},
                UNIVERSE,
            ).empty
        )
        self.assertEqual(
            denote(Exists(P.open(0, 1), p), {"p": P.singleton(0.5)}, UNIVERSE),
            UNIVERSE,
        )

    def test_evaluator_agrees_with_independent_finite_oracle(self):
        p, q = Atom("p"), Atom("q")
        left_domain = portion_from_points((-1, 0))
        right_domain = portion_from_points((0, 1))
        formulas = (
            p,
            Not(p),
            And((p, q)),
            Or((Not(p), q)),
            ForAll(left_domain, Or((p, q))),
            Exists(right_domain, And((p, Not(q)))),
            Restrict(left_domain, Or((p, q))),
            Guard(right_domain, And((p, Not(q)))),
        )
        for valuation in all_valuations("p", "q"):
            portion_valuation = {
                name: portion_from_points(values)
                for name, values in valuation.items()
            }
            for formula in formulas:
                for point in POINTS:
                    with self.subTest(formula=formula, valuation=valuation, at=point):
                        self.assertEqual(
                            holds(formula, portion_valuation, point, UNIVERSE),
                            finite_oracle(formula, valuation, point),
                        )


class SimplificationTests(unittest.TestCase):
    def assert_equivalent_on_finite_models(self, original, rewritten):
        for valuation in all_valuations("p", "q"):
            for point in POINTS:
                self.assertEqual(
                    finite_oracle(original, valuation, point),
                    finite_oracle(rewritten, valuation, point),
                    (original, rewritten, valuation, point),
                )

    def test_boolean_constants_complements_and_absorption(self):
        p, q = Atom("p"), Atom("q")

        self.assertEqual(simplify(And((Bool(True), p))), p)
        self.assertEqual(simplify(And((Bool(False), p))), Bool(False))
        self.assertEqual(simplify(Or((Bool(False), p))), p)
        self.assertEqual(simplify(Or((Bool(True), p))), Bool(True))
        self.assertEqual(simplify(And((p, Not(p)))), Bool(False))
        self.assertEqual(simplify(Or((p, Not(p)))), Bool(True))
        self.assertEqual(simplify(And((p, Or((p, q))))), p)
        self.assertEqual(simplify(Or((p, And((p, q))))), p)

    def test_equality_constants_reflexivity_and_complements(self):
        j = Signal("j")
        equality = j.equals(7)

        self.assertEqual(simplify(Equal(1, 1)), Bool(True))
        self.assertEqual(simplify(Equal(1, 2)), Bool(False))
        self.assertEqual(simplify(j.equals(j)), Bool(True))
        self.assertEqual(simplify(equality), equality)
        self.assertEqual(simplify(And((equality, Not(equality)))), Bool(False))
        self.assertEqual(simplify(Or((equality, Not(equality)))), Bool(True))

    def test_variadic_nodes_are_flattened_deduplicated_and_sorted(self):
        p, q = Atom("p"), Atom("q")

        expected = And((p, q))
        self.assertEqual(simplify(And((q, And((p, q)), p))), expected)
        self.assertEqual(simplify(And((q, p))), simplify(And((p, q))))
        self.assertEqual(simplify(Or((q, p))), simplify(Or((p, q))))

    def test_empty_interval_precedes_constant_body(self):
        self.assertEqual(simplify(ForAll(P.empty(), Bool(False))), Bool(True))
        self.assertEqual(simplify(Exists(P.empty(), Bool(True))), Bool(False))

    def test_universe_dependent_constant_quantifiers_are_not_over_simplified(self):
        outside = P.closed(2, 3)
        universal = ForAll(outside, Bool(False))
        existential = Exists(outside, Bool(True))

        self.assertEqual(simplify(universal), universal)
        self.assertEqual(simplify(existential), existential)
        self.assertEqual(denote(universal, {}, UNIVERSE), UNIVERSE)
        self.assertEqual(denote(existential, {}, UNIVERSE), P.empty())

    def test_equal_interval_quantifiers_combine_bodies(self):
        p, q = Atom("p"), Atom("q")
        interval = P.closed(0, 1)

        universal = simplify(And((ForAll(interval, p), ForAll(interval, q))))
        existential = simplify(Or((Exists(interval, p), Exists(interval, q))))

        self.assertEqual(universal, ForAll(interval, And((p, q))))
        self.assertEqual(existential, Exists(interval, Or((p, q))))

    def test_same_body_quantifiers_merge_interval_unions(self):
        p = Atom("p")
        left, right = P.closed(-1, 0), P.closed(0, 1)

        self.assertEqual(
            simplify(And((ForAll(left, p), ForAll(right, p)))),
            ForAll(left | right, p),
        )
        self.assertEqual(
            simplify(Or((Exists(left, p), Exists(right, p)))),
            Exists(left | right, p),
        )

    def test_window_constants_full_domain_and_nesting(self):
        p = Atom("p")
        left, right = P.closed(-1, 0), P.closed(0, 1)
        all_time = P.open(-P.inf, P.inf)

        self.assertEqual(simplify(Restrict(P.empty(), p)), Bool(False))
        self.assertEqual(simplify(Guard(P.empty(), p)), Bool(True))
        self.assertEqual(simplify(Restrict(left, Bool(False))), Bool(False))
        self.assertEqual(simplify(Guard(left, Bool(True))), Bool(True))
        self.assertEqual(simplify(Restrict(all_time, p)), p)
        self.assertEqual(simplify(Guard(all_time, p)), p)
        self.assertEqual(
            simplify(Restrict(left, Restrict(right, p))),
            Restrict(left & right, p),
        )
        self.assertEqual(
            simplify(Guard(left, Guard(right, p))), Guard(left & right, p)
        )

    def test_same_window_bodies_and_same_body_intervals_merge(self):
        p, q = Atom("p"), Atom("q")
        left, right = P.closed(-1, 0), P.closed(0, 1)

        self.assertEqual(
            simplify(And((Restrict(left, p), Restrict(left, q)))),
            Restrict(left, And((p, q))),
        )
        self.assertEqual(
            simplify(Or((Guard(left, p), Guard(left, q)))),
            Guard(left, Or((p, q))),
        )
        self.assertEqual(
            simplify(And((Restrict(left, p), Restrict(right, p)))),
            Restrict(left & right, p),
        )
        self.assertEqual(
            simplify(Or((Restrict(left, p), Restrict(right, p)))),
            Restrict(left | right, p),
        )
        self.assertEqual(
            simplify(And((Guard(left, p), Guard(right, p)))),
            Guard(left | right, p),
        )
        self.assertEqual(
            simplify(Or((Guard(left, p), Guard(right, p)))),
            Guard(left & right, p),
        )

    def test_quantifiers_absorb_compatible_windows(self):
        p = Atom("p")
        left, right = P.closed(-1, 0), P.closed(0, 1)

        self.assertEqual(
            simplify(Exists(left, Restrict(right, p))), Exists(left & right, p)
        )
        self.assertEqual(
            simplify(ForAll(left, Guard(right, p))), ForAll(left & right, p)
        )

    def test_all_window_rewrites_preserve_finite_model_semantics(self):
        p, q = Atom("p"), Atom("q")
        left, right = P.closed(-1, 0), P.closed(0, 1)
        formulas = (
            Restrict(left, Restrict(right, p)),
            Guard(left, Guard(right, p)),
            And((Restrict(left, p), Restrict(right, p))),
            Or((Restrict(left, p), Restrict(right, p))),
            And((Guard(left, p), Guard(right, p))),
            Or((Guard(left, p), Guard(right, p))),
            And((Restrict(left, p), Restrict(left, q))),
            Or((Guard(left, p), Guard(left, q))),
            Exists(left, Restrict(right, p)),
            ForAll(left, Guard(right, p)),
        )
        for formula in formulas:
            with self.subTest(formula=formula):
                result = simplify(formula)
                self.assertEqual(simplify(result), result)
                self.assertLessEqual(result.node_count, formula.node_count)
                self.assert_equivalent_on_finite_models(formula, result)

    def test_simplification_is_semantics_preserving_idempotent_and_compact(self):
        p, q = Atom("p"), Atom("q")
        interval = P.closed(0, 1)
        formulas = (
            Not(Not(p)),
            And((Bool(True), p, Or((p, q)))),
            Or((Bool(False), q, And((p, q)))),
            And((ForAll(interval, p), ForAll(interval, q))),
            Or((Exists(interval, p), Exists(interval, q))),
            And((ForAll(P.closed(-1, 0), p), ForAll(P.closed(0, 1), p))),
            Or((Exists(P.closed(-1, 0), q), Exists(P.closed(0, 1), q))),
            Restrict(interval, Restrict(P.closed(-1, 0), p)),
            Guard(interval, Guard(P.closed(-1, 0), q)),
        )

        for formula in formulas:
            with self.subTest(formula=formula):
                result = simplify(formula)
                self.assertEqual(simplify(result), result)
                self.assertLessEqual(result.node_count, formula.node_count)
                self.assert_equivalent_on_finite_models(formula, result)


class NormalizationTests(unittest.TestCase):
    def test_nnf_lowers_derived_nodes_and_pushes_negation_to_atoms(self):
        p, q = Atom("p"), Atom("q")
        result = to_nnf(Not(Implies(p, ForAll(P.closed(0, 1), q))))

        self.assertEqual(result, And((p, Exists(P.closed(0, 1), Not(q)))))
        self.assertTrue(self._negations_only_wrap_atoms(result))

    def test_nnf_swaps_window_polarity(self):
        p, q = Atom("p"), Atom("q")
        interval = P.closed(0, 1)

        self.assertEqual(
            to_nnf(Not(Restrict(interval, Or((p, q))))),
            Guard(interval, And((Not(p), Not(q)))),
        )
        self.assertEqual(
            to_nnf(Not(Guard(interval, And((p, q))))),
            Restrict(interval, Or((Not(p), Not(q)))),
        )

    def test_equality_is_an_atomic_nnf_literal(self):
        equality = Signal("j").equals(0)

        self.assertEqual(to_nnf(Not(Not(equality))), equality)
        self.assertEqual(to_nnf(Not(equality)), Not(equality))
        self.assertTrue(self._negations_only_wrap_atoms(Not(equality)))
        self.assertEqual(partition_intervals(equality), equality)

    def test_partitioning_uses_shared_disjoint_cells(self):
        p, q = Atom("p"), Atom("q")
        original = And(
            (
                ForAll(P.closed(0, 2), p),
                ForAll(P.closed(1, 3), q),
            )
        )

        result = partition_intervals(original)
        intervals = [
            node.interval
            for node in self._walk(result)
            if isinstance(node, ForAll)
        ]

        self.assertEqual(
            set(intervals),
            {P.closedopen(0, 1), P.closed(1, 2), P.openclosed(2, 3)},
        )
        for valuation in all_valuations("p", "q"):
            portion_valuation = {
                name: portion_from_points(values)
                for name, values in valuation.items()
            }
            self.assertEqual(
                denote(original, portion_valuation, P.closed(-1, 3)),
                denote(result, portion_valuation, P.closed(-1, 3)),
            )

    def test_partitioning_handles_disconnected_intervals(self):
        p = Atom("p")
        interval = P.closed(-1, 0) | P.openclosed(1, 2)

        result = partition_intervals(Exists(interval, p))

        self.assertEqual(
            result,
            Or((Exists(P.closed(-1, 0), p), Exists(P.openclosed(1, 2), p))),
        )

    def test_partitioning_splits_windows_with_dual_connectives(self):
        p, q = Atom("p"), Atom("q")
        restricted_interval = P.closed(0, 2)
        guarded_interval = P.closed(1, 3)
        original = And(
            (
                Restrict(restricted_interval, p),
                Guard(guarded_interval, q),
            )
        )

        result = partition_intervals(original)
        restricted = [
            node.interval for node in self._walk(result) if isinstance(node, Restrict)
        ]
        guarded = [node.interval for node in self._walk(result) if isinstance(node, Guard)]

        self.assertEqual(set(restricted), {P.closedopen(0, 1), P.closed(1, 2)})
        self.assertEqual(set(guarded), {P.closed(1, 2), P.openclosed(2, 3)})
        for valuation in all_valuations("p", "q"):
            portion_valuation = {
                name: portion_from_points(values)
                for name, values in valuation.items()
            }
            self.assertEqual(
                denote(original, portion_valuation, P.closed(-1, 3)),
                denote(result, portion_valuation, P.closed(-1, 3)),
            )

    def test_partitioning_enforces_node_budget(self):
        p, q = Atom("p"), Atom("q")
        expression = And(
            (
                ForAll(P.closed(0, 2), p),
                ForAll(P.closed(1, 3), q),
            )
        )

        with self.assertRaises(ExpansionLimitError) as caught:
            partition_intervals(expression, max_nodes=expression.node_count)
        self.assertEqual(caught.exception.limit, expression.node_count)
        self.assertGreater(caught.exception.attempted, caught.exception.limit)

    def _walk(self, expression):
        yield expression
        for child in expression.children:
            yield from self._walk(child)

    def _negations_only_wrap_atoms(self, expression):
        return all(
            not isinstance(node, Not) or isinstance(node.operand, (Atom, Equal))
            for node in self._walk(expression)
        )


class DerivedOperatorTests(unittest.TestCase):
    def test_builtin_derived_operators_lower_to_core_formulas(self):
        p, q = Atom("p"), Atom("q")

        self.assertEqual(lower_derived(Implies(p, q)), Or((Not(p), q)))
        self.assertEqual(
            lower_derived(Equivalent(p, q)),
            Or((And((p, q)), And((Not(p), Not(q))))),
        )
        self.assertEqual(
            lower_derived(Xor(p, q)),
            Or((And((p, Not(q))), And((Not(p), q)))),
        )

    def test_derived_operators_have_expected_truth_tables(self):
        p, q = Atom("p"), Atom("q")
        expressions = {
            Implies(p, q): lambda left, right: (not left) or right,
            Equivalent(p, q): lambda left, right: left == right,
            Xor(p, q): lambda left, right: left != right,
        }
        for expression, expected in expressions.items():
            for left, right in itertools.product((False, True), repeat=2):
                valuation = {
                    "p": UNIVERSE if left else P.empty(),
                    "q": UNIVERSE if right else P.empty(),
                }
                with self.subTest(expression=expression, left=left, right=right):
                    self.assertEqual(
                        holds(expression, valuation, 0, UNIVERSE),
                        expected(left, right),
                    )

    def test_custom_derived_operator_requires_no_evaluator_changes(self):
        p, q = Atom("p"), Atom("q")
        expression = Nand(p, q)

        self.assertEqual(simplify(expression), Not(And((p, q))))
        self.assertFalse(
            holds(expression, {"p": UNIVERSE, "q": UNIVERSE}, 0, UNIVERSE)
        )

    def test_malformed_and_cyclic_derived_operators_fail_clearly(self):
        with self.assertRaises(DerivedExpressionError):
            lower_derived(BrokenDerived())
        with self.assertRaises(DerivedExpressionCycleError):
            lower_derived(CyclicDerived())
        with self.assertRaises(DerivedExpressionCycleError):
            lower_derived(RegeneratingCycle())


class Nand(DerivedExpression):
    def __init__(self, left, right):
        self.left = left
        self.right = right

    @property
    def children(self):
        return (self.left, self.right)

    def lower(self):
        return Not(And((self.left, self.right)))


class RecordingPrinter:
    def __init__(self):
        self.value = None

    def text(self, value):
        self.value = value


class BrokenDerived(DerivedExpression):
    @property
    def children(self):
        return ()

    def lower(self):
        return "not an expression"


class CyclicDerived(DerivedExpression):
    @property
    def children(self):
        return ()

    def lower(self):
        return self


class RegeneratingCycle(DerivedExpression):
    @property
    def children(self):
        return ()

    def lower(self):
        return RegeneratingCycle()


if __name__ == "__main__":
    unittest.main()
