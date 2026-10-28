"""Execute ltms_blas.ipynb in a fresh coordinator kernel, preserving worker logs."""
import argparse
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', choices=('root', 'notebooks'), default='root')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root/'notebooks'/'ltms_blas.ipynb'
    notebook = nbformat.read(path, as_version=4)
    manager = KernelManager(kernel_name='python3')
    manager.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
    client = NotebookClient(notebook, km=manager, timeout=args.timeout,
                            resources={'metadata': {'path': str(root if args.cwd == 'root' else root/'notebooks')}})
    env = None
    if args.output:
        import os
        env = {**os.environ, 'LTMS_OUTPUT': str(args.output.resolve())}
    client.execute(cleanup_kc=True, **({} if env is None else {'env': env}))
    if args.save:
        for cell in notebook.cells:
            cell.metadata.pop('execution', None)
            for output in cell.get('outputs', []):
                data = output.get('data', {})
                if 'application/vnd.plotly.v1+json' in data:
                    data.pop('text/html', None)
        nbformat.write(notebook, path)
    print(f'Executed {path.name}; saved outputs: {args.save}')


if __name__ == '__main__':
    main()
