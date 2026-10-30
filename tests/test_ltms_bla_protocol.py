"""Lifecycle checks on the notebook's own stages; run with the numerical stack."""
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import unittest

try:
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest('the notebook stages need numpy; run in the LTMS Python 3.13 environment') from error

import interval_logic as il
import portion as P
import protocol
from protocol import Booking, CertifiedOffer, affine_policies, BargainingResult, normalize
from protocol.companion import load_method_notebook
from ltms_bla.bargaining import load_bargain, validate_corridors
from ltms_bla.records import Certificate, CrossingRequest, CrossingService, CorridorOffer, implies, refines
from ltms_bla.scenario import load_method

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'notebooks'/'protocol.ipynb').exists():
    ROOT = Path.cwd()
METHOD = load_method(ROOT)


def offer(service, departure, **certificate):
    # Synthetic certificate data is used only for lifecycle unit checks. Real
    # numerical evidence is exercised by the fresh-kernel notebook run.
    evidence = Certificate(**{'capability': True, 'window_applies': True, 'compatible': True, **certificate})
    return CorridorOffer(service, METHOD.service_contracts(service)[0], departure,
                         F(departure+METHOD.LEASE), evidence)


def synthetic_base(capability=True):
    """Unit-test data only: each lane is a band of cells for the whole horizon.

    Opposite directions use separate bands and never meet; crossing directions
    meet whenever their leases overlap, and a turn reserves both of its lanes.
    """
    lanes = {d: np.zeros((37, 10, 10), bool) for d in ('east', 'north', 'west', 'south')}
    lanes['east'][:, :, 1:4] = lanes['west'][:, :, 6:9] = True
    lanes['north'][:, 6:9, :] = lanes['south'][:, 1:4, :] = True
    routes = {(a, b): dict(reserved=lanes[a] | lanes[b], capability=capability) for a in lanes for b in lanes}
    return dict(dt=.25, routes=routes)


def run_synthetic():
    ledger, attempts = (), []
    for spec in METHOD.REQUESTS:
        attempts.append(METHOD.attempt(spec, ledger, synthetic_base()))
        ledger = attempts[-1]['result'].ledger
    return attempts, ledger


