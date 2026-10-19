"""Independent checks and concrete complete joint witnesses, not protocol orchestration."""
from itertools import product
from fractions import Fraction as F
import portion as P
import interval_logic as il
from .contracts import Contract
from ._util import FULL, region, time


def independent_feasible_starts(service, bookings, client, now=0):
    """Partition at critical boundaries; test actual booking/reservation intersections.

    Deliberately does not call pruning, normalization, the production decision
    procedure, or its forbidden-start construction. Between successive critical
    boundaries the overlap truth value is constant; endpoints are tested alone.
    """
    now = time(now)
    starts = service.starts & P.closedopen(now, P.inf)
    fixed = [(b.client, b.interval & P.closedopen(now, P.inf)) for b in bookings]
    if any(k != j and not (w & v).empty
           for k, w in fixed for j, v in fixed):
        return P.empty()
    points = {x for c in starts for x in (c.lower, c.upper)}
    points.update(x for _, w in fixed for c in w
                  for x in (c.lower - service.duration, c.upper))
    points = sorted(points)
    atoms = [P.singleton(x) for x in points]
    atoms += [P.open(a, b) for a, b in zip(points, points[1:])]
    result = P.empty()
    for atom in atoms:
        candidate = atom & starts
        if candidate.empty:
            continue
        s = candidate.lower if candidate.left == P.CLOSED else (candidate.lower + candidate.upper) / 2
        window = P.closedopen(s, s + service.duration)
        if all(k == client or (window & w).empty for k, w in fixed):
            result |= candidate
    return result


def joint_witness(bookings, use_bookings):
    """Complete piecewise-constant acc/use trace, idle outside the supplied windows."""
    def signal(records):
        windows = {}
        for b in records:
            windows[b.client] = windows.get(b.client, P.empty()) | b.interval
        return il.NaturalSignal(windows, default=0)
    return il.Trace(FULL, signals={'acc': signal(bookings), 'use': signal(use_bookings)})


def check_joint_behavior(trace, owner, client, task, now=0):
    """Evaluate four distinct obligations with interval_logic's trace semantics."""
    return dict(owner=il.satisfies(owner.guarantee, trace, now),
                client_assumption=il.satisfies(client.assumption, trace, now),
                client_guarantee=il.satisfies(client.guarantee, trace, now),
                joint_task=il.satisfies(task.guarantee, trace, now))


def check_boolean_algebra():
    """Exhaust all nine saturated contracts over a complete two-behavior universe.

    Checks the actual formula operations, not a second implementation used by
    the protocol. This finite regression is separate from the algebraic proof.
    """
    atom = il.Proposition('algebra_behavior')
    predicates = (il.Boolean(False), ~atom, atom, il.Boolean(True))
    traces = [il.Trace(P.singleton(0), propositions={
        'algebra_behavior': P.singleton(0) if value else P.empty()}) for value in (False, True)]
    universe = frozenset(range(2))
    def denote(f):
        return frozenset(i for i, trace in enumerate(traces) if il.satisfies(f, trace, 0))
    def meaning(c):
        return denote(c.assumption), denote(c.guarantee)
    def refines(x, y):
        return y[0] <= x[0] and x[1] <= y[1]
    contracts, meanings = [], []
    for a, g in product(predicates, repeat=2):
        c = Contract(a, g)
        assert meaning(c) == (denote(a), denote(g) | (universe - denote(a)))
        if universe - denote(a) <= denote(g):
            contracts.append(c)
            meanings.append(meaning(c))
    composed, quotients, meets = {}, {}, {}
    for i, x in enumerate(contracts):
        for j, y in enumerate(contracts):
            a, g = meanings[i]; b, h = meanings[j]
            composed[i, j] = meaning(x.compose(y))
            quotients[i, j] = meaning(x.quotient(y))
            meets[i, j] = meaning(x.conjoin(y))
            assert composed[i, j] == ((a & b) | (universe - (g & h)), g & h)
            assert quotients[i, j] == (a & h, (g & b) | (universe - (a & h)))
            assert meets[i, j] == (a | b, g & h)
    for i, j, k in product(range(len(contracts)), repeat=3):
        assert refines(composed[i, j], meanings[k]) == refines(meanings[i], quotients[k, j])
        assert refines(meanings[k], meets[i, j]) == (refines(meanings[k], meanings[i]) and refines(meanings[k], meanings[j]))
    return {'saturated_contracts': len(contracts), 'triples': len(contracts) ** 3, 'passed': True}
