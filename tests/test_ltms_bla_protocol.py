"""Lifecycle checks on the notebook's own stages; run with the numerical stack."""
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import json
import tempfile
import unittest

try:
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest('the notebook stages need numpy; run in the LTMS Python 3.13 environment') from error

import interval_logic as il
import portion as P
from protocol import Booking, Certificate, CertifiedOffer, affine_policies, BargainingResult, normalize
from protocol.companion import load_method_notebook
from ltms_bla.bargaining import load_bargain, validate_corridors
from ltms_bla.records import (SERVICE_CHECKS, Admission, Candidate, CrossingService, CorridorOffer,
                              ServiceAdmission, certify_compatibility, certify_service, commit_exact,
                              implies, refines, snapshot_id, standing)
from ltms_bla.scenario import file_digest, load_method, outcome_summary, run_scenario

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'notebooks'/'protocol.ipynb').exists():
    ROOT = Path.cwd()
METHOD = load_method(ROOT)


def evidence(checks=None, compatibility=None):
    return json.dumps(dict(service={**dict.fromkeys(SERVICE_CHECKS, True), **(checks or {})},
                           compatibility={'compatible': True, 'disjoint_from': [], **(compatibility or {})}),
                      sort_keys=True)


def offer(service, departure, ledger=(), **overrides):
    # Synthetic certificate data is used only for lifecycle unit checks. Real
    # numerical evidence is exercised by the fresh-kernel integration runner.
    return CorridorOffer(f'{service.client}-{departure}', service, METHOD.service_contracts(service)[0],
                         departure, F(departure+METHOD.LEASE), snapshot_id(ledger), '', '', evidence(**overrides))


def synthetic_base(directory):
    """Unit-test data only: an eastbound band of cells for the whole horizon.

    Westbound (the rotation by pi) occupies a band two cells away, so opposite
    directions never meet and same-direction leases meet whenever they overlap.
    """
    reserved = np.zeros((37, 6, 10), bool)
    reserved[:, :, 1:4] = True
    path = Path(directory)/'base.npz'
    np.savez(path, reserved=reserved)
    return dict(reserved=reserved, dt=.25, path=str(path), digest=file_digest(path),
                service_checks=dict.fromkeys(SERVICE_CHECKS[:-1], True), output=str(directory))


