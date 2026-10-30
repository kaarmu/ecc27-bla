"""Immutable, dependency-light coordinator records; prices stay outside contracts.

The client's task is a structured interval_logic formula over interpreted state
atoms (road, exit, allocation), so the notebook can generate reachability
queries from it. The capability predicates F_s and promises H_kappa are atoms;
Boolean normalization cannot infer entailments between atoms under the
dynamics, so the capability is recorded as separate evidence.
"""
from dataclasses import dataclass
from fractions import Fraction as F

import interval_logic as il
import portion as P
from protocol import Contract, normalize


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
    def road(self):
        return il.Proposition(f"road_{self.route[0]}")

    @property
    def exit(self):
        return il.Proposition(f"exit_{self.route[0]}")

    @property
    def alloc(self):
        """p(z_j(t)) ∈ r_j(t): the client's position lies in its allocation."""
        return il.Proposition(f'alloc_{self.client}')

    def task_for(self, departure):
        """Phi_s, read at s from the entry state: (road ∧ alloc) U_[s,d] exit."""
        if departure not in self.departures:
            raise ValueError('departure is outside selected service')
        return il.Until(self.road & self.alloc, self.exit, P.closed(departure, self.deadline))

    @property
    def task(self):
        """T: the client crosses from one of its departures, inside its allocation."""
        return il.Or(self.task_for(s) for s in self.departures)

    def access_for(self, departure):
        """F_s, owner-only: the allocation admits a control input satisfying Phi_s."""
        if departure not in self.departures:
            raise ValueError('departure is outside selected service')
        return il.Proposition(f'F_{self.client}_{self.route}_{departure}')

    @property
    def symbols(self):
        d = self.route[0]
        return {**{self.access_for(s).name: f'F^{{{self.client}}}_{{{s}}}' for s in self.departures},
                self.road.name: rf'\mathit{{road}}_{d}', self.exit.name: rf'\mathit{{exit}}_{d}',
                self.alloc.name: f'r_{{{self.client}}}'}


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


@dataclass(frozen=True)
class Admission:
    request: CrossingRequest
    service: CrossingService
    access: il.Formula  # S_a, fixed for the whole offer family
    client_contract: Contract
    task: Contract
    quotient: Contract
    obligations: Contract
    feasible_departures: tuple[int, ...]
    commitment: Contract


@dataclass(frozen=True)
class Certificate:
    """Capability evidence for H_kappa ⊨ F_s, and compatibility inherited from admission."""
    capability: bool       # the query generated from F_s with alloc := R_kappa holds at the entry state
    window_applies: bool   # its window [s, s+lease] lies within [s, d]
    compatible: bool       # R_kappa is disjoint from every standing reservation

    @property
    def certified(self):
        return self.capability and self.window_applies


@dataclass(frozen=True)
class CorridorOffer:
    service: CrossingService
    access: il.Formula  # the selected service's fixed S_a, shared by the whole family
    departure: int
    end: F
    certificate: Certificate

    @property
    def start(self):
        return F(self.departure)

    @property
    def promise(self):
        """H_kappa: the allocation covers the entire inflated reservation."""
        return il.Proposition(f'H_{self.service.client}_{self.departure}')

    @property
    def contract(self):
        # K_kappa = <T | H_kappa and F_s>: the capability predicate is the
        # explicit consequence of the promise, decided by the generated query.
        return Contract(True, self.promise & self.service.access_for(self.departure))

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
