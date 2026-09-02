"""Pure in-memory adversarial checks for the sealed V4 receipt vector."""
from __future__ import annotations

import json
import pathlib
import unittest

from tools import reaper_v4_receipt_schema as receipt_schema
from tools import reaper_v4_protocol


FIXTURE = pathlib.Path(__file__).with_name("fixtures") / "reaper_v4_closure" / "receipt-exchange.json"


def exchange() -> tuple[dict[str, object], bytes, dict[str, object]]:
    vector = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return vector["pre"], bytes.fromhex(vector["ack_hex"]), vector["post"]


def rebind_identity(payload: dict[str, object]) -> None:
    payload["config_sha256"] = reaper_v4_protocol.config_sha256(
        {key: payload[key] for key in ("schema", "namespace", "nonce", "config_sha256", "inputs")}
    )


class ReceiptGateTest(unittest.TestCase):
    def assert_rejected(self, pre: dict[str, object], ack: object, post: dict[str, object]) -> None:
        with self.assertRaises(receipt_schema.ReceiptSchemaError):
            receipt_schema.validate_exchange(pre, ack, post)

    def test_valid_exchange_returns_immutable_snapshots(self) -> None:
        pre, ack, post = exchange()
        pre_receipt, post_receipt = receipt_schema.validate_exchange(pre, ack, post)
        pre["nonce"] = "fedcba9876543210fedcba9876543210"
        post["attestation"]["environment_keys"].append("PATH")
        self.assertEqual(pre_receipt.phase, receipt_schema.ReceiptPhase.PRE)
        self.assertEqual(post_receipt.phase, receipt_schema.ReceiptPhase.POST)
        self.assertEqual(pre_receipt.payload["nonce"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(post_receipt.payload["attestation"]["environment_keys"], ("LANG",))
        with self.assertRaises(TypeError):
            pre_receipt.payload["nonce"] = "mutated"
        with self.assertRaises(TypeError):
            post_receipt.payload["attestation"]["home"] = "mutated"

    def test_rejects_wrong_ack(self) -> None:
        for ack in (b"", b"\x15", b"\x06\x00", bytearray(b"\x06")):
            with self.subTest(ack=ack):
                pre, _, post = exchange()
                self.assert_rejected(pre, ack, post)

    def test_rejects_different_but_individually_valid_identity(self) -> None:
        pre, ack, post = exchange()
        post["nonce"] = "fedcba9876543210fedcba9876543210"
        rebind_identity(post)
        receipt_schema.validate_pre_payload(pre, 0)
        receipt_schema.validate_post_payload(post, 1)
        self.assert_rejected(pre, ack, post)

    def test_rejects_different_but_individually_valid_shared_attestation(self) -> None:
        pre, ack, post = exchange()
        pre["attestation"]["home"] = "other-synthetic-home"
        receipt_schema.validate_pre_payload(pre, 0)
        receipt_schema.validate_post_payload(post, 1)
        self.assert_rejected(pre, ack, post)

    def test_rejects_false_or_missing_post_scan_root_attestation(self) -> None:
        for mutation in (
            lambda value: value["attestation"].__setitem__("scan_root_unchanged", False),
            lambda value: value["attestation"].pop("scan_root_unchanged"),
        ):
            with self.subTest(mutation=mutation):
                pre, ack, post = exchange()
                mutation(post)
                self.assert_rejected(pre, ack, post)

    def test_rejects_false_or_missing_shared_containment_attestation(self) -> None:
        for mutation in (
            lambda value: value["attestation"].__setitem__("production_bundle_absent", False),
            lambda value: value["attestation"].pop("production_bundle_absent"),
        ):
            with self.subTest(mutation=mutation):
                pre, ack, post = exchange()
                mutation(pre)
                self.assert_rejected(pre, ack, post)

    def test_accepts_closed_child_and_clock_boundaries(self) -> None:
        for child_pid, child_returncode, pre_clock, post_clock in (
            (1, -255, 1, 1),
            (2147483647, 255, 9223372036854775807, 9223372036854775807),
        ):
            with self.subTest(child_pid=child_pid, child_returncode=child_returncode):
                pre, ack, post = exchange()
                post.update(
                    child_pid=child_pid,
                    child_returncode=child_returncode,
                    pre_monotonic_ns=pre_clock,
                    post_monotonic_ns=post_clock,
                )
                receipt_schema.validate_exchange(pre, ack, post)

    def test_rejects_boolean_or_out_of_range_child_and_clock_fields(self) -> None:
        for field, value in (
            ("child_pid", True),
            ("child_pid", 0),
            ("child_pid", 2147483648),
            ("child_returncode", False),
            ("child_returncode", -256),
            ("child_returncode", 256),
            ("pre_monotonic_ns", True),
            ("post_monotonic_ns", False),
            ("pre_monotonic_ns", 0),
            ("post_monotonic_ns", 9223372036854775808),
        ):
            with self.subTest(field=field, value=value):
                pre, ack, post = exchange()
                post[field] = value
                self.assert_rejected(pre, ack, post)

    def test_rejects_invalid_or_regressing_post_clocks(self) -> None:
        for label, mutation in (
            ("invalid-pre", lambda value: value.__setitem__("pre_monotonic_ns", 0)),
            ("invalid-post", lambda value: value.__setitem__("post_monotonic_ns", 0)),
            ("regressing", lambda value: value.update(pre_monotonic_ns=3, post_monotonic_ns=2)),
        ):
            with self.subTest(label=label):
                pre, ack, post = exchange()
                mutation(post)
                self.assert_rejected(pre, ack, post)

    def test_rejects_nonprintable_attestation_text(self) -> None:
        pre, ack, post = exchange()
        post["attestation"]["home"] = "synthetic\x00home"
        self.assert_rejected(pre, ack, post)

    def test_rejects_wrong_row(self) -> None:
        pre, ack, post = exchange()
        post["row"]["block_size"] = 64
        self.assert_rejected(pre, ack, post)

    def test_rejects_cycle_and_container_subclass(self) -> None:
        class ExactLookingDict(dict):
            pass

        pre, ack, post = exchange()
        post["attestation"]["x11_identity"]["display"] = post
        self.assert_rejected(pre, ack, post)
        pre, ack, post = exchange()
        pre["inputs"] = ExactLookingDict(pre["inputs"])
        self.assert_rejected(pre, ack, post)
