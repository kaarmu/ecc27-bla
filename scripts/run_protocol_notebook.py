"""Run the paper companion in a fresh kernel using this Python environment.

Run from the root: uv run --group notebooks python scripts/run_protocol_notebook.py --save
Use --cwd notebooks to reproduce with the other supported working directory.
"""
import argparse
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', choices=('root', 'notebooks'), default='root')
    parser.add_argument('--save', action='store_true', help='save compact verified outputs')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / 'notebooks' / 'protocol.ipynb'
    working_directory = root if args.cwd == 'root' else root / 'notebooks'
    notebook = nbformat.read(path, as_version=4)
    manager = KernelManager(kernel_name='python3')
    manager.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
    client = NotebookClient(notebook, km=manager, timeout=120,
                            resources={'metadata': {'path': str(working_directory)}})
    client.execute(cleanup_kc=True)
    if args.save:
        for cell in notebook.cells:
            cell.metadata.pop('execution', None)
            for output in cell.get('outputs', []):
                data = output.get('data', {})
                if 'application/vnd.plotly.v1+json' in data:
                    # Native interactive figures remain in the saved notebook.
                    # Runtime display still supplies an embedded HTML fallback;
                    # the final export preserves it without bloating the .ipynb.
                    data.pop('text/html', None)
        nbformat.write(notebook, path)
    print(f'Executed {path.name} from {working_directory}; outputs saved: {args.save}')


if __name__ == '__main__':
    main()
