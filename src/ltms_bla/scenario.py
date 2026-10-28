"""Serial corridor admission, unchanged bargaining rounds and exact commitment."""
from dataclasses import asdict
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from time import perf_counter
import json
import os
import shutil
import subprocess
import sys

from protocol import affine_policies
from .bargaining import load_bargain
from .records import (CrossingService, CorridorOffer, snapshot_id, standing,
                      certify_template, commit_exact, digest)


class NumericalWorker:
    def __init__(self, root, output, worker_python=None):
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        if worker_python:
            command = [str(worker_python), '-m', 'ltms_bla.worker']
        else:
            uv = shutil.which('uv')
            if uv is None:
                raise RuntimeError('set LTMS_WORKER_PYTHON to a pyspect-enabled Python, or install uv')
            command = [uv, 'run', '--no-project', '--python', '3.13',
                       '--with', 'pyspect[hj_reachability]==1.2', '--with', 'pillow',
                       '--with', 'matplotlib>=3.10',
                       'python', '-m', 'ltms_bla.worker']
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join((str(Path(__file__).resolve().parents[1]), str(root/'src')))
        env['MPLBACKEND'] = 'Agg'  # do not inherit the coordinator kernel's inline backend
        self.log = (self.output/'worker.log').open('w')
        self.process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)

    def call(self, **message):
        self.process.stdin.write(json.dumps(message)+'\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f'numerical worker stopped; see {self.output / "worker.log"}')
        reply = json.loads(line)
        if not reply['ok']:
            raise RuntimeError(reply['error'])
        return reply['result']

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=10)
        self.process.stdout.close()
        self.log.close()


def artifact_record(offer):
    return dict(artifact=offer.artifact, artifact_digest=offer.artifact_digest)


def verify_artifact(offer):
    path = Path(offer.artifact)
    if sha256(path.read_bytes()).hexdigest() != offer.artifact_digest:
        raise ValueError('offer artifact changed after generation')
    info = json.loads(path.read_text())
    if (info['id'] != offer.id or info['snapshot'] != offer.snapshot
            or info['departure'] != offer.departure or info['route'] != offer.service.route
            or digest(info['service']) != digest(asdict(offer.service))
            or info['checks'] != offer.evidence):
        raise ValueError('artifact does not describe the exact offered promise')
    if sha256(Path(info['base']).read_bytes()).hexdigest() != info['base_digest']:
        raise ValueError('full numerical corridor changed after generation')


