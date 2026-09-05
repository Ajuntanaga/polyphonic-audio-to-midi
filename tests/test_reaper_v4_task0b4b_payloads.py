"""Receipt assembly tests for V4 owned evidence baselines."""
from __future__ import annotations

import importlib
import types
import unittest

from tests.test_reaper_v4_task0b4b_admission import _forged_config, _valid_config
from tests.test_reaper_v4_task0b4b_evidence import _EvidenceFixture
from tests.test_reaper_v4_task0b4b_static_contract import assert_b4b_source_contract
from tools import reaper_v4_receipt_schema as receipt_schema


def _session_module() -> object:
    assert_b4b_source_contract()
    return importlib.import_module("tools.reaper_v4_session")


class Task0B4bPayloadTests(unittest.TestCase):
    def test_builds_a_valid_pre_from_an_owned_baseline(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            try:
                payload = session._assemble_pre_payload(fixture.config, baseline)
                receipt = receipt_schema.validate_pre_payload(payload, 0)
            finally:
                session._release_evidence_baseline(baseline)

        self.assertEqual(receipt.phase, receipt_schema.ReceiptPhase.PRE)
        self.assertEqual(payload["phase"], "pre")
        self.assertTrue(payload["no_child_started"])
        self.assertNotIn("scan_root_unchanged", payload["attestation"])

    def test_builds_a_valid_post_and_exact_exchange(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            try:
                pre = session._assemble_pre_payload(fixture.config, baseline)
                outcome = session.child_runner.ChildOutcome(123, 0, False, 4)
                post = session._assemble_post_payload(
                    fixture.config, baseline, outcome, 10, 11,
                )
                pre_receipt, post_receipt = receipt_schema.validate_exchange(
                    pre, receipt_schema.ACK_BYTE, post,
                )
            finally:
                session._release_evidence_baseline(baseline)

        self.assertEqual(pre_receipt.phase, receipt_schema.ReceiptPhase.PRE)
        self.assertEqual(post_receipt.phase, receipt_schema.ReceiptPhase.POST)
        self.assertEqual(post["phase"], "post")
        self.assertTrue(post["terminal"])
        self.assertTrue(post["attestation"]["scan_root_unchanged"])
        self.assertEqual(
            {key: post["attestation"][key] for key in receipt_schema.ATTESTATION_KEYS},
            pre["attestation"],
        )
        self.assertEqual(
            set(post["attestation"]),
            set(receipt_schema.ATTESTATION_KEYS) | {"scan_root_unchanged"},
        )

    def test_returns_fresh_unaliased_exact_builtin_values(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            try:
                first = session._assemble_pre_payload(fixture.config, baseline)
                second = session._assemble_pre_payload(fixture.config, baseline)
            finally:
                session._release_evidence_baseline(baseline)

        self.assertIs(type(first), dict)
        self.assertIs(type(first["inputs"]), dict)
        self.assertIs(type(first["row"]), dict)
        self.assertIs(type(first["attestation"]), dict)
        self.assertIsNot(first, second)
        self.assertIsNot(first["inputs"], second["inputs"])
        self.assertIsNot(first["row"], second["row"])
        self.assertIsNot(first["attestation"], second["attestation"])
        first["inputs"]["fixture_input_a"] = "0" * 64
        self.assertNotEqual(first["inputs"], second["inputs"])

    def test_refuses_mismatched_consumed_or_mutated_evidence(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            try:
                other = _forged_config(session, _valid_config())
                self.assertIs(type(other.data), types.MappingProxyType)
                with self.assertRaises(session.SessionError):
                    session._assemble_pre_payload(other, baseline)
                object.__setattr__(baseline, "environment", session._freeze_session_data({}))
                with self.assertRaises(session.SessionError):
                    session._assemble_pre_payload(fixture.config, baseline)
            finally:
                session._release_evidence_baseline(baseline)
            with self.assertRaises(session.SessionError):
                session._assemble_pre_payload(fixture.config, baseline)

    def test_refuses_uncertain_child_outcomes_and_invalid_clocks(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            try:
                vectors = (
                    (session.child_runner.ChildOutcome(123, 0, True, 4), 10, 11),
                    (session.child_runner.ChildOutcome(123, -9, False, 4), 10, 11),
                    (session.child_runner.ChildOutcome(123, 0, False, 4), 0, 11),
                    (session.child_runner.ChildOutcome(123, 0, False, 4), 12, 11),
                )
                for outcome, pre_clock, post_clock in vectors:
                    with self.subTest(outcome=outcome, clocks=(pre_clock, post_clock)):
                        with self.assertRaises(session.SessionError):
                            session._assemble_post_payload(
                                fixture.config, baseline, outcome, pre_clock, post_clock,
                            )
            finally:
                session._release_evidence_baseline(baseline)


if __name__ == "__main__":
    unittest.main()
