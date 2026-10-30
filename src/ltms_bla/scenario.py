"""The notebook-method loader.

The model, environment, numerical construction and protocol stages are defined
in notebooks/ltms_blas.ipynb. ``load_method`` compiles its tagged definition
cells verbatim, so tests and the notebook execute one implementation.
"""
from pathlib import Path
from types import SimpleNamespace
import json


def definition_cells(root):
    path = Path(root).resolve()/'notebooks'/'ltms_blas.ipynb'
    return [(f'{path}:cell_{index}', ''.join(cell['source']))
            for index, cell in enumerate(json.loads(path.read_text())['cells'])
            if cell['cell_type'] == 'code' and 'definitions' in cell.get('metadata', {}).get('tags', [])]


def load_method(root):
    """Compile the notebook's tagged definition cells verbatim (no copies)."""
    namespace = {'__name__': '_ltms_method', 'ROOT': Path(root).resolve()}
    for name, source in definition_cells(root):
        exec(compile(source, name, 'exec'), namespace)
    return SimpleNamespace(**{k: v for k, v in namespace.items() if not k.startswith('__')})
