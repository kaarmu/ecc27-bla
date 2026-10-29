import unittest
try:
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest('optional numerical geometry tests need numpy') from error

from ltms_bla.checks import aligned_disjoint, boxes_covered, boxes_disjoint, minimum_separation


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
        self.assertAlmostEqual(minimum_separation(times, a, times, b), 0.)  # they meet at t=1
        b[:, 1] = .8
        self.assertAlmostEqual(minimum_separation(times, a, times, b), .8)

    def test_box_coverage_needs_every_cell_a_box_meets(self):
        rx, ry = np.arange(-1, 1.01, .1), np.arange(-1, 1.01, .1)
        reserved = np.zeros((2, len(rx), len(ry)), bool)
        reserved[0, 8:13, 8:13] = True  # cells centred on [-0.2, 0.2]^2
        self.assertTrue(boxes_covered(reserved, rx, ry, [(0, -.1, .1, -.1, .1)]))
        # A box reaching into the next cell's closure, or on another slab, is not covered.
        self.assertFalse(boxes_covered(reserved, rx, ry, [(0, -.1, .26, -.1, .1)]))
        self.assertFalse(boxes_covered(reserved, rx, ry, [(1, -.1, .1, -.1, .1)]))

    def test_shifted_reservations_compare_neighbouring_slabs(self):
        a = np.zeros((4, 7, 7), bool)
        a[3, 2, 2] = True
        b = np.zeros((4, 7, 7), bool)
        b[0, 2, 2] = True
        self.assertTrue(aligned_disjoint(a, 0, b, 1, 1.))   # b's slab 0 lands on a's slab 1: two slabs apart
        self.assertFalse(aligned_disjoint(a, 0, b, 2, 1.))  # neighbouring slabs (2 and 3) count as meeting
        self.assertFalse(aligned_disjoint(a, 0, b, 3, 1.))  # same slab
        self.assertTrue(aligned_disjoint(a, 0, b, 5, 1.))   # no common time
