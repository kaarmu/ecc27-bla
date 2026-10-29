from fractions import Fraction as F
import unittest

from ltms_bla import model as M


class CrossingModelTests(unittest.TestCase):
    def test_declared_reference_fulfils_the_task_exactly(self):
        argument = M.client_argument(0, 9)
        self.assertTrue(all(argument[k] for k in ('body_in_lane', 'body_clear_at_exit', 'reaches_exit', 'timely')))
        self.assertEqual(argument['exit_x'], F('1.55'))
        self.assertEqual(argument['body_y'], (F('-0.58'), F('-0.22')))
        self.assertEqual(M.reference(7), (F('1.55'), F('-0.4'), 0, 0, F('0.45')))

    def test_failing_references_are_detected(self):
        slower = M.client_argument(0, 9, speed=.35)
        self.assertFalse(slower['body_clear_at_exit'] or slower['reaches_exit'])
        self.assertFalse(M.client_argument(3, 9)['timely'])
        self.assertFalse(M.client_argument(0, 9, lateral=-.7)['body_in_lane'])

    def test_deadline_relations(self):
        for s in range(5):
            for d in range(s+1, s+12):
                # The TLT window [s+7, s+8] inside [s, d] strengthens 'clear by d'.
                if M.tlt_evidence_applies(s, d):
                    self.assertIn(s, M.eligible_departures((s,), d))
        self.assertEqual(M.eligible_departures((0, 1, 2), 8), (0, 1))
        self.assertTrue(M.speed_bound_excludes(20, 22))   # 0.6 * 2 < 3
        self.assertFalse(M.speed_bound_excludes(20, 25))  # 0.6 * 5 >= 3
        self.assertTrue(M.eligible_departures((30,), 37) and not M.tlt_evidence_applies(30, 37))

    def test_masks_and_full_body(self):
        self.assertEqual([r['holds'] for r in M.mask_to_task()], [True, False, True, False])

    def test_selection_reads_only_the_promise(self):
        self.assertEqual(M.select_departure((0, 1), 9, {0, 1}), 0)
        self.assertEqual(M.select_departure((0, 1), 9, {1}), 1)
        self.assertIsNone(M.select_departure((0, 3), 9, {3}))
        self.assertIsNone(M.select_departure((0, 1), 9, set()))
