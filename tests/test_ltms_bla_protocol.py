"""Lifecycle checks on the notebook's own stages; run with the numerical stack."""
from fractions import Fraction as F
from pathlib import Path
import unittest

try:
    import numpy as np  # noqa: F401
except ImportError as error:
    raise unittest.SkipTest('the notebook stages need numpy; run in the LTMS Python 3.13 environment') from error

import interval_logic as il
import portion as P
import protocol
from protocol import Booking, CertifiedOffer, affine_policies, BargainingResult, normalize
from protocol.companion import load_method_notebook
from ltms_bla.bargaining import load_bargain
from ltms_bla.scenario import load_method

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'notebooks'/'protocol.ipynb').exists():
    ROOT = Path.cwd()
METHOD = load_method(ROOT)
J = (0, F(1, 2))


def crossing(client='B', inbound='west', outbound='west', entry=J):
    return METHOD.Crossing(client, inbound, outbound, entry)


def offer(service, index, certified=True):
    # Synthetic offers for lifecycle checks; the corridors are exercised by the fresh-kernel notebook run.
    exit = (service.entry[0] + 5 + index, service.entry[0] + 6.5 + index)
    return METHOD.Offer(service, index, exit, None, None, certified)


def admission(service, ledger=()):
    commitment = METHOD.standing(ledger)
    C_req, C_trg = METHOD.service_contracts(service)
    Q = C_trg.quotient(C_req).normalize()
    return METHOD.Admission(METHOD.Request(service.client, service), service, C_req, C_trg, Q,
                            commitment.conjoin(Q), commitment, None, ())


def refines(first, second):
    implies = lambda p, q: normalize(p & ~q) == il.Boolean(False)
    return implies(second.assumption, first.assumption) and implies(first.guarantee, second.guarantee)


class CorridorProtocolTests(unittest.TestCase):
    def test_bargaining_is_identical_to_charging_on_equivalent_utilities(self):
        original = load_method_notebook(ROOT/'notebooks'/'protocol.ipynb').bargain
        service = crossing()
        corridors = tuple(offer(service, k) for k in (0, 1))
        bookings = tuple(CertifiedOffer(Booking(1, P.closedopen(o.start, o.start+8)),
                         protocol.Certificate(True, True, True, True, True)) for o in corridors)

        def execute(method, family, price_failure):
            policies = affine_policies(dict(zip(family, map(F, [5, 2]))),
                                       dict(zip(family, map(F, [1, 0] if price_failure else [10, 8]))))
            result = method(family, policies, {'owner': F(4), 'client': F(1 if price_failure else 4)},
                            {'owner': F(2 if price_failure else 1), 'client': F(0 if price_failure else 1)},
                            (F(0), F(20)), 3)
            return result.status, [(r.number, r.proposer, r.targets, r.proposal.price,
                                    r.proposal.offer.start, r.utilities, r.accepted) for r in result.history]
        for failure in (False, True):
            self.assertEqual(execute(original, bookings, failure), execute(METHOD.bargain, corridors, failure))

    def test_quotient_is_access_only(self):
        for service in (crossing(), crossing('E', 'east', 'north', (12, F(25, 2)))):
            s = admission(service)
            self.assertEqual(s.quotient.guarantee, normalize(service.access))
            self.assertEqual(normalize(s.obligations.guarantee), normalize(service.access))

    def test_offers_refine_quotient_and_compose_to_the_task(self):
        A = crossing('A', 'east', 'east')
        ledger = (METHOD.BLA(offer(A, 2), F(15, 2)),)
        s = admission(crossing(), ledger)
        self.assertEqual(normalize(s.obligations.guarantee), normalize(s.commitment.guarantee & s.service.access))
        for k in (1, 2):
            K = offer(s.service, k).contract
            self.assertTrue(refines(K, s.quotient))
            self.assertTrue(refines(s.commitment.conjoin(K), s.obligations))
            self.assertTrue(refines(s.client_contract.compose(s.commitment.conjoin(K)), s.commitment.conjoin(s.task)))
        # Boolean algebra alone cannot see a spatial conflict: that is the entry condition's job.
        conflict = offer(crossing('C', 'north', 'north'), 1)
        self.assertNotEqual(normalize(s.commitment.guarantee & conflict.contract.guarantee), il.Boolean(False))

    def test_only_certified_offers_of_one_service_are_offered_and_bargained(self):
        service = crossing()
        pool = (offer(service, 1, certified=False), offer(service, 2), offer(service, 3))
        self.assertEqual([o.index for o in METHOD.generate(pool)], [2, 3])
        METHOD.validate_offers(METHOD.generate(pool))
        with self.assertRaises(ValueError):
            METHOD.validate_offers(pool)
        with self.assertRaises(ValueError):
            METHOD.validate_offers((offer(service, 2), offer(crossing('C'), 3)))

    def test_exact_commit_and_no_bla_preservation(self):
        s = admission(crossing())
        offers = (offer(s.service, 2),)
        result = METHOD.bargain(offers, affine_policies({offers[0]: F(1)}, {offers[0]: F(10)}),
                                {'owner': F(2), 'client': F(2)}, {'owner': F(0), 'client': F(0)})
        committed = METHOD.commit(s, offers, result, s.commitment)
        self.assertIs(committed.ledger[-1].offer, result.agreement.offer)
        self.assertEqual(committed.ledger[-1].price, result.agreement.price)
        with self.assertRaises(ValueError):  # the commitment moved on after admission
            METHOD.commit(s, offers, result, committed.commitment, committed.ledger)
        declined = BargainingResult('NO-BLA', None, (), offers)
        unchanged = METHOD.commit(s, offers, declined, committed.commitment, committed.ledger)
        self.assertEqual(unchanged.ledger, committed.ledger)
        self.assertEqual(unchanged.commitment, committed.commitment)


