"""Background loading and presentation for scenario companions; no protocol stages."""
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
import json
import portion as P


def load_method_notebook(path):
    """Load the actual definitions from the trusted local method notebook.

    Executes only its tagged definition cells, including ordinary imports;
    excludes parameters, worked examples, figures and exports. Implementations
    are compiled verbatim rather than copied or reconstructed.
    """
    path = Path(path).resolve()
    notebook = json.loads(path.read_text())
    namespace = {'__name__': '_protocol_companion_methods'}
    for index, cell in enumerate(notebook['cells']):
        if cell['cell_type'] == 'code' and 'definitions' in cell.get('metadata', {}).get('tags', []):
            exec(compile(''.join(cell['source']), f'{path}:cell_{index}', 'exec'), namespace)
    names = ('service_contracts', 'admit', 'generate', 'bargain', 'commit')
    return SimpleNamespace(**{name: namespace[name] for name in names})


def clock(minutes):
    """Exact HH:MM notation for this scenario's whole-minute boundaries."""
    minutes = F(minutes)
    hours, remainder = divmod(minutes, 60)
    if remainder.denominator == 1:
        return f'{int(hours):02d}:{int(remainder):02d}'
    return f'{int(hours):02d}:{remainder}'


def clock_interval(interval):
    return ' ∪ '.join(
        ('{' + clock(c.lower) + '}' if c.lower == c.upper else
         ('[' if c.left == P.CLOSED else '(') + clock(c.lower) + ',' + clock(c.upper)
         + (']' if c.right == P.CLOSED else ')')) for c in interval) or '∅'


