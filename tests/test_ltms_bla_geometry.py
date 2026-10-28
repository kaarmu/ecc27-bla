import unittest
try:
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest('optional numerical geometry tests need numpy') from error

from ltms_bla.checks import boxes_disjoint, minimum_body_gap


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