class CorridorProtocolTests(unittest.TestCase):
    def test_bargaining_is_identical_to_charging_on_equivalent_utilities(self):
        original = load_method_notebook(ROOT/'notebooks'/'protocol.ipynb').bargain
        adapted = load_bargain(ROOT)
        service = CrossingService('B', 'west', 'west', (0, 1), 9)
        corridors = tuple(offer(service, s) for s in service.departures)
        bookings = tuple(CertifiedOffer(Booking(1, P.closedopen(s, s+8)),
                         protocol.Certificate(True, True, True, True, True)) for s in service.departures)
        def execute(method, family, price_failure):
            policies = affine_policies(dict(zip(family, map(F, [5, 2]))),
                                        dict(zip(family, map(F, [1, 0] if price_failure else [10, 8]))))
            result = method(family, policies, {'owner': F(4), 'client': F(1 if price_failure else 4)},
                            {'owner': F(2 if price_failure else 1), 'client': F(0 if price_failure else 1)},
                            (F(0), F(20)), 3)
            return result.status, [(r.number, r.proposer, r.targets, r.proposal.price,
                                    r.proposal.offer.start, r.utilities, r.accepted) for r in result.history]
        for failure in (False, True):
            self.assertEqual(execute(original, bookings, failure), execute(adapted, corridors, failure))

    def test_notebook_stages_reproduce_scenario_outcomes(self):
        attempts, ledger = run_synthetic()
        self.assertEqual([a['result'].status for a in attempts],
                         ['COMMITTED', 'COMMITTED', 'NO-BLA', 'NO-BLA', 'COMMITTED'])
        self.assertEqual([None if a['result'].agreement is None else
                          (a['result'].agreement.offer.departure, a['result'].agreement.price) for a in attempts],
                         [(0, F(15, 2)), (0, F(15, 2)), None, None, (20, F(15, 2))])
        self.assertEqual([len(a['offers']) for a in attempts], [1, 2, 0, 2, 1])
        self.assertEqual([b.offer.service.client for b in ledger], ['A', 'B', 'E'])
        self.assertIsNone(attempts[2]['admission'])  # C meets A's reservation at every departure

    def test_admission_retains_contracts_and_rebuilds_them_for_adaptations(self):
        attempts, _ = run_synthetic()
        for a in attempts:
            s = a['admission']
            if s is None:
                continue
            T = s.service.task
            self.assertEqual(s.quotient.assumption, normalize(~s.access | T))
            self.assertEqual(s.quotient.guarantee, normalize(s.access))
            self.assertEqual(normalize(s.obligations.guarantee), normalize(s.commitment.guarantee & s.access))
        # E's original deadline leaves no room for the certified window; the permitted one does.
        E = attempts[4]
        original, adapted = E['request'].services
        self.assertIs(E['admission'].service, adapted)
        self.assertIsNone(METHOD.admit(CrossingRequest('E', original), (), synthetic_base()))
        self.assertNotEqual(original.task, adapted.task)  # the task's until window ends at d
        B = attempts[1]
        self.assertTrue(all(o.service is B['admission'].service for o in B['offers']))
        self.assertTrue(all(o.access == B['admission'].access for o in B['offers']))

    def test_offers_refine_quotient_and_compose_to_the_task(self):
        attempts, _ = run_synthetic()
        admission = attempts[1]['admission']
        for o in attempts[1]['offers']:
            K, C_cmt = o.contract, admission.commitment
            self.assertTrue(implies(K.guarantee, admission.access))
            self.assertTrue(refines(K, admission.quotient))
            self.assertTrue(refines(C_cmt.conjoin(K), admission.obligations))
            self.assertTrue(refines(admission.client_contract.compose(C_cmt.conjoin(K)),
                                    C_cmt.conjoin(admission.task)))
        # Boolean algebra alone cannot see C's geometric conflict with A.
        conflict = offer(attempts[2]['request'].service, 0)
        self.assertNotEqual(normalize(attempts[2]['result'].commitment.guarantee & conflict.contract.guarantee),
                            il.Boolean(False))

    def test_missing_capability_admits_nothing(self):
        request = METHOD.REQUESTS[0]['request']
        self.assertIsNone(METHOD.admit(request, (), synthetic_base(capability=False)))

    def test_uncertified_offers_cannot_be_bargained(self):
        service = CrossingService('B', 'west', 'west', (0, 1), 9)
        args = ({'owner': 1, 'client': 1}, {'owner': 0, 'client': 0}, (0, 10), 3)
        validate_corridors((offer(service, 0),), *args)
        for key in ('capability', 'window_applies', 'compatible'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_corridors((offer(service, 0, **{key: False}),), *args)
        # Capability evidence for one departure does not reach another departure's access predicate.
        with self.assertRaises(ValueError):
            validate_corridors((replace(offer(service, 1), access=service.access_for(0)),), *args)

    def test_client_model_stays_fixed_across_offers(self):
        service = CrossingService('B', 'west', 'west', (0, 1), 9)
        family = tuple(offer(service, s) for s in service.departures)
        self.assertIs(family[0].service, family[1].service)
        for invalid in (replace(family[1], service=CrossingService('C', 'west', 'west', (0, 1), 9)),
                        replace(family[1], access=service.access_for(1))):
            with self.assertRaises(ValueError):
                validate_corridors((family[0], invalid), {'owner': 1, 'client': 1},
                                   {'owner': 0, 'client': 0}, (0, 10), 3)

    def test_exact_commit_and_no_bla_preservation(self):
        request = METHOD.REQUESTS[0]['request']
        admission = METHOD.admit(request, (), synthetic_base())
        offers = METHOD.generate(admission, synthetic_base())
        bargain = load_bargain(ROOT)
        result = bargain(offers, affine_policies({offers[0]: F(1)}, {offers[0]: F(10)}),
                         {'owner': F(2), 'client': F(2)}, {'owner': F(0), 'client': F(0)})
        committed = METHOD.commit(admission, offers, result, admission.commitment)
        self.assertIs(committed.ledger[-1].offer, result.agreement.offer)
        self.assertEqual(committed.ledger[-1].price, result.agreement.price)
        with self.assertRaises(ValueError):  # the commitment moved on after admission
            METHOD.commit(admission, offers, result, committed.commitment, committed.ledger)
        declined = BargainingResult('NO-BLA', None, (), offers)
        unchanged = METHOD.commit(admission, offers, declined, committed.commitment, committed.ledger)
        self.assertEqual(unchanged.ledger, committed.ledger)
        self.assertEqual(unchanged.commitment, committed.commitment)


class NotebookModelTests(unittest.TestCase):
    """The notebook's model cells, exercised directly."""
    def test_task_formula_keeps_its_physical_structure(self):
        service = CrossingService('B', 'west', 'west', (0, 1), 9)
        phi = service.task_for(1)
        self.assertIsInstance(phi, il.Until)
        self.assertEqual(phi.left, il.Proposition('road_w') & il.Proposition('alloc_B'))
        self.assertEqual(phi.right, il.Proposition('exit_w'))
        self.assertEqual(phi.parameter.interval, P.closed(1, 9))
        self.assertEqual(service.task, il.Or((service.task_for(0), phi)))
        S_a, T, C_client, R_task = METHOD.service_contracts(service)
        self.assertEqual(S_a, il.Or((service.access_for(0), service.access_for(1))))
        self.assertEqual(normalize(R_task.quotient(C_client).guarantee), normalize(S_a))

    def test_a_turn_uses_both_roads_and_exits_on_the_outbound_one(self):
        turn = CrossingService('E', 'east', 'north', (0,), 8)
        self.assertEqual(turn.task_for(0).left,
                         (il.Proposition('road_e') | il.Proposition('road_n')) & il.Proposition('alloc_E'))
        self.assertEqual(turn.exit, il.Proposition('exit_n'))
        with self.assertRaises(ValueError):  # no U-turns
            CrossingService('E', 'east', 'west', (0,), 8)

    def test_deadline_relations(self):
        self.assertTrue(METHOD.certified_window_applies(0, 8))
        self.assertFalse(METHOD.certified_window_applies(30, 37))
        self.assertFalse(METHOD.certified_window_applies(20, 22))
        self.assertTrue(METHOD.certified_window_applies(20, 28))