def plot_charging_morning(initial, attempts, names):
    """Four physical-time rows from actual sequential attempt records.

    Solid rectangles are commitments; transparent outlined rectangles are
    mutually exclusive alternatives. Red shows a rejected original service;
    a star marks the exact accepted offer. Float conversion is plotting-only.
    """
    import plotly.graph_objects as go
    if len(attempts) != 3:
        raise ValueError('the morning figure requires three successive attempts')
    colors = {1: '#3763A6', 2: '#8254AF', 3: '#15805E', 4: '#BE6A16', 5: '#287F94'}
    red = '#BA3645'
    fig = go.Figure()
    labels = ['Initial commitments', '08:05 · C · full service',
              '08:10 · D · 60 → 30 min', '08:15 · E · NO-BLA']
    centers = [3.9, 2.6, 1.3, 0.0]

    def rectangle(window, y, height, *, kind, row, client=None, label='', solid=False,
                  color=None, dash='solid', extra=None):
        color = color or colors[client]
        meta = dict(kind=kind, row=row, client=client, interval=clock_interval(window),
                    lower=str(window.lower), upper=str(window.upper))
        meta.update(extra or {})
        text = f'{label}<br>{clock_interval(window)}'
        if client is not None:
            text += f'<br>Client {names[client]}'
        fig.add_trace(go.Scatter(
            x=[float(window.lower), float(window.upper), float(window.upper), float(window.lower), float(window.lower)],
            y=[y-height/2, y-height/2, y+height/2, y+height/2, y-height/2],
            mode='lines', line=dict(color=color, width=2, dash=dash),
            fill='toself', fillcolor=color if solid else 'rgba(255,255,255,0)',
            hoveron='fills', hovertemplate=text+'<extra></extra>',
            showlegend=False, meta=meta))
        if solid and client is not None:
            fig.add_annotation(x=float((window.lower+window.upper)/2), y=y,
                               text=f'<b>{names[client]}</b>', showarrow=False,
                               font=dict(color='white', size=13))

    def starts(window, y, row, client, *, kind='feasible_starts', color=None, label='Feasible starts'):
        color = color or colors[client]
        for c in window:
            points = [c.lower] if c.lower == c.upper else [c.lower, c.upper]
            fills = ([color] if c.lower == c.upper else
                     [color if c.left == P.CLOSED else 'white', color if c.right == P.CLOSED else 'white'])
            fig.add_trace(go.Scatter(
                x=[float(t) for t in points], y=[y]*len(points), mode='lines+markers',
                line=dict(color=color, width=4),
                marker=dict(symbol='circle', size=8, color=fills, line=dict(color=color, width=2)),
                showlegend=False, hovertemplate=label+'<br>'+clock_interval(c)+'<extra></extra>',
                meta=dict(kind=kind, row=row, client=client, interval=clock_interval(c),
                          lower=str(c.lower), upper=str(c.upper),
                          left_closed=c.left==P.CLOSED, right_closed=c.right==P.CLOSED)))

    for row, y in enumerate(centers):
        fig.add_hline(y=y-.49, line_color='#E3E7EC', line_width=1)
        bookings = initial if row == 0 else attempts[row-1]['bookings_after']
        for booking in bookings:
            rectangle(booking.interval, y-.22, .27, kind='commitment', row=row,
                      client=booking.client, label='Unconditional reserved access', solid=True)
        if row == 0:
            continue
        attempt = attempts[row-1]
        admission, negotiation = attempt['admission'], attempt['negotiation']
        client = attempt['request'].client
        starts(admission.feasible_starts, y+.57, row, client)
        for index, offer in enumerate(attempt['offers']):
            offer_y = y+.10+index*.18
            accepted = negotiation.agreement is not None and negotiation.agreement.offer == offer
            rectangle(offer.interval, offer_y, .12, kind='candidate', row=row, client=client,
                      label='Alternative access booking', extra=dict(accepted=accepted))
            if accepted:
                fig.add_trace(go.Scatter(
                    x=[float(offer.start)], y=[offer_y], mode='markers',
                    marker=dict(symbol='star', size=17, color=colors[client], line=dict(color='#202A35', width=1)),
                    showlegend=False,
                    hovertemplate=f'Accepted {names[client]} · €{negotiation.agreement.price}<br>'
                                  +clock_interval(offer.interval)+'<extra></extra>',
                    meta=dict(kind='selected', row=row, client=client, interval=clock_interval(offer.interval),
                              price=str(negotiation.agreement.price))))
        if admission.service != attempt['request'].service:
            service = attempt['request'].service
            starts(service.starts, y+.73, row, client, kind='rejected_starts', color=red,
                   label=f'Original {service.duration}-minute request: infeasible')
            # Illustrate the earliest rejected duration window, not an offer from generate().
            window = P.closedopen(service.starts.lower, service.starts.lower+service.duration)
            rectangle(window, y+.34, .12, kind='rejected_request', row=row, client=client,
                      color=red, dash='dash', label='Rejected 60-minute request (earliest start)',
                      extra=dict(requested_starts=clock_interval(service.starts), duration=str(service.duration)))
            fig.add_annotation(x=float(window.upper), y=y+.34, xanchor='left', xshift=8,
                               text='60 min infeasible', showarrow=False, font=dict(color=red, size=11))
        summary = (f'Accepted €{float(negotiation.agreement.price):.2f}' if negotiation.agreement else
                   f'NO-BLA · {len(negotiation.history)} rejected proposals')
        fig.add_annotation(xref='paper', x=1, y=y-.43, xanchor='right', text=summary, showarrow=False,
                           font=dict(color=colors[client], size=11))
    final = attempts[-1]['bookings_after']
    end = max(b.interval.upper for b in final)
    rectangle(P.closedopen(end, 780), centers[-1]-.22, .27, kind='unreserved', row=3,
              color='#AAB4BE', label='Unreserved time')
    fig.add_annotation(x=float((end+780)/2), y=centers[-1]-.22, text='Unreserved',
                       showarrow=False, font=dict(size=12, color='#65717D'))
    for text, color, filled, symbol in (
            ('Committed access', '#536579', True, 'square'),
            ('Alternative booking', '#536579', False, 'square-open'),
            ('Selected offer', '#536579', True, 'star'),
            ('Rejected original request', red, False, 'square-open'),
            ('Feasible start region', '#15805E', True, 'circle')):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers',
                                marker=dict(symbol=symbol, size=12, color=color),
                                name=text, hoverinfo='skip', meta=dict(kind='legend')))
    ticks = list(range(480, 781, 30))
    fig.update_layout(
        title=dict(text='One charging point · three successive requests', x=0), template='plotly_white',
        height=910, margin=dict(l=205, r=35, t=115, b=115),
        xaxis=dict(title='Physical time · half-open reserved access windows', tickvals=ticks,
                   ticktext=[clock(t) for t in ticks], range=[475, 782], dtick=30),
        yaxis=dict(tickvals=centers, ticktext=labels, range=[-.55, 4.7], fixedrange=True, zeroline=False),
        legend=dict(orientation='h', y=-.12, x=0), hovermode='closest',
        meta=dict(kind='charging_morning', rows=4, final_schedule=[
            dict(client=b.client, interval=clock_interval(b.interval)) for b in sorted(final, key=lambda b:b.start)]))
    fig.add_annotation(xref='paper', yref='paper', x=0, y=1.075, xanchor='left', align='left',
                       text='Solid blocks = commitments · outlined blocks = alternatives · ★ = accepted offer<br>'
                            'Thin lines/dots = start regions; red = infeasible original service.',
                       showarrow=False, font=dict(size=12, color='#566373'))
    return fig
