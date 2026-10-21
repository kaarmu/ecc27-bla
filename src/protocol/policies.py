"""Policy data, affine example callbacks and local output validation.

No negotiation loop or commitment orchestration lives here. Callbacks must be pure.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import portion as P
import interval_logic as il
from typing import Callable
from .contracts import Contract
from .bookings import CertifiedOffer
from ._util import rational

@dataclass(frozen=True)
class PricedOffer:
    offer: CertifiedOffer
    price: F

    def __post_init__(self):
        object.__setattr__(self, 'price', rational(self.price, 'price'))

@dataclass(frozen=True)
class Policies:
    utility: Callable
    propose: Callable
    accept: Callable
    concede: Callable

@dataclass(frozen=True)
class BargainRound:
    number: int
    proposer: str
    targets: tuple
    proposal: PricedOffer
    utilities: tuple
    accepted: bool

@dataclass(frozen=True)
class BargainingResult:
    status: str
    agreement: PricedOffer | None
    history: tuple[BargainRound, ...]
    offers: tuple[CertifiedOffer, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'offers', tuple(self.offers))

def affine_policies(costs, values):
    costs = {o: rational(c, 'cost') for o, c in costs.items()}
    values = {o: rational(v, 'value') for o, v in values.items()}

    def utility(party, offer, price):
        return price - costs[offer] if party == 'owner' else values[offer] - price

    def propose(party, offers, target, prices):
        for offer in sorted(offers, key=lambda o: o.start):
            price = (max(prices[0], costs[offer] + target) if party == 'owner'
                     else min(prices[1], values[offer] - target))
            if prices[0] <= price <= prices[1]:
                return PricedOffer(offer, price)
        raise ValueError('initial/current target is unattainable under the affine policy')

    def accept(party, proposal, target, minimum):
        return utility(party, proposal.offer, proposal.price) >= max(target, minimum)

    return Policies(utility, propose, accept,
                    lambda party, target, minimum: (target + minimum) / 2)

@dataclass(frozen=True)
class BLA:
    contract: Contract
    price: F

    def __post_init__(self):
        object.__setattr__(self, 'price', rational(self.price, 'price'))

@dataclass(frozen=True)
class CommitResult:
    status: str
    commitment: Contract
    ledger: tuple[BLA, ...]
    agreement: BLA | None


def validate_bargaining(offers, targets, minima, prices, round_budget):
    """Validate immutable offers and numeric policy inputs, without running rounds."""
    if type(round_budget) is not int or round_budget <= 0:
        raise ValueError('round_budget must be a positive integer')
    if any(not isinstance(o, CertifiedOffer) or not o.certificate.certified
           or not o.certificate.compatible for o in offers):
        raise ValueError('bargaining accepts only certified compatible offers')
    parties = ('owner', 'client')
    if set(targets) != set(parties) or set(minima) != set(parties):
        raise ValueError('targets and minima must contain owner and client')
    targets = {p: rational(targets[p], 'target') for p in parties}
    minima = {p: rational(minima[p], 'minimum') for p in parties}
    prices = tuple(rational(q, 'price bound') for q in prices)
    if len(prices) != 2 or prices[0] > prices[1]:
        raise ValueError('prices must be ordered finite lower and upper bounds')
    if any(targets[p] < minima[p] for p in parties):
        raise ValueError('targets cannot be below minima')
    return targets, minima, prices


def checked_proposal(policies, party, offers, target, prices):
    """Validate one callback output and its proposer's utility target."""
    proposal = policies.propose(party, offers, target, prices)
    if (not isinstance(proposal, PricedOffer) or proposal.offer not in offers
            or not prices[0] <= proposal.price <= prices[1]):
        raise ValueError('proposal must select one fixed offer and an allowed price')
    if rational(policies.utility(party, proposal.offer, proposal.price), 'utility') < target:
        raise ValueError('proposal does not attain the proposer target')
    return proposal


def checked_acceptance(policies, responder, proposal, target, minimum):
    """Validate the response, including the responder's minimum on acceptance."""
    accepted = policies.accept(responder, proposal, target, minimum)
    if type(accepted) is not bool:
        raise ValueError('acceptance policy must return bool')
    utility = rational(policies.utility(responder, proposal.offer, proposal.price), 'utility')
    if accepted and utility < minimum:
        raise ValueError('acceptance policy accepted below the responder minimum')
    return accepted


def checked_concession(policies, party, target, minimum):
    """Validate one new target, bounded by minimum and previous target."""
    updated = rational(policies.concede(party, target, minimum), 'target')
    if not minimum <= updated <= target:
        raise ValueError('concessions must stay between minimum and previous target')
    return updated


def validate_commit(admission, offers, negotiation, commitment):
    """Check frozen snapshots and the exact accepted pair; no regeneration or SAT."""
    if admission is None or commitment != admission.commitment:
        raise ValueError('commit requires the unchanged admitted commitment snapshot')
    if tuple(offers) != negotiation.offers:
        raise ValueError('offers differ from the frozen negotiation snapshot')
    pair = negotiation.agreement
    if (negotiation.status != 'ACCEPTED' or not isinstance(pair, PricedOffer)
            or pair.offer not in offers or not negotiation.history
            or not negotiation.history[-1].accepted
            or negotiation.history[-1].proposal != pair):
        raise ValueError('commit requires the exact mutually accepted priced offer')


def policy_utilities(policies, proposal):
    """Evaluate both utilities and reject nonnumeric or nonfinite outputs."""
    return tuple((party, rational(policies.utility(party, proposal.offer, proposal.price), 'utility'))
                 for party in ('owner', 'client'))
