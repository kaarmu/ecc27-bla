from dataclasses import dataclass
import unittest

import interval_logic as il


@dataclass(frozen=True)
class FiniteStateSet:
    values: frozenset[int]
    universe: frozenset[int]

    def intersection(self, other):
        return FiniteStateSet(self.values & other.values, self.universe)

    def union(self, other):
        return FiniteStateSet(self.values | other.values, self.universe)

    def complement(self):
        return FiniteStateSet(self.universe - self.values, self.universe)

    def difference(self, other):
        return FiniteStateSet(self.values - other.values, self.universe)

    def is_empty(self):
        return not self.values

    def is_subset(self, other):
        return self.values <= other.values

    def normalize(self):
        return self


class FiniteSystem:
    def __init__(self):
        self._universe = frozenset({0, 1, 2})
        self.transitions = {0: {0, 1}, 1: {1, 2}, 2: {2}}

    @property
    def admissible_states(self):
        return self._set(self._universe)

    def atom(self, atom):
        if isinstance(atom, il.Proposition):
            values = {"p": {2}, "q": {1}}.get(atom.name, set())
            return self._set(values)
        raise il.UnsupportedReachabilityError("equalities are absent in this model")

    def predecessor(self, states):
        return self._set(
            state
            for state, successors in self.transitions.items()
            if successors & states.values
        )

    def constrained_reach(self, target, constraint, parameter, anchor):
        if isinstance(parameter, il.RelativeParameter):
            if parameter.duration != 0:
                raise il.UnsupportedTemporalParameterError("physical time unavailable")
            return target if parameter.include_endpoint else self._set(set())
        if isinstance(parameter, il.AbsoluteParameter):
            raise il.UnsupportedTemporalParameterError("physical time unavailable")
        current = target
        while True:
            following = target.union(constraint.intersection(self.predecessor(current)))
            if following == current:
                return current
            current = following

    def existential_invariance(self, safe, parameter, anchor):
        if isinstance(parameter, il.RelativeParameter):
            if parameter.duration != 0:
                raise il.UnsupportedTemporalParameterError("physical time unavailable")
            return safe if parameter.include_endpoint else self.admissible_states
        if isinstance(parameter, il.AbsoluteParameter):
            raise il.UnsupportedTemporalParameterError("physical time unavailable")
        current = self.admissible_states
        while True:
            following = safe.intersection(self.predecessor(current))
            if following == current:
                return current
            current = following

    def certify_conjunction(self, formula, operands, anchor):
        return False

    def _set(self, values):
        return FiniteStateSet(frozenset(values), self._universe)


class ReachabilityTests(unittest.TestCase):
    def setUp(self):
        self.system = FiniteSystem()

    def test_eventual_reachability_uses_predecessor_fixed_point(self):
        result = il.reach("eventually p", self.system, 0)
        self.assertEqual(result.tlt_set.values, frozenset({0, 1, 2}))
        self.assertTrue(result.certified)

    def test_state_local_and_is_certified(self):
        result = il.reach("p and not q", self.system, 0)
        self.assertEqual(result.tlt_set.values, frozenset({2}))
        self.assertTrue(result.certified)

    def test_temporal_conjunction_exposes_leaking_corner(self):
        result = il.reach("eventually p and eventually q", self.system, 0)
        self.assertEqual(result.tlt_set.values, frozenset({0, 1}))
        self.assertFalse(result.certified)

    def test_selector_reduces_locally_without_temporal_backend_call(self):
        closed = il.reach(il.Selection("p", "q", "0]"), self.system, 0)
        opened = il.reach(il.Selection("p", "q", 0), self.system, 0)
        positive = il.reach(il.Selection("p", "q", 50), self.system, 0)
        self.assertEqual(closed.tlt_set.values, frozenset({2}))
        self.assertEqual(opened.tlt_set.values, frozenset({1}))
        self.assertEqual(positive.tlt_set.values, frozenset({2}))

        nested = il.reach(il.Eventually(il.Selection("p", "q", 50)), self.system, 0)
        self.assertEqual(nested.tlt_set.values, frozenset({0, 1, 2}))
        self.assertTrue(nested.certified)

    def test_absolute_selector_requires_future_anchor_information(self):
        inside = il.reach(il.Selection("p", "q", "[2,5]"), self.system, 3)
        outside = il.reach(il.Selection("p", "q", "[2,5]"), self.system, 1)
        self.assertEqual(inside.tlt_set.values, frozenset({2}))
        self.assertEqual(outside.tlt_set.values, frozenset({1}))

        with self.assertRaises(il.UnsupportedTemporalParameterError):
            il.reach(
                il.Eventually(il.Selection("p", "q", "[2,5]")),
                self.system,
                0,
            )

    def test_zero_release_and_weak_until_reduce_before_dispatch(self):
        release_closed = il.reach(il.Release("p", "q", "0]"), self.system, 0)
        release_open = il.reach(il.Release("p", "q", 0), self.system, 0)
        weak_closed = il.reach(il.WeakUntil("p", "q", "0]"), self.system, 0)
        weak_open = il.reach(il.WeakUntil("p", "q", 0), self.system, 0)

        self.assertEqual(release_closed.tlt_set.values, frozenset({1}))
        self.assertEqual(release_open.tlt_set.values, frozenset({0, 1, 2}))
        self.assertEqual(weak_closed.tlt_set.values, frozenset({1, 2}))
        self.assertEqual(weak_open.tlt_set.values, frozenset({0, 1, 2}))
        self.assertTrue(release_closed.certified)
        self.assertTrue(release_open.certified)
        self.assertTrue(weak_closed.certified)
        self.assertTrue(weak_open.certified)

    def test_quantitative_condition_is_rejected(self):
        with self.assertRaises(il.UnsupportedTemporalParameterError):
            il.reach("eventually_2] p", self.system, 0)
        with self.assertRaises(il.UnsupportedTemporalParameterError):
            il.reach(il.Eventually("p", "[2,5]"), self.system, 0)

    def test_wait_loops_make_unbounded_existential_invariance_explicit(self):
        result = il.reach("always p", self.system, 0)
        self.assertEqual(result.tlt_set.values, frozenset({2}))
        self.assertTrue(result.certified)


if __name__ == "__main__":
    unittest.main()
