"""Booking records and the restricted exact access decision procedure.

Unknown syntax raises UnsupportedContractError, never an optimistic SAT answer.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import portion as P
import interval_logic as il
from .contracts import Contract, normalize
from ._util import FULL, acc, use, TRUE, FALSE, rational, time, region, terms, grouped

@dataclass(frozen=True)
class Service:
    starts: P.Interval
    duration: F

    def __post_init__(self):
        duration = time(self.duration)
        if duration <= 0:
            raise ValueError('duration must be positive')
        object.__setattr__(self, 'duration', duration)
        object.__setattr__(self, 'starts', region(self.starts, bounded=True))

@dataclass(frozen=True)
class Request:
    client: int
    service: Service
    alternatives: tuple[Service, ...] = ()

    def __post_init__(self):
        if type(self.client) is not int or self.client <= 0:
            raise ValueError('a request needs a positive client id')
        alternatives = tuple(self.alternatives)
        if not isinstance(self.service, Service) or not all(
                isinstance(s, Service) for s in alternatives):
            raise TypeError('service and alternatives must be Service objects')
        object.__setattr__(self, 'alternatives', alternatives)

@dataclass(frozen=True)
class Booking:
    client: int
    interval: P.Interval

    def __post_init__(self):
        if type(self.client) is not int or self.client <= 0:
            raise ValueError('a booking needs a positive client id')
        interval = region(self.interval, bounded=True)
        if (interval.empty or not interval.atomic or interval.left != P.CLOSED
                or interval.right != P.OPEN):
            raise ValueError('a booking must be one finite nonempty half-open interval')
        object.__setattr__(self, 'interval', interval)

    @property
    def start(self):
        return self.interval.lower

    @property
    def duration(self):
        return self.interval.upper - self.interval.lower

    @property
    def contract(self):
        return Contract(True, il.Always(acc.equals(self.client), self.interval))

def standing(*bookings):
    contract = Contract(True, True)
    for booking in bookings:
        contract = contract.conjoin(booking.contract)
    return contract

class UnsupportedContractError(NotImplementedError):
    pass

def _access_id(atom):
    if not isinstance(atom, il.Equal):
        raise UnsupportedContractError('only access-to-literal assignments are supported')
    for signal, literal in ((atom.left, atom.right), (atom.right, atom.left)):
        if signal == acc and isinstance(literal, il.NaturalLiteral):
            return literal.value
    raise UnsupportedContractError('only acc = natural-literal assignments are supported')

def _flexible_view(formula):
    if not (isinstance(formula, il.Eventually)
            and isinstance(formula.parameter, il.AbsoluteParameter)
            and isinstance(formula.body, il.Always)
            and isinstance(formula.body.parameter, il.RelativeParameter)
            and not formula.body.parameter.include_endpoint
            and formula.body.parameter.duration > 0):
        raise UnsupportedContractError('expected an absolute-start, positive half-open duration request')
    return (_access_id(formula.body.body), formula.body.parameter.duration,
            formula.parameter.interval)

def _booking_shape(formula):
    """Validate before normalization; never turn unknown syntax into SAT."""
    fixed, flexible = [], None
    for term in terms(formula, il.And):
        if isinstance(term, il.Boolean):
            continue
        if isinstance(term, il.Always) and isinstance(term.parameter, il.AbsoluteParameter):
            fixed.append((_access_id(term.body), term.parameter.interval))
            continue
        alternatives = tuple(_flexible_view(alt) for alt in terms(term, il.Or))
        if flexible is not None or len({(k, d) for k, d, _ in alternatives}) != 1:
            raise UnsupportedContractError('only one flexible request is supported')
        flexible = alternatives
    return fixed, flexible

@dataclass(frozen=True)
class BookingDecision:
    satisfiable: bool
    feasible_starts: P.Interval | None
    normalized: Contract

def decide_booking(contract, now=0):
    now = time(now)
    if contract.assumption.simplify() != TRUE:
        raise UnsupportedContractError('booking decisions require an unconditional contract')
    # to_nnf flattens conjunctions without performing temporal reasoning.
    formula = il.to_nnf(contract.guarantee)
    _, flexible = _booking_shape(formula)
    result = contract.normalize(now)
    if result.guarantee == FALSE:
        return BookingDecision(False, P.empty() if flexible else None, result)
    _, remaining = _booking_shape(result.guarantee)
    if flexible is None:
        return BookingDecision(True, None, result)
    if remaining is None:
        raise UnsupportedContractError('normalization lost the duration-request witness')
    starts = P.empty()
    for _, _, window in remaining:
        starts |= window & P.closedopen(now, P.inf)
    return BookingDecision(not starts.empty, starts, result)

@dataclass(frozen=True)
class Admission:
    request: Request
    service: Service
    client_contract: Contract
    task: Contract
    quotient: Contract
    obligations: Contract
    feasible_starts: P.Interval
    commitment: Contract
    now: F


def validate_standing(commitment, now=0):
    """Require consistent, unconditional fixed access obligations."""
    now = time(now)
    _, flexible = _booking_shape(il.to_nnf(commitment.guarantee))
    if flexible is not None or not decide_booking(commitment, now).satisfiable:
        raise ValueError('standing commitments must be fixed and jointly satisfiable')
    return now


def representative_starts(starts, duration):
    """Sample each component's left-anchored duration/2 grid, using exact times.

    Keep only grid points belonging to the component, respecting open/closed
    endpoints. A short open component may contain no grid points. The bound is
    on starts; a booking may complete beyond the component's right endpoint.
    """
    duration = time(duration)
    if duration <= 0:
        raise ValueError('duration must be positive')
    step = duration / 2
    result = []
    for component in region(starts, bounded=True):
        start = component.lower
        while start <= component.upper:
            if start in component:
                result.append(start)
            start += step
    return tuple(result)


@dataclass(frozen=True)
class Certificate:
    """Booking witness evidence and compatibility, derived or independently checked.

    Generation inherits compatibility from admission's feasible-start membership;
    independent validation may instead decide compatibility for a supplied booking.
    """
    same_client: bool
    duration_matches: bool
    start_allowed: bool
    not_past: bool
    compatible: bool

    @property
    def certified(self):
        return all((self.same_client, self.duration_matches, self.start_allowed, self.not_past))


@dataclass(frozen=True)
class CertifiedOffer:
    booking: Booking
    certificate: Certificate

    @property
    def contract(self):
        return self.booking.contract

    @property
    def start(self):
        return self.booking.start

    @property
    def interval(self):
        return self.booking.interval
