"""Artifact storage, the method loader and the serial runner.

The model, environment, numerical construction and protocol stages are defined
in notebooks/ltms_blas.ipynb. ``load_method`` compiles its tagged definition
cells verbatim, so the runner and the notebook execute one implementation.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json

from .records import digest, snapshot_id, standing


def file_digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write_artifact(directory, info):
    """Store one offer's exact promise and evidence; returns (path, digest)."""
    path = Path(directory)/f"offer-{info['id']}.json"
    path.write_text(json.dumps(info, sort_keys=True, indent=2, allow_nan=False))
    return str(path), file_digest(path)


def artifact_record(offer):
    return dict(artifact=offer.artifact, artifact_digest=offer.artifact_digest)


def verify_artifact(offer):
    path = Path(offer.artifact)
    if file_digest(path) != offer.artifact_digest:
        raise ValueError('offer artifact changed after generation')
    info = json.loads(path.read_text())
    if (info['id'] != offer.id or info['snapshot'] != offer.snapshot
            or info['departure'] != offer.departure or info['route'] != offer.service.route
            or digest(info['service']) != digest(asdict(offer.service))
            or info['checks'] != offer.evidence):
        raise ValueError('artifact does not describe the exact offered promise')
    if file_digest(info['base']) != info['base_digest']:
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
    return SimpleNamespace(**{k: v for k, v in namespace.items() if not k.startswith('__')})


def run_scenario(root, base, method=None):
    """Serial A–E attempts with the notebook's own stages and inputs."""
    method = load_method(root) if method is None else method
    ledger, attempts = (), []
    for spec in method.REQUESTS:
        record = method.attempt(spec, ledger, base)
        attempts.append(record)
        ledger = record['result'].ledger
    return attempts, ledger


def outcome_summary(attempts):
    """Outcome, offer family, selected departure, price and retained promises."""
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
        services=[dict(service=asdict(s.service), key=s.service.key,
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


def build_report(root, attempts, ledger, final, numerics):
    return dict(attempts=[attempt_record(a) for a in attempts],
                accepted=[dict(id=b.offer.id, client=b.offer.service.client, departure=b.offer.departure,
                               price=str(b.price), contract=str(b.contract), **artifact_record(b.offer))
                          for b in ledger],
                standing_contract=str(standing(ledger)), final=final, numerics=numerics,
                method_source=method_digest(root),
                bargaining_source=file_digest(Path(root)/'notebooks'/'protocol.ipynb'),
                claim='Illustrative numerical BLA scenario with exact nominal straight-motion clients; '
                      'no robustness certificate.')
