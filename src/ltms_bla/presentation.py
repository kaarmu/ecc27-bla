"""Figures and tables from recorded scenario results, without importing JAX."""
from pathlib import Path
import json

from protocol import fmt
from .records import latex_atom

try:
    from IPython.display import Markdown, display
except ImportError:
    Markdown, display = str, print

# Attempt outcomes and candidate statuses keep distinct meanings.
MEANINGS = {
    'COMMITTED': 'exact negotiated offer and price stored; standing commitment conjoined',
    'NO-COMPATIBLE-OFFER': 'every template conflicts with a retained reservation; not physical impossibility',
    'PRICE-NO-BLA': 'qualified offers exist; bargaining exhausted without agreement',
    'PROVED-IMPOSSIBLE': 'an independent analytic bound excludes every permitted service',
    'UNRESOLVED': 'numerical evidence does not apply; neither an offer nor impossibility',
    'QUALIFIED': 'service and compatibility evidence both hold',
    'GEOMETRIC_CONFLICT': 'template rejected: its reservation meets a standing one',
    'PROVED_IMPOSSIBLE': 'independent necessary bound fails',
}


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


def candidate_rows(admission, names):
    """One row per template: status, meaning, and the two kinds of evidence apart.

    ``names`` maps standing offer identities to client names.
    """
    for tried in admission.services:
        for c in tried.candidates:
            checks = c.reply.get('info', {}).get('checks', {})
            service = checks.get('service', c.reply.get('service'))
            comparisons = checks.get('compatibility', {}).get('disjoint_from', c.reply.get('comparisons'))
            yield (f'{tried.service.client} · d={tried.service.deadline}', c.departure, c.status,
                   MEANINGS[c.status], '—' if service is None else all(service.values()),
                   '—' if comparisons is None else ', '.join(
                       f"{names[x['offer']]}: {'disjoint' if x['disjoint'] else 'meets'}"
                       for x in comparisons) or 'no standing BLA',
                   c.reply.get('reason', ''))


def results_table(report):
    rows = ['| Client | Candidate statuses | Outcome | Meaning | Offers | Selected departure | Price | Prior BLAs retained |',
            '|:--|:--|:--|:--|--:|--:|--:|:--|']
    for attempt in report['attempts']:
        accepted = attempt['accepted']
        chosen = next((o for o in attempt['offers'] if accepted and o['id'] == accepted['id']), None)
        statuses = '; '.join(f"d={s['service']['deadline']}: " + ', '.join(
            f"s={c['departure']} {c['status']}" for c in s['candidates']) for s in attempt['services'])
        rows.append(f"| {attempt['client']} | {statuses} | {attempt['status']} | {MEANINGS[attempt['status']]} | "
                    f"{len(attempt['offers'])} | {'—' if chosen is None else chosen['departure']} | "
                    f"{'—' if accepted is None else accepted['price']} | {attempt['previous_preserved']} |")
    return '\n'.join(rows)


def plot_scenario(report):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    figure = make_subplots(rows=2, cols=2, specs=[[{}, {}], [{'colspan': 2}, None]],
                           subplot_titles=('Accepted crossings and reserved lane bands',
                                           'TLT root at t=0, h=0, d=0, v=0.45',
                                           'Offered lease intervals and exact accepted choices'),
                           vertical_spacing=.17, row_heights=[.65, .35])
    colors = {'A': '#0072B2', 'B': '#D55E00', 'C': '#888888', 'D': '#CC79A7', 'E': '#009E73'}
    figure.add_shape(type='rect', x0=-1.2, x1=1.2, y0=-1.2, y1=1.2,
                     fillcolor='#f0f0f0', line=dict(width=0), row=1, col=1)
    by_id = {b['id']: b for b in report['accepted']}
    for path in report['final']['paths']:
        name = by_id[path['id']]['client']
        states = path['states']
        figure.add_trace(go.Scatter(x=[s[0] for s in states], y=[s[1] for s in states],
                                   mode='lines', line=dict(color=colors[name], width=3),
                                   name=f'{name}: checked execution',
                                   customdata=path['times'], hovertemplate='x=%{x:.2f}, y=%{y:.2f}<br>t=%{customdata:.2f}s'), row=1, col=1)
        figure.add_trace(go.Contour(x=report['final']['rx'], y=report['final']['ry'],
                                   z=path['reserved_union'], showscale=False, opacity=.13,
                                   colorscale=[[0, 'rgba(255,255,255,0)'], [1, colors[name]]],
                                   contours=dict(start=.5, end=.5, size=1), line_width=0,
                                   hoverinfo='skip', name=f'{name} reservation projection'), row=1, col=1)
    data = report['final']
    figure.add_trace(go.Contour(x=data['x'], y=data['y'], z=data['slice'],
                               colorscale='RdBu', zmid=0, showscale=False,
                               contours=dict(start=-.1, end=.3, size=.05),
                               name='HJ value', hovertemplate='x=%{x:.2f}, y=%{y:.2f}<br>V=%{z:.4f}'), row=1, col=2)
    figure.add_trace(go.Scatter(x=[-1.6], y=[-.4], mode='markers', name='Specified full entry state',
                               marker=dict(symbol='star', size=13, color='black')), row=1, col=2)
    for i, attempt in enumerate(report['attempts']):
        color = colors[attempt['client']]
        for offer in attempt['offers']:
            accepted = attempt['accepted'] is not None and attempt['accepted']['id'] == offer['id']
            figure.add_trace(go.Scatter(x=[offer['departure'], float(offer['end'])], y=[i, i],
                                       mode='lines', line=dict(color=color, width=8 if accepted else 3,
                                                              dash='solid' if accepted else 'dot'),
                                       name=f"{attempt['client']} lease", showlegend=False,
                                       hovertemplate=f"{attempt['client']}: {offer['id']}<br>t=%{{x}}s"), row=2, col=1)
            if accepted:
                figure.add_trace(go.Scatter(x=[offer['departure']], y=[i], mode='markers', showlegend=False,
                                           marker=dict(symbol='star', size=14, color=color)), row=2, col=1)
    figure.update_xaxes(title_text='x [m]', range=[-2.1, 2.1], row=1, col=1)
    figure.update_yaxes(title_text='y [m]', range=[-1.3, 1.3], scaleanchor='x', scaleratio=1, row=1, col=1)
    figure.update_xaxes(title_text='x [m]', row=1, col=2)
    figure.update_yaxes(title_text='y [m]', row=1, col=2)
    figure.update_xaxes(title_text='Physical time [s]', row=2, col=1)
    figure.update_yaxes(tickvals=list(range(len(report['attempts']))),
                        ticktext=[a['client']+' · '+a['status'] for a in report['attempts']], row=2, col=1)
    figure.update_layout(template='plotly_white', height=780, width=1050,
                         title=dict(text='LTMS reachability-based BLAs', x=.5, y=.99),
                         margin=dict(l=110, r=30, t=115, b=40), legend=dict(orientation='h', y=1.10))
    return figure


def export_report(report, figure, output):
    output = Path(output)
    (output/'results.md').write_text(results_table(report))
    (output/'figure.json').write_text(figure.to_json())
    figure.write_html(output/'ltms_blas.html', include_plotlyjs=True)
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
