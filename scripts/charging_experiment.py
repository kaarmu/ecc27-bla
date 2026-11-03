"""Section V, Experiment A: one charging socket, eight sequential requests.

Run from the root: uv run --locked --group experiment python scripts/charging_experiment.py
Writes artifacts/charging_experiment/{log.json,table.csv,figure.pdf,environment.json}.

Time is exact integer minutes since midnight (Fraction); the horizon is 06:00-12:00.
admit, generate, bargain and commit are loaded verbatim from notebooks/protocol.ipynb.
New here: grid/linear-concession policies, a refinement decision for the
reservation fragment, the scenario, the checks and the outputs.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
import csv
import json
import platform
import sys

import portion as P
import interval_logic as il
from protocol import (Booking, Request, Service, decide_booking, independent_feasible_starts, joint_witness, check_joint_behavior,
                      standing)
from protocol.bookings import _access_id, _flexible_view, UnsupportedContractError
from protocol.contracts import normalize, _cnf, _dual
from protocol.companion import clock, clock_interval
from bla_stages import Backend, Checks, Protocol, attempt, method, same_protocol_code, validators_pass

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'charging_experiment'
HORIZON = (360, 720)
GRID = tuple(F(q) for q in range(0, 21))        # €0, €1, ..., €20
PRICES = (GRID[0], GRID[-1])
ROUND_BUDGET = 4
PROTOCOL = Protocol(GRID, ROUND_BUDGET)
OWNER = dict(target=F(10), minimum=F(4))        # u_o = q
SEED = 0                                         # no draws: the sequence is designed by hand


# ---------------------------------------------------------------- scenario
@dataclass(frozen=True)
class Spec:
    branch: str
    received: F
    request: Request
    v: F                                          # u_c = v - q - alpha * max(0, s - s_pref)
    alpha: F
    s_pref: F
    client_target: F
    client_minimum: F = F(1)

    @property
    def targets(self):
        return {'owner': OWNER['target'], 'client': self.client_target}

    @property
    def minima(self):
        return {'owner': OWNER['minimum'], 'client': self.client_minimum}


def theta(k, a, b, d, *alternatives):
    return Request(k, Service(P.closed(a, b), d), tuple(Service(P.closed(x, y), e) for x, y, e in alternatives))


SCENARIO = (
    Spec('as requested, accepted', F(300), theta(1, 390, 450, 60), F(16), F('0.05'), F(390), F(4)),
    Spec('several starts, multi-round', F(305), theta(2, 420, 510, 60), F(12), F('0.05'), F(450), F(5)),
    Spec('empty residual, adapted', F(310), theta(3, 420, 480, 60, (420, 480, 30), (420, 570, 60)),
         F(15), F('0.01'), F(420), F(4)),
    Spec('NO-BLA, budget exhausted', F(315), theta(4, 570, 660, 50), F('4.5'), F(0), F(570), F(2)),
    Spec('rejected, no adaptation', F(320), theta(5, 360, 420, 40), F(10), F(0), F(360), F(2)),
    Spec('several starts, multi-round', F(325), theta(6, 570, 630, 90), F(12), F('0.1'), F(600), F(7)),
    Spec('empty residual, adapted', F(330), theta(7, 360, 420, 60, (360, 420, 30)), F(10), F(0), F(360), F(2)),
    Spec('as requested, accepted', F(335), theta(8, 630, 690, 30), F(16), F('0.05'), F(660), F(3)),
)


def validate_scenario():
    for s in SCENARIO:
        J, d = s.request.service.starts, s.request.service.duration
        assert 30 <= d <= 90 and 60 <= J.upper - J.lower <= 120, s
        for service in (s.request.service, *s.request.alternatives):
            assert HORIZON[0] <= service.starts.lower and service.starts.upper + service.duration <= HORIZON[1], s
            assert s.received < service.starts.lower and (service.duration / 2).denominator == 1, s


# ---------------------------------------------------------------- domain backend (charging)
def charging_utility(spec, offers):
    """u_o = q; u_c = v - q - alpha * max(0, s - s_pref)."""
    def utility(party, offer, price):
        return price if party == 'owner' else spec.v - price - spec.alpha * max(F(0), offer.start - spec.s_pref)
    return utility


BACKEND = Backend(admit=lambda request, commitment, _resources, now: method.admit(request, commitment, now),
                  generate=method.generate, utility=charging_utility)


# ---------------------------------------------------------------- refinement in the reservation fragment
def _fixed(literal):
    """(j, W) for an absolute-window access literal □_W (acc = j), else None."""
    if isinstance(literal, il.Always) and isinstance(literal.parameter, il.AbsoluteParameter):
        try:
            return _access_id(literal.body), literal.parameter.interval
        except UnsupportedContractError:
            return None
    return None


def _holds(literal, cover, now):
    """Does the literal hold in every behavior realizing the access coverage?"""
    future = P.closedopen(now, P.inf)
    if (fixed := _fixed(literal)) is not None:
        j, W = fixed
        return ((W & future) - cover.get(j, P.empty())).empty
    try:
        j, d, J = _flexible_view(literal)
    except UnsupportedContractError:
        return False
    # Some start s in J with [s, s+d) inside one covered component.
    return any(not (P.Interval.from_atomic(c.left, c.lower, c.upper - d, P.CLOSED) & J & future).empty
               for c in cover.get(j, P.empty()) if c.upper - c.lower >= d)


def _refuted(clauses, now):
    """Unit propagation over fixed access facts; True only if the clauses are unsatisfiable."""
    clauses, cover = set(clauses), {}
    while True:
        if any(not (cover[i] & cover[j]).empty for i in cover for j in cover if i < j):
            return True
        units = {next(iter(c)) for c in clauses if len(c) == 1}
        progress = False
        for clause in list(clauses):
            live = frozenset(l for l in clause if not (_holds(_dual(l), cover, now) or _dual(l) in units))
            if any(_holds(l, cover, now) for l in live):
                clauses.discard(clause)
                progress = True
            elif not live:
                return True
            elif len(live) == 1 and (fixed := _fixed(next(iter(live)))) is not None:
                cover[fixed[0]] = cover.get(fixed[0], P.empty()) | fixed[1]
                clauses.discard(clause)
                progress = True
            elif live != clause:
                clauses.discard(clause)
                clauses.add(live)
                progress = True
        if not progress:
            return False


def entails(premise, conclusion, now):
    """Sound, incomplete: premise ∧ ¬c is refuted for every CNF clause c of the conclusion."""
    premise = _cnf(normalize(premise, now))
    return all(_refuted(premise | {frozenset({_dual(l)}) for l in clause}, now)
               for clause in _cnf(normalize(conclusion, now)))


def refines(lower, upper, now):
    """lower ⪯ upper: upper's assumption implies lower's, lower's guarantee implies upper's."""
    return entails(upper.assumption, lower.assumption, now) and entails(lower.guarantee, upper.guarantee, now)


# ---------------------------------------------------------------- attempt and checks
def overlaps(x, y):
    return x.lower < y.upper and y.lower < x.upper


def check_attempt(check, spec, record, commitment, bookings, ledger, after):
    request, now = spec.request, spec.received
    admission, offers, negotiation, result = (record[k] for k in ('admission', 'offers', 'negotiation', 'result'))
    others = [b for b in bookings if b.client != request.client]
    label = f'request {request.client}'

    # Admission agrees with J \ ∪ (W_j ⊕ (-d, 0]) computed by direct overlap tests.
    expected = next(((s, r) for s in (request.service, *request.alternatives)
                     if not (r := independent_feasible_starts(s, bookings, request.client, now)).empty), None)
    check('admission = interval arithmetic',
          (admission is None and expected is None) or (admission is not None and expected is not None
           and (admission.service, admission.feasible_starts) == expected), label)

    # 1. Committed windows pairwise disjoint.
    check('1 disjoint windows', not any(overlaps(x.interval, y.interval)
                                        for i, x in enumerate(after) for y in after[i + 1:]), label)

    if admission is not None:
        J, d = admission.service.starts, admission.service.duration
        S_a, S_u, R, C_req, C_trg = method.service_contracts(request.client, admission.service)
        C_plus = admission.obligations
        check('quotient guarantee = S_a', admission.quotient.guarantee == normalize(S_a, now), label)
        for o in offers:
            # 3. Certified and compatible: interval arithmetic vs contract algebra.
            cert_iv = o.start in J and o.start >= now and o.booking.duration == d and o.booking.client == request.client
            comp_iv = not any(overlaps(o.interval, b.interval) for b in others)
            cert_ca = refines(commitment.conjoin(o.contract), C_plus, now)
            comp_ca = decide_booking(commitment.conjoin(o.contract), now).satisfiable
            check('3 offer certified', cert_iv and cert_ca and o.certificate.certified, f'{label} s={o.start}')
            check('3 offer compatible', comp_iv and comp_ca and o.certificate.compatible, f'{label} s={o.start}')
            check('3 interval/algebra agreement', (cert_iv, comp_iv) == (cert_ca, comp_ca), f'{label} s={o.start}')

    if result.agreement is not None:
        pair = negotiation.agreement
        K, s = pair.offer.contract, pair.offer.start
        # 2. Start in J ∩ residual and K_s ⪯ Q.
        check('2 start in J ∩ residual', s in J and s in admission.feasible_starts, label)
        check('2 K refines Q', refines(K, admission.quotient, now), label)
        # 4. C_req ∥ (C_cmt ∧ K*) ⪯ C_cmt ∧ C_trg, symbolically; plus a complete-trace witness.
        check('4 composition refines target', refines(C_req.compose(commitment.conjoin(K)),
                                                      commitment.conjoin(C_trg), now), label)
        trace = joint_witness(after, (pair.offer.booking,))
        joint = check_joint_behavior(trace, result.commitment, C_req, commitment.conjoin(C_trg), now)
        check('4 trace witness', all(joint.values()), f'{label} {joint}')
        # 5. Consistency of C_cmt ∧ K*.
        check('5 consistent', decide_booking(result.commitment, now).satisfiable, label)
        # Commitment is the exact priced offer, never recomputed.
        check('commit = priced offer', result.commitment == commitment.conjoin(K) and result.agreement.contract == K
              and result.agreement.price == pair.price and any(o is pair.offer for o in offers), label)
    else:
        # 6. NO-BLA and rejection leave C_cmt unchanged.
        check('6 unchanged on failure', result.commitment is commitment and result.ledger == ledger
              and after == bookings, label)

    # 7. Bargaining and commit validators, re-run on the recorded outputs.
    if negotiation is not None:
        check('7 validators', validators_pass(spec, record, BACKEND, PROTOCOL), label)


def negative_controls():
    """The symbolic checks must reject bad offers, so they are not vacuous."""
    bookings = (Booking(1, P.closedopen(390, 450)),)
    commitment, now = standing(*bookings), F(300)
    admission = method.admit(Request(2, Service(P.closed(420, 510), 60)), commitment, now)
    C_plus = admission.obligations

    def verdict(start, duration):
        K = Booking(2, P.closedopen(start, start + duration)).contract
        return (refines(commitment.conjoin(K), C_plus, now),
                decide_booking(commitment.conjoin(K), now).satisfiable, refines(K, admission.quotient, now))

    cases = {'valid start 450': ((450, 60), (True, True, True)),
             'start outside J (540)': ((540, 60), (False, True, False)),
             'too short (450, 30 min)': ((450, 30), (False, True, False)),
             # Certification is vacuous for an inconsistent C_cmt ∧ K; compatibility catches it.
             'overlaps W_1 (420)': ((420, 60), (True, False, True))}
    return {name: dict(expected=list(e), got=list(v := verdict(*args)), ok=v == e)
            for name, (args, e) in cases.items()}


# ---------------------------------------------------------------- outputs
def minutes(interval):
    return ' ∪ '.join(('[' if c.left == P.CLOSED else '(') + f'{c.lower},{c.upper}'
                      + (']' if c.right == P.CLOSED else ')') for c in interval) or '∅'


def service_json(s):
    return dict(J=minutes(s.starts), J_clock=clock_interval(s.starts), d=int(s.duration))


def log_entry(spec, record, bookings, checks_seconds):
    request, admission, negotiation = spec.request, record['admission'], record['negotiation']
    tried = []
    for s in (request.service, *request.alternatives):
        r = independent_feasible_starts(s, bookings, request.client, spec.received)
        tried.append(dict(**service_json(s), residual=minutes(r)))
        if not r.empty:
            break
    if admission is None:
        status = 'rejected'
    elif admission.service == request.service:
        status = 'as requested'
    else:
        status = f'adapted ({request.alternatives.index(admission.service) + 1})'
    offers = record['offers']
    agreement = None if negotiation is None else negotiation.agreement
    outcome = ('REJECTED' if admission is None else 'NO-BLA (no sampled offer)' if not offers
               else 'NO-BLA' if agreement is None else 'ACCEPTED')
    return dict(
        request=request.client, branch=spec.branch, received=clock(spec.received),
        theta=service_json(request.service), adaptations=[service_json(s) for s in request.alternatives],
        policy=dict(v=str(spec.v), alpha=str(spec.alpha), s_pref=clock(spec.s_pref),
                    targets={p: str(x) for p, x in spec.targets.items()},
                    minima={p: str(x) for p, x in spec.minima.items()}),
        standing=[dict(client=b.client, W=minutes(b.interval)) for b in sorted(bookings, key=lambda b: b.start)],
        admission=status, tried=tried,
        residual=None if admission is None else minutes(admission.feasible_starts),
        offers=dict(generated=len(offers), certified=sum(o.certificate.certified for o in offers),
                    compatible=sum(o.certificate.compatible for o in offers),
                    starts=[clock(o.start) for o in offers]),
        rounds=[] if negotiation is None else [
            dict(round=r.number, proposer=r.proposer, offer=minutes(r.proposal.offer.interval),
                 price=str(r.proposal.price), targets={p: str(x) for p, x in r.targets},
                 utilities={p: str(x) for p, x in r.utilities},
                 response='accept' if r.accepted else 'reject') for r in negotiation.history],
        outcome=outcome,
        s_star=None if agreement is None else clock(agreement.offer.start),
        q_star=None if agreement is None else str(agreement.price),
        seconds={**{k: v for k, v in record['times'].items()}, 'total': sum(record['times'].values()),
                 'checks': checks_seconds})


def write_table(entries, path):
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['request', 'J', 'd_min', 'admission', 'residual', 'offers_gen', 'offers_cert',
                    'offers_compat', 'rounds', 'outcome', 's_star', 'q_star_eur', 'time_ms'])
        for e in entries:
            w.writerow([e['request'], e['theta']['J_clock'], e['theta']['d'], e['admission'], e['residual'] or '∅',
                        e['offers']['generated'], e['offers']['certified'], e['offers']['compatible'],
                        len(e['rounds']), e['outcome'], e['s_star'] or '', e['q_star'] or '',
                        f"{1000 * e['seconds']['total']:.1f}"])


def plot(specs, records, standing_before, path):
    import matplotlib
    matplotlib.use('pdf')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    plt.rcParams.update({'font.size': 7, 'font.family': 'serif', 'font.serif': ['STIXGeneral'],
                         'mathtext.fontset': 'stix', 'pdf.fonttype': 42, 'axes.linewidth': .5,
                         'xtick.major.width': .5, 'ytick.major.width': .5})
    blue, gray, ink = (30 / 255, 100 / 255, 180 / 255), '#BDBDBD', '#222222'
    n = len(specs)
    fig, ax = plt.subplots(figsize=(8.5 / 2.54, 6.2 / 2.54))
    for i, (spec, record, before) in enumerate(zip(specs, records, standing_before)):
        y = n - 1 - i
        for b in before:
            ax.broken_barh([(float(b.start), float(b.duration))], (y - .34, .3), fc=gray, ec='white', lw=.6)
        # Request window J as a bracket; an admitted adaptation's window dashed.
        def bracket(J, yy, dashed=False):
            ls = (0, (2, 1.2)) if dashed else '-'
            ax.plot([J.lower, J.lower, J.upper, J.upper], [yy - .07, yy, yy, yy - .07],
                    color=ink, lw=.6, ls=ls, solid_capstyle='butt')
        bracket(spec.request.service.starts, y + .34)
        admission = record['admission']
        if admission is not None and admission.service != spec.request.service:
            bracket(admission.service.starts, y + .2, dashed=True)
        if admission is not None:
            for c in admission.feasible_starts:
                lo, hi = float(c.lower), float(c.upper)
                if lo == hi:
                    ax.plot([lo], [y + .05], marker='o', ms=2.2, color=blue, mec=blue, lw=0, clip_on=False)
                else:
                    ax.plot([lo, hi], [y + .05, y + .05], color=blue, lw=1.4, solid_capstyle='round')
        agreement = record['result'].agreement and record['negotiation'].agreement
        if agreement:
            b = agreement.offer.booking
            ax.broken_barh([(float(b.start), float(b.duration))], (y - .34, .3), fc=blue, ec='white', lw=.6)
            text = f'€{agreement.price}'
        else:
            text = 'rejected' if admission is None else 'NO-BLA'
        ax.text(HORIZON[1] + 4, y - .19, text, va='center', ha='left', color=ink)
    ax.set_xlim(HORIZON[0] - 6, HORIZON[1] + 2)
    ax.set_ylim(-.6, n - .4)
    ticks = range(HORIZON[0], HORIZON[1] + 1, 60)
    ax.set_xticks(list(ticks), [clock(t) for t in ticks])
    ax.set_yticks([y - .05 for y in range(n)], [str(spec.request.client) for spec in reversed(specs)])
    ax.set_ylabel('Request (arrival order)')
    ax.tick_params(length=2, pad=1.5)
    ax.grid(axis='x', color='#E6E6E6', lw=.4)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    handles = [Patch(color=gray, label='committed'), Line2D([], [], color=ink, lw=.6, label='window $J$'),
               Line2D([], [], color=ink, lw=.6, ls=(0, (2, 1.2)), label=r"adapted $J'$"),
               Line2D([], [], color=blue, lw=1.4, label='residual starts'), Patch(color=blue, label='accepted')]
    fig.legend(handles=handles, loc='upper center', ncol=3, frameon=False, handlelength=1.3,
               columnspacing=.9, handletextpad=.4, bbox_to_anchor=(.5, 1.01))
    fig.subplots_adjust(left=.1, right=.86, top=.86, bottom=.08)
    fig.savefig(path)
    plt.close(fig)


def environment():
    cpu = next((l.split(':', 1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines()
                if l.startswith('model name')), platform.processor()) if Path('/proc/cpuinfo').exists() \
        else platform.processor()
    return dict(python=sys.version, platform=platform.platform(), machine=platform.machine(), cpu=cpu,
                packages={p: version(p) for p in ('interval-logic', 'portion', 'matplotlib')},
                timing='time.perf_counter, single run, one process; stage times exclude checks')


# ---------------------------------------------------------------- run
def main():
    validate_scenario()
    assert same_protocol_code(BACKEND)
    OUT.mkdir(parents=True, exist_ok=True)
    check, commitment, bookings, ledger = Checks(), standing(), (), ()
    entries, records, standing_before = [], [], []
    for spec in SCENARIO:
        record = attempt(spec, commitment, bookings, ledger, BACKEND, PROTOCOL)
        result = record['result']
        after = bookings if result.agreement is None else (*bookings, record['negotiation'].agreement.offer.booking)
        t = perf_counter()
        check_attempt(check, spec, record, commitment, bookings, ledger, after)
        entries.append(log_entry(spec, record, bookings, perf_counter() - t))
        records.append(record)
        standing_before.append(bookings)
        if check.violations:
            break                                 # stop at the first violating attempt
        commitment, bookings, ledger = result.commitment, after, result.ledger

    controls = negative_controls()
    branches = {
        '1 as requested, accepted': any(e['admission'] == 'as requested' and e['outcome'] == 'ACCEPTED' for e in entries),
        '2 empty residual, adapted, accepted': any(e['admission'].startswith('adapted') and e['outcome'] == 'ACCEPTED'
                                                   and P.empty() == independent_feasible_starts(
                                                       s.request.service, b, s.request.client, s.received)
                                                   for e, s, b in zip(entries, SCENARIO, standing_before)),
        '3 several certified starts, >1 round': any(e['offers']['certified'] > 1 and len(e['rounds']) > 1
                                                    and e['outcome'] == 'ACCEPTED' for e in entries),
        '4 NO-BLA, budget exhausted': any(e['outcome'] == 'NO-BLA' and len(e['rounds']) == ROUND_BUDGET for e in entries),
        '5 rejected, no adaptation': any(e['outcome'] == 'REJECTED' and not e['adaptations'] for e in entries),
    }
    summary = dict(seed=SEED, round_budget=ROUND_BUDGET, price_grid=f'€{GRID[0]}..€{GRID[-1]} step €1',
                   owner=dict(target=str(OWNER['target']), minimum=str(OWNER['minimum'])),
                   checks={k: dict(evaluated=n, violations=bad) for k, (n, bad) in check.counts.items()},
                   violations=check.violations, branches=branches, negative_controls=controls,
                   final_schedule=[dict(client=b.client, W=clock_interval(b.interval))
                                   for b in sorted(bookings, key=lambda b: b.start)])
    (OUT / 'log.json').write_text(json.dumps(dict(summary=summary, requests=entries), indent=1, ensure_ascii=False))
    (OUT / 'environment.json').write_text(json.dumps(environment(), indent=1))
    write_table(entries, OUT / 'table.csv')
    plot(SCENARIO[:len(records)], records, standing_before, OUT / 'figure.pdf')

    for name, c in summary['checks'].items():
        print(f'{name:32s} {c["evaluated"]:3d} evaluated, {c["violations"]} violations')
    print('branches:', {k: v for k, v in branches.items()})
    print('negative controls ok:', all(c['ok'] for c in controls.values()))
    print(f'wrote {OUT.relative_to(ROOT)}/{{log.json,table.csv,figure.pdf,environment.json}}')
    if check.violations or not all(branches.values()) or not all(c['ok'] for c in controls.values()):
        sys.exit('FAILED: ' + '; '.join(check.violations or ['branch coverage or negative controls']))


if __name__ == '__main__':
    main()
