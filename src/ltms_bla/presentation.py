"""Markdown tables with display symbols, without importing JAX."""
from protocol import fmt
from .records import latex_atom

try:
    from IPython.display import Markdown, display
except ImportError:
    Markdown, display = str, print


def latex(value, symbols=None):
    """protocol.fmt, with proposition names replaced by display symbols."""
    if getattr(value, 'shape', None) == ():  # NumPy scalar
        value = value.item()
    if isinstance(value, (tuple, list)):
        return '(' + ', '.join(latex(v, symbols) for v in value) + ')'
    if isinstance(value, float):
        return f'{value:.4g}'
    text = fmt(value)
    for name, symbol in (symbols or {}).items():
        text = text.replace(latex_atom(name), symbol)
    return text


def table(headers, rows, symbols=None):
    def line(values):
        return '| ' + ' | '.join(latex(v, symbols).replace('|', r'\|') for v in values) + ' |'
    display(Markdown('\n'.join([line(headers), line(['---']*len(headers)), *(line(r) for r in rows)])))
