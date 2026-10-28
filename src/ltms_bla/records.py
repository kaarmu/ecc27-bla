"""Immutable, dependency-light coordinator records; prices stay outside contracts."""
from dataclasses import dataclass
from fractions import Fraction as F
from hashlib import sha256
import json

import interval_logic as il
from protocol import Contract, normalize


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class CrossingService:
    client: str
    route: str
    departures: tuple[int, ...]
    deadline: int

    def __post_init__(self):
        if (not self.client or self.route not in ('east', 'west') or not self.departures
                or any(type(s) is not int or s < 0 for s in self.departures)
                or tuple(sorted(set(self.departures))) != self.departures
                or self.deadline <= max(self.departures)):
            raise ValueError('invalid crossing service')

    @property
    def key(self):
        return digest(dict(client=self.client, route=self.route,
                           departures=self.departures, deadline=self.deadline))[:16]

    def access_for(self, departure):
        if departure not in self.departures:
            raise ValueError('departure is outside selected service')
        # An owner-only predicate: the allocation contains this fixed reference
        # vehicle's disk throughout its declared crossing, absent afterwards.
        return il.Proposition(f'covers_ref_{self.key}_{departure}')

    @property
    def access(self):
        return il.Or(self.access_for(s) for s in self.departures if s+7 <= self.deadline)

    def contracts(self):
        B = il.Proposition(f'access_rule_{self.client}')
        Su = il.Proposition(f'road_and_clear_by_{self.deadline}_{self.key}')
        client, task = Contract(self.access, B & Su), Contract(True, B & Su)
        quotient = task.quotient(client).normalize()
        assert quotient.guarantee == normalize(self.access)
        return client, task, quotient


@dataclass(frozen=True)
class CorridorOffer:
    id: str
    service: CrossingService
    departure: int
    end: F
    snapshot: str
    artifact: str
    artifact_digest: str
    evidence_json: str

    @property
    def start(self):
        return F(self.departure)

    @property
    def contract(self):
        # The corridor predicate promises the full owner reservation; the
        # reference predicate is its checked, geometrically implied consequence.
        return Contract(True, il.Proposition(f'covers_corridor_{self.id}') &
                        self.service.access_for(self.departure))

    @property
    def evidence(self):
        return json.loads(self.evidence_json)


@dataclass(frozen=True)
class CorridorBLA:
    offer: CorridorOffer
    price: F

    @property
    def contract(self):
        return self.offer.contract


def snapshot_id(ledger):
    return digest([(b.offer.id, b.offer.artifact_digest, str(b.price)) for b in ledger])


def standing(ledger):
    result = Contract(True, True)
    for bla in ledger:
        result = result.conjoin(bla.contract)
    return result


def certify_template(offer):
    """Boolean implication plus separately established numerical/geometry facts."""
    if normalize(offer.contract.guarantee & ~offer.service.access) != il.Boolean(False):
        raise ValueError('offer does not imply the fixed sufficient-access predicate')
    e = offer.evidence
    if not all(e.get(k) for k in ('entry_inside', 'rollout_inside', 'road_ok',
                                  'clear_ok', 'input_ok', 'compatible', 'reference_covered')):
        raise ValueError('offer lacks a required numerical/geometry check')


def commit_exact(offers, negotiation, ledger, verify_artifact):
    ledger = tuple(ledger)
    if negotiation.status == 'NO-BLA':
        if negotiation.agreement is not None:
            raise ValueError('NO-BLA cannot carry an agreement')
        return ledger
    pair = negotiation.agreement
    if (negotiation.status != 'ACCEPTED' or tuple(offers) != negotiation.offers
            or not negotiation.history or not negotiation.history[-1].accepted
            or negotiation.history[-1].proposal != pair
            or not any(pair.offer is o for o in offers)
            or pair.offer.snapshot != snapshot_id(ledger)):
        raise ValueError('stale snapshot or substituted accepted pair')
    certify_template(pair.offer)
    verify_artifact(pair.offer)
    return (*ledger, CorridorBLA(pair.offer, pair.price))