class CorridorProtocolTests(unittest.TestCase):
    def run_synthetic(self, directory=None):
        if directory is not None:
            attempts, ledger = run_scenario(ROOT, synthetic_base(directory), METHOD)
            return attempts, ledger, outcome_summary(attempts)
        with tempfile.TemporaryDirectory() as directory:
            return self.run_synthetic(directory)

    def test_bargaining_is_identical_to_charging_on_equivalent_utilities(self):
        original = load_method_notebook(ROOT/'notebooks'/'protocol.ipynb').bargain
        adapted = load_bargain(ROOT)
        service = CrossingService('B', 'west', (0, 1), 9)
        corridors = tuple(offer(service, s) for s in service.departures)
        bookings = tuple(CertifiedOffer(Booking(1, P.closedopen(s, s+8)),
                         Certificate(True, True, True, True, True)) for s in service.departures)
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
        attempts, ledger, summary = self.run_synthetic()
        self.assertEqual([row[:2] for row in summary],
                         [('A', 'COMMITTED'), ('B', 'COMMITTED'), ('C', 'NO-COMPATIBLE-OFFER'),
                          ('D', 'PRICE-NO-BLA'), ('E', 'COMMITTED')])
        self.assertEqual([(row[3], row[4]) for row in summary],
                         [(0, F(15, 2)), (0, F(15, 2)), (None, None), (None, None), (20, F(15, 2))])
        self.assertEqual([len(row[2]) for row in summary], [1, 2, 0, 2, 1])
        self.assertEqual([b.offer.service.client for b in ledger], ['A', 'B', 'E'])
        self.assertTrue(all(a['previous_preserved'] for a in attempts))
        # Offer identities are deterministic for one artifact directory, so a
        # second serial run there (the notebook's runner check) agrees exactly.
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.run_synthetic(directory)[2], self.run_synthetic(directory)[2])

    def test_admission_retains_contracts_and_rebuilds_them_for_adaptations(self):
        attempts, _, _ = self.run_synthetic()
        for a in attempts:
            for s in a['admission'].services:
                self.assertEqual(s.quotient.assumption, normalize(~s.S_a | (s.B & s.S_u)))
                self.assertEqual(s.quotient.guarantee, normalize(s.S_a))
                self.assertEqual(normalize(s.obligations.guarantee),
                                 normalize(a['admission'].commitment.guarantee & s.S_a))
        E = attempts[4]['admission']
        original, adapted = E.services
        self.assertEqual(normalize(original.S_a), il.Boolean(False))  # 20+7 > 22: no eligible reference
        self.assertEqual(normalize(adapted.S_a), adapted.service.access_for(20))
        self.assertEqual([c.status for c in original.candidates], ['PROVED_IMPOSSIBLE'])
        self.assertIs(E.selected, adapted)
        B = attempts[1]
        self.assertTrue(all(o.service is B['admission'].selected.service for o in B['offers']))
        self.assertTrue(all(o.access == B['admission'].selected.S_a for o in B['offers']))
        self.assertTrue(all(o.snapshot == B['admission'].snapshot for o in B['offers']))

    def test_offers_refine_quotient_and_compose_to_the_task(self):
        attempts, _, _ = self.run_synthetic()
        B = attempts[1]
        admission, selected = B['admission'], B['admission'].selected
        for o in B['offers']:
            K, C_cmt = o.contract, admission.commitment
            self.assertTrue(implies(K.guarantee, selected.S_a))
            self.assertTrue(refines(K, selected.quotient))
            self.assertTrue(refines(C_cmt.conjoin(K), selected.obligations))
            self.assertTrue(refines(selected.client.compose(C_cmt.conjoin(K)), C_cmt.conjoin(selected.task)))
        # Boolean algebra alone cannot see C's geometric conflict with A.
        conflict = attempts[2]['admission'].services[0].candidates[0]
        H = il.Proposition(f'H_{conflict.offer_id}')
        a = attempts[2]['admission'].services[0].service.access_for(conflict.departure)
        self.assertNotEqual(normalize(attempts[2]['admission'].commitment.guarantee & H & a), il.Boolean(False))

    def test_false_evidence_cannot_qualify_an_offer(self):
        service = CrossingService('B', 'west', (0, 1), 9)
        certify_service(offer(service, 0))
        for key in SERVICE_CHECKS:
            with self.subTest(key=key), self.assertRaises(ValueError):
                certify_service(offer(service, 0, checks={key: False}))
        for broken in ({'compatible': False}, {'disjoint_from': [{'offer': 'x', 'disjoint': False}]}):
            with self.assertRaises(ValueError):
                certify_compatibility(offer(service, 0, compatibility=broken))
            with self.assertRaises(ValueError):
                validate_corridors((offer(service, 0, compatibility=broken),), {'owner': 1, 'client': 1},
                                   {'owner': 0, 'client': 0}, (0, 10), 3)
        # Service evidence for an ineligible departure does not reach S_a.
        with self.assertRaises(ValueError):
            certify_service(offer(CrossingService('B', 'west', (0, 3), 9), 3))

    def test_failure_meanings_stay_distinct(self):
        service = CrossingService('F', 'east', (0, 1), 9)
        def admission(*statuses):
            candidates = tuple(Candidate(s, f'id{s}', dict(status=status)) for s, status in enumerate(statuses))
            return Admission(None, '', standing(()), (ServiceAdmission(service, *[None]*7, candidates),))
        self.assertEqual(admission('PROVED_IMPOSSIBLE', 'PROVED_IMPOSSIBLE').failure, 'PROVED-IMPOSSIBLE')
        self.assertEqual(admission('GEOMETRIC_CONFLICT', 'PROVED_IMPOSSIBLE').failure, 'NO-COMPATIBLE-OFFER')
        self.assertEqual(admission('UNRESOLVED', 'PROVED_IMPOSSIBLE').failure, 'UNRESOLVED')
        self.assertIsNone(admission('QUALIFIED', 'UNRESOLVED').failure)

    def test_client_model_stays_fixed_across_offers(self):
        service = CrossingService('B', 'west', (0, 1), 9)
        family = tuple(offer(service, s) for s in service.departures)
        self.assertIs(family[0].service, family[1].service)
        for invalid in (replace(family[1], service=CrossingService('C', 'west', (0, 1), 9)),
                        replace(family[1], access=service.access_for(1))):
            with self.assertRaises(ValueError):
                validate_corridors((family[0], invalid), {'owner': 1, 'client': 1},
                                   {'owner': 0, 'client': 0}, (0, 10), 3)

    def test_exact_commit_stale_snapshot_and_no_bla_preservation(self):
        service = CrossingService('A', 'east', (0,), 8)
        chosen = offer(service, 0)
        bargain = load_bargain(ROOT)
        result = bargain((chosen,), affine_policies({chosen: F(1)}, {chosen: F(10)}),
                         {'owner': F(2), 'client': F(2)}, {'owner': F(0), 'client': F(0)})
        ledger = commit_exact((chosen,), result, (), lambda o: None)
        self.assertIs(ledger[-1].offer, result.agreement.offer)
        self.assertEqual(ledger[-1].price, result.agreement.price)
        with self.assertRaises(ValueError):
            commit_exact((chosen,), result, ledger, lambda o: None)
        clone = replace(chosen)
        with self.assertRaises(ValueError):
            commit_exact((clone,), replace(result, offers=(clone,)), (), lambda o: None)
        declined = BargainingResult('NO-BLA', None, (), (chosen,))
        self.assertIs(commit_exact((chosen,), declined, ledger, lambda o: None), ledger)


