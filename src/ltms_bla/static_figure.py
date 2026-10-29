"""Standalone Matplotlib figure from the notebook's recorded scenario results."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def export_figure(data, attempts, output):
    colors = {'A': '#0072B2', 'B': '#D55E00', 'C': '#888888', 'D': '#CC79A7', 'E': '#009E73'}
    fig = plt.figure(figsize=(9, 6.4), layout='constrained')
    grid = fig.add_gridspec(2, 2, height_ratios=[1.7, 1])
    map_ax, reach_ax, time_ax = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])
    clients = {a['accepted']['id']: a['client'] for a in attempts if a['accepted']}
    for path in data['paths']:
        name = clients[path['id']]
        states = np.array(path['states'])
        mask = np.ma.masked_equal(np.array(path['reserved_union']), 0)
        from matplotlib.colors import ListedColormap
        map_ax.pcolormesh(data['rx'], data['ry'], mask, cmap=ListedColormap([colors[name]]), alpha=.15, shading='nearest')
        map_ax.plot(states[:, 0], states[:, 1], color=colors[name], label=name, lw=1.8)
    map_ax.set(xlim=(-2.1, 2.1), ylim=(-1.3, 1.3), xlabel='x [m]', ylabel='y [m]', title='Accepted paths and reservation projections')
    map_ax.set_aspect('equal')
    map_ax.legend(ncol=3, loc='upper center')
    values = np.array(data['slice'])
    reach_ax.contourf(data['x'], data['y'], values, levels=np.linspace(-.15, .3, 16), cmap='RdBu_r', extend='both')
    reach_ax.contour(data['x'], data['y'], values, levels=[0], colors='black', linewidths=.7)
    reach_ax.plot(-1.6, -.4, marker='*', color='black', ms=10)
    reach_ax.set(xlabel='x [m]', ylabel='y [m]', title='TLT root: t=0, h=0, v=0.45')
    reach_ax.set_aspect('equal')
    for i, attempt in enumerate(attempts):
        for offer in attempt['offers']:
            accepted = attempt['accepted'] and offer['id'] == attempt['accepted']['id']
            time_ax.plot([offer['departure'], float(offer['end'])], [i, i],
                         color=colors[attempt['client']], lw=4 if accepted else 1.5,
                         ls='-' if accepted else ':')
            if accepted:
                time_ax.plot(offer['departure'], i, '*', color=colors[attempt['client']], ms=9)
    time_ax.set(yticks=range(len(attempts)), yticklabels=[f"{a['client']}: {a['status']}" for a in attempts],
                xlabel='Physical time [s]', title='Lease offers (dotted); exact accepted offers (solid)')
    time_ax.invert_yaxis()
    time_ax.grid(axis='x', alpha=.2)
    fig.savefig(output/'ltms_blas.svg')
    fig.savefig(output/'ltms_blas.png', dpi=150)
    plt.close(fig)
