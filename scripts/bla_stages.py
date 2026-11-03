"""Domain-neutral protocol stages shared by Section V, Experiments A (charging) and B (intersection).

A backend supplies only the domain parts: satisfiability and admission (admit), offer
generation (generate, with the offer-type check validate_offers) and utilities (utility).
Everything else is fixed here: bargain and commit are notebooks/protocol.ipynb's own code
objects, the grid-price / linear-concession policy shell, the attempt sequence and the
round-by-round validator.
"""
from dataclasses import dataclass, field
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter
from types import FunctionType, SimpleNamespace
from typing import Callable

from protocol import Policies, PricedOffer, validate_bargaining, validate_commit
from protocol.companion import load_method_notebook

ROOT = Path(__file__).resolve().parents[1]
PARTIES = ('owner', 'client')
method = load_method_notebook(ROOT / 'notebooks' / 'protocol.ipynb')


@dataclass(frozen=True)
class Protocol:
    """Negotiation parameters: a finite price grid and a round budget."""
    grid: tuple
    round_budget: int

    @property
    def prices(self):
        return (self.grid[0], self.grid[-1])


@dataclass(frozen=True)
class Backend:
    """The domain-specific parts. admit(request, commitment, resources, now) -> admission or None."""
    admit: Callable
    generate: Callable
    utility: Callable                       # utility(spec, offers) -> (party, offer, price) -> F
    validate_offers: Callable | None = None  # None: protocol.ipynb's booking-offer check

    @property
    def bargain(self):
        """protocol.ipynb's bargain; only its offer-type check is the backend's."""
        if self.validate_offers is None:
            return method.bargain

        def validate(offers, targets, minima, prices, round_budget):
            self.validate_offers(offers)
            return validate_bargaining((), targets, minima, prices, round_budget)
        original = method.bargain
        return FunctionType(original.__code__, {**original.__globals__, 'validate_bargaining': validate},
                            original.__name__, original.__defaults__)


def same_protocol_code(backend):
    """The backend's bargain is protocol.ipynb's code object (attempt always calls method.commit)."""
    return backend.bargain.__code__ is method.bargain.__code__


@dataclass
class Checks:
    counts: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)

    def __call__(self, name, ok, detail=''):
        n, bad = self.counts.get(name, (0, 0))
        self.counts[name] = (n + 1, bad + (not ok))
        if not ok:
            self.violations.append(f'{name}: {detail}')


def grid_policies(offers, utility, spec, protocol):
    """Grid prices; propose the earliest offer meeting the target; linear concession to the minimum."""
    step = {p: (spec.targets[p] - spec.minima[p]) / (protocol.round_budget - 1) for p in PARTIES}

    def propose(party, offers, target, prices):
        # Earliest offer with a grid price meeting the target; the proposer's best such price.
        for offer in sorted(offers, key=lambda o: o.start):
            meets = [q for q in protocol.grid if prices[0] <= q <= prices[1] and utility(party, offer, q) >= target]
            if meets:
                return PricedOffer(offer, min(meets) if party == 'owner' else max(meets))
        raise ValueError('target unattainable on the price grid')

    def accept(party, proposal, target, minimum):
        return utility(party, proposal.offer, proposal.price) >= max(target, minimum)

    def concede(party, target, minimum):
        return max(minimum, target - step[party])

    return Policies(utility, propose, accept, concede)


def attempt(spec, commitment, resources, ledger, backend, protocol):
    """admit -> generate -> bargain -> commit against frozen commitments and resources."""
    times, now, request = {}, spec.received, spec.request
    t = perf_counter(); admission = backend.admit(request, commitment, resources, now); times['admit'] = perf_counter() - t
    t = perf_counter(); offers = backend.generate(admission); times['generate'] = perf_counter() - t
    if admission is None:
        return dict(admission=None, offers=(), negotiation=None, policies=None, times=times,
                    result=SimpleNamespace(status='REJECTED', commitment=commitment, ledger=ledger, agreement=None))
    policies = grid_policies(offers, backend.utility(spec, offers), spec, protocol)
    t = perf_counter()
    negotiation = backend.bargain(offers, policies, spec.targets, spec.minima, protocol.prices, protocol.round_budget)
    times['bargain'] = perf_counter() - t
    t = perf_counter(); result = method.commit(admission, offers, negotiation, commitment, ledger)
    times['commit'] = perf_counter() - t
    return dict(admission=admission, offers=offers, negotiation=negotiation, policies=policies,
                result=result, times=times)


def validators_pass(spec, record, backend, protocol):
    """Re-run the bargaining and commit validators and check every recorded round."""
    offers, negotiation = record['offers'], record['negotiation']
    utility = backend.utility(spec, offers)
    try:
        if backend.validate_offers is None:
            validate_bargaining(offers, spec.targets, spec.minima, protocol.prices, protocol.round_budget)
        else:
            backend.validate_offers(offers)
            validate_bargaining((), spec.targets, spec.minima, protocol.prices, protocol.round_budget)
        if negotiation.status == 'ACCEPTED':
            validate_commit(record['admission'], offers, negotiation, record['admission'].commitment)
    except ValueError:
        return False
    budget = protocol.round_budget
    ok, previous = len(negotiation.history) <= budget, None
    for i, r in enumerate(negotiation.history):
        targets, utilities = dict(r.targets), dict(r.utilities)
        responder = 'client' if r.proposer == 'owner' else 'owner'
        declared = {p: utility(p, r.proposal.offer, r.proposal.price) for p in PARTIES}
        ok &= (r.number == i + 1 and r.proposer == PARTIES[i % 2] and r.proposal.price in protocol.grid
               and any(o is r.proposal.offer for o in offers) and utilities == declared
               and utilities[r.proposer] >= targets[r.proposer]
               and (not r.accepted or utilities[responder] >= spec.minima[responder])
               and all(spec.minima[p] <= targets[p] for p in PARTIES))
        if previous is not None:
            # Linear concession: a fixed step per party, floored at the minimum.
            step = {p: (spec.targets[p] - spec.minima[p]) / (budget - 1) for p in PARTIES}
            ok &= all(targets[p] == max(spec.minima[p], previous[p] - step[p]) <= previous[p] for p in PARTIES)
        previous = targets
    accepted = negotiation.status == 'ACCEPTED'
    ok &= accepted == bool(negotiation.history and negotiation.history[-1].accepted)
    ok &= accepted or not offers or len(negotiation.history) == budget
    return ok
