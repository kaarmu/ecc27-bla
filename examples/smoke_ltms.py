"""Small real-backend smoke run; see docs/LTMS_REACHABILITY.md."""
import json
from importlib.metadata import version

import numpy as np

from ltms_reachability import GridSpec, LTMSPlanner, create_4way, route_constraints


def main():
    spec = GridSpec.bicycle5d(horizon=.2, time_step=.1, shape=(9, 9, 17, 3, 3))
    planner = LTMSPlanner.bicycle5d(spec)
    regions = create_4way(planner.grid)
    rules = route_constraints(regions, 'entry_w', 'exit_e')
    target = regions['center']
    direct = planner.reach(target, rules)
    tree, root = planner.until(rules, target)
    np.testing.assert_allclose(root, direct, atol=1e-6)
    print(json.dumps(dict(
        pyspect=version('pyspect'), hj_reachability=version('hj-reachability'),
        jax=version('jax'), shape=root.shape,
        finite=bool(np.isfinite(root).all()),
        initial_nonpositive_samples=int((root[0] <= 0).sum()),
        tlt_matches_direct=True,
    ), indent=2))


if __name__ == '__main__':
    main()
