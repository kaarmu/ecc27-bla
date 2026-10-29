import unittest
try:
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest('optional numerical geometry tests need numpy') from error

from ltms_bla import model as M
from ltms_bla.checks import boxes_disjoint, minimum_body_gap, reference_coverage


class CorridorGeometryTests(unittest.TestCase):
    def test_closed_cell_contact_is_rejected(self):
        a = np.zeros((2, 7, 7), bool)
        b = a.copy()
        a[:, 2, 2] = True
        b[:, 3, 2] = True
        self.assertFalse(boxes_disjoint(a, b))
        b[:] = False
        b[:, 4, 2] = True
        self.assertTrue(boxes_disjoint(a, b))

    def test_continuous_relative_motion_detects_between_sample_collision(self):
        times = np.array([0., 2.])
        a = np.array([[-1., 0.], [1., 0.]])
        b = np.array([[1., 0.], [-1., 0.]])
        self.assertAlmostEqual(minimum_body_gap(times, a, times, b, .18), -.36)
        b[:, 1] = .8
        self.assertAlmostEqual(minimum_body_gap(times, a, times, b, .18), .44)

    def test_reference_coverage_needs_every_swept_box(self):
        times = np.arange(0, 9.01, .25)
        rx, ry = np.arange(-2.6, 2.61, .1), np.arange(-1, .21, .1)
        x0, y0 = M.ENTRY[:2]
        reserved = np.zeros((len(times), len(rx), len(ry)), bool)
        for i, t in enumerate(times):
            a = x0 + M.SPEED*min(t, M.CROSSING)
            b = x0 + M.SPEED*min(t+.25, M.CROSSING)
            reserved[i] = ((rx[:, None] >= a-.35) & (rx[:, None] <= b+.35)
                           & (abs(ry[None, :]-y0) <= .35))
        self.assertTrue(reference_coverage(reserved, rx, ry, times))
        # A reference departing one second later is not covered by this reservation.
        self.assertFalse(reference_coverage(reserved, rx, ry, times, delay=1.))
        # Presence before the reservation's time zero is never covered.
        self.assertFalse(reference_coverage(reserved, rx, ry, times, delay=-1.))
        thin = reserved & (abs(ry[None, None, :]-y0) <= .1)
        self.assertFalse(reference_coverage(thin, rx, ry, times))
