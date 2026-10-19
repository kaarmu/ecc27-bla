"""Readable notebook tables and optional offline Plotly timelines."""
from dataclasses import dataclass
from fractions import Fraction as F
import portion as P
import interval_logic as il
from ._util import FULL, region, time
try:
    from IPython.display import Markdown, display
except ImportError:
    Markdown, display = str, print

def fmt(value):
    if isinstance(value, il.Formula):
        return "$" + il.format_latex(value) + "$"
    if isinstance(value, il.NumericTerm):
        return "$" + il.format_term_latex(value) + "$"
    if isinstance(value, P.Interval):
        return ' ∪ '.join(il.format_temporal_parameter(il.AbsoluteParameter(c))
                          for c in value) or '∅'
    return str(value)

def table(headers, rows):
    def line(values):
        return '| ' + ' | '.join(fmt(v).replace('|', r'\|') for v in values) + ' |'
    display(Markdown('\n'.join([line(headers), line(['---'] * len(headers)),
                                *(line(row) for row in rows)])))

# Plotting is optional: Plotly is imported only when a figure is requested.
def _timeline_interval(interval):
    """Exact, compact notation for finite or infinite interval components."""
    parts = []
    for part in interval:
        if part.lower == part.upper:
            parts.append('{' + str(part.lower) + '}')
        else:
            parts.append(('[' if part.left == P.CLOSED else '(')
                         + str(part.lower) + ',' + str(part.upper)
                         + (']' if part.right == P.CLOSED else ')'))
    return ' ∪ '.join(parts) or '∅'


def _timeline_color(client):
    colors = {0: '#89929D', 1: '#8661C5', 2: '#2878B5'}
    extra = ('#D47B26', '#A84978', '#288B80', '#B24949', '#70753C')
    return colors.get(client, extra[(client - 3) % len(extra)])


def protocol_horizon(stored, request, offers=()):
    """Finite display domain covering all permitted service completions."""
    ends = [F(1)]
    for booking in stored:
        ends.append(booking.interval.upper)
    for service in (request.service, *request.alternatives):
        if not service.starts.empty:
            ends.append(service.starts.upper + service.duration)
    ends.extend(offer.interval.upper for offer in offers)
    return P.closed(F(0), max(ends))


def _timeline_horizon(horizon):
    horizon = region(horizon, bounded=True)
    if horizon.empty or not horizon.atomic or horizon.lower == horizon.upper:
        raise ValueError('a timeline horizon must be one finite interval of positive width')
    return horizon


def _timeline_component(figure, component, y, *, kind, lane, color, client=None,
                        width=14, dash='solid', label='', row=None, visible=True,
                        extra=None):
    """One exact connected component: a segment, its endpoint markers, or a dot."""
    import plotly.graph_objects as go

    singleton = component.lower == component.upper
    ends = [component.lower] if singleton else [component.lower, component.upper]
    symbols = 'circle'
    fills = ([color] if singleton else
             [color if component.left == P.CLOSED else '#FFFFFF',
              color if component.right == P.CLOSED else '#FFFFFF'])
    metadata = dict(kind=kind, lane=lane, client=client,
                    interval=_timeline_interval(component),
                    lower=str(component.lower), upper=str(component.upper),
                    left_closed=component.left == P.CLOSED,
                    right_closed=component.right == P.CLOSED, singleton=singleton)
    if extra:
        metadata.update(extra)
    hover = label + '<br>' if label else ''
    hover += _timeline_interval(component)
    if client is not None:
        hover += '<br>' + ('Idle (0)' if client == 0 else f'Client {client}')
    item = go.Scatter(
        x=[float(end) for end in ends], y=[y] * len(ends),
        mode='markers' if singleton else 'lines+markers',
        line=dict(color=color, width=width, dash=dash),
        marker=dict(color=fills, size=max(10, width + 3),
                    symbol=symbols, line=dict(width=2, color=color)),
        name=label, showlegend=False,
        legendgroup=f'client_{client}' if client is not None else 'start_regions',
        hovertemplate=hover + '<extra></extra>',
        visible=visible, meta=metadata,
    )
    figure.add_trace(item, row=row, col=1) if row else figure.add_trace(item)


