import unittest
try:
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest('optional numerical geometry tests need numpy') from error

from ltms_bla.checks import aligned_disjoint, boxes_disjoint


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

    def test_shifted_reservations_compare_neighbouring_slabs(self):
        a = np.zeros((4, 7, 7), bool)
        a[3, 2, 2] = True
        b = np.zeros((4, 7, 7), bool)
        b[0, 2, 2] = True
        self.assertTrue(aligned_disjoint(a, 0, b, 1, 1.))   # b's slab 0 lands on a's slab 1: two slabs apart
        self.assertFalse(aligned_disjoint(a, 0, b, 2, 1.))  # neighbouring slabs (2 and 3) count as meeting
        self.assertFalse(aligned_disjoint(a, 0, b, 3, 1.))  # same slab
        self.assertTrue(aligned_disjoint(a, 0, b, 5, 1.))   # no common time