def run_scenario(root, output=None, worker_python=None, refine=True):
    root = Path(root).resolve()
    output = root/'artifacts'/'ltms_blas' if output is None else Path(output).resolve()
    worker = NumericalWorker(root, output, worker_python or os.environ.get('LTMS_WORKER_PYTHON'))
    started = perf_counter()
    try:
        setup = worker.call(op='prepare', output=str(output))
        refinement = worker.call(op='refine') if refine else None
        bargain = load_bargain(root)
        ledger, attempts = (), []
        requests = (
            ('A', (CrossingService('A', 'east', (0,), 8),), False),
            ('B', (CrossingService('B', 'west', (0, 1), 9),), False),
            ('C', (CrossingService('C', 'east', (0, 1), 9),), False),
            ('D', (CrossingService('D', 'west', (10, 11), 19),), True),
            ('E', (CrossingService('E', 'east', (20,), 22),
                   CrossingService('E', 'east', (20,), 28)), False),
        )
        for name, alternatives, price_failure in requests:
            previous, snapshot = ledger, snapshot_id(ledger)
            for bla in previous:
                verify_artifact(bla.offer)
            service_log, offers, selected = [], (), None
            for service in alternatives:
                client, task, quotient = service.contracts()
                candidates, replies = [], []
                for departure in service.departures:
                    offer_id = digest(dict(service=service.key, departure=departure,
                                           snapshot=snapshot, base=setup['base_digest']))[:20]
                    evaluated = perf_counter()
                    reply = worker.call(op='evaluate', service=asdict(service), departure=departure,
                                        snapshot=snapshot, id=offer_id,
                                        accepted=[artifact_record(b.offer) for b in ledger])
                    reply['warm_roundtrip_seconds'] = perf_counter()-evaluated
                    replies.append(dict(departure=departure, **reply))
                    if reply['status'] != 'QUALIFIED':
                        continue
                    info = reply['info']
                    offer = CorridorOffer(offer_id, service, departure, F(info['end']), snapshot,
                                          reply['artifact'], reply['artifact_digest'],
                                          json.dumps(info['checks'], sort_keys=True))
                    certify_template(offer)
                    candidates.append(offer)
                service_log.append(dict(service=asdict(service), key=service.key,
                                        sufficient_access=str(service.access),
                                        client_contract=str(client), quotient=str(quotient),
                                        candidates=replies))
                if candidates:
                    selected, offers = service, tuple(candidates)
                    break  # freeze ONE service/client model before bargaining
            if not offers:
                negotiation = None
                status = 'NO-COMPATIBLE-OFFER'
                rounds = []
            else:
                assert all(o.service is selected for o in offers)
                costs = {o: F(5 if i == 0 else 2) for i, o in enumerate(offers)}
                values = {o: F((1 if i == 0 else 0) if price_failure else (10 if i == 0 else 8))
                          for i, o in enumerate(offers)}
                policies = affine_policies(costs, values)
                targets = {'owner': F(4), 'client': F(1 if price_failure else 4)}
                minima = {'owner': F(2 if price_failure else 1), 'client': F(0 if price_failure else 1)}
                negotiation = bargain(offers, policies, targets, minima, (F(0), F(20)), round_budget=3)
                ledger = commit_exact(offers, negotiation, ledger, verify_artifact)
                status = 'COMMITTED' if negotiation.status == 'ACCEPTED' else 'PRICE-NO-BLA'
                rounds = [dict(number=r.number, proposer=r.proposer, offer=r.proposal.offer.id,
                               price=str(r.proposal.price), accepted=r.accepted,
                               targets={k: str(v) for k, v in r.targets},
                               utilities={k: str(v) for k, v in r.utilities}) for r in negotiation.history]
            # Retain every prior artifact/contract and the exact priced offer.
            preserved = all(ledger[i] is bla for i, bla in enumerate(previous))
            for bla in previous:
                verify_artifact(bla.offer)
            if status != 'COMMITTED':
                assert ledger is previous
            assert preserved
            attempts.append(dict(client=name, status=status, services=service_log,
                                 selected_service=None if selected is None else selected.key,
                                 offers=[dict(id=o.id, departure=o.departure, end=str(o.end),
                                              contract=str(o.contract), **artifact_record(o)) for o in offers],
                                 rounds=rounds, previous_preserved=preserved,
                                 snapshot=snapshot, ledger_after=snapshot_id(ledger),
                                 accepted=None if status != 'COMMITTED' else dict(
                                     id=ledger[-1].offer.id, price=str(ledger[-1].price),
                                     exact_object=ledger[-1].offer is negotiation.agreement.offer)))
        final = worker.call(op='final', accepted=[artifact_record(b.offer) for b in ledger], attempts=attempts)
        expected = ['COMMITTED', 'COMMITTED', 'NO-COMPATIBLE-OFFER', 'PRICE-NO-BLA', 'COMMITTED']
        assert [a['status'] for a in attempts] == expected, [a['status'] for a in attempts]
        assert len(attempts[1]['offers']) == 2
        assert attempts[-1]['services'][0]['candidates'][0]['status'] == 'PROVED_IMPOSSIBLE'
        report = dict(attempts=attempts, accepted=[dict(id=b.offer.id, client=b.offer.service.client,
                       price=str(b.price), contract=str(b.contract), **artifact_record(b.offer)) for b in ledger],
                      standing_contract=str(standing(ledger)), final=final,
                      seconds=perf_counter()-started, method_source=sha256(
                          (root/'notebooks'/'protocol.ipynb').read_bytes()).hexdigest(),
                      refinement=refinement,
                      claim='Illustrative numerical BLA scenario with exact nominal straight-motion clients; no robustness certificate.')
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
        return report
    finally:
        worker.close()