def _timeline_legend(figure, clients):
    import plotly.graph_objects as go

    for client in sorted(clients):
        figure.add_trace(go.Scatter(
            x=[None], y=[None], mode='lines',
            line=dict(color=_timeline_color(client), width=8),
            name='Idle (0)' if client == 0 else f'Client {client}',
            legendgroup=f'client_{client}', hoverinfo='skip',
            meta=dict(kind='legend', client=client),
        ))


def plot_booking_progression(stored, request, admission, offers, negotiation,
                             committed, *, horizon=None):
    """Plot start regions, mutually exclusive candidate bookings, and the ledger."""
    import plotly.graph_objects as go

    stored, offers = tuple(stored), tuple(offers)
    horizon = _timeline_horizon(
        protocol_horizon(stored, request, offers) if horizon is None else horizon)
    pair = (negotiation.agreement
            if (committed is not None and committed.status == 'COMMITTED'
                and committed.agreement is not None and negotiation is not None)
            else None)
    lanes = [dict(key='standing', label='Standing bookings · booked time'),
             dict(key='requested_starts', label='Requested starts · start time'),
             dict(key='feasible_starts', label='Feasible starts · start time')]
    lanes.extend(dict(key=f'candidate_{i}', label=f'Candidate {i} · booked time')
                 for i in range(1, len(offers) + 1))
    lanes.append(dict(key='committed', label='After attempt · booked time'))
    positions = {lane['key']: len(lanes) - 1 - i for i, lane in enumerate(lanes)}
    fig = go.Figure()
    clients = {booking.client for booking in stored} | {request.client}

    def draw(window, lane, *, kind=None, client=None, color=None, **kwargs):
        for component in window & horizon:
            _timeline_component(fig, component, positions[lane],
                                kind=kind or lane, lane=lane, client=client,
                                color=color or _timeline_color(client), **kwargs)

    for booking in stored:
        draw(booking.interval, 'standing', client=booking.client,
             label='Standing unconditional access')
    draw(request.service.starts, 'requested_starts', color='#A66C13', width=5,
         dash='dot', label=f'Requested starts; duration {request.service.duration}')
    if admission is not None:
        draw(admission.feasible_starts, 'feasible_starts', client=request.client,
             color='#258A76', width=5, label='Exact feasible starts')
    for index, offer in enumerate(offers, 1):
        draw(offer.interval, f'candidate_{index}', kind='candidate',
             client=offer.booking.client,
             label=f'Candidate {index} — alternative, not a standing commitment',
             extra=dict(offer_index=index, certified=offer.certificate.certified,
                        compatible=offer.certificate.compatible))
    for booking in stored:
        draw(booking.interval, 'committed', client=booking.client,
             label='Preserved standing access', extra=dict(accepted=False))
    accepted = None
    if pair is not None:
        booking = pair.offer.booking
        accepted_round = next((r.number for r in negotiation.history
                               if r.accepted and r.proposal == pair), None)
        accepted = dict(client=booking.client, interval=_timeline_interval(booking.interval),
                        price=str(pair.price), round=accepted_round)
        draw(booking.interval, 'committed', kind='accepted_highlight',
             client=booking.client, color='#21956A', width=23,
             label='Accepted booking', extra=dict(accepted=True))
        draw(booking.interval, 'committed', client=booking.client,
             label=f'Accepted unconditional access; price {pair.price}; round {accepted_round}',
             extra=dict(accepted=True, price=str(pair.price), round=accepted_round))
        center = (booking.interval.lower + booking.interval.upper) / 2
        fig.add_annotation(x=float(center), y=positions['committed'] + .35,
                           text=f'<b>Accepted · price {pair.price} · round {accepted_round}</b>',
                           showarrow=False, font=dict(color='#16734F', size=12))
    else:
        fig.add_annotation(xref='paper', x=1, xanchor='right',
                           y=positions['committed'] + .35,
                           text='No agreement — standing bookings preserved',
                           showarrow=False, font=dict(color='#5E6875', size=12))
    _timeline_legend(fig, clients)
    span = horizon.upper - horizon.lower
    fig.update_layout(
        template='plotly_white', title=dict(text='Booking progression', x=0),
        height=max(450, 145 + 57 * len(lanes)),
        margin=dict(l=245, r=30, t=85, b=140),
        xaxis=dict(title='Physical time t',
                   range=[float(horizon.lower - span / 50),
                          float(horizon.upper + span / 50)], zeroline=False),
        yaxis=dict(tickvals=[positions[lane['key']] for lane in lanes],
                   ticktext=[lane['label'] for lane in lanes],
                   range=[-.65, len(lanes) - .4], fixedrange=True, zeroline=False),
        legend=dict(orientation='h', x=0, y=-.34, yanchor='top'),
        hovermode='closest',
        meta=dict(kind='booking_progression', horizon=_timeline_interval(horizon),
                  lanes=lanes, accepted=accepted),
    )
    fig.add_annotation(xref='paper', yref='paper', x=0, y=1.07, showarrow=False,
                       xanchor='left', text='Dotted/thin = possible start times; thick = reserved access.<br>'
                       'Filled/open endpoints = included/excluded.', align='left',
                       font=dict(size=11, color='#5E6875'))
    return fig


