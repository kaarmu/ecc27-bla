"""Executable regression coverage for the notebook-led booking protocol."""

from dataclasses import replace
from functools import lru_cache
from fractions import Fraction as F
from itertools import product
from importlib.util import find_spec
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

import interval_logic as il
import portion as P


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "protocol.ipynb"
HAS_PLOTLY = find_spec("plotly") is not None


@lru_cache(maxsize=1)
def protocol_definitions():
    """Import background normally; load only the actual notebook's method cells."""
    import protocol as background
    notebook = json.loads(NOTEBOOK.read_text())
    module = types.ModuleType("_protocol_notebook_under_test")
    module.__dict__.update({name: getattr(background, name) for name in background.__all__})
    sys.modules[module.__name__] = module
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code" and "definitions" in cell.get("metadata", {}).get("tags", []):
            exec(compile("".join(cell["source"]), f"{NOTEBOOK}:cell_{index}", "exec"), module.__dict__)
    return module


class ProtocolNotebookExecutionTests(unittest.TestCase):
    def test_background_import_is_independent_of_plotly_and_notebook(self):
        script = """
import builtins
original = builtins.__import__
def no_plotly(name, *args, **kwargs):
    if name == 'plotly' or name.startswith('plotly.'):
        raise ImportError('optional plotting unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = no_plotly
import protocol
assert protocol.decide_booking(protocol.Booking(1, __import__('portion').closedopen(1, 2)).contract).satisfiable
assert not any(hasattr(protocol, name) for name in ('admit', 'generate', 'bargain', 'commit'))
"""
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(find_spec('nbclient') and HAS_PLOTLY, 'Install the notebook dependency group')
    def test_every_cell_in_fresh_kernels_from_both_working_directories(self):
        import tempfile
        import nbformat
        from nbclient import NotebookClient
        from jupyter_client import KernelManager
        for directory in (ROOT, ROOT / 'notebooks'):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as temporary:
                notebook = nbformat.read(NOTEBOOK, as_version=4)
                export = next(c for c in notebook.cells if 'export' in c.metadata.get('tags', []))
                export.source = 'EXPORT_PATH = Path(' + repr(str(Path(temporary) / 'timelines.html')) + ')\n' + export.source
                km = KernelManager(kernel_name='python3')
                km.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
                client = NotebookClient(notebook, km=km, timeout=120, resources={'metadata': {'path': str(directory)}})
                client.execute(cleanup_kc=True)
                self.assertTrue((Path(temporary) / 'timelines.html').is_file())
                self.assertFalse(any(o.output_type == 'error' for c in notebook.cells if c.cell_type == 'code' for o in c.outputs))




class BookingProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = protocol_definitions()

    def fixture(self, starts=P.closedopen(1, 5), duration=F(1), raw=((1, P.closedopen(2, 3)),), now=0):
        p = self.p
        commitment = p.standing(*(p.Booking(client, window) for client, window in raw))
        request = p.Request(2, p.Service(starts, duration))
        return commitment, request, p.admit(request, commitment, now)

    def test_admission_boundaries_and_component_representatives(self):
        fixtures = (
            (P.closed(0, 4), F(1), (), 0),
            (P.closedopen(1, 5), F(1), ((1, P.closedopen(2, 3)),), 0),
            (P.closed(1, 2), F(1), ((1, P.closedopen(0, 4)),), 0),
            (P.closed(0, 3), F(1), ((1, P.closedopen(0, 1)), (3, P.closedopen(2, 4))), 0),
            (P.openclosed(1, 3), F(1), ((1, P.closedopen(0, 1)), (3, P.closedopen(2, 4))), 0),
            (P.singleton(1) | P.open(3, 4) | P.singleton(5), F(1), (), 0),
            (P.closed(1, 3), F(1), ((2, P.closedopen(1, 4)),), 0),
            (P.closed(0, 2), F(1, 3), ((1, P.closedopen(F(2, 3), F(4, 3))),), 0),
            (P.closed(1, 5), F(1), ((1, P.closedopen(2, 3)),), F(7, 2)),
            (P.empty(), F(1), (), 0),
        )
        for starts, duration, raw, now in fixtures:
            with self.subTest(starts=starts, duration=duration, raw=raw, now=now):
                commitment, request, admission = self.fixture(starts, duration, raw, now)
                expected = starts & P.closedopen(now, P.inf)
                for client, window in raw:
                    if client != request.client:
                        expected -= P.open(window.lower - duration, window.upper)
                self.assertEqual(admission is not None, not expected.empty)
                offers = self.p.generate(admission)
                grid = tuple(c.lower + n * duration / 2 for c in expected
                             for n in range(int(2 * (c.upper - c.lower) // duration) + 1)
                             if c.lower + n * duration / 2 in c)
                self.assertEqual(tuple(o.start for o in offers), grid)
                if admission is None:
                    continue
                self.assertEqual(admission.feasible_starts, expected)
                self.assertEqual(admission.commitment, commitment)
                self.assertEqual(admission.service, request.service)
                decision = self.p.decide_booking(admission.obligations, now)
                self.assertTrue(decision.satisfiable)
                self.assertEqual(decision.feasible_starts, expected)
                self.assertEqual(decision.normalized.guarantee, admission.obligations.guarantee)
                for start, offer in zip(grid, offers, strict=True):
                    self.assertEqual(offer.interval, P.closedopen(start, start + duration))
                    self.assertTrue(offer.certificate.certified)
                    self.assertTrue(offer.certificate.compatible)
                    self.assertEqual(offer.contract.assumption.simplify(), il.Boolean(True))

    def test_feasible_open_component_without_grid_points_does_not_commit(self):
        p = self.p
        commitment, request, admission = self.fixture(P.open(3, F(13, 4)), 1)
        self.assertIsNotNone(admission)
        offers = p.generate(admission)
        self.assertEqual(offers, ())
        policies = p.affine_policies({}, {})
        failed = p.bargain(offers, policies, {'owner': 1, 'client': 1}, {'owner': 0, 'client': 0})
        result = p.commit(admission, offers, failed, commitment)
        self.assertEqual(result.status, 'NO-BLA')
        self.assertIs(result.commitment, commitment)
        self.assertEqual(result.ledger, ())

    def test_generation_inherits_evidence_without_certification_or_sat_queries(self):
        p = self.p
        _, _, admission = self.fixture()
        with patch.object(p, 'certify_offer', side_effect=AssertionError('independent validation called')), \
                patch.object(p, 'decide_booking', side_effect=AssertionError('SAT called')), \
                patch('protocol.bookings.decide_booking', side_effect=AssertionError('SAT called')), \
                patch('protocol.verification.decide_booking', side_effect=AssertionError('SAT called')):
            offers = p.generate(admission)
        self.assertEqual(tuple(o.start for o in offers), (F(1), F(3), F(7, 2), F(4), F(9, 2)))
        for offer in offers:
            self.assertIn(offer.start, admission.feasible_starts)
            self.assertEqual(offer.certificate, p.certify_offer(admission, offer.booking))

    def test_exact_feasibility_agrees_with_an_independent_intersection_oracle(self):
        for duration, block in product(
            (F(1, 3), F(2, 3), F(2)),
            (P.closedopen(1, 2), P.closedopen(F(4, 3), F(7, 3))),
        ):
            _, _, admission = self.fixture(P.closed(0, 4), duration, ((1, block),))
            self.assertIsNotNone(admission)
            self.assertEqual(self.p.independent_feasible_starts(admission.service,
                             (self.p.Booking(1, block),), 2), admission.feasible_starts)
            for start in (F(index, 6) for index in range(25)):
                with self.subTest(duration=duration, block=block, start=start):
                    expected = (P.closedopen(start, start + duration) & block).empty
                    self.assertEqual(start in admission.feasible_starts, expected)

    def test_supported_booking_decision_rejects_unknown_formulas(self):
        p = self.p
        request = il.Eventually(il.Always(p.acc.equals(2), 1), P.closed(1, 3))
        unsupported = (
            il.Proposition("unresolved"),
            il.Always(il.Proposition("unresolved"), P.closedopen(1, 2)),
            il.Always(p.use.equals(2), P.closedopen(1, 2)),
            il.Always(p.acc.equals(p.use), P.closedopen(1, 2)),
            il.Always(p.acc.equals(2), 2),
            request & il.Eventually(il.Always(p.acc.equals(3), 1), P.closed(1, 3)),
            request & il.Eventually(il.Always(p.acc.equals(2), 2), P.closed(1, 3)),
            il.Eventually(il.Always(p.acc.equals(2), "1]"), P.closed(1, 3)),
        )
        for formula in unsupported:
            with self.subTest(formula=str(formula)):
                with self.assertRaises(p.UnsupportedContractError):
                    p.decide_booking(p.Contract(True, formula))
        with self.assertRaises(p.UnsupportedContractError):
            p.decide_booking(p.Contract(il.Proposition("condition"), True))
        self.assertFalse(p.decide_booking(p.Contract(True, False)).satisfiable)
        self.assertTrue(p.decide_booking(p.Contract(True, True)).satisfiable)
        conflicting = p.standing(p.Booking(1, P.closedopen(1, 2)), p.Booking(2, P.closedopen(1, 2)))
        self.assertFalse(p.decide_booking(conflicting).satisfiable)
        with self.assertRaises(ValueError):
            p.admit(p.Request(3, p.Service(P.singleton(3), 1)), conflicting)

    def test_service_and_booking_input_validation(self):
        p = self.p
        for duration in (0, -1, True, float("inf"), float("nan")):
            with self.subTest(duration=duration):
                with self.assertRaises((TypeError, ValueError)):
                    p.Service(P.closed(1, 2), duration)
        for starts in (P.closed(-1, 2), P.closedopen(0, P.inf)):
            with self.assertRaises((TypeError, ValueError)):
                p.Service(starts, 1)
        for client in (0, -1, True, F(1)):
            with self.assertRaises(ValueError):
                p.Request(client, p.Service(P.singleton(1), 1))
        for window in (P.empty(), P.closed(1, 2), P.open(1, 2), P.singleton(1) | P.singleton(3)):
            with self.assertRaises(ValueError):
                p.Booking(2, window)

    def test_permitted_adaptations_are_readmitted_in_order(self):
        p = self.p
        commitment = p.standing(p.Booking(1, P.closedopen(2, 3)))
        original = p.Service(P.singleton(F(3, 2)), 1)
        shorter = p.Service(P.singleton(F(3, 2)), F(1, 2))
        expanded = p.Service(P.closed(F(3, 2), 3), 1)
        shifted = p.Service(P.singleton(3), 1)
        selected = p.admit(p.Request(2, original, (original, shorter, shifted)), commitment)
        self.assertEqual(selected.service, shorter)
        self.assertEqual(selected.feasible_starts, shorter.starts)
        for alternative in (shorter, expanded, shifted):
            with self.subTest(alternative=alternative):
                result = p.admit(p.Request(2, original, (alternative,)), commitment)
                self.assertEqual(result.service, alternative)
                access, _, _, client, task = p.service_contracts(2, alternative)
                self.assertEqual(result.client_contract, client)
                self.assertEqual(result.task, task)
                self.assertEqual(result.quotient.guarantee, p.normalize(access))
        self.assertIsNone(p.admit(p.Request(2, original, (original,)), commitment))
        self.assertEqual(commitment, p.standing(p.Booking(1, P.closedopen(2, 3))))
        feasible = p.Request(2, shifted, (shorter,))
        self.assertEqual(p.admit(feasible, commitment).service, shifted)

    def test_adaptation_refinement_claims_and_incomparable_client_contracts(self):
        p = self.p
        original = p.Service(P.singleton(1), 2)
        shorter = p.Service(P.singleton(1), 1)
        shifted = p.Service(P.singleton(4), 2)
        expanded = p.Service(P.singleton(1) | P.singleton(4), 2)
        contracts = {
            name: p.service_contracts(2, service)
            for name, service in (("original", original), ("shorter", shorter),
                                  ("shifted", shifted), ("expanded", expanded))
        }
        owners = {
            name: p.admit(p.Request(2, service), p.standing()).obligations
            for name, service in (("original", original), ("shorter", shorter),
                                  ("shifted", shifted), ("expanded", expanded))
        }

        def trace(access, usage):
            return il.Trace(p.FULL, signals={
                "acc": il.NaturalSignal({2: access}, default=0),
                "use": il.NaturalSignal({2: usage}, default=0),
            })

        regions = (P.empty(), P.closedopen(1, 2), P.closedopen(1, 3),
                   P.closedopen(4, 6), P.closedopen(1, 3) | P.closedopen(4, 6))
        for access, usage in product(regions, repeat=2):
            behavior = trace(access, usage)
            holds = lambda formula: il.satisfies(formula, behavior, 0)
            for adapted in ("shorter", "expanded"):
                with self.subTest(access=access, usage=usage, adapted=adapted):
                    if holds(contracts["original"][4].guarantee):
                        self.assertTrue(holds(contracts[adapted][4].guarantee))
                    if holds(owners["original"].guarantee):
                        self.assertTrue(holds(owners[adapted].guarantee))

        original_client, shorter_client = contracts["original"][3], contracts["shorter"][3]
        # Original <= shorter would require A_shorter to imply A_original.
        only_short_access = trace(P.closedopen(1, 2), P.empty())
        self.assertTrue(il.satisfies(shorter_client.assumption, only_short_access, 0))
        self.assertFalse(il.satisfies(original_client.assumption, only_short_access, 0))
        # Shorter <= original would require G_shorter to imply G_original.
        only_short_use = trace(P.closedopen(1, 3), P.closedopen(1, 2))
        self.assertTrue(il.satisfies(original_client.assumption, only_short_use, 0))
        self.assertTrue(il.satisfies(shorter_client.assumption, only_short_use, 0))
        self.assertTrue(il.satisfies(shorter_client.guarantee, only_short_use, 0))
        self.assertFalse(il.satisfies(original_client.guarantee, only_short_use, 0))

        # Replacing the window can make both task and owner obligations incomparable.
        for present, absent, window in (("original", "shifted", P.closedopen(1, 3)),
                                        ("shifted", "original", P.closedopen(4, 6))):
            behavior = trace(window, window)
            self.assertTrue(il.satisfies(contracts[present][4].guarantee, behavior, 0))
            self.assertFalse(il.satisfies(contracts[absent][4].guarantee, behavior, 0))
            self.assertTrue(il.satisfies(owners[present].guarantee, behavior, 0))
            self.assertFalse(il.satisfies(owners[absent].guarantee, behavior, 0))

    def test_refinement_certification_is_independent_of_compatibility(self):
        p = self.p
        _, _, admission = self.fixture()
        collision = p.certify_offer(admission, p.Booking(2, P.closedopen(2, 3)))
        self.assertTrue(collision.same_client)
        self.assertTrue(collision.duration_matches)
        self.assertTrue(collision.start_allowed)
        self.assertTrue(collision.not_past)
        self.assertTrue(collision.certified)
        self.assertFalse(collision.compatible)
        for booking in (
            p.Booking(3, P.closedopen(4, 5)),
            p.Booking(2, P.closedopen(0, 1)),
            p.Booking(2, P.closedopen(1, F(3, 2))),
        ):
            certificate = p.certify_offer(admission, booking)
            self.assertFalse(certificate.certified)
            self.assertTrue(certificate.compatible)
        with self.assertRaises(TypeError):
            p.certify_offer(admission, p.Contract(True, True))

    def test_quotient_admission_and_joint_task_have_the_paper_semantics(self):
        p = self.p
        service = p.Service(P.singleton(1) | P.singleton(2), 1)
        access, usage, rule, client, task = p.service_contracts(2, service)
        quotient = task.quotient(client).normalize()
        commitment = p.standing(p.Booking(1, P.closedopen(0, 1)))
        raw = commitment.conjoin(quotient)
        admitted = p.admit(p.Request(2, service), commitment)
        joint = client.compose(admitted.obligations)
        # Exhaust independent access/use choices in two candidate booking windows.
        for standing_holds, access_bits, use_bits in product(
            (False, True), product((False, True), repeat=2), product((False, True), repeat=2)
        ):
            access_region = P.empty()
            use_region = P.empty()
            for start, present in zip((1, 2), access_bits):
                if present:
                    access_region |= P.closedopen(start, start + 1)
            for start, present in zip((1, 2), use_bits):
                if present:
                    use_region |= P.closedopen(start, start + 1)
            trace = il.Trace(p.FULL, signals={
                "acc": il.NaturalSignal({1: P.closedopen(0, 1) if standing_holds else P.empty(),
                                         2: access_region}, default=0),
                "use": il.NaturalSignal({2: use_region}, default=0),
            })
            holds = lambda formula: il.satisfies(formula, trace, 0)
            with self.subTest(standing=standing_holds, access=access_bits, use=use_bits):
                self.assertEqual(holds(quotient.assumption), holds(~access | (rule & usage)))
                self.assertEqual(holds(quotient.guarantee), holds(access))
                self.assertTrue(holds(admitted.obligations.assumption))
                self.assertEqual(holds(admitted.obligations.guarantee), holds(commitment.guarantee & access))
                self.assertTrue(holds(joint.assumption))
                self.assertEqual(holds(joint.guarantee), holds(commitment.guarantee & access & rule & usage))
                self.assertEqual(il.denote(raw.guarantee, trace, 0),
                                 il.denote(admitted.obligations.guarantee, trace, 0))

    def test_access_and_use_have_independent_witnesses_without_absence_release(self):
        p = self.p
        _, request, admission = self.fixture(raw=())
        offer = p.generate(admission)[0]
        _, _, rule, client, task = p.service_contracts(2, request.service)
        independent = il.Trace(p.FULL, signals={
            "acc": il.NaturalSignal({2: P.closedopen(1, 2) | P.closedopen(3, 4)}, default=0),
            "use": il.NaturalSignal({2: P.closedopen(3, 4)}, default=0),
        })
        self.assertTrue(il.satisfies(client.assumption & client.guarantee, independent, 0))
        self.assertTrue(il.satisfies(offer.contract.guarantee, independent, 0))
        completed = client.compose(admission.commitment.conjoin(offer.contract))
        target = admission.commitment.conjoin(task)
        self.assertTrue(il.satisfies(completed.assumption & completed.guarantee, independent, 0))
        self.assertTrue(il.satisfies(target.guarantee, independent, 0))
        absent = il.Trace(p.FULL, signals={
            "acc": il.NaturalSignal({2: P.closedopen(1, 2)}, default=0),
            "use": il.NaturalSignal({}, default=0),
        })
        self.assertTrue(il.satisfies(offer.contract.guarantee, absent, 0))
        absent_without_access = il.Trace(p.FULL, signals={
            "acc": il.NaturalSignal({}, default=0),
            "use": il.NaturalSignal({}, default=0),
        })
        self.assertFalse(il.satisfies(offer.contract.guarantee, absent_without_access, 0))
        circular = p.Contract(rule, offer.contract.guarantee)
        counterexample = il.Trace(p.FULL, signals={
            "acc": il.NaturalSignal({}, default=0),
            "use": il.NaturalSignal({2: P.closedopen(1, 2)}, default=0),
        })
        self.assertTrue(il.satisfies(client.guarantee, counterexample, 0))
        self.assertTrue(il.satisfies(circular.guarantee, counterexample, 0))
        self.assertFalse(il.satisfies(task.guarantee, counterexample, 0))
        self.assertFalse(il.satisfies(offer.contract.guarantee, counterexample, 0))


class BargainingProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = protocol_definitions()

    def setUp(self):
        p = self.p
        self.commitment = p.standing(p.Booking(1, P.closedopen(2, 3)))
        self.admission = p.admit(p.Request(2, p.Service(P.closedopen(1, 5), 1)), self.commitment)
        self.offers = p.generate(self.admission)
        self.costs = {o: F(3, 2) + o.start / 2 for o in self.offers}
        self.values = {o: F(17, 2) - o.start / 2 for o in self.offers}
        self.policies = p.affine_policies(self.costs, self.values)
        self.targets = {"owner": F(4), "client": F(6)}
        self.minima = {"owner": F(1), "client": F(1)}

    def bargain(self, **kwargs):
        return self.p.bargain(self.offers, kwargs.pop("policies", self.policies),
                              kwargs.pop("targets", self.targets),
                              kwargs.pop("minima", self.minima), **kwargs)

    def test_one_priced_offer_per_round_targets_and_earliest_ties(self):
        p = self.p
        targets, minima = dict(self.targets), dict(self.minima)
        result = self.bargain()
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(result.agreement, p.PricedOffer(self.offers[0], F(9, 2)))
        self.assertEqual([r.proposer for r in result.history], ["owner", "client"])
        self.assertEqual([r.proposal.price for r in result.history], [F(6), F(9, 2)])
        self.assertEqual(dict(result.history[1].targets), {"owner": F(5, 2), "client": F(7, 2)})
        for row in result.history:
            self.assertIsInstance(row.proposal, p.PricedOffer)
            self.assertEqual(row.proposal.offer, self.offers[0])
            self.assertGreaterEqual(dict(row.utilities)[row.proposer], dict(row.targets)[row.proposer])
            if row.accepted:
                responder = "client" if row.proposer == "owner" else "owner"
                self.assertGreaterEqual(dict(row.utilities)[responder], self.minima[responder])
        self.assertEqual(self.targets, targets)
        self.assertEqual(self.minima, minima)

    def test_affine_targets_may_already_be_exceeded_at_a_price_boundary(self):
        policies = self.p.affine_policies({o: 0 for o in self.offers},
                                          {o: 20 for o in self.offers})
        owner = policies.propose("owner", self.offers, F(0), (F(1), F(10)))
        client = policies.propose("client", self.offers, F(0), (F(0), F(10)))
        self.assertEqual(owner, self.p.PricedOffer(self.offers[0], F(1)))
        self.assertEqual(client, self.p.PricedOffer(self.offers[0], F(10)))
        self.assertGreater(policies.utility("owner", owner.offer, owner.price), 0)
        self.assertGreater(policies.utility("client", client.offer, client.price), 0)
        for party, target in (("owner", F(11)), ("client", F(21))):
            with self.assertRaises(ValueError):
                policies.propose(party, self.offers, target, (F(0), F(10)))

    def test_last_round_uses_the_same_acceptance_policy_and_bounded_concessions(self):
        calls = []

        def reject(party, proposal, target, minimum):
            calls.append((party, proposal, target, minimum))
            return False

        policies = replace(self.policies, accept=reject)
        for budget in (1, 3):
            calls.clear()
            result = self.bargain(policies=policies, round_budget=budget)
            self.assertEqual(result.status, "NO-BLA")
            self.assertIsNone(result.agreement)
            self.assertEqual(len(result.history), budget)
            self.assertEqual(len(calls), budget)
            self.assertEqual([r.proposer for r in result.history],
                             ["owner", "client", "owner"][:budget])
            for previous, current in zip(result.history, result.history[1:]):
                for party, old in previous.targets:
                    self.assertEqual(dict(current.targets)[party], (old + self.minima[party]) / 2)
                    self.assertLessEqual(dict(current.targets)[party], old)
                    self.assertGreaterEqual(dict(current.targets)[party], self.minima[party])
        # At the last round this deal is above the minimum, yet a declined
        # policy remains a decline. There is no deadline-specific override.
        last = result.history[-1]
        self.assertGreaterEqual(dict(last.utilities)["client"], self.minima["client"])

    def test_invalid_policy_outputs_raise_errors(self):
        p = self.p
        foreign_offer = replace(self.offers[0], booking=p.Booking(2, P.closedopen(9, 10)))
        invalid_proposals = (
            lambda *args: (self.offers[0], F(6)),
            lambda *args: p.PricedOffer(foreign_offer, F(6)),
            lambda *args: p.PricedOffer(self.offers[0], 11),
            lambda *args: p.PricedOffer(self.offers[0], 0),
        )
        for propose in invalid_proposals:
            with self.subTest(propose=propose):
                with self.assertRaises(ValueError):
                    self.bargain(policies=replace(self.policies, propose=propose))
        with self.assertRaises(ValueError):
            self.bargain(policies=replace(self.policies, accept=lambda *args: 1))
        with self.assertRaises(ValueError):
            self.bargain(policies=replace(self.policies, accept=lambda *args: True),
                         minima={"owner": 1, "client": 3})
        for concede in (lambda party, target, minimum: target + 1,
                        lambda party, target, minimum: minimum - 1):
            with self.subTest(concede=concede):
                with self.assertRaises(ValueError):
                    self.bargain(policies=replace(self.policies, accept=lambda *args: False,
                                                 concede=concede), round_budget=2)
        for budget in (0, -1, True, F(2)):
            with self.assertRaises(ValueError):
                self.bargain(round_budget=budget)
        with self.assertRaises(ValueError):
            self.bargain(prices=(10, 0))
        with self.assertRaises(ValueError):
            self.bargain(targets={"owner": 100, "client": 6})
        with self.assertRaises(ValueError):
            self.bargain(targets={"owner": 0, "client": 6})
        invalid_offer = replace(self.offers[0], certificate=p.Certificate(False, False, False, True, True))
        with self.assertRaises(ValueError):
            p.bargain((invalid_offer,), self.policies, self.targets, self.minima)
        empty = p.bargain((), self.policies, self.targets, self.minima)
        self.assertEqual((empty.status, empty.agreement, empty.history), ("NO-BLA", None, ()))

    def test_commit_stores_exact_pair_and_preserves_earlier_obligations(self):
        p = self.p
        previous = p.BLA(p.Booking(1, P.closedopen(2, 3)).contract, F(5))
        negotiation = self.bargain()
        result = p.commit(self.admission, self.offers, negotiation, self.commitment, (previous,))
        self.assertEqual(result.status, "COMMITTED")
        expected = p.BLA(negotiation.agreement.offer.contract, negotiation.agreement.price)
        self.assertEqual(result.agreement, expected)
        self.assertEqual(result.ledger, (previous, expected))
        self.assertEqual(result.commitment, self.commitment.conjoin(expected.contract))
        self.assertTrue(p.decide_booking(result.commitment).satisfiable)
        later = p.admit(p.Request(3, p.Service(P.closed(1, 3), 1)), result.commitment)
        self.assertEqual(later.feasible_starts, P.singleton(3))
        # Idle use does not release either stored access obligation.
        trace = il.Trace(p.FULL, signals={
            "acc": il.NaturalSignal({1: P.closedopen(2, 3), 2: P.closedopen(1, 2)}, default=0),
            "use": il.NaturalSignal({}, default=0),
        })
        self.assertTrue(il.satisfies(result.commitment.guarantee, trace, 0))
        for client, window in ((1, P.closedopen(2, 3)), (2, P.closedopen(1, 2))):
            regions = {1: P.closedopen(2, 3), 2: P.closedopen(1, 2)}
            del regions[client]
            regions[3] = window
            missing = il.Trace(p.FULL, signals={
                "acc": il.NaturalSignal(regions, default=0),
                "use": il.NaturalSignal({}, default=0),
            })
            self.assertFalse(il.satisfies(result.commitment.guarantee, missing, 0))
        failed = self.bargain(policies=replace(self.policies, accept=lambda *args: False), round_budget=1)
        unchanged = p.commit(self.admission, self.offers, failed, self.commitment, (previous,))
        self.assertEqual(unchanged.status, "NO-BLA")
        self.assertIs(unchanged.commitment, self.commitment)
        self.assertEqual(unchanged.ledger, (previous,))
        self.assertIsNone(unchanged.agreement)

    def test_commit_uses_frozen_offers_without_regeneration_or_sat_queries(self):
        p = self.p
        supplied = list(self.offers)
        negotiation = p.bargain(supplied, self.policies, self.targets, self.minima)
        supplied.clear()
        self.assertEqual(negotiation.offers, self.offers)
        with patch.object(p, 'generate', side_effect=AssertionError('regeneration called')), \
                patch.object(p, 'certify_offer', side_effect=AssertionError('independent validation called')), \
                patch.object(p, 'decide_booking', side_effect=AssertionError('SAT called')), \
                patch('protocol.bookings.decide_booking', side_effect=AssertionError('SAT called')), \
                patch('protocol.verification.decide_booking', side_effect=AssertionError('SAT called')):
            committed = p.commit(self.admission, self.offers, negotiation, self.commitment)
        self.assertEqual(committed.agreement, p.BLA(negotiation.agreement.offer.contract,
                                                  negotiation.agreement.price))
        with self.assertRaises(ValueError):
            p.commit(self.admission, self.offers, replace(negotiation, offers=()), self.commitment)

    def test_commit_rejects_changed_snapshot_offer_set_or_accepted_pair(self):
        p = self.p
        result = self.bargain()
        with self.assertRaises(ValueError):
            p.commit(self.admission, self.offers, result,
                     self.commitment.conjoin(p.Booking(4, P.closedopen(8, 9)).contract))
        with self.assertRaises(ValueError):
            p.commit(self.admission, self.offers[:1], result, self.commitment)
        forged = replace(result, agreement=replace(result.agreement, price=F(5)))
        with self.assertRaises(ValueError):
            p.commit(self.admission, self.offers, forged, self.commitment)


@unittest.skipUnless(HAS_PLOTLY, "Install the optional notebook dependencies for figure checks")
class ProtocolTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = protocol_definitions()

    def setUp(self):
        p = self.p
        self.stored = (p.Booking(1, P.closedopen(2, 3)),)
        self.commitment = p.standing(*self.stored)
        self.request = p.Request(2, p.Service(P.closedopen(1, 5), 1))
        self.admission = p.admit(self.request, self.commitment)
        self.offers = p.generate(self.admission)
        policies = p.affine_policies(
            {o: F(3, 2) + o.start / 2 for o in self.offers},
            {o: F(17, 2) - o.start / 2 for o in self.offers},
        )
        self.negotiation = p.bargain(
            self.offers, policies,
            {"owner": F(4), "client": F(6)}, {"owner": F(1), "client": F(1)},
        )
        self.committed = p.commit(
            self.admission, self.offers, self.negotiation, self.commitment,
        )

    @staticmethod
    def traces(figure, kind):
        return [trace for trace in figure.data
                if isinstance(trace.meta, dict) and trace.meta.get("kind") == kind]

    def booking_figure(self, negotiation=None, committed=None):
        return self.p.plot_booking_progression(
            self.stored, self.request, self.admission, self.offers,
            negotiation or self.negotiation, committed or self.committed,
        )

    def scenarios(self):
        p = self.p
        standing = P.closedopen(2, 3)
        accepted = P.closedopen(1, 2)
        later = P.closedopen(3, 4)

        def trace(access, usage):
            return il.Trace(p.FULL, signals={
                "acc": il.NaturalSignal({1: standing, 2: access}, default=0),
                "use": il.NaturalSignal({1: standing, 2: usage}, default=0),
            })

        return {
            "Use during the booking": {
                "trace": trace(accepted, accepted), "note": "Uses the agreed booking.",
            },
            "Later use with additional access": {
                "trace": trace(accepted | later, later),
                "note": "Additional access is illustrative, outside the negotiated obligation.",
            },
            "Client absent": {
                "trace": trace(accepted, P.empty()),
                "note": "Access remains reserved; the client service is unfulfilled.",
            },
        }

    def test_booking_progression_uses_protocol_results_without_committing_alternatives(self):
        figure = self.booking_figure()
        self.assertEqual(self.p.protocol_horizon(self.stored, self.request, self.offers),
                         P.closed(0, 6))
        self.assertEqual(figure.layout.meta["kind"], "booking_progression")
        self.assertEqual(figure.layout.meta["horizon"], "[0,6]")
        expected_intervals = {
            "standing": {"[2,3)"},
            "requested_starts": {"[1,5)"},
            "feasible_starts": {"{1}", "[3,5)"},
            "candidate": {"[1,2)", "[3,4)", "[7/2,9/2)", "[4,5)", "[9/2,11/2)"},
            "committed": {"[2,3)", "[1,2)"},
        }
        for kind, intervals in expected_intervals.items():
            with self.subTest(kind=kind):
                self.assertEqual({t.meta["interval"] for t in self.traces(figure, kind)},
                                 intervals)
        candidates = self.traces(figure, "candidate")
        self.assertEqual({t.meta["lane"] for t in candidates},
                         {f"candidate_{i}" for i in range(1, 6)})
        accepted = [t for t in self.traces(figure, "committed") if t.meta["accepted"]]
        self.assertEqual([(t.meta["client"], t.meta["interval"]) for t in accepted],
                         [(2, "[1,2)")])
        annotation = " ".join(a.text for a in figure.layout.annotations)
        self.assertIn("9/2", annotation)
        self.assertRegex(annotation.lower(), r"round\s*2")
        for trace in self.traces(figure, "candidate"):
            self.assertEqual(trace.marker.symbol, "circle")
            self.assertEqual(list(trace.marker.color), [trace.line.color, "#FFFFFF"])
            self.assertEqual(trace.marker.line.color, trace.line.color)
            self.assertTrue(trace.meta["left_closed"])
            self.assertFalse(trace.meta["right_closed"])
        singleton, = [t for t in self.traces(figure, "feasible_starts")
                      if t.meta["singleton"]]
        self.assertEqual(list(singleton.x), [1.0])
        self.assertEqual(singleton.meta["interval"], "{1}")
        # The horizon accounts for every requested completion, not just the
        # starts chosen as the representative candidate offers.
        self.assertGreater(float(self.p.protocol_horizon(
            self.stored, self.request, self.offers).upper),
            max(float(offer.interval.upper) for offer in self.offers))

    def test_no_bla_keeps_only_standing_bookings_in_committed_lane(self):
        p = self.p
        failed = p.BargainingResult("NO-BLA", None, ())
        unchanged = p.commit(self.admission, self.offers, failed, self.commitment)
        figure = self.booking_figure(failed, unchanged)
        self.assertIsNone(figure.layout.meta["accepted"])
        self.assertFalse(self.traces(figure, "accepted_highlight"))
        self.assertEqual(
            [(t.meta["client"], t.meta["interval"]) for t in self.traces(figure, "committed")],
            [(1, "[2,3)")],
        )
        self.assertTrue(all(not t.meta["accepted"]
                            for t in self.traces(figure, "committed")))
        self.assertEqual(len(self.traces(figure, "candidate")), 5)

    def test_rational_open_components_and_singletons_retain_exact_labels(self):
        p = self.p
        request = p.Request(2, p.Service(
            P.open(F(1, 3), F(5, 3)) | P.singleton(F(7, 3)), F(1, 3),
        ))
        admission = p.admit(request, p.standing())
        offers = p.generate(admission)
        failed = p.BargainingResult("NO-BLA", None, ())
        unchanged = p.commit(admission, offers, failed, admission.commitment)
        figure = p.plot_booking_progression(
            (), request, admission, offers, failed, unchanged,
        )
        self.assertEqual(p.protocol_horizon((), request, offers), P.closed(0, F(8, 3)))
        feasible = self.traces(figure, "feasible_starts")
        self.assertEqual({t.meta["interval"] for t in feasible},
                         {"(1/3,5/3)", "{7/3}"})
        opened, = [t for t in feasible if not t.meta["singleton"]]
        self.assertEqual(opened.marker.symbol, "circle")
        self.assertEqual(list(opened.marker.color), ["#FFFFFF", "#FFFFFF"])
        self.assertEqual(opened.marker.line.color, opened.line.color)
        self.assertFalse(opened.meta["left_closed"])
        self.assertFalse(opened.meta["right_closed"])
        self.assertEqual((opened.meta["lower"], opened.meta["upper"]), ("1/3", "5/3"))
        hover_text = repr(opened.to_plotly_json())
        self.assertIn("1/3", hover_text)
        self.assertIn("5/3", hover_text)
        self.assertEqual({t.meta["interval"] for t in self.traces(figure, "candidate")},
                         {"[1/2,5/6)", "[2/3,1)", "[5/6,7/6)", "[1,4/3)",
                          "[7/6,3/2)", "[4/3,5/3)", "[3/2,11/6)", "[7/3,8/3)"})

    def test_signal_scenarios_report_semantics_and_switch_complete_trace_groups(self):
        p = self.p
        scenarios = self.scenarios()
        figure = p.plot_signal_traces(
            scenarios, self.committed.commitment, self.admission.client_contract,
            horizon=p.protocol_horizon(self.stored, self.request, self.offers),
        )
        self.assertEqual(figure.layout.meta["kind"], "signal_traces")
        records = figure.layout.meta["scenarios"]
        self.assertEqual([record["name"] for record in records], list(scenarios))
        buttons = figure.layout.updatemenus[0].buttons
        self.assertEqual([button.label for button in buttons], list(scenarios))
        booking_colors = {
            t.meta["client"]: t.line.color for t in self.booking_figure().data
            if isinstance(t.meta, dict) and t.meta.get("kind") in ("standing", "candidate")
        }
        for record, button in zip(records, buttons, strict=True):
            name = record["name"]
            trace = scenarios[name]["trace"]
            expected_task = name != "Client absent"
            self.assertTrue(il.satisfies(self.committed.commitment.guarantee, trace, 0))
            self.assertEqual(il.satisfies(self.admission.client_contract.assumption
                                         & self.admission.client_contract.guarantee, trace, 0),
                             expected_task)
            self.assertTrue(record["owner_satisfied"])
            self.assertTrue(record["client_assumption"])
            self.assertEqual(record["client_guarantee"], expected_task)
            self.assertEqual(record["client_task"], expected_task)
            visible = list(button.args[0]["visible"])
            indices = record["trace_indices"]
            self.assertEqual([index for index, value in enumerate(visible)
                              if value and figure.data[index].meta["kind"] == "signal"], indices)
            self.assertTrue(indices)
            self.assertTrue(all(figure.data[index].meta["scenario"] == name for index in indices))
            signals = [figure.data[index] for index in indices]
            self.assertEqual({t.meta["signal"] for t in signals}, {"acc", "use"})
            for segment in signals:
                self.assertEqual(len(set(segment.y)), 1)
                if segment.meta["client"] in booking_colors:
                    self.assertEqual(segment.line.color, booking_colors[segment.meta["client"]])
            self.assertTrue(any(t.meta["signal"] == "acc" and t.meta["client"] == 1
                                and t.meta["interval"] == "[2,3)" for t in signals))
            if name == "Later use with additional access":
                self.assertIn("outside the negotiated obligation", record["note"])
                self.assertTrue(any(t.meta["signal"] == "use" and t.meta["client"] == 2
                                    and t.meta["interval"] == "[3,4)" for t in signals))
            if name == "Client absent":
                self.assertFalse(any(t.meta["signal"] == "use" and t.meta["client"] == 2
                                     for t in signals))
        initially_visible = [index for index, trace in enumerate(figure.data)
                             if trace.visible is not False and trace.meta["kind"] == "signal"]
        self.assertEqual(initially_visible, records[0]["trace_indices"])

    def test_signal_clipping_resolves_defaults_on_the_complete_trace_universe(self):
        p = self.p
        trace = il.Trace(p.FULL, signals={
            "acc": il.NaturalSignal({2: P.closedopen(F(1, 3), F(4, 3))
                                        | P.closedopen(10, 11)}, default=0),
            "use": il.NaturalSignal({2: P.closedopen(F(1, 3), F(4, 3))}, default=0),
        })
        figure = p.plot_signal_traces(
            {"clipped": {"trace": trace, "note": "Only the middle is displayed."}},
            p.Contract(True, True), p.Contract(True, True),
            horizon=P.closed(F(1, 2), 1),
        )
        signals = self.traces(figure, "signal")
        self.assertEqual({t.meta["signal"] for t in signals}, {"acc", "use"})
        self.assertEqual(len(signals), 2)
        for segment in signals:
            self.assertEqual(segment.meta["full_interval"], "[1/3,4/3)")
            self.assertEqual(segment.meta["interval"], "[1/2,1]")
            self.assertTrue(segment.meta["clipped"])
            self.assertEqual(list(segment.x), [0.5, 1.0])
            self.assertEqual(segment.marker.symbol, "circle")
            self.assertEqual(list(segment.marker.color), [segment.line.color] * 2)
            self.assertTrue(segment.meta["left_closed"])
            self.assertTrue(segment.meta["right_closed"])
            self.assertEqual(segment.meta["client"], 2)

    def test_notebook_example_traces_keep_standing_access_and_explain_absence(self):
        p = self.p
        scenarios = p.illustrative_signal_scenarios(
            self.stored, self.negotiation.agreement.offer.booking, self.offers[1].booking,
        )
        self.assertEqual(list(scenarios), list(self.scenarios()))
        for name, scenario in scenarios.items():
            trace = scenario["trace"]
            self.assertTrue(il.satisfies(self.committed.commitment.guarantee, trace, 0))
            self.assertEqual(trace.signals["acc"].parts(trace.universe)[1], P.closedopen(2, 3))
            self.assertEqual(il.satisfies(self.admission.client_contract.assumption
                                         & self.admission.client_contract.guarantee, trace, 0),
                             name != "Client absent")
        self.assertIn("not part of the accepted BLA",
                      scenarios["Later use with additional access"]["note"])
        self.assertIn("does not release", scenarios["Client absent"]["note"])

    @unittest.skipUnless(find_spec("IPython"), "Native notebook display requires IPython")
    def test_native_display_supplies_a_self_contained_html_fallback(self):
        from html.parser import HTMLParser

        class Scripts(HTMLParser):
            def __init__(self):
                super().__init__()
                self.sources = []

            def handle_starttag(self, tag, attrs):
                if tag == "script" and dict(attrs).get("src"):
                    self.sources.append(dict(attrs)["src"])

        figure = self.booking_figure()
        with patch("IPython.get_ipython", return_value=object()), \
                patch("IPython.display.display") as render:
            self.assertIsNone(self.p.display_timeline(figure))
        render.assert_called_once()
        bundle, = render.call_args.args
        self.assertTrue(render.call_args.kwargs["raw"])
        native = bundle["application/vnd.plotly.v1+json"]
        self.assertEqual(native["layout"]["meta"]["accepted"]["price"], "9/2")
        self.assertTrue(native["config"]["responsive"])
        self.assertFalse(native["config"]["displaylogo"])
        html = bundle["text/html"]
        self.assertIn("Plotly.newPlot", html)
        scripts = Scripts()
        scripts.feed(html)
        self.assertEqual(scripts.sources, [], "The fallback must work without a script CDN")

    @unittest.skipUnless(find_spec("IPython"), "Headless notebook display check requires IPython")
    def test_headless_execution_does_not_display_or_launch_a_browser(self):
        with patch("IPython.get_ipython", return_value=None), \
                patch("IPython.display.display") as render, \
                patch("webbrowser.open") as launch:
            self.assertIsNone(self.p.display_timeline(self.booking_figure()))
        render.assert_not_called()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