class NotebookModelTests(unittest.TestCase):
    """The notebook's model cells, exercised directly."""
    def test_query_is_read_on_map_atoms(self):
        phi = crossing().query(il.Proposition('D_B'))
        self.assertIsInstance(phi, il.Until)
        self.assertEqual(phi.left, il.Proposition('road_w') & ~il.Proposition('D_B'))
        self.assertEqual(phi.right, il.Proposition('exit_w'))
        self.assertEqual(phi.parameter.interval, P.closed(0, METHOD.HORIZON))

    def test_a_turn_uses_both_roads_and_exits_on_the_outbound_one(self):
        turn = crossing('D', 'south', 'west', (6, F(13, 2)))
        self.assertEqual(turn.road(True), il.Proposition('road_s_D*') | il.Proposition('road_w_D*'))
        self.assertEqual(turn.exiting(), il.Proposition('exit_w'))

    def test_exit_windows_follow_the_route_length(self):
        kinds = {route: METHOD.manoeuvre(crossing('Z', *route)) for route in
                 (('east', 'east'), ('east', 'north'), ('south', 'west'), ('east', 'west'))}
        self.assertEqual(list(kinds.values()), ['straight', 'left', 'right', 'U-turn'])
        first = {kind: METHOD.exit_windows(crossing('Z', *route))[0][0] for route, kind in kinds.items()}
        self.assertLess(first['right'], first['straight'])
        self.assertLess(first['straight'], first['left'])
        self.assertLessEqual(METHOD.exit_windows(crossing('Z', 'east', 'north'))[-1][1], METHOD.HORIZON)

    def test_vehicles_have_their_own_atoms(self):
        A, E = crossing('A', 'east', 'east'), crossing('E', 'east', 'east')
        self.assertNotEqual(A.access, E.access)
        self.assertNotEqual(A.rule, E.rule)
        self.assertNotEqual(A.use, A.entering(True))


if __name__ == '__main__':
    unittest.main()