def plot_signal_traces(scenarios, owner_contract, client_contract, *, horizon, now=0):
    """Plot complete acc/use traces; switching scenarios updates semantic labels."""
    from html import escape
    from textwrap import wrap
    from plotly.subplots import make_subplots

    horizon = _timeline_horizon(horizon)
    now = time(now)
    if not scenarios:
        raise ValueError('provide at least one signal scenario')
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.2,
                        subplot_titles=('Owner-controlled access · acc(t)',
                                        'Client-controlled use · use(t)'))
    records, clients = [], set()
    for index, (name, scenario) in enumerate(scenarios.items()):
        trace = scenario['trace']
        note = scenario.get('note', '')
        record = dict(
            name=name, note=note,
            owner_satisfied=il.satisfies(owner_contract.guarantee, trace, now),
            client_assumption=il.satisfies(client_contract.assumption, trace, now),
            client_guarantee=il.satisfies(client_contract.guarantee, trace, now),
            client_task=il.satisfies(client_contract.assumption & client_contract.guarantee,
                                     trace, now), trace_indices=[])
        for row, signal in enumerate(('acc', 'use'), 1):
            # Resolve the default on the complete trace FIRST. A plotting crop
            # is not a trace universe and may exclude explicitly defined regions.
            for client, window in trace.signals[signal].parts(trace.universe).items():
                clients.add(client)
                for full_component in window:
                    for component in full_component & horizon:
                        record['trace_indices'].append(len(fig.data))
                        _timeline_component(
                            fig, component, client, row=row, kind='signal', lane=signal,
                            client=client, color=_timeline_color(client), width=5,
                            label=f'{name}<br>{signal}(t) = {client}', visible=index == 0,
                            extra=dict(scenario=name, signal=signal,
                                       full_interval=_timeline_interval(full_component),
                                       clipped=component != full_component))
        records.append(record)
    _timeline_legend(fig, clients)
    legend_indices = [i for i, item in enumerate(fig.data) if item.meta['kind'] == 'legend']

    def annotations(record):
        # Keep make_subplots' two panel labels when changing scenario annotations.
        labels = [a.to_plotly_json() for a in fig.layout.annotations[:2]]
        owner = 'satisfied' if record['owner_satisfied'] else 'violated'
        client = 'fulfilled' if record['client_task'] else 'unfulfilled'
        labels.append(dict(xref='paper', yref='paper', x=0, y=1.17,
                           xanchor='left', showarrow=False,
                           text=f'<b>Owner commitments: {owner} · Client task: {client}</b>',
                           font=dict(size=12, color='#374151')))
        note = '<br>'.join(escape(line) for line in wrap(record['note'], width=75))
        labels.append(dict(xref='paper', yref='paper', x=0, y=-.2,
                           xanchor='left', yanchor='top', showarrow=False,
                           align='left', text=note, font=dict(size=11, color='#5E6875')))
        return labels

    buttons = []
    for record in records:
        indices = set(record['trace_indices']) | set(legend_indices)
        buttons.append(dict(label=record['name'], method='update',
                            args=[dict(visible=[i in indices for i in range(len(fig.data))]),
                                  dict(annotations=annotations(record))]))
    span = horizon.upper - horizon.lower
    values = sorted(clients)
    fig.update_yaxes(tickmode='array', tickvals=values,
                     ticktext=['Idle (0)' if k == 0 else f'Client {k}' for k in values],
                     range=[min(values, default=0) - .45, max(values, default=0) + .45],
                     fixedrange=True, zeroline=False)
    fig.update_xaxes(range=[float(horizon.lower - span / 50),
                            float(horizon.upper + span / 50)], zeroline=False)
    fig.update_xaxes(title='Physical time t', row=2, col=1)
    fig.update_layout(
        template='plotly_white', title=dict(text='Access and use signals', x=0),
        height=740, margin=dict(l=105, r=30, t=175, b=200),
        annotations=annotations(records[0]),
        updatemenus=[dict(type='dropdown', x=0, xanchor='left', y=1.33,
                          yanchor='top', direction='down', buttons=buttons, active=0)],
        legend=dict(orientation='h', x=0, y=-.38, yanchor='top'),
        hovermode='closest', meta=dict(kind='signal_traces',
                                     horizon=_timeline_interval(horizon), scenarios=records),
    )
    return fig


