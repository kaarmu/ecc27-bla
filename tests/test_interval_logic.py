import itertools
import unittest
from dataclasses import FrozenInstanceError

import interval_logic as il
import portion as P

from interval_logic import (
    And,
    Proposition,
    Bool,
    DerivedExpression,
    DerivedExpressionCycleError,
    DerivedExpressionError,
    Equal,
    Equivalent,
    ExistentialCondition,
    ExpansionLimitError,
    UniversalCondition,
    VacuousSelection,
    Implies,
    NaturalLiteral,
    NaturalSignal,
    Not,
    Or,
    RestrictiveSelection,
    Signal,
    Xor,
    as_expr,
    as_term,
    satisfying_anchors,
    format_expression,
    satisfies,
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
        case Proposition(name=name):
            return at in valuation[name]
        case Equal(left=left, right=right):
            return finite_term(left, signals, at) == finite_term(right, signals, at)
        case Not(operand=operand):
            return not finite_oracle(operand, valuation, at, signals)
        case And(operands=operands):
            return all(finite_oracle(item, valuation, at, signals) for item in operands)
        case Or(operands=operands):
            return any(finite_oracle(item, valuation, at, signals) for item in operands)
        case RestrictiveSelection(interval=interval, body=body):
            return at in interval and finite_oracle(body, valuation, at, signals)
        case VacuousSelection(interval=interval, body=body):
            return at not in interval or finite_oracle(body, valuation, at, signals)
        case UniversalCondition(interval=interval, body=body):
            return all(
                finite_oracle(body, valuation, point, signals)
                for point in POINTS
                if point in interval
            )
        case ExistentialCondition(interval=interval, body=body):
            return any(
                finite_oracle(body, valuation, point, signals)
                for point in POINTS
                if point in interval
            )
        case _:
            raise TypeError(type(expression).__name__)


def finite_term(term, signals, at):
    match term:
        case NaturalLiteral(value=value):
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
        left = And((Proposition("p"), Proposition("q")))
        right = And((Proposition("p"), Proposition("q")))

        self.assertEqual(left, right)
        self.assertEqual(hash(left), hash(right))
        with self.assertRaises(FrozenInstanceError):
            left.operands = ()

    def test_depth_and_node_count_include_all_descendants(self):
        expression = Not(And((Proposition("p"), Not(Proposition("q")))))

        self.assertEqual(expression.depth, 4)
        self.assertEqual(expression.node_count, 5)

    def test_python_operators_and_boolean_coercion_construct_formulas(self):
        p = Proposition("p")

        self.assertEqual(~p, Not(p))
        self.assertEqual(p & True, And((p, Bool(True))))
        self.assertEqual(False | p, Or((Bool(False), p)))
        self.assertEqual(as_expr(True), Bool(True))

    def test_interval_expressions_parse_string_arguments_as_floats(self):
        p = Proposition("p")
        expected = P.closedopen(0.0, 1.0)

        for expression_type in (RestrictiveSelection, VacuousSelection, UniversalCondition, ExistentialCondition):
            with self.subTest(expression_type=expression_type.__name__):
                expression = expression_type("[0, 1)", p)

                self.assertIsInstance(expression.interval, P.Interval)
                self.assertEqual(expression.interval, expected)
                self.assertIsInstance(next(iter(expression.interval)).lower, float)

    def test_absolute_temporal_parameters_must_be_connected(self):
        p = Proposition("p")
        disconnected = P.closed(0, 1) | P.closed(3, 4)
        for expression_type in (
            RestrictiveSelection,
            VacuousSelection,
            UniversalCondition,
            ExistentialCondition,
        ):
            with self.subTest(expression_type=expression_type.__name__):
                with self.assertRaisesRegex(ValueError, "must be connected"):
                    expression_type(disconnected, p)

    def test_natural_terms_and_equality_are_immutable_and_canonical(self):
        j1, j2 = Signal("j_1"), Signal("j_2")

        self.assertEqual(as_term(0), NaturalLiteral(0))
        self.assertEqual(j1.equals(0), Equal(j1, NaturalLiteral(0)))
        self.assertEqual(j1.not_equals(j2), Not(Equal(j1, j2)))
        self.assertEqual(Equal(j2, j1), Equal(j1, j2))
        self.assertEqual(hash(Equal(j2, j1)), hash(Equal(j1, j2)))
        self.assertEqual(Equal(1, 0), Equal(0, 1))

    def test_expression_has_no_python_truth_value(self):
        with self.assertRaisesRegex(TypeError, "satisfies.*satisfying_anchors"):
            bool(Proposition("p"))

    def test_constructors_reject_invalid_values(self):
        with self.assertRaises(TypeError):
            Bool(1)
        with self.assertRaises(ValueError):
            Proposition("")
        with self.assertRaises(TypeError):
            Not(True)
        with self.assertRaises(TypeError):
            UniversalCondition((0, 1), Proposition("p"))
        with self.assertRaises(TypeError):
            And((Proposition("p"), True))
        with self.assertRaises(TypeError):
            RestrictiveSelection((0, 1), Proposition("p"))
        with self.assertRaises(TypeError):
            VacuousSelection(P.closed(0, 1), True)
        with self.assertRaises(TypeError):
            NaturalLiteral(True)
        with self.assertRaises(ValueError):
            NaturalLiteral(-1)
        with self.assertRaises(ValueError):
            Signal("")
        with self.assertRaises(TypeError):
            Equal(Signal("j"), True)
        with self.assertRaises(TypeError):
            bool(Signal("j"))


class ReplacementTests(unittest.TestCase):
    def test_matching_workflow_replaces_selected_equalities(self):
        keep = Signal("j").equals(1)
        negate = Signal("j").equals(2)
        formula = And((keep, ExistentialCondition("[0, 1]", negate)))

        def rewrite(expression):
            if isinstance(expression, il.Equal):
                return expression if expression == keep else il.Not(expression)
            return expression

        self.assertEqual(
            formula.replace(rewrite),
            And((keep, ExistentialCondition("[0, 1]", Not(negate)))),
        )

    def test_replacement_rebuilds_every_core_parent_shape(self):
        p, q, replacement = Proposition("p"), Proposition("q"), Proposition("replacement")
        equality = Signal("j").equals(1)
        formula = And(
            (
                Bool(True),
                equality,
                Not(p),
                Or((p, q)),
                RestrictiveSelection("[0, 1]", p),
                VacuousSelection("[1, 2]", p),
                UniversalCondition("[2, 3]", p),
                ExistentialCondition("[3, 4]", p),
            )
        )

        result = formula.replace(
            lambda expression: replacement if expression is p else expression
        )

        self.assertEqual(
            result,
            And(
                (
                    Bool(True),
                    equality,
                    Not(replacement),
                    Or((replacement, q)),
                    RestrictiveSelection("[0, 1]", replacement),
                    VacuousSelection("[1, 2]", replacement),
                    UniversalCondition("[2, 3]", replacement),
                    ExistentialCondition("[3, 4]", replacement),
                )
            ),
        )

    def test_replacement_is_bottom_up_and_left_to_right(self):
        p, q, replacement = Proposition("p"), Proposition("q"), Proposition("replacement")
        visited = []

        def rewrite(expression):
            visited.append(expression)
            if expression is p:
                return replacement
            if isinstance(expression, Not) and expression.operand is replacement:
                return Bool(False)
            return expression

        expected = And((Bool(False), q))

        self.assertEqual(And((Not(p), q)).replace(rewrite), expected)
        self.assertEqual(visited, [p, Not(replacement), q, expected])

    def test_callback_created_expression_is_not_revisited(self):
        p, q = Proposition("p"), Proposition("q")
        visited = []

        def rewrite(expression):
            visited.append(expression)
            return Not(q)

        self.assertEqual(p.replace(rewrite), Not(q))
        self.assertEqual(visited, [p])

    def test_equal_terms_are_not_visited(self):
        equality = Signal("j").equals(1)
        visited = []

        def record(expression):
            visited.append(expression)
            return expression

        self.assertIs(
            equality.replace(record),
            equality,
        )
        self.assertEqual(visited, [equality])

    def test_no_op_replacement_preserves_original_instances(self):
        formula = Implies(Not(Proposition("p")), ExistentialCondition("[0, 1]", Proposition("q")))

        self.assertIs(formula.replace(lambda expression: expression), formula)

    def test_replacement_preserves_derived_expression_types(self):
        p, q, replacement = Proposition("p"), Proposition("q"), Proposition("replacement")

        def rewrite(expression):
            return replacement if expression is p else expression

        builtin = Implies(p, q).replace(rewrite)
        positional_custom = Nand(p, q).replace(rewrite)
        configured_custom = TaggedDerived("tag", p).replace(rewrite)

        self.assertIsInstance(builtin, Implies)
        self.assertEqual(builtin, Implies(replacement, q))
        self.assertIsInstance(positional_custom, Nand)
        self.assertEqual(positional_custom.children, (replacement, q))
        self.assertIsInstance(configured_custom, TaggedDerived)
        self.assertEqual(configured_custom.label, "tag")
        self.assertEqual(configured_custom.children, (replacement,))

    def test_custom_derived_rebuild_failure_explains_required_hook(self):
        p, replacement = Proposition("p"), Proposition("replacement")

        with self.assertRaisesRegex(TypeError, "override _with_children"):
            ConfiguredDerived("tag", p).replace(
                lambda expression: replacement if expression is p else expression
            )

    def test_replacement_validates_callback_and_its_result(self):
        p = Proposition("p")

        with self.assertRaisesRegex(TypeError, "must be callable"):
            p.replace(None)
        with self.assertRaisesRegex(TypeError, "must return an Expression"):
            p.replace(lambda expression: True)

    def test_callback_exceptions_propagate_unchanged(self):
        error = RuntimeError("callback failed")

        def fail(_expression):
            raise error

        with self.assertRaises(RuntimeError) as caught:
            Proposition("p").replace(fail)
        self.assertIs(caught.exception, error)


class PrettyPrintingTests(unittest.TestCase):
    def test_str_uses_compact_unicode_notation(self):
        p, q, r = Proposition("p"), Proposition("q"), Proposition("r")

        self.assertEqual(str(Bool(True)), "⊤")
        self.assertEqual(str(Bool(False)), "⊥")
        self.assertEqual(str(Not(p)), "¬p")
        self.assertEqual(str(And((p, Or((q, r))))), "p ∧ (q ∨ r)")
        self.assertEqual(str(Or((And((p, q)), r))), "p ∧ q ∨ r")

    def test_conditions_make_scope_explicit(self):
        p, q = Proposition("p"), Proposition("q")
        interval = P.closedopen(0, 1)

        self.assertEqual(str(UniversalCondition(interval, Or((p, q)))), "□_[0,1) (p ∨ q)")
        self.assertEqual(
            str(And((p, ExistentialCondition(interval, q)))), "p ∧ ◇_[0,1) q"
        )
        self.assertEqual(str(Not(UniversalCondition(interval, p))), "¬□_[0,1) p")

    def test_derived_operator_precedence(self):
        p, q, r = Proposition("p"), Proposition("q"), Proposition("r")

        self.assertEqual(str(Implies(And((p, q)), r)), "p ∧ q → r")
        self.assertEqual(str(Implies(p, Implies(q, r))), "p → q → r")
        self.assertEqual(str(Implies(Implies(p, q), r)), "(p → q) → r")
        self.assertEqual(str(Equivalent(p, Xor(q, r))), "p ↔ q ⊕ r")

    def test_ascii_output_and_quoted_proposition_names(self):
        expression = UniversalCondition(
            P.closed(0, 1),
            Implies(Proposition("vehicle connected"), Not(Proposition("fault"))),
        )

        self.assertEqual(
            format_expression(expression, unicode=False),
            "always_[0,1] (`vehicle connected` -> !fault)",
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
        expression = And((Proposition("p"), Proposition("q")))

        self.assertEqual(str(expression), "p ∧ q")
        self.assertIn("And(operands=", repr(expression))

    def test_ipython_pretty_output_uses_formula_notation(self):
        printer = RecordingPrinter()

        And((Proposition("p"), Proposition("q")))._repr_pretty_(printer, cycle=False)

        self.assertEqual(printer.value, "p ∧ q")

    def test_custom_derived_operator_has_readable_fallback(self):
        self.assertEqual(str(Nand(Proposition("p"), Proposition("q"))), "Nand(p, q)")

    def test_windows_use_notebook_notation_with_explicit_scope(self):
        p, q = Proposition("p"), Proposition("q")
        interval = P.closedopen(0, 1)

        self.assertEqual(str(RestrictiveSelection(interval, Or((p, q)))), "⟨p ∨ q⟩*_[0,1)")
        self.assertEqual(str(VacuousSelection(interval, And((p, q)))), "⟨p ∧ q⟩_[0,1)")
        self.assertEqual(
            format_expression(RestrictiveSelection(interval, Not(p)), unicode=False),
            "<!p>*_[0,1)",
        )
        self.assertEqual(
            str(RestrictiveSelection(interval, VacuousSelection(P.closed(1, 2), p))),
            "⟨⟨p⟩_[1,2]⟩*_[0,1)",
        )


class TimelineTests(unittest.TestCase):
    def test_timeline_contains_universe_valuation_and_formula_rows(self):
        p, q = Proposition("p"), Proposition("q")
        valuation = {"q": P.closed(1, 3), "p": P.closedopen(0, 2)}

        result = timeline(And((p, q)), valuation, P.closed(0, 4))

        self.assertEqual([row.label for row in result.rows[:3]], ["Universe", "p", "q"])
        self.assertEqual(result.rows[-1].label, "φ = p ∧ q")
        self.assertEqual(result.rows[-1].interval, P.closedopen(1, 2))
        self.assertEqual(result.rows[-1].kind, "formula")

    def test_timeline_plain_text_is_an_exact_interval_table(self):
        result = timeline(
            Proposition("p"), {"p": P.closed(1, 2)}, P.closed(0, 3), formula_label="result"
        )

        text = str(result)
        self.assertIn("row       satisfying anchors", text)
        self.assertIn("Universe  [0,3]", text)
        self.assertIn("p         [1,2]", text)
        self.assertIn("result    [1,2]", text)

    def test_finite_numeric_timeline_renders_inline_svg_and_html_table(self):
        result = timeline(
            Proposition("<ready>"),
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
        result = timeline(Proposition("p"), {"p": P.open(-P.inf, P.inf)}, P.open(-P.inf, P.inf))

        html = result._repr_html_()
        self.assertNotIn("<svg", html)
        self.assertIn("finite numeric universe", html)
        self.assertIn("(-inf,+inf)", html)

    def test_timeline_validates_display_options(self):
        with self.assertRaises(ValueError):
            timeline(Proposition("p"), {"p": P.empty()}, UNIVERSE, width=200)
        with self.assertRaises(ValueError):
            timeline(Proposition("p"), {"p": P.empty()}, UNIVERSE, formula_label="")

    def test_timeline_visualizes_window_formula_denotation(self):
        p, q = Proposition("p"), Proposition("q")
        expression = And(
            (
                RestrictiveSelection(P.closed(0, 1), p),
                VacuousSelection(P.closed(0.5, 1.5), q),
            )
        )
        valuation = {"p": P.closed(0, 1), "q": P.closed(0.75, 1.5)}

        result = timeline(expression, valuation, P.closed(0, 2))

        self.assertEqual(
            result.rows[-1].interval,
            P.closedopen(0, 0.5) | P.closed(0.75, 1),
        )
        self.assertIn("⟨p⟩*_[0,1]", result.rows[-1].label)
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
    def test_propositions_are_clipped_to_universe_and_missing_propositions_fail(self):
        p = Proposition("p")

        self.assertEqual(
            satisfying_anchors(p, {"p": P.closed(-10, 10)}, UNIVERSE), UNIVERSE
        )
        with self.assertRaisesRegex(KeyError, "missing valuation.*p"):
            satisfying_anchors(p, {}, UNIVERSE)
        with self.assertRaises(TypeError):
            satisfying_anchors(p, {"p": {0, 1}}, UNIVERSE)

    def test_disconnected_valuations_and_evaluation_universes_are_supported(self):
        p = Proposition("p")
        universe = P.closed(0, 1) | P.closed(3, 4)
        valuation = {"p": P.singleton(0) | P.singleton(4)}

        self.assertEqual(satisfying_anchors(p, valuation, universe), valuation["p"])
        self.assertTrue(satisfies(p, valuation, 4, universe))

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

        self.assertEqual(satisfying_anchors(Equal(1, 1), {}, UNIVERSE), UNIVERSE)
        self.assertEqual(satisfying_anchors(Equal(1, 2), {}, UNIVERSE), P.empty())
        self.assertEqual(
            satisfying_anchors(j1.equals(0), {}, UNIVERSE, signals=signals),
            P.closedopen(-1, 0) | P.openclosed(0, 1),
        )
        self.assertEqual(
            satisfying_anchors(j1.equals(j2), {}, UNIVERSE, signals=signals),
            P.closed(-1, 0),
        )
        self.assertTrue(satisfies(j1.equals(7), {}, 0, UNIVERSE, signals=signals))
        self.assertFalse(satisfies(j1.equals(7), {}, 1, UNIVERSE, signals=signals))

    def test_signal_evaluation_reports_missing_or_malformed_values(self):
        formula = Signal("j").equals(0)

        with self.assertRaisesRegex(KeyError, "missing valuation.*j"):
            satisfying_anchors(formula, {}, UNIVERSE)
        with self.assertRaisesRegex(TypeError, "NaturalSignal"):
            satisfying_anchors(formula, {}, UNIVERSE, signals={"j": P.closed(0, 1)})

    def test_job_allocation_formula_detects_duplicate_nonzero_jobs(self):
        universe = P.closed(0, 2)
        j1, j2 = Signal("j_1"), Signal("j_2")
        formula = UniversalCondition(
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

        self.assertEqual(satisfying_anchors(formula, {}, universe, signals=conflict), P.empty())
        self.assertEqual(satisfying_anchors(formula, {}, universe, signals=no_conflict), universe)

    def test_equality_evaluator_agrees_with_independent_finite_oracle(self):
        discrete_universe = portion_from_points(POINTS)
        j1, j2 = Signal("j_1"), Signal("j_2")
        allocation_safe = j1.not_equals(j2) | (j1.equals(0) & j2.equals(0))
        formulas = (
            j1.equals(0),
            j1.equals(j2),
            j1.not_equals(j2),
            allocation_safe,
            And(
                UniversalCondition(P.singleton(point), allocation_safe)
                for point in POINTS
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
                            satisfies(
                                formula,
                                {},
                                point,
                                discrete_universe,
                                signals=signals,
                            ),
                            finite_oracle(formula, {}, point, oracle_signals),
                        )

    def test_boolean_denotation_respects_open_and_closed_endpoints(self):
        p = Proposition("p")
        valuation = {"p": P.openclosed(0, 1)}

        self.assertFalse(satisfies(p, valuation, 0, UNIVERSE))
        self.assertTrue(satisfies(p, valuation, 1, UNIVERSE))
        self.assertEqual(satisfying_anchors(Not(p), valuation, UNIVERSE), P.closed(-1, 0))

    def test_empty_conditions_have_standard_vacuous_semantics(self):
        p = Proposition("p")

        self.assertEqual(satisfying_anchors(UniversalCondition(P.empty(), p), {}, UNIVERSE), UNIVERSE)
        self.assertTrue(satisfying_anchors(ExistentialCondition(P.empty(), p), {}, UNIVERSE).empty)

    def test_condition_intervals_are_restricted_to_universe(self):
        p = Proposition("p")
        outside_and_inside = P.closed(-100, 0)

        self.assertEqual(
            satisfying_anchors(UniversalCondition(outside_and_inside, p), {"p": P.closed(-1, 0)}, UNIVERSE),
            UNIVERSE,
        )
        self.assertEqual(
            satisfying_anchors(ExistentialCondition(P.open(2, P.inf), p), {"p": UNIVERSE}, UNIVERSE),
            P.empty(),
        )

    def test_continuous_condition_semantics(self):
        p = Proposition("p")

        self.assertEqual(
            satisfying_anchors(UniversalCondition(P.closed(0, 1), p), {"p": P.closed(0, 1)}, UNIVERSE),
            UNIVERSE,
        )

    def test_restrictive_and_guarded_window_denotations(self):
        p = Proposition("p")
        interval = P.closedopen(0, 1)
        valuation = {"p": P.openclosed(0, 2)}

        self.assertEqual(
            satisfying_anchors(RestrictiveSelection(interval, p), valuation, UNIVERSE), P.open(0, 1)
        )
        self.assertEqual(
            satisfying_anchors(VacuousSelection(interval, p), valuation, UNIVERSE),
            P.closedopen(-1, 0) | P.openclosed(0, 1),
        )

    def test_windows_clip_to_universe_and_short_circuit_empty_domains(self):
        p = Proposition("p")
        outside = P.open(2, P.inf)

        self.assertEqual(satisfying_anchors(RestrictiveSelection(outside, p), {}, UNIVERSE), P.empty())
        self.assertEqual(satisfying_anchors(VacuousSelection(outside, p), {}, UNIVERSE), UNIVERSE)
        self.assertEqual(satisfying_anchors(RestrictiveSelection(P.empty(), p), {}, UNIVERSE), P.empty())
        self.assertEqual(satisfying_anchors(VacuousSelection(P.empty(), p), {}, UNIVERSE), UNIVERSE)

    def test_full_window(self):
        p = Proposition("p")
        all_time = P.open(-P.inf, P.inf)
        valuation = {"p": P.closed(-0.75, 0.75)}

        self.assertEqual(satisfying_anchors(RestrictiveSelection(all_time, p), valuation, UNIVERSE), valuation["p"])
        self.assertEqual(satisfying_anchors(VacuousSelection(all_time, p), valuation, UNIVERSE), valuation["p"])

    def test_selection_duality_and_condition_definitions(self):
        p = Proposition("p")
        interval = P.closed(0, 1)
        for values in all_valuations("p"):
            valuation = {"p": portion_from_points(values["p"])}
            restricted = satisfying_anchors(RestrictiveSelection(interval, p), valuation, UNIVERSE)
            guarded = satisfying_anchors(VacuousSelection(interval, p), valuation, UNIVERSE)

            self.assertEqual(
                satisfying_anchors(Not(RestrictiveSelection(interval, p)), valuation, UNIVERSE),
                satisfying_anchors(VacuousSelection(interval, Not(p)), valuation, UNIVERSE),
            )
            self.assertEqual(
                satisfying_anchors(Not(VacuousSelection(interval, p)), valuation, UNIVERSE),
                satisfying_anchors(RestrictiveSelection(interval, Not(p)), valuation, UNIVERSE),
            )
            self.assertEqual(
                satisfying_anchors(ExistentialCondition(interval, p), valuation, UNIVERSE),
                UNIVERSE if not restricted.empty else P.empty(),
            )
            self.assertEqual(
                satisfying_anchors(UniversalCondition(interval, p), valuation, UNIVERSE),
                UNIVERSE if guarded == UNIVERSE else P.empty(),
            )
        self.assertTrue(
            satisfying_anchors(
                UniversalCondition(P.closed(0, 1), p),
                {"p": P.closedopen(0, 1)},
                UNIVERSE,
            ).empty
        )
        self.assertEqual(
            satisfying_anchors(ExistentialCondition(P.open(0, 1), p), {"p": P.singleton(0.5)}, UNIVERSE),
            UNIVERSE,
        )

    def test_evaluator_agrees_with_independent_finite_oracle(self):
        p, q = Proposition("p"), Proposition("q")
        left_domain = P.singleton(-1)
        right_domain = P.singleton(1)
        formulas = (
            p,
            Not(p),
            And((p, q)),
            Or((Not(p), q)),
            UniversalCondition(left_domain, Or((p, q))),
            ExistentialCondition(right_domain, And((p, Not(q)))),
            RestrictiveSelection(left_domain, Or((p, q))),
            VacuousSelection(right_domain, And((p, Not(q)))),
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
                            satisfies(formula, portion_valuation, point, UNIVERSE),
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
        p, q = Proposition("p"), Proposition("q")

        self.assertEqual(simplify(And((Bool(True), p))), p)
        self.assertEqual(simplify(And((Bool(False), p))), Bool(False))
        self.assertEqual(simplify(Or((Bool(False), p))), p)
        self.assertEqual(simplify(Or((Bool(True), p))), Bool(True))
        self.assertEqual(simplify(And((p, Not(p)))), Bool(False))
        self.assertEqual(simplify(Or((p, Not(p)))), Bool(True))
        self.assertEqual(simplify(And((p, Or((p, q))))), p)
        self.assertEqual(simplify(Or((p, And((p, q))))), p)

    def test_negations_are_normalized_before_boolean_simplification(self):
        p, q = Proposition("p"), Proposition("q")
        interval = P.closed(0, 1)

        self.assertEqual(
            simplify(Not(Or((p, q)))),
            And((Not(p), Not(q))),
        )
        self.assertEqual(
            simplify(Not(And((p, q)))),
            Or((Not(p), Not(q))),
        )
        self.assertEqual(
            simplify(Not(UniversalCondition(interval, And((p, q))))),
            ExistentialCondition(interval, Or((Not(p), Not(q)))),
        )
        self.assertEqual(
            simplify(Not(ExistentialCondition(interval, Or((p, q))))),
            UniversalCondition(interval, And((Not(p), Not(q)))),
        )

    def test_condition_duals_are_recognized_as_boolean_complements(self):
        p, q = Proposition("p"), Proposition("q")
        body = And((p, q))
        negated_body = Or((Not(p), Not(q)))
        intervals = (
            P.empty(),
            P.closed(0, 1),
        )

        for interval in intervals:
            with self.subTest(interval=interval):
                self.assertEqual(
                    simplify(
                        Or((UniversalCondition(interval, body), ExistentialCondition(interval, negated_body)))
                    ),
                    Bool(True),
                )
                self.assertEqual(
                    simplify(
                        And((UniversalCondition(interval, body), ExistentialCondition(interval, negated_body)))
                    ),
                    Bool(False),
                )
                self.assertEqual(
                    simplify(
                        Or((ExistentialCondition(interval, body), UniversalCondition(interval, negated_body)))
                    ),
                    Bool(True),
                )
                self.assertEqual(
                    simplify(
                        And((ExistentialCondition(interval, body), UniversalCondition(interval, negated_body)))
                    ),
                    Bool(False),
                )

    def test_subset_absorption_factoring_and_distributive_cancellation(self):
        p, q, r = Proposition("p"), Proposition("q"), Proposition("r")

        self.assertEqual(
            simplify(Or((And((p, q)), And((p, q, r))))),
            And((p, q)),
        )
        self.assertEqual(
            simplify(Or((And((p, q)), And((p, Not(q)))))),
            p,
        )
        self.assertEqual(
            simplify(And((Or((p, q)), Or((p, Not(q)))))),
            p,
        )
        self.assertEqual(simplify(Or((p, And((Not(p), q))))), Or((p, q)))
        self.assertEqual(simplify(And((p, Or((Not(p), q))))), And((p, q)))

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
        p, q = Proposition("p"), Proposition("q")

        expected = And((p, q))
        self.assertEqual(simplify(And((q, And((p, q)), p))), expected)
        self.assertEqual(simplify(And((q, p))), simplify(And((p, q))))
        self.assertEqual(simplify(Or((q, p))), simplify(Or((p, q))))

    def test_empty_interval_precedes_constant_body(self):
        self.assertEqual(simplify(UniversalCondition(P.empty(), Bool(False))), Bool(True))
        self.assertEqual(simplify(ExistentialCondition(P.empty(), Bool(True))), Bool(False))

    def test_universe_dependent_constant_conditions_are_not_over_simplified(self):
        outside = P.closed(2, 3)
        universal = UniversalCondition(outside, Bool(False))
        existential = ExistentialCondition(outside, Bool(True))

        self.assertEqual(simplify(universal), universal)
        self.assertEqual(simplify(existential), existential)
        self.assertEqual(satisfying_anchors(universal, {}, UNIVERSE), UNIVERSE)
        self.assertEqual(satisfying_anchors(existential, {}, UNIVERSE), P.empty())

    def test_universe_context_enables_safe_condition_implication(self):
        p = Proposition("p")
        left = P.closed(0, 1)
        touching = P.closed(1, 2)
        disjoint = P.open(1, 2)
        universe = P.closed(0, 2)

        disjunction = Or((UniversalCondition(left, p), ExistentialCondition(touching, p)))
        conjunction = And((UniversalCondition(left, p), ExistentialCondition(touching, p)))
        no_overlap = Or((UniversalCondition(left, p), ExistentialCondition(disjoint, p)))

        self.assertEqual(simplify(disjunction), disjunction)
        self.assertEqual(simplify(disjunction, universe=universe), ExistentialCondition(touching, p))
        self.assertEqual(simplify(conjunction, universe=universe), UniversalCondition(left, p))
        self.assertEqual(simplify(no_overlap, universe=universe), no_overlap)

        for valuation in all_valuations("p"):
            portion_valuation = {"p": portion_from_points(valuation["p"])}
            for formula in (disjunction, conjunction, no_overlap):
                with self.subTest(formula=formula, valuation=valuation):
                    self.assertEqual(
                        satisfying_anchors(formula, portion_valuation, universe),
                        satisfying_anchors(
                            simplify(formula, universe=universe),
                            portion_valuation,
                            universe,
                        ),
                    )

    def test_universe_context_simplifies_effective_windows_and_constants(self):
        p = Proposition("p")
        interval = P.closed(0, 1)
        inside = P.closed(0, 1)
        outside = P.closed(2, 3)

        self.assertEqual(simplify(RestrictiveSelection(interval, p), universe=inside), p)
        self.assertEqual(simplify(VacuousSelection(interval, p), universe=inside), p)
        self.assertEqual(
            simplify(RestrictiveSelection(interval, p), universe=outside), Bool(False)
        )
        self.assertEqual(simplify(VacuousSelection(interval, p), universe=outside), Bool(True))
        self.assertEqual(
            simplify(UniversalCondition(interval, Bool(False)), universe=inside), Bool(False)
        )
        self.assertEqual(
            simplify(UniversalCondition(interval, Bool(False)), universe=outside), Bool(True)
        )
        self.assertEqual(
            simplify(ExistentialCondition(interval, Bool(True)), universe=inside), Bool(True)
        )
        self.assertEqual(
            simplify(ExistentialCondition(interval, Bool(True)), universe=outside), Bool(False)
        )

    def test_interval_decomposition_is_bounded_and_kept_only_when_smaller(self):
        p = Proposition("p")
        whole = P.closed(0, 2)
        part = P.closed(0, 1)
        contradiction = And((UniversalCondition(whole, p), ExistentialCondition(part, Not(p))))
        left = P.closed(-1, 0)
        right = P.openclosed(1, 2)

        self.assertEqual(simplify(contradiction), Bool(False))
        self.assertEqual(simplify(contradiction, max_nodes=2), contradiction)
        disjoint = Or(
            (ExistentialCondition(left, p), ExistentialCondition(right, p))
        )
        self.assertEqual(simplify(disjoint), disjoint)

    def test_known_equivalence_can_be_substituted_between_simplification_passes(self):
        q = Proposition("q")
        equality = Signal("j").equals(1)
        interval = P.closed(0, 1)
        formula = Or((UniversalCondition(interval, equality), ExistentialCondition(interval, Not(q))))

        rewritten = simplify(formula).replace(
            lambda expression: q if expression == equality else expression
        )

        self.assertEqual(simplify(rewritten), Bool(True))

    def test_simplification_context_and_budget_are_validated_and_forwarded(self):
        p = Proposition("p")
        interval = P.closed(0, 1)

        self.assertEqual(
            RestrictiveSelection(interval, p).simplify(universe=interval),
            p,
        )
        with self.assertRaisesRegex(TypeError, "portion.Interval"):
            simplify(p, universe="[0,1]")
        for invalid in (True, 0, -1, 1.5):
            with self.subTest(max_nodes=invalid):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    simplify(p, max_nodes=invalid)

    def test_contextual_simplification_preserves_semantics_across_universes(self):
        p, q = Proposition("p"), Proposition("q")
        formulas = (
            Not(And((p, q))),
            Or((UniversalCondition(P.closed(-1, 0), p), ExistentialCondition(P.closed(0, 1), p))),
            And(
                (
                    UniversalCondition(P.closed(-1, 1), p),
                    ExistentialCondition(P.closed(-1, 0), Not(p)),
                )
            ),
            RestrictiveSelection(P.closed(-1, 0), p),
            VacuousSelection(P.closed(0, 1), q),
        )
        universes = (P.empty(), P.singleton(0), UNIVERSE, P.closed(2, 3))

        for universe in universes:
            for formula in formulas:
                result = simplify(formula, universe=universe)
                self.assertEqual(simplify(result, universe=universe), result)
                for valuation in all_valuations("p", "q"):
                    portion_valuation = {
                        name: portion_from_points(values)
                        for name, values in valuation.items()
                    }
                    with self.subTest(
                        universe=universe,
                        formula=formula,
                        valuation=valuation,
                    ):
                        self.assertEqual(
                            satisfying_anchors(formula, portion_valuation, universe),
                            satisfying_anchors(result, portion_valuation, universe),
                        )

    def test_equal_interval_conditions_combine_bodies(self):
        p, q = Proposition("p"), Proposition("q")
        interval = P.closed(0, 1)

        universal = simplify(And((UniversalCondition(interval, p), UniversalCondition(interval, q))))
        existential = simplify(Or((ExistentialCondition(interval, p), ExistentialCondition(interval, q))))

        self.assertEqual(universal, UniversalCondition(interval, And((p, q))))
        self.assertEqual(existential, ExistentialCondition(interval, Or((p, q))))

    def test_same_body_conditions_merge_connected_interval_unions(self):
        p = Proposition("p")
        left, right = P.closed(-1, 0), P.closed(0, 1)

        self.assertEqual(
            simplify(And((UniversalCondition(left, p), UniversalCondition(right, p)))),
            UniversalCondition(left | right, p),
        )
        self.assertEqual(
            simplify(Or((ExistentialCondition(left, p), ExistentialCondition(right, p)))),
            ExistentialCondition(left | right, p),
        )

    def test_window_constants_full_domain_and_nesting(self):
        p = Proposition("p")
        left, right = P.closed(-1, 0), P.closed(0, 1)
        all_time = P.open(-P.inf, P.inf)

        self.assertEqual(simplify(RestrictiveSelection(P.empty(), p)), Bool(False))
        self.assertEqual(simplify(VacuousSelection(P.empty(), p)), Bool(True))
        self.assertEqual(simplify(RestrictiveSelection(left, Bool(False))), Bool(False))
        self.assertEqual(simplify(VacuousSelection(left, Bool(True))), Bool(True))
        self.assertEqual(simplify(RestrictiveSelection(all_time, p)), p)
        self.assertEqual(simplify(VacuousSelection(all_time, p)), p)
        self.assertEqual(
            simplify(RestrictiveSelection(left, RestrictiveSelection(right, p))),
            RestrictiveSelection(left & right, p),
        )
        self.assertEqual(
            simplify(VacuousSelection(left, VacuousSelection(right, p))), VacuousSelection(left & right, p)
        )

    def test_same_window_bodies_and_same_body_intervals_merge(self):
        p, q = Proposition("p"), Proposition("q")
        left, right = P.closed(-1, 0), P.closed(0, 1)

        self.assertEqual(
            simplify(And((RestrictiveSelection(left, p), RestrictiveSelection(left, q)))),
            RestrictiveSelection(left, And((p, q))),
        )
        self.assertEqual(
            simplify(Or((VacuousSelection(left, p), VacuousSelection(left, q)))),
            VacuousSelection(left, Or((p, q))),
        )
        self.assertEqual(
            simplify(And((RestrictiveSelection(left, p), RestrictiveSelection(right, p)))),
            RestrictiveSelection(left & right, p),
        )
        self.assertEqual(
            simplify(Or((RestrictiveSelection(left, p), RestrictiveSelection(right, p)))),
            RestrictiveSelection(left | right, p),
        )
        self.assertEqual(
            simplify(And((VacuousSelection(left, p), VacuousSelection(right, p)))),
            VacuousSelection(left | right, p),
        )
        self.assertEqual(
            simplify(Or((VacuousSelection(left, p), VacuousSelection(right, p)))),
            VacuousSelection(left & right, p),
        )

    def test_disconnected_merges_remain_explicit(self):
        p = Proposition("p")
        left, right = P.closed(-2, -1), P.closed(1, 2)
        formulas = (
            Or((RestrictiveSelection(left, p), RestrictiveSelection(right, p))),
            And((VacuousSelection(left, p), VacuousSelection(right, p))),
            And((UniversalCondition(left, p), UniversalCondition(right, p))),
            Or((ExistentialCondition(left, p), ExistentialCondition(right, p))),
        )

        for formula in formulas:
            with self.subTest(formula=formula):
                self.assertEqual(simplify(formula), formula)

    def test_conditions_absorb_compatible_selections(self):
        p = Proposition("p")
        left, right = P.closed(-1, 0), P.closed(0, 1)

        self.assertEqual(
            simplify(ExistentialCondition(left, RestrictiveSelection(right, p))), ExistentialCondition(left & right, p)
        )
        self.assertEqual(
            simplify(UniversalCondition(left, VacuousSelection(right, p))), UniversalCondition(left & right, p)
        )

    def test_all_window_rewrites_preserve_finite_model_semantics(self):
        p, q = Proposition("p"), Proposition("q")
        left, right = P.closed(-1, 0), P.closed(0, 1)
        formulas = (
            RestrictiveSelection(left, RestrictiveSelection(right, p)),
            VacuousSelection(left, VacuousSelection(right, p)),
            And((RestrictiveSelection(left, p), RestrictiveSelection(right, p))),
            Or((RestrictiveSelection(left, p), RestrictiveSelection(right, p))),
            And((VacuousSelection(left, p), VacuousSelection(right, p))),
            Or((VacuousSelection(left, p), VacuousSelection(right, p))),
            And((RestrictiveSelection(left, p), RestrictiveSelection(left, q))),
            Or((VacuousSelection(left, p), VacuousSelection(left, q))),
            ExistentialCondition(left, RestrictiveSelection(right, p)),
            UniversalCondition(left, VacuousSelection(right, p)),
        )
        for formula in formulas:
            with self.subTest(formula=formula):
                result = simplify(formula)
                self.assertEqual(simplify(result), result)
                self.assertLessEqual(result.node_count, formula.node_count)
                self.assert_equivalent_on_finite_models(formula, result)

    def test_simplification_is_semantics_preserving_idempotent_and_compact(self):
        p, q = Proposition("p"), Proposition("q")
        interval = P.closed(0, 1)
        formulas = (
            Not(Not(p)),
            And((Bool(True), p, Or((p, q)))),
            Or((Bool(False), q, And((p, q)))),
            And((UniversalCondition(interval, p), UniversalCondition(interval, q))),
            Or((ExistentialCondition(interval, p), ExistentialCondition(interval, q))),
            And((UniversalCondition(P.closed(-1, 0), p), UniversalCondition(P.closed(0, 1), p))),
            Or((ExistentialCondition(P.closed(-1, 0), q), ExistentialCondition(P.closed(0, 1), q))),
            RestrictiveSelection(interval, RestrictiveSelection(P.closed(-1, 0), p)),
            VacuousSelection(interval, VacuousSelection(P.closed(-1, 0), q)),
        )

        for formula in formulas:
            with self.subTest(formula=formula):
                result = simplify(formula)
                self.assertEqual(simplify(result), result)
                self.assertLessEqual(result.node_count, formula.node_count)
                self.assert_equivalent_on_finite_models(formula, result)


class NormalizationTests(unittest.TestCase):
    def test_nnf_lowers_derived_nodes_and_pushes_negation_to_leaves(self):
        p, q = Proposition("p"), Proposition("q")
        result = to_nnf(Not(Implies(p, UniversalCondition(P.closed(0, 1), q))))

        self.assertEqual(result, And((p, ExistentialCondition(P.closed(0, 1), Not(q)))))
        self.assertTrue(self._negations_only_wrap_leaves(result))

    def test_nnf_swaps_window_polarity(self):
        p, q = Proposition("p"), Proposition("q")
        interval = P.closed(0, 1)

        self.assertEqual(
            to_nnf(Not(RestrictiveSelection(interval, Or((p, q))))),
            VacuousSelection(interval, And((Not(p), Not(q)))),
        )
        self.assertEqual(
            to_nnf(Not(VacuousSelection(interval, And((p, q))))),
            RestrictiveSelection(interval, Or((Not(p), Not(q)))),
        )

    def test_equality_is_an_nnf_literal(self):
        equality = Signal("j").equals(0)

        self.assertEqual(to_nnf(Not(Not(equality))), equality)
        self.assertEqual(to_nnf(Not(equality)), Not(equality))
        self.assertTrue(self._negations_only_wrap_leaves(Not(equality)))
        self.assertEqual(partition_intervals(equality), equality)

    def test_partitioning_uses_shared_disjoint_cells(self):
        p, q = Proposition("p"), Proposition("q")
        original = And(
            (
                UniversalCondition(P.closed(0, 2), p),
                UniversalCondition(P.closed(1, 3), q),
            )
        )

        result = partition_intervals(original)
        intervals = [
            node.interval
            for node in self._walk(result)
            if isinstance(node, UniversalCondition)
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
                satisfying_anchors(original, portion_valuation, P.closed(-1, 3)),
                satisfying_anchors(result, portion_valuation, P.closed(-1, 3)),
            )

    def test_partitioning_preserves_explicit_disjoint_condition_composition(self):
        p = Proposition("p")
        original = Or(
            (
                ExistentialCondition(P.closed(-1, 0), p),
                ExistentialCondition(P.openclosed(1, 2), p),
            )
        )

        result = partition_intervals(original)

        self.assertEqual(result, original)

    def test_partitioning_splits_windows_with_dual_connectives(self):
        p, q = Proposition("p"), Proposition("q")
        restricted_interval = P.closed(0, 2)
        guarded_interval = P.closed(1, 3)
        original = And(
            (
                RestrictiveSelection(restricted_interval, p),
                VacuousSelection(guarded_interval, q),
            )
        )

        result = partition_intervals(original)
        restricted = [
            node.interval for node in self._walk(result) if isinstance(node, RestrictiveSelection)
        ]
        guarded = [node.interval for node in self._walk(result) if isinstance(node, VacuousSelection)]

        self.assertEqual(set(restricted), {P.closedopen(0, 1), P.closed(1, 2)})
        self.assertEqual(set(guarded), {P.closed(1, 2), P.openclosed(2, 3)})
        for valuation in all_valuations("p", "q"):
            portion_valuation = {
                name: portion_from_points(values)
                for name, values in valuation.items()
            }
            self.assertEqual(
                satisfying_anchors(original, portion_valuation, P.closed(-1, 3)),
                satisfying_anchors(result, portion_valuation, P.closed(-1, 3)),
            )

    def test_partitioning_enforces_node_budget(self):
        p, q = Proposition("p"), Proposition("q")
        expression = And(
            (
                UniversalCondition(P.closed(0, 2), p),
                UniversalCondition(P.closed(1, 3), q),
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

    def _negations_only_wrap_leaves(self, expression):
        return all(
            not isinstance(node, Not) or isinstance(node.operand, (Proposition, Equal))
            for node in self._walk(expression)
        )


class DerivedOperatorTests(unittest.TestCase):
    def test_builtin_derived_operators_lower_to_core_formulas(self):
        p, q = Proposition("p"), Proposition("q")

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
        p, q = Proposition("p"), Proposition("q")
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
                        satisfies(expression, valuation, 0, UNIVERSE),
                        expected(left, right),
                    )

    def test_custom_derived_operator_requires_no_evaluator_changes(self):
        p, q = Proposition("p"), Proposition("q")
        expression = Nand(p, q)

        self.assertEqual(simplify(expression), Or((Not(p), Not(q))))
        self.assertFalse(
            satisfies(expression, {"p": UNIVERSE, "q": UNIVERSE}, 0, UNIVERSE)
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


class TaggedDerived(DerivedExpression):
    def __init__(self, label, operand):
        self.label = label
        self.operand = operand

    @property
    def children(self):
        return (self.operand,)

    def lower(self):
        return self.operand

    def _with_children(self, children):
        return type(self)(self.label, children[0])


class ConfiguredDerived(DerivedExpression):
    def __init__(self, label, operand):
        self.label = label
        self.operand = operand

    @property
    def children(self):
        return (self.operand,)

    def lower(self):
        return self.operand


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
