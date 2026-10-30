"""Numerical regressions; run with the optional reachability dependencies."""
import itertools
import unittest

try:
    import numpy as np
    import jax.numpy as jnp
    from hj_reachability import dynamics, sets
    from pyspect.impls.hj_reachability import TVHJImpl
except ImportError as error:
    raise unittest.SkipTest(f"optional LTMS numerical dependencies: {error}") from error

from ltms_reachability import (
    LTMSPlanner, GridSpec, NoCorridorError, SpatialReservation,
    ControlLimits, NoAdmissibleControlError, TimeWindow, WindowPolicy,
    create_4way, create_chaos, route_constraints,
)
from ltms_reachability.levelsets import rectangle, project_onto
from ltms_reachability.windows import select_window, window_mask


class SingleIntegrator(dynamics.ControlAndDisturbanceAffineDynamics):
    """Test-only x_dot = u, to check the real PDE backend against known motion."""
    def __init__(self, min_vel=1., max_vel=1.):
        super().__init__('min', 'max', sets.Box(jnp.array([min_vel]), jnp.array([max_vel])),
                         sets.Box(jnp.zeros(1), jnp.zeros(1)))

    def with_mode(self, mode):
        self.control_mode = 'min' if mode == 'reach' else 'max'
        return self

    def open_loop_dynamics(self, state, time):
        return jnp.zeros(1)

    def control_jacobian(self, state, time):
        return jnp.ones((1, 1))

    def disturbance_jacobian(self, state, time):
        return jnp.zeros((1, 1))


class SampledGeometryTests(unittest.TestCase):
    def test_windows_against_exhaustive_elapsed_time_oracle(self):
        times = np.arange(6)*.2
        for bits in itertools.product((False, True), repeat=6):
            for minimum, maximum in ((0, 0), (.2, .4), (.4, .8)):
                candidates = [(i, j) for i in range(6) for j in range(i, 6)
                              if all(bits[i:j+1]) and minimum-1e-9 <= times[j]-times[i] <= maximum+1e-9]
                result = select_window(times, bits, minimum, maximum)
                expected = min(candidates, key=lambda ij: (ij[0], -ij[1])) if candidates else None
                self.assertEqual(None if result is None else (result.first, result.last), expected)
        np.testing.assert_array_equal(window_mask(times, TimeWindow(.2, .6, False, True)),
                                      [False, False, True, True, False, False])

    def test_projection_preserves_requested_axis_order(self):
        a = np.arange(24).reshape(2, 3, 4)
        np.testing.assert_array_equal(project_onto(a, 2, 0), a.min(axis=1).T)

    def test_reservation_alignment_dilation_and_copy(self):
        xy = np.arange(5.)
        positions = np.zeros((3, 5, 5), bool)
        positions[0, 1, 2] = positions[1, 2, 2] = positions[2, 3, 2] = True
        reservation = SpatialReservation([10, 11, 12], xy, xy, positions, body_radius=.5)
        positions[:] = False
        occupied = reservation.on_grid([10.5, 11.5], xy, xy, ego_radius=.5)
        self.assertTrue(occupied[0, 1:4, 2].all())  # includes bracketing stored samples
        self.assertTrue(occupied[1, 4, 2])  # combined radii are workspace distances
        self.assertFalse(occupied[0, 0, 0])
        self.assertFalse(reservation.positions.flags.writeable)
        self.assertFalse(reservation.on_grid([8, 9], xy, xy).any())
        with self.assertRaises(ValueError):
            reservation.on_grid([10, 11], xy+.1, xy)

    def test_control_projection_and_empty_halfspace(self):
        limits = ControlLimits(0., [1., 1.], [-1., -1.], [1., 1.])
        np.testing.assert_allclose(limits.project([1, 1]), [0, 0], atol=1e-9)
        saturated = ControlLimits(.5, [1., 0.], [-1., -1.], [1., 1.])
        np.testing.assert_allclose(saturated.project([4, 3]), [-.5, 1], atol=1e-9)
        self.assertTrue(saturated.contains(saturated.project([4, 3])))
        with self.assertRaises(NoAdmissibleControlError):
            ControlLimits(2, [1], [-1], [1]).project([0])


class PyspectPlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = LTMSPlanner(TVHJImpl(dict(cls=SingleIntegrator), [
            dict(name='t', bounds=[0, 2], points=21),
            dict(name='x', bounds=[-2, 3], points=101)], accuracy='low'))
        cls.goal = rectangle(cls.planner.grid, [.4], [1.])
        cls.entry = rectangle(cls.planner.grid, [-.8], [-.2])
        cls.rules = rectangle(cls.planner.grid, [-2], [3])
        cls.offline = cls.planner.reach(cls.goal, cls.rules)

    def test_backward_reachability_and_actual_tlt_agree(self):
        p = self.planner
        tree, root = p.until(self.rules, self.goal)
        np.testing.assert_allclose(root, self.offline, atol=1e-6)
        self.assertIsNotNone(tree)
        x = np.asarray(p.grid.coordinate_vectors[0])
        # x_dot=1: x=.0 can hit [.4,1] by t=2; x=1.5 cannot return to it.
        self.assertLess(self.offline[0, np.argmin(abs(x))], 0)
        self.assertGreater(self.offline[0, np.argmin(abs(x-1.5))], 0)
        # A terminal-only target has the known preimage [.4-2, 1-2].
        _, terminal = p.until(self.rules, self.goal, target_window=TimeWindow(2, 2))
        self.assertLess(terminal[0, np.argmin(abs(x+1.3))], 0)
        self.assertGreater(terminal[0, np.argmin(abs(x))], 0)

    def test_timed_target_endpoints_and_constraint_at_witness(self):
        p = self.planner
        x = np.asarray(p.grid.coordinate_vectors[0])
        at = lambda tube, value: tube[0, np.argmin(abs(x-value))]
        # x_dot=1: the goal [.4,1] is occupied during [1,2] exactly from x0 in [-1.6, 0].
        _, windowed = p.until(self.rules, self.goal, target_window=TimeWindow(1, 2))
        self.assertLess(at(windowed, -1.5), 0)
        self.assertLess(at(windowed, -.1), 0)
        self.assertGreater(at(windowed, .3), 0)   # leaves the goal before t=1
        self.assertGreater(at(windowed, -1.8), 0)  # reaches the goal after t=2
        # The native backend intersects the target with the constraint at the
        # witness: with constraint x <= .7, the terminal witness set is [.4,.7].
        rules = rectangle(p.grid, [-2], [.7])
        _, terminal = p.until(rules, self.goal, target_window=TimeWindow(2, 2))
        self.assertLess(at(terminal, -1.5), 0)
        self.assertGreater(at(terminal, -1.1), 0)

    def test_generated_query_matches_the_windowed_until(self):
        import interval_logic as il
        import portion as P
        from pyspect import Set
        from ltms_bla.tlt import compile_query
        p = self.planner
        x = np.asarray(p.grid.coordinate_vectors[0])
        at = lambda tube, value: tube[0, np.argmin(abs(x-value))]
        road, alloc, goal = il.Proposition('road'), il.Proposition('alloc'), il.Proposition('goal')
        where = dict(road=Set(p._tube(self.rules)), alloc=Set(-np.ones(p.shape)), goal=Set(p._tube(self.goal)))
        # Read at anchor 5, the absolute window [6, 7] is the solver's [1, 2].
        tree = compile_query(il.Until(road & alloc, goal, P.closed(6, 7)), 5, where)
        generated = np.asarray(tree.realize(p.impl))
        _, windowed = p.until(self.rules, self.goal, target_window=TimeWindow(1, 2))
        for value in (-1.5, -.1, .3, -1.8):
            self.assertEqual(at(generated, value) <= 0, at(windowed, value) <= 0)
        # Outside the supported fragment, or uninterpreted: refused, not approximated.
        for formula, anchor in ((il.Until(road, goal, P.closed(4, 7)), 5),
                                (il.Until(road, goal, P.open(6, 7)), 5),
                                (il.Until(road, goal, 2), 5),
                                (il.Or((il.Until(road, goal, P.closed(6, 7)), goal)), 5),
                                (il.Until(road, il.Proposition('elsewhere'), P.closed(6, 7)), 5)):
            with self.subTest(formula=str(formula)), self.assertRaises(ValueError):
                compile_query(formula, anchor, where)

    def test_set_builders_are_realized_on_the_backend(self):
        from pyspect.set_builder import BoxSet
        p = self.planner
        goal, entry, rules = (BoxSet(dict(x=b), axes=['x']) for b in ((.4, 1.), (-.8, -.2), (-2, 3)))
        policy = WindowPolicy(.1, .3, .1, .4)
        built = p.analyze(entry=entry, goal=goal, constraints=rules, policy=policy, entry_window=TimeWindow(0, .4))
        arrays = p.analyze(entry=np.asarray(entry(p.impl)), goal=np.asarray(goal(p.impl)),
                           constraints=np.asarray(rules(p.impl)), policy=policy, entry_window=TimeWindow(0, .4))
        for name in ('pass1', 'pass3', 'pass4'):
            np.testing.assert_array_equal(built.passes[name], arrays.passes[name])

    def test_four_passes_candidate_order_and_cached_input(self):
        p = self.planner
        original = self.offline.copy()
        policy = WindowPolicy(.1, .3, .1, .4)
        def evaluate(window):
            return p.analyze(entry=self.entry, goal=self.goal, constraints=self.rules,
                             policy=policy, entry_window=window, offline=self.offline)
        a1 = evaluate(TimeWindow(0, .4))
        b1 = evaluate(TimeWindow(.4, .8))
        b2 = evaluate(TimeWindow(.4, .8))
        a2 = evaluate(TimeWindow(0, .4))
        for first, second in ((a1, a2), (b1, b2)):
            np.testing.assert_array_equal(first.corridor, second.corridor)
            self.assertFalse(first.corridor.flags.writeable)
            self.assertLessEqual(first.entry_window.end, first.exit_window.end)
            for prior, after in zip(('pass1', 'pass2', 'pass3'), ('pass2', 'pass3', 'pass4')):
                self.assertFalse(np.any((first.passes[after] <= 0) & (first.passes[prior] > 0)))
        np.testing.assert_array_equal(self.offline, original)
        with self.assertRaises(NoCorridorError) as caught:
            evaluate(TimeWindow(5, 6))
        self.assertEqual(caught.exception.stage, 'pass3')

    def test_driving_limit_matches_linear_tube(self):
        p = self.planner
        tube = np.asarray(p.grid.coordinate_vectors[0])[None, :] - p.times[:, None]
        limits = p.control_limits(tube, [0.], 0)
        # V(t+dt,0)+dt*dV/dx*u = -.1+.1*u <= 0.
        self.assertAlmostEqual(limits.a, -.1, places=6)
        np.testing.assert_allclose(limits.b, [.1], atol=1e-6)
        with self.assertRaises(ValueError):
            p.control_limits(tube, [0.], len(p.times)-1)
        with self.assertRaises(ValueError):
            p.control_limits(tube, [4.], 0)

    def test_bicycle5d_and_copied_maps_on_real_backend(self):
        spec = GridSpec.bicycle5d(horizon=.2, time_step=.1, shape=(9, 9, 17, 3, 3))
        p = LTMSPlanner.bicycle5d(spec)
        regions = create_4way(p.grid)
        rules = route_constraints(regions, 'entry_e', 'exit_w')
        self.assertEqual(rules.shape, (9, 9, 17, 3, 3))
        # Westbound road crosses the heading seam; both sides must be present.
        h = np.asarray(p.grid.coordinate_vectors[2])
        west = rectangle(p.grid, [np.pi-np.pi/5], [-np.pi+np.pi/5], axes=[2])
        self.assertTrue((west[:, :, 0] <= 0).all())
        self.assertTrue((west[:, :, -1] <= 0).all())
        self.assertTrue((west[:, :, np.argmin(abs(h))] > 0).all())
        chaos = create_chaos(p.grid, 'full', 'init')
        self.assertEqual(chaos['init'].shape, rules.shape)
        target = rectangle(p.grid, [-.5, -.5], [.5, .5])
        tube = p.reach(target, -np.ones(p.grid.shape))
        self.assertEqual(tube.shape, (3, 9, 9, 17, 3, 3))
        self.assertTrue(np.isfinite(tube).all())
        np.testing.assert_array_equal(tube[-1] <= 0, target <= 0)

    def test_explicit_reservations_prune_pass2_without_mutating_inputs(self):
        class PlanarIntegrator(SingleIntegrator):
            def open_loop_dynamics(self, state, time):
                return jnp.zeros(2)

            def control_jacobian(self, state, time):
                return jnp.array([[1.], [0.]])

            def disturbance_jacobian(self, state, time):
                return jnp.zeros((2, 1))

        p = LTMSPlanner(TVHJImpl(dict(cls=PlanarIntegrator), [
            dict(name='t', bounds=[0, 2], points=21),
            dict(name='x', bounds=[-2, 3], points=101),
            dict(name='y', bounds=[-1, 1], points=11)], accuracy='low'))
        x, y = map(np.asarray, p.grid.coordinate_vectors)
        occupied = np.broadcast_to((abs(x[:, None]) <= .2) & (y[None, :] < -.2),
                                   (len(p.times), len(x), len(y))).copy()
        reservation = SpatialReservation(p.times+10, x, y, occupied)
        result = p.analyze(entry=rectangle(p.grid, [-.8], [-.2]),
                           goal=rectangle(p.grid, [.4], [1.]),
                           constraints=-np.ones(p.grid.shape),
                           reservations=[reservation], time_origin=10,
                           policy=WindowPolicy(.1, .3, .1, .4))
        self.assertTrue(np.any((result.passes['pass1'] <= 0) & occupied))
        self.assertFalse(np.any((result.passes['pass2'] <= 0) & occupied))
        np.testing.assert_array_equal(reservation.positions, occupied)
        projected = result.reservation(body_radius=.1)
        np.testing.assert_array_equal(projected.positions, result.corridor <= 0)
        np.testing.assert_allclose(projected.times, p.times+10)
