"""Worker transport, artifact checks and the serial runner for the LTMS notebook.

The protocol stages (contracts, admission, offers, commitment) are defined in
notebooks/ltms_blas.ipynb. ``load_method`` compiles its tagged definition
cells verbatim, so the runner and the notebook execute one implementation.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
import os
import shutil
import subprocess

from .records import digest, snapshot_id, standing

METHOD = ('service_contracts', 'qualify', 'admit', 'generate', 'commit', 'attempt',
          'bargain', 'REQUESTS', 'PRICES', 'ROUND_BUDGET')


class NumericalWorker:
    def __init__(self, root, output, worker_python=None):
        root = Path(root).resolve()
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        worker_python = worker_python or os.environ.get('LTMS_WORKER_PYTHON')
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

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def prepare(self):
        """Compute or verify-and-reuse the base artifacts; kept for offer identities."""
        self.setup = self.call(op='prepare', output=str(self.output))
        return self.setup

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


def definition_cells(root):
    path = Path(root).resolve()/'notebooks'/'ltms_blas.ipynb'
    return [(f'{path}:cell_{index}', ''.join(cell['source']))
            for index, cell in enumerate(json.loads(path.read_text())['cells'])
            if cell['cell_type'] == 'code' and 'definitions' in cell.get('metadata', {}).get('tags', [])]


def method_digest(root):
    """Digest of the method source only; saved outputs do not change it."""
    return digest([source for _, source in definition_cells(root)])


def load_method(root):
    """Compile the notebook's tagged definition cells verbatim (no copies)."""
    namespace = {'__name__': '_ltms_method', 'ROOT': Path(root).resolve()}
    for name, source in definition_cells(root):
        exec(compile(source, name, 'exec'), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in METHOD})


def run_scenario(root, worker, method=None):
    """Serial A–E attempts with the notebook's own stages and inputs."""
    method = load_method(root) if method is None else method
    ledger, attempts = (), []
    for spec in method.REQUESTS:
        record = method.attempt(spec, ledger, worker)
        attempts.append(record)
        ledger = record['result'].ledger
    return attempts, ledger


def outcome_summary(attempts):
    """Outcome, selected departure, price, offer family and retained promises."""
    rows = []
    for a in attempts:
        agreement = a['negotiation'].agreement
        rows.append((a['request'].client, a['result'].status, tuple(o.id for o in a['offers']),
                     None if agreement is None else agreement.offer.departure,
                     None if agreement is None else agreement.price,
                     tuple((b.offer.id, b.price) for b in a['result'].ledger)))
    return rows


def attempt_record(a):
    """A JSON summary of one staged attempt; no stage is re-run."""
    admission, negotiation, result = a['admission'], a['negotiation'], a['result']
    accepted = result.agreement
    return dict(
        client=a['request'].client, status=result.status, snapshot=admission.snapshot,
        services=[dict(service=asdict(s.service), key=s.service.key, eligible=list(s.service.eligible),
                       sufficient_access=str(s.S_a), client_contract=str(s.client),
                       quotient=str(s.quotient), obligations=str(s.obligations),
                       candidates=[dict(departure=c.departure, id=c.offer_id, status=c.status,
                                        reason=c.reply.get('reason'), evidence=c.reply.get('evidence'))
                                   for c in s.candidates])
                  for s in admission.services],
        selected_service=None if admission.selected is None else admission.selected.service.key,
        offers=[dict(id=o.id, departure=o.departure, end=str(o.end), contract=str(o.contract),
                     **artifact_record(o)) for o in a['offers']],
        rounds=[dict(number=r.number, proposer=r.proposer, offer=r.proposal.offer.id,
                     price=str(r.proposal.price), accepted=r.accepted,
                     targets={k: str(v) for k, v in r.targets},
                     utilities={k: str(v) for k, v in r.utilities}) for r in negotiation.history],
        previous_preserved=a['previous_preserved'], ledger_after=snapshot_id(result.ledger),
        accepted=None if accepted is None else dict(
            id=accepted.offer.id, price=str(accepted.price),
            exact_object=accepted.offer is negotiation.agreement.offer))


def build_report(root, attempts, ledger, setup, refinement, worker):
    records = [attempt_record(a) for a in attempts]
    final = worker.call(op='final', accepted=[artifact_record(b.offer) for b in ledger], attempts=records)
    return dict(attempts=records,
                accepted=[dict(id=b.offer.id, client=b.offer.service.client, departure=b.offer.departure,
                               price=str(b.price), contract=str(b.contract), **artifact_record(b.offer))
                          for b in ledger],
                standing_contract=str(standing(ledger)), final=final, setup=setup, refinement=refinement,
                method_source=method_digest(root),
                bargaining_source=sha256((Path(root)/'notebooks'/'protocol.ipynb').read_bytes()).hexdigest(),
                claim='Illustrative numerical BLA scenario with exact nominal straight-motion clients; '
                      'no robustness certificate.')
