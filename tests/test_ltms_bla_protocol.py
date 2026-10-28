from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import json
import unittest

from protocol import Booking, Certificate, CertifiedOffer, affine_policies, BargainingResult
from protocol.companion import load_method_notebook
from ltms_bla.bargaining import load_bargain, validate_corridors
from ltms_bla.records import (CrossingService, CorridorOffer, CorridorBLA,
                              snapshot_id, commit_exact)
import portion as P

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'notebooks'/'protocol.ipynb').exists():
    ROOT = Path.cwd()


def offer(service, departure, ledger=()):
    # Synthetic certificate data is used only for lifecycle unit checks. Real
    # numerical evidence is exercised by the fresh-kernel integration runner.
    checked = dict.fromkeys(('entry_inside', 'rollout_inside', 'road_ok', 'clear_ok',
                             'input_ok', 'compatible', 'reference_covered'), True)
    return CorridorOffer(f'{service.client}-{departure}', service, departure, F(departure+8),
                         snapshot_id(ledger), '', '', json.dumps(checked))


class CorridorProtocolTests(unittest.TestCase):
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

    def test_client_model_stays_fixed_across_offers(self):
        service = CrossingService('B', 'west', (0, 1), 9)
        family = tuple(offer(service, s) for s in service.departures)
        self.assertIs(family[0].service, family[1].service)
        self.assertEqual(service.contracts(), family[1].service.contracts())
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
