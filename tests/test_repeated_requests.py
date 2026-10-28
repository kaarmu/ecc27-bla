"""Exercise the repeated-request notebook cells on a reduced workload, and its checks on planted faults."""
from contextlib import redirect_stdout
from dataclasses import replace
from functools import lru_cache
from importlib.util import find_spec
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import portion as P
from protocol import Booking, standing

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'notebooks' / 'repeated_requests.ipynb'
REDUCED_SEEDS = 'SEEDS = range(2)\n'


def cells():
    return [c for c in json.loads(NOTEBOOK.read_text())['cells'] if c['cell_type'] == 'code']


@lru_cache(maxsize=1)
def scenario():
    """All cells, with two seeds per load level instead of twenty."""
    scope = {'__name__': '__main__'}
    with patch('protocol.presentation.display'), redirect_stdout(StringIO()):
        for i, cell in enumerate(cells()):
            source = ''.join(cell['source'])
            if 'experiment' in cell.get('metadata', {}).get('tags', []):
                source = REDUCED_SEEDS + source
            exec(compile(source, f'{NOTEBOOK}:cell_{i}', 'exec'), scope)
    return scope


class RepeatedRequestTests(unittest.TestCase):
    def test_declared_workload_is_deterministic_and_valid(self):
        scope = scenario()
        for load in scope['LOADS']:
            day = scope['synthetic_day'](load, 0)
            self.assertEqual(day, scope['synthetic_day'](load, 0))
            self.assertEqual(len(day), load)
            self.assertEqual([s['received'] for s in day], sorted(s['received'] for s in day))
            self.assertEqual(len({s['request'].client for s in day}), load)
            for s in day:
                for alternative in s['request'].alternatives:
                    self.assertEqual(alternative.starts, s['request'].service.starts)
                    self.assertEqual(2 * alternative.duration, s['request'].service.duration)

    def test_reduced_days_and_boundary_cases_pass_every_check(self):
        scope = scenario()
        attempts = [r for rs in scope['records'].values() for r in rs] + scope['boundary']
        self.assertEqual(len(attempts), 2 * sum(scope['LOADS']) + len(scope['BOUNDARY']))
        self.assertFalse(any(r['disagreement'] for r in attempts))
        self.assertFalse(any(any(r['violations'].values()) for r in attempts))
        self.assertEqual({r['outcome'] for r in scope['boundary']}, set(scope['OUTCOMES']))

    def test_checks_detect_planted_faults(self):
        scope = scenario()
        check, OUTCOMES = scope['check_attempt'], scope['OUTCOMES']
        record = next(r for r in scope['records'][10] if r['outcome'] == OUTCOMES[0] and len(r['bookings_before']) > 2)
        before, result = record['bookings_before'], record['result']
        commitment = standing(*before)

        def violated(result, after, offers=record['offers']):
            out = check(record['spec'], record['admission'], offers, record['negotiation'],
                        result, commitment, result.ledger[:-1], before, after)
            return out['disagreement'], {k for k, v in out['violations'].items() if v}

        self.assertEqual(violated(result, record['bookings_after']), (False, set()))
        # Drop an earlier commitment.
        dropped = (*before[1:], record['negotiation'].agreement.offer.booking)
        self.assertIn('retained', violated(replace(result, commitment=standing(*dropped)), dropped)[1])
        # Commit an overlapping booking for another client.
        clash = Booking(99, record['negotiation'].agreement.offer.interval)
        crowded = (*record['bookings_after'], clash)
        self.assertIn('jointly satisfiable',
                      violated(replace(result, commitment=standing(*crowded)), crowded)[1])
        # A failed attempt that nevertheless changes the commitment.
        failed = next(r for r in scope['records'][40] if r['outcome'] == OUTCOMES[2])
        extra = standing(*failed['bookings_before'], Booking(98, P.closedopen(1000, 1010)))
        out = check(failed['spec'], failed['admission'], failed['offers'], failed['negotiation'],
                    replace(failed['result'], commitment=extra), standing(*failed['bookings_before']),
                    failed['result'].ledger, failed['bookings_before'], failed['bookings_after'])
        self.assertTrue(out['violations']['failure unchanged'])
        # An offer outside the independently feasible starts.
        stray = replace(record['offers'][0], booking=Booking(record['spec']['request'].client, P.closedopen(0, 1)))
        self.assertTrue(violated(result, record['bookings_after'], (stray, *record['offers'][1:]))[0])

    @unittest.skipUnless(find_spec('plotly'), 'Install the notebook dependency group')
    def test_figure_encodes_actual_outcome_counts(self):
        scope = scenario()
        figure = scope['figure']
        self.assertEqual([t.name for t in figure.data], list(scope['OUTCOMES']))
        self.assertEqual(figure.layout.meta['totals'], [2 * load for load in scope['LOADS']])
        for i, rs in enumerate(scope['records'].values()):
            self.assertEqual([t.meta['counts'][i] for t in figure.data],
                             [sum(r['outcome'] == o for r in rs) for o in scope['OUTCOMES']])

    @unittest.skipUnless(find_spec('plotly') and find_spec('nbformat') and find_spec('nbclient'),
                         'Install the notebook dependency group')
    def test_reduced_notebook_in_fresh_kernel_from_notebooks_directory(self):
        import nbformat
        from nbclient import NotebookClient
        from jupyter_client import KernelManager
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        experiment = next(c for c in notebook.cells if 'experiment' in c.metadata.get('tags', []))
        experiment.source = REDUCED_SEEDS + experiment.source
        manager = KernelManager(kernel_name='python3')
        manager.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
        NotebookClient(notebook, km=manager, timeout=300,
                       resources={'metadata': {'path': str(ROOT / 'notebooks')}}).execute(cleanup_kc=True)


if __name__ == '__main__':
    unittest.main()
