"""Execute ltms_blas.ipynb in a fresh Python 3.13 kernel with the numerical stack.

JAX has no Python 3.14 wheel on Intel macOS, so this notebook's kernel runs
outside the >=3.14 project environment: by default through ``uv run
--no-project --python 3.13`` with the packages below, or with the interpreter
named by ``LTMS_PYTHON``. The runner itself may run in either environment.
"""
import argparse
import os
from pathlib import Path
import shutil

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager

PACKAGES = ('pyspect[hj_reachability]==1.2', 'pillow', 'matplotlib>=3.10', 'portion>=2.6.1',
            'plotly', 'nbformat', 'ipykernel')


def kernel_command():
    if os.environ.get('LTMS_PYTHON'):
        return [os.environ['LTMS_PYTHON'], '-m', 'ipykernel_launcher', '-f', '{connection_file}']
    uv = shutil.which('uv')
    if uv is None:
        raise SystemExit('install uv, or set LTMS_PYTHON to a Python 3.13 with: ' + ' '.join(PACKAGES))
    return [uv, 'run', '--no-project', '--python', '3.13',
            *(arg for package in PACKAGES for arg in ('--with', package)),
            'python', '-m', 'ipykernel_launcher', '-f', '{connection_file}']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', choices=('root', 'notebooks'), default='root')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root/'notebooks'/'ltms_blas.ipynb'
    notebook = nbformat.read(path, as_version=4)
    manager = KernelManager(kernel_name='python3')
    manager.kernel_spec.argv = kernel_command()
    client = NotebookClient(notebook, km=manager, timeout=args.timeout, startup_timeout=300,
                            resources={'metadata': {'path': str(root if args.cwd == 'root' else root/'notebooks')}})
    client.execute(cleanup_kc=True, env={**os.environ, 'MPLBACKEND': 'Agg'})
    if args.save:
        for cell in notebook.cells:
            cell.metadata.pop('execution', None)
            for output in cell.get('outputs', []):
                data = output.get('data', {})
                if 'application/vnd.plotly.v1+json' in data:
                    data.pop('text/html', None)  # keep native Plotly data, not an embedded plotly.js
        nbformat.write(notebook, path)
    print(f'Executed {path.name}; saved outputs: {args.save}')


if __name__ == '__main__':
    main()
