"""Exercise the actual example cells and their unchanged method-notebook source."""
import ast
from contextlib import redirect_stdout
from fractions import Fraction as F
from importlib.util import find_spec
from functools import lru_cache
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import portion as P
from protocol.companion import load_method_notebook

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'notebooks' / 'charging_morning.ipynb'
METHOD = ROOT / 'notebooks' / 'protocol.ipynb'


@lru_cache(maxsize=1)
def scenario():
    notebook = json.loads(NOTEBOOK.read_text())
    scope = {'__name__': '__main__'}
    with patch('protocol.presentation.display'), redirect_stdout(StringIO()):
        for i, cell in enumerate(notebook['cells']):
            if cell['cell_type'] == 'code' and 'export' not in cell.get('metadata', {}).get('tags', []):
                exec(compile(''.join(cell['source']), f'{NOTEBOOK}:cell_{i}', 'exec'), scope)
    return scope


class MorningScenarioTests(unittest.TestCase):
    def test_loader_compiles_actual_method_cells_without_running_example(self):
        methods = load_method_notebook(METHOD)
        source = json.loads(METHOD.read_text())
        for name in ('service_contracts', 'admit', 'generate', 'bargain', 'commit'):
            index, cell = next((i, c) for i, c in enumerate(source['cells'])
                               if c['cell_type'] == 'code' and any(
                                   isinstance(n, ast.FunctionDef) and n.name == name
                                   for n in ast.parse(''.join(c['source'])).body))
            function = getattr(methods, name)
            self.assertEqual(function.__code__.co_filename, f'{METHOD}:cell_{index}')
            self.assertNotIn('booking_figure', function.__globals__)
            self.assertNotIn('request', function.__globals__)

    @unittest.skipUnless(find_spec('plotly'), 'Install the notebook dependency group')
    def test_full_service_adaptation_and_economic_failure(self):
        scope = scenario()
        c, d, e = scope['attempts']
        self.assertEqual(tuple(o.start for o in c['offers']), (F(540), F(570)))
        self.assertEqual(c['negotiation'].agreement.offer.interval, P.closedopen(540, 600))
        self.assertTrue(d['original_starts'].empty)
        self.assertEqual(d['admission'].service.duration, 30)
        self.assertEqual(tuple(o.interval for o in d['offers']), (P.closedopen(600, 630),))
        self.assertEqual(e['result'].status, 'NO-BLA')
        self.assertEqual(tuple(o.start for o in e['offers']), (F(690), F(720)))
        self.assertEqual([r.proposal.price for r in e['negotiation'].history], [F(8), F(6), F(8)])
        self.assertTrue(all(not r.accepted for r in e['negotiation'].history))
        self.assertEqual(e['bookings_before'], e['bookings_after'])
        self.assertEqual(e['result'].ledger, d['result'].ledger)
        self.assertEqual(len(scope['ledger']), 2)
        for attempt in scope['attempts']:
            self.assertTrue(attempt['previous_unchanged'])
            self.assertTrue(attempt['jointly_satisfiable'])

    @unittest.skipUnless(find_spec('plotly'), 'Install the notebook dependency group')
    def test_four_row_figure_encodes_actual_results_and_styles(self):
        figure = scenario()['figure']
        self.assertEqual(figure.layout.meta['rows'], 4)
        traces = lambda kind: [t for t in figure.data if t.meta.get('kind') == kind]
        final = [(t.meta['client'], t.meta['interval']) for t in traces('commitment') if t.meta['row']==3]
        self.assertCountEqual(final, [(1, '[08:00,09:00)'), (3, '[09:00,10:00)'),
                                     (4, '[10:00,10:30)'), (2, '[10:30,11:30)')])
        self.assertEqual([sum(t.meta['row']==row for t in traces('candidate')) for row in (1,2,3)], [2,1,2])
        self.assertEqual([(t.meta['row'], t.meta['interval']) for t in traces('selected')],
                         [(1, '[09:00,10:00)'), (2, '[10:00,10:30)')])
        self.assertTrue(all(t.marker.symbol == 'star' for t in traces('selected')))
        self.assertTrue(all(t.fillcolor != 'rgba(255,255,255,0)' for t in traces('commitment')))
        self.assertTrue(all(t.fillcolor == 'rgba(255,255,255,0)' for t in traces('candidate')))
        self.assertEqual([(t.meta['row'], t.meta['interval']) for t in traces('rejected_request')],
                         [(2, '[10:00,11:00)')])
        self.assertEqual(traces('unreserved')[0].meta['interval'], '[11:30,13:00)')

    @unittest.skipUnless(find_spec('plotly') and find_spec('nbformat') and find_spec('nbclient'),
                         'Install the notebook dependency group')
    def test_all_cells_in_fresh_kernels_from_both_working_directories(self):
        import nbformat
        from nbclient import NotebookClient
        from jupyter_client import KernelManager
        for directory in (ROOT, ROOT / 'notebooks'):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as temporary:
                notebook = nbformat.read(NOTEBOOK, as_version=4)
                export = next(c for c in notebook.cells if 'export' in c.metadata.get('tags', []))
                destination = Path(temporary) / 'morning.html'
                export.source = f"export_timelines(Path({str(destination)!r}), figure)"
                manager = KernelManager(kernel_name='python3')
                manager.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
                client = NotebookClient(notebook, km=manager, timeout=120,
                                        resources={'metadata': {'path': str(directory)}})
                client.execute(cleanup_kc=True)
                self.assertTrue(destination.is_file())
                self.assertIn('protocol-figure-0', destination.read_text())


if __name__ == '__main__':
    unittest.main()