class NotebookModelTests(unittest.TestCase):
    """The notebook's model cells, exercised directly."""
    def test_declared_reference_fulfils_the_task(self):
        M = METHOD
        start, end = M.reference(0), M.reference(M.PRESENCE)
        self.assertAlmostEqual(end[0], 1.55)
        self.assertTrue(M.in_lane(start) and M.in_lane(end) and M.in_zone(end, M.EXIT_ZONE))
        self.assertFalse(M.in_zone(M.reference(M.PRESENCE, speed=.35), M.EXIT_ZONE))
        self.assertFalse(M.in_road((-1.6, -.9, 0., M.SPEED)))
        self.assertTrue(M.in_road((0., .9, 1., M.SPEED)))  # the centre admits any heading

    def test_deadline_relations(self):
        M = METHOD
        for s in range(5):
            for d in range(s+1, s+12):
                if M.tlt_evidence_applies(s, d):  # [s+7, s+8] ⊆ [s, d] strengthens "clear by d"
                    self.assertIn(s, M.eligible(CrossingService('X', 'east', (s,), d)))
        self.assertEqual(M.eligible(CrossingService('X', 'east', (0, 1, 2), 8)), (0, 1))
        self.assertTrue(M.speed_bound_excludes(20, 22))   # 0.6 * 2 < 3
        self.assertFalse(M.speed_bound_excludes(20, 25))  # 0.6 * 5 >= 3
        self.assertFalse(M.tlt_evidence_applies(30, 37))

    def test_selection_reads_only_the_promise(self):
        M = METHOD
        service = CrossingService('X', 'east', (0, 1), 9)
        self.assertEqual(M.select_departure(service, {0, 1}), 0)
        self.assertEqual(M.select_departure(service, {1}), 1)
        self.assertIsNone(M.select_departure(service, set()))
        self.assertIsNone(M.select_departure(CrossingService('X', 'east', (0, 3), 9), {3}))
