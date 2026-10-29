"""Immutable, dependency-light coordinator records; prices stay outside contracts.

Predicates are Boolean atoms whose meanings are fixed in the notebook's model
cells. Boolean normalization cannot infer containment between different atoms,
so geometric facts are recorded as separate evidence.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from hashlib import sha256
import json

import interval_logic as il
from protocol import Contract, normalize

SERVICE_CHECKS = ('entry_inside', 'rollout_inside', 'road_ok', 'clear_ok', 'input_ok',
                  'reference_covered', 'tlt_window_within_deadline')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def latex_atom(name):
    """The default interval_logic LaTeX rendering of a proposition name."""
    return r'\mathit{' + name.replace('_', r'\_') + '}'


@dataclass(frozen=True)
class CrossingService:
    client: str
    route: str
    departures: tuple[int, ...]
    deadline: int

    def __post_init__(self):
        if (not self.client.isalnum() or self.route not in ('east', 'west') or not self.departures
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
        # a_s, owner-only: the allocation covers this client's reference body
        # throughout its presence interval [s, s+7].
        return il.Proposition(f'a_{self.client}_{self.route}_{departure}')

    @property
    def rule(self):
        """B_j: the client's body stays in its allocation while present."""
        return il.Proposition(f'B_{self.client}')

    @property
    def task_atom(self):
        """S_u(theta): road-compliant full-body clearance by the deadline."""
        return il.Proposition(f'Su_{self.client}_{self.route}_{self.deadline}')

    @property
    def symbols(self):
        return {**{self.access_for(s).name: f'a^{{{self.client}}}_{{{s}}}' for s in self.departures},
                self.rule.name: f'B_{{{self.client}}}',
                self.task_atom.name: f'S_u^{{{self.client}}}({self.deadline})'}


@dataclass(frozen=True)
class CrossingRequest:
    client: str
    service: CrossingService
    alternatives: tuple[CrossingService, ...] = ()

    def __post_init__(self):
        if any(s.client != self.client for s in self.services):
            raise ValueError('every permitted service must belong to the requesting client')

    @property
    def services(self):
        """The original service, then permitted adaptations in order."""
        return (self.service, *self.alternatives)


@dataclass(frozen=True, eq=False)
class Candidate:
    """One finite template's qualification reply, kept with its meaning."""
    departure: int
    offer_id: str
    reply: dict

    @property
    def status(self):
        return self.reply['status']


@dataclass(frozen=True, eq=False)
class ServiceAdmission:
    service: CrossingService
    S_a: il.Formula
    B: il.Formula
    S_u: il.Formula
    client: Contract
    task: Contract
    quotient: Contract
    obligations: Contract
    candidates: tuple[Candidate, ...]

    @property
    def qualified(self):
        return tuple(c for c in self.candidates if c.status == 'QUALIFIED')


@dataclass(frozen=True, eq=False)
class Admission:
    request: CrossingRequest
    snapshot: str
    commitment: Contract
    services: tuple[ServiceAdmission, ...]

    @property
    def selected(self):
        return next((s for s in self.services if s.qualified), None)

    @property
    def failure(self):
        """Why no family exists; an empty family alone is not impossibility."""
        if self.selected is not None:
            return None
        statuses = {c.status for s in self.services for c in s.candidates}
        if statuses == {'PROVED_IMPOSSIBLE'}:
            return 'PROVED-IMPOSSIBLE'
        if 'GEOMETRIC_CONFLICT' in statuses:
            return 'NO-COMPATIBLE-OFFER'
        return 'UNRESOLVED'


@dataclass(frozen=True)
class CorridorOffer:
    id: str
    service: CrossingService
    access: il.Formula  # the selected service's fixed S_a, shared by the whole family
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
    def promise(self):
        """H_kappa: the allocation covers the entire inflated reservation."""
        return il.Proposition(f'H_{self.id}')

    @property
    def contract(self):
        # K_kappa = <T | H_kappa and a_s>: the reference predicate is the
        # explicit, geometrically checked consequence of the corridor promise.
        return Contract(True, self.promise & self.service.access_for(self.departure))

    @property
    def evidence(self):
        return json.loads(self.evidence_json)

    @property
    def symbols(self):
        return {**self.service.symbols,
                self.promise.name: f'H^{{{self.service.client}}}_{{{self.departure}}}'}


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
    """C_cmt = <T | L>, the conjunction of every retained BLA."""
    result = Contract(True, True)
    for bla in ledger:
        result = result.conjoin(bla.contract)
    return result


def ledger_symbols(ledger, *offers):
    result = {}
    for offer in (*(b.offer for b in ledger), *offers):
        result.update(offer.symbols)
    return result


def implies(left, right):
    return normalize(il.as_formula(left) & ~il.as_formula(right)) == il.Boolean(False)


def refines(first, second):
    """C1 <= C2: A2 implies A1 and G1 implies G2 (saturated guarantees)."""
    return implies(second.assumption, first.assumption) and implies(first.guarantee, second.guarantee)


def certify_service(offer):
    """Service evidence first, then the Boolean implication to the fixed S_a.

    The implication is algebraic only because K_kappa names a_s explicitly;
    its redundancy given H_kappa rests on the reference_covered evidence.
    """
    service = offer.evidence.get('service', {})
    missing = [k for k in SERVICE_CHECKS if service.get(k) is not True]
    if missing:
        raise ValueError(f'offer lacks service evidence: {", ".join(missing)}')
    if not implies(offer.contract.guarantee, offer.access):
        raise ValueError('offer does not imply the fixed sufficient-access predicate')


def certify_compatibility(offer):
    """Compatibility evidence: disjoint from every standing reservation at its snapshot."""
    compatibility = offer.evidence.get('compatibility', {})
    if compatibility.get('compatible') is not True or not all(
            c.get('disjoint') is True for c in compatibility.get('disjoint_from', ())):
        raise ValueError('offer lacks compatibility evidence')


def certify_template(offer):
    """Both kinds of evidence; neither is substituted for the other."""
    certify_service(offer)
    certify_compatibility(offer)


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