def display_timeline(figure):
    """Native notebook output with an offline HTML fallback; no browser launches."""
    try:
        from IPython import get_ipython
        from IPython.display import display as display_bundle
    except ImportError:
        return
    if get_ipython() is None:
        return  # Headless execution still builds and tests both figure objects.
    import json

    config = dict(responsive=True, displaylogo=False, scrollZoom=True)
    native = json.loads(figure.to_json())
    native['config'] = config
    display_bundle({
        'application/vnd.plotly.v1+json': native,
        'text/html': figure.to_html(full_html=False, include_plotlyjs=True, config=config),
        'text/plain': figure.layout.title.text,
    }, raw=True)


def illustrative_signal_scenarios(stored, accepted_booking, extra_booking):
    """Explicit possible executions, not observations inferred from a booking."""
    stored = tuple(stored)
    if extra_booking.client != accepted_booking.client:
        raise ValueError('the additional access must belong to the accepted client')

    def signal(bookings):
        windows = {}
        for booking in bookings:
            windows[booking.client] = windows.get(booking.client, P.empty()) | booking.interval
        return il.NaturalSignal(windows, default=0)

    access_bookings = (*stored, accepted_booking)
    other_use = tuple(b for b in stored if b.client != accepted_booking.client)

    def trace(access_bookings, use_bookings):
        return il.Trace(FULL, signals={'acc': signal(access_bookings),
                                       'use': signal(use_bookings)})

    return {
        'Use during the booking': {
            'trace': trace(access_bookings, (*other_use, accepted_booking)),
            'note': 'Illustrative joint execution: the selected client uses its accepted booking; '
                    'standing access is preserved. Idle is shown explicitly outside these windows.',
        },
        'Later use with additional access': {
            'trace': trace((*access_bookings, extra_booking), (*other_use, extra_booking)),
            'note': f'Illustrative extra access {_timeline_interval(extra_booking.interval)} is not '
                    'part of the accepted BLA. It permits a later use witness while the accepted '
                    'booking and all standing access remain in force.',
        },
        'Client absent': {
            'trace': trace(access_bookings, other_use),
            'note': 'The selected client does not use the resource. The owner still supplies '
                    'its unconditional access booking, but the client task is unfulfilled; '
                    'absence does not release the reservation.',
        },
    }


def export_timelines(path, *figures):
    """Export these exact figures as one offline HTML document (Plotly embedded once)."""
    from pathlib import Path
    from html import escape
    path = Path(path)
    config = dict(responsive=True, displaylogo=False, scrollZoom=True)
    content = ''.join(fig.to_html(full_html=False, include_plotlyjs=i == 0,
                                  config=config, div_id=f'protocol-figure-{i}')
                      for i, fig in enumerate(figures))
    path.write_text('<!doctype html><html><head><meta charset="utf-8">'
                    '<title>Protocol timelines</title></head><body>'
                    '<p>Generated from the protocol notebook figure objects. '
                    'Signals are illustrative complete traces.</p>' + content + '</body></html>')
    return path
