from dataclasses import replace
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest

import interval_logic as il
import portion as P
from protocol import Booking, Certificate, CertifiedOffer, affine_policies, BargainingResult, normalize
from protocol.companion import load_method_notebook
from ltms_bla import model as M
from ltms_bla.bargaining import load_bargain, validate_corridors
from ltms_bla.records import (SERVICE_CHECKS, Admission, Candidate, CrossingService, CorridorOffer,
                              ServiceAdmission, certify_compatibility, certify_service, commit_exact,
                              implies, refines, snapshot_id, standing)
from ltms_bla.scenario import load_method, outcome_summary, run_scenario

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'notebooks'/'protocol.ipynb').exists():
    ROOT = Path.cwd()


def evidence(checks=None, compatibility=None):
    return json.dumps(dict(service={**dict.fromkeys(SERVICE_CHECKS, True), **(checks or {})},
                           compatibility={'compatible': True, 'disjoint_from': [], **(compatibility or {})}),
                      sort_keys=True)


def offer(service, departure, ledger=(), **overrides):
    # Synthetic certificate data is used only for lifecycle unit checks. Real
    # numerical evidence is exercised by the fresh-kernel integration runner.
    return CorridorOffer(f'{service.client}-{departure}', service, departure, F(departure+M.LEASE),
                         snapshot_id(ledger), '', '', evidence(**overrides))


class SyntheticWorker:
    """Unit-test data only: overlapping same-route leases conflict, else disjoint.

    Status precedence and offer artifacts follow ltms_bla.worker; no HJ value.
    """
    def __init__(self, directory):
        self.directory = Path(directory)
        base = self.directory/'base.npz'
        base.write_bytes(b'synthetic')
        self.base, self.setup = str(base), dict(base_digest=sha256(b'synthetic').hexdigest())

    def call(self, op, **message):
        assert op == 'evaluate'
        service, s = message['service'], message['departure']
        if M.speed_bound_excludes(s, service['deadline']):
            return dict(status='PROVED_IMPOSSIBLE', reason='speed bound')
        if not M.tlt_evidence_applies(s, service['deadline']):
            return dict(status='UNRESOLVED', reason='window exceeds deadline')
        comparisons = []
        for record in message['accepted']:
            old = json.loads(Path(record['artifact']).read_text())
            comparisons.append(dict(offer=old['id'], disjoint=old['route'] != service['route']
                                    or s >= old['end'] or old['departure'] >= s+M.LEASE))
        checks = dict.fromkeys(SERVICE_CHECKS, True)
        if not all(c['disjoint'] for c in comparisons):
            return dict(status='GEOMETRIC_CONFLICT', reason='meets', service=checks, comparisons=comparisons)
        info = dict(id=message['id'], service=service, departure=s, route=service['route'],
                    snapshot=message['snapshot'], end=s+M.LEASE, base=self.base,
                    base_digest=self.setup['base_digest'],
                    checks=dict(service=checks, compatibility=dict(compatible=True, disjoint_from=comparisons)))
        path = self.directory/f"offer-{message['id']}.json"
        path.write_text(json.dumps(info, sort_keys=True))
        return dict(status='QUALIFIED', artifact=str(path),
                    artifact_digest=sha256(path.read_bytes()).hexdigest(), info=info)


class CorridorProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.method = load_method(ROOT)

    def run_synthetic(self, directory=None):
        if directory is not None:
            attempts, ledger = run_scenario(ROOT, SyntheticWorker(directory), self.method)
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
        late = CrossingService('B', 'west', (0, 3), 9)
        with self.assertRaises(ValueError):
            certify_service(offer(late, 3))

    def test_failure_meanings_stay_distinct(self):
        service = CrossingService('F', 'east', (0, 1), 9)
        commitment = standing(())
        def admission(*statuses):
            candidates = tuple(Candidate(s, f'id{s}', dict(status=status)) for s, status in enumerate(statuses))
            return Admission(None, '', commitment, (ServiceAdmission(service, *[None]*7, candidates),))
        self.assertEqual(admission('PROVED_IMPOSSIBLE', 'PROVED_IMPOSSIBLE').failure, 'PROVED-IMPOSSIBLE')
        self.assertEqual(admission('GEOMETRIC_CONFLICT', 'PROVED_IMPOSSIBLE').failure, 'NO-COMPATIBLE-OFFER')
        self.assertEqual(admission('UNRESOLVED', 'PROVED_IMPOSSIBLE').failure, 'UNRESOLVED')
        self.assertIsNone(admission('QUALIFIED', 'UNRESOLVED').failure)

    def test_client_model_stays_fixed_across_offers(self):
        service = CrossingService('B', 'west', (0, 1), 9)
        family = tuple(offer(service, s) for s in service.departures)
        self.assertIs(family[0].service, family[1].service)
        self.assertEqual(self.method.service_contracts(service),
                         self.method.service_contracts(family[1].service))
        invalid = replace(family[1], service=CrossingService('C', 'west', (0, 1), 9))
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

