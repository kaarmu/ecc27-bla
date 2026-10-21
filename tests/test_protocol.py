"""Background package regressions use ordinary imports, independent of the notebook."""
from fractions import Fraction as F
from itertools import product
import unittest
import portion as P
import interval_logic as il
import protocol

class ContractAlgebraTests(unittest.TestCase):
    def test_actual_contract_algebra_over_all_small_behavior_sets(self):
        import protocol
        atom = il.Proposition("finite_behavior")
        predicates = (il.Boolean(False), ~atom, atom, il.Boolean(True))
        traces = tuple(
            il.Trace(
                P.singleton(0),
                propositions={"finite_behavior": P.singleton(0) if value else P.empty()},
            )
            for value in (False, True)
        )

        def denotation(formula):
            return frozenset(
                index
                for index, trace in enumerate(traces)
                if il.satisfies(formula, trace, 0)
            )

        def meaning(contract):
            return denotation(contract.assumption), denotation(contract.guarantee)

        def refines(left, right):
            return left[0] >= right[0] and left[1] <= right[1]

        universe = frozenset(range(len(traces)))
        contracts = []
        meanings = []
        # Every saturated contract over this complete two-behavior universe.
        for assumption, guarantee in product(predicates, repeat=2):
            a, g = denotation(assumption), denotation(guarantee)
            saturated = protocol.Contract(assumption, guarantee)
            self.assertEqual(meaning(saturated), (a, g | (universe - a)))
            if universe - a <= g:
                contracts.append(saturated)
                meanings.append((a, g))
        self.assertEqual(len(contracts), 9)
        composed, quotients, conjunctions = {}, {}, {}
        for i, left in enumerate(contracts):
            for j, right in enumerate(contracts):
                a, g = meanings[i]
                b, h = meanings[j]
                composed[i, j] = meaning(left.compose(right))
                quotients[i, j] = meaning(left.quotient(right))
                conjunctions[i, j] = meaning(left.conjoin(right))
                self.assertEqual(
                    composed[i, j], ((a & b) | (universe - (g & h)), g & h)
                )
                quotient_assumption = a & h
                self.assertEqual(
                    quotients[i, j],
                    (quotient_assumption, (g & b) | (universe - quotient_assumption)),
                )
                self.assertEqual(conjunctions[i, j], (a | b, g & h))
                for actual in (composed[i, j], quotients[i, j], conjunctions[i, j]):
                    self.assertTrue(universe - actual[0] <= actual[1])
        for i, j, k in product(range(len(contracts)), repeat=3):
            # X || Y <= R iff X <= R / Y.
            self.assertEqual(
                refines(composed[i, j], meanings[k]),
                refines(meanings[i], quotients[k, j]),
            )
            # Meet is exactly the greatest lower bound in refinement order.
            self.assertEqual(
                refines(meanings[k], conjunctions[i, j]),
                refines(meanings[k], meanings[i]) and refines(meanings[k], meanings[j]),
            )


class BookingBackgroundTests(unittest.TestCase):
    def test_exact_decisions_against_critical_boundary_intersection_checker(self):
        for starts, duration, now, client in product(
                (P.closed(0, 5), P.singleton(1) | P.open(2, 3) | P.singleton(4), P.empty()),
                (F(1, 3), F(1), F(2)), (F(0), F(3, 2)), (1, 2)):
            with self.subTest(starts=starts, duration=duration, now=now, client=client):
                service = protocol.Service(starts, duration)
                stored = (protocol.Booking(1, P.closedopen(F(4, 3), F(7, 3))),)
                access = protocol.grouped(il.Eventually, il.Always(protocol.acc.equals(client), duration), starts)
                decision = protocol.decide_booking(protocol.Contract(True, protocol.standing(*stored).guarantee & access), now)
                independent = protocol.independent_feasible_starts(service, stored, client, now)
                self.assertEqual(decision.feasible_starts or P.empty(), independent)
                self.assertEqual(decision.satisfiable, not independent.empty)

    def test_exhaustive_evidence_helper_uses_the_actual_algebra(self):
        self.assertEqual(protocol.check_boolean_algebra(),
                         {'saturated_contracts': 9, 'triples': 729, 'passed': True})

    def test_no_reverse_dependency_or_hidden_protocol_orchestration(self):
        from pathlib import Path
        self.assertFalse(any(hasattr(protocol, name) for name in ('admit', 'generate', 'bargain', 'commit')))
        source_root = Path(il.__file__).parent
        self.assertFalse(any('from protocol' in p.read_text() or 'import protocol' in p.read_text()
                             for p in source_root.glob('*.py')))

    def test_numeric_records_and_representative_selection(self):
        for invalid in (True, float('inf'), float('nan'), -1, 0):
            with self.assertRaises((TypeError, ValueError)):
                protocol.Service(P.singleton(1), invalid)
        self.assertEqual(protocol.representative_starts(P.singleton(F(1, 3)) | P.open(F(2, 3), F(4, 3)), F(2, 3)),
                         (F(1, 3), F(1)))

    def test_half_duration_grids_respect_endpoints_and_component_origins(self):
        cases = (
            (P.singleton(1) | P.closedopen(3, 5), 1, (F(1), F(3), F(7, 2), F(4), F(9, 2))),
            (P.openclosed(3, 5), 1, (F(7, 2), F(4), F(9, 2), F(5))),
            (P.closed(3, 5), 1, (F(3), F(7, 2), F(4), F(9, 2), F(5))),
            (P.open(3, 5), 1, (F(7, 2), F(4), F(9, 2))),
            (P.open(0, F(1, 4)), 1, ()),
            (P.openclosed(0, F(1, 2)), 1, (F(1, 2),)),
            (P.closed(0, F(1, 4)), 1, (F(0),)),
            (P.closed(F(1, 3), 1), F(1, 3), (F(1, 3), F(1, 2), F(2, 3), F(5, 6), F(1))),
            (P.closedopen(F(1, 3), F(2, 3)) | P.closedopen(1, 2), 1, (F(1, 3), F(1), F(3, 2))),
            (P.empty(), 1, ()),
            (P.closed(0, 0.3), 0.2, (F(0), F(1, 10), F(1, 5), F(3, 10))),
        )
        for starts, duration, expected in cases:
            with self.subTest(starts=starts, duration=duration):
                actual = protocol.representative_starts(starts, duration)
                self.assertEqual(actual, expected)
                self.assertTrue(all(isinstance(s, F) and s in protocol.Service(starts, duration).starts
                                    for s in actual))
        for duration in (0, -1, True, float('inf'), float('nan')):
            with self.assertRaises((TypeError, ValueError)):
                protocol.representative_starts(P.closed(0, 1), duration)
        with self.assertRaises(ValueError):
            protocol.representative_starts(P.closedopen(0, P.inf), 1)

    def test_unknown_formulas_are_not_declared_satisfiable(self):
        with self.assertRaises(protocol.UnsupportedContractError):
            protocol.decide_booking(protocol.Contract(True, il.Proposition('unknown')))

    def test_joint_witness_checks_distinct_obligations(self):
        booking = protocol.Booking(2, P.closedopen(1, 2))
        trace = protocol.joint_witness((booking,), ())
        client = protocol.Contract(booking.contract.guarantee, il.Eventually(protocol.use.equals(2)))
        result = protocol.check_joint_behavior(trace, booking.contract, client, protocol.Contract(True, client.guarantee))
        self.assertEqual(result, dict(owner=True, client_assumption=True, client_guarantee=False, joint_task=False))


if __name__ == '__main__':
    unittest.main()
