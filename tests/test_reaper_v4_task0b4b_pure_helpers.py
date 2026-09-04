"""Focused in-memory tests for the non-admissible Task 0B4b-pure helpers."""
from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
import types
import unittest
from unittest import mock

from tests.test_reaper_v4_task0b4b_static_contract import assert_b4b_source_contract
from tools import reaper_v4_protocol as protocol
from tools import reaper_v4_receipt_schema as receipt_schema


FIXTURE_PATH = pathlib.Path(__file__).resolve().parent / "fixtures" / "reaper_v4_closure" / "receipt-exchange.json"
SESSION_NAMESPACE = "native-vst3-probe-v4-scan-isolated"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _base_config() -> dict[str, object]:
    value: dict[str, object] = {
        "schema": 1,
        "namespace": SESSION_NAMESPACE,
        "nonce": "0123456789abcdef0123456789abcdef",
        "config_sha256": "0" * 64,
        "inputs": {
            "fixture_input": "1" * 64,
            "session_policy": "2" * 64,
        },
    }
    value["config_sha256"] = protocol.config_sha256(value)
    return value


def _session_config() -> dict[str, object]:
    value: dict[str, object] = {
        "schema": 1,
        "namespace": SESSION_NAMESPACE,
        "session_config_sha256": "0" * 64,
        "base_config": _base_config(),
        "session_policy_sha256": "2" * 64,
        "direct_input_digests": {"fixture_input": "1" * 64},
        "row": {"sample_rate_hz": 44100, "block_size": 32},
        "runtime_manifest_sha256": "3" * 64,
        "run_input_manifest_sha256": "4" * 64,
        "fixture_manifest_sha256": "5" * 64,
        "namespace_policy_sha256": "6" * 64,
        "fixture_certificates": {},
        "bwrap": {},
        "namespace_expectations": {},
        "child": {},
        "limits": {},
    }
    digest_input = {key: item for key, item in value.items() if key != "session_config_sha256"}
    value["session_config_sha256"] = hashlib.sha256(_canonical(digest_input)).hexdigest()
    return value


def _session_module() -> object:
    assert_b4b_source_contract()
    return importlib.import_module("tools.reaper_v4_session")


class Task0B4bPureHelperTests(unittest.TestCase):
    def test_public_session_surface_remains_fail_closed(self) -> None:
        session = _session_module()
        with self.assertRaises(session.SessionError):
            session.SessionConfig()
        with self.assertRaises(session.SessionError):
            session.SessionResult()
        with self.assertRaises(session.SessionError):
            session.load_session_config("/ignored", "/ignored")
        with self.assertRaises(session.SessionError):
            session.run_session(object())

    def test_freeze_and_materialize_are_bounded_unaliased_exact_containers(self) -> None:
        session = _session_module()
        raw = {"alpha": [1, True, None, {"text": "value"}]}
        frozen = session._freeze_session_data(raw)
        self.assertIs(type(frozen), types.MappingProxyType)
        self.assertIs(type(frozen["alpha"]), tuple)
        self.assertIs(type(frozen["alpha"][3]), types.MappingProxyType)
        with self.assertRaises(TypeError):
            frozen["alpha"] = ()
        materialized = session._materialize_exact_builtins(frozen)
        self.assertEqual(materialized, raw)
        self.assertIsNot(materialized, raw)
        self.assertIsNot(materialized["alpha"], raw["alpha"])
        materialized["alpha"][3]["text"] = "changed"
        self.assertEqual(frozen["alpha"][3]["text"], "value")
        self.assertEqual(session._materialize_exact_builtins(raw), raw)
        self.assertEqual(dict(session._freeze_session_data((("pair", 1),))), {"pair": 1})
        self.assertEqual(session._materialize_exact_builtins(session._freeze_session_data({"empty_a": [], "empty_b": []})), {"empty_a": [], "empty_b": []})
        escaped = {"escaped": ['"' * 512] * 15}
        self.assertIs(type(session._freeze_session_data(escaped)), types.MappingProxyType)
        with self.assertRaises(session.SessionError):
            session._canonical_session_json_bytes(escaped)

        cycle: list[object] = []
        cycle.append(cycle)
        shared: dict[str, object] = {}
        too_deep: object = None
        for _ in range(17):
            too_deep = [too_deep]
        deepest_container: object = []
        for _ in range(16):
            deepest_container = [deepest_container]
        cases = (
            cycle,
            {"alias_a": shared, "alias_b": shared},
            {"non_ascii": "é"},
            {"too_long": "x" * 513},
            [None] * 257,
            too_deep,
            deepest_container,
            {"byte_budget": ["x" * 512] * 16},
            {"too_large": 9223372036854775808},
            {"float": 1.0},
            ("not", "object_pairs"),
        )
        for value in cases:
            with self.subTest(value=repr(value)[:40]):
                with self.assertRaises(session.SessionError):
                    session._freeze_session_data(value)
        with self.assertRaises(session.SessionError):
            session._freeze_session_data((("duplicate", 1), ("duplicate", 2)))
        materialize_cycle: dict[str, object] = {}
        materialize_cycle["self"] = materialize_cycle
        materialize_alias: list[object] = []
        materialize_deep: object = None
        for _ in range(17):
            materialize_deep = [materialize_deep]
        materialize_deepest_container: object = []
        for _ in range(16):
            materialize_deepest_container = [materialize_deepest_container]
        materialize_cases = (
            types.MappingProxyType(materialize_cycle),
            types.MappingProxyType({"a": materialize_alias, "b": materialize_alias}),
            type("DictSubclass", (dict,), {})(),
            [None] * 257,
            materialize_deep,
            materialize_deepest_container,
            {"byte_budget": ["x" * 512] * 16},
            {"too_large": 9223372036854775808},
        )
        for value in materialize_cases:
            with self.subTest(materialize=type(value).__name__):
                with self.assertRaises(session.SessionError):
                    session._materialize_exact_builtins(value)

    def test_canonical_digest_and_nonadmitted_parse_are_exact(self) -> None:
        session = _session_module()
        self.assertEqual(
            session._canonical_session_json_bytes({"b": 1, "a": "text"}),
            b'{"a":"text","b":1}',
        )
        configuration = _session_config()
        original_digest = session._session_config_digest(configuration)
        altered_embedded = dict(configuration)
        altered_embedded["session_config_sha256"] = "f" * 64
        self.assertEqual(session._session_config_digest(altered_embedded), original_digest)
        altered_value = dict(configuration)
        altered_value["limits"] = {"different": 1}
        self.assertNotEqual(session._session_config_digest(altered_value), original_digest)
        with self.assertRaises(session.SessionError):
            session._session_config_digest({"schema": 1})

        raw = _canonical(configuration)
        frozen = session._parse_session_config_bytes(raw, configuration["session_config_sha256"].encode("ascii"))
        self.assertIs(type(frozen), types.MappingProxyType)
        self.assertEqual(session._materialize_exact_builtins(frozen), configuration)

        malformed = (
            (b'{"schema":1,"schema":1}', b"0" * 64),
            (b" " + raw, configuration["session_config_sha256"].encode("ascii")),
            (raw, configuration["session_config_sha256"].encode("ascii") + b"\n"),
            (b"[" * 1500 + b"0" + b"]" * 1500, b"0" * 64),
        )
        for config_bytes, sidecar_bytes in malformed:
            with self.subTest(config_bytes=config_bytes[:24], sidecar_bytes=sidecar_bytes[:8]):
                with self.assertRaises(session.SessionError):
                    session._parse_session_config_bytes(config_bytes, sidecar_bytes)

        with self.assertRaises(session.SessionError):
            session._parse_session_config_bytes(raw, b"f" * 64)
        embedded_mismatch = json.loads(raw.decode("ascii"))
        embedded_mismatch["session_config_sha256"] = "f" * 64
        with self.assertRaises(session.SessionError):
            session._parse_session_config_bytes(_canonical(embedded_mismatch), b"f" * 64)
        computed_mismatch = json.loads(raw.decode("ascii"))
        computed_mismatch["limits"] = {"changed": 1}
        with self.assertRaises(session.SessionError):
            session._parse_session_config_bytes(
                _canonical(computed_mismatch), configuration["session_config_sha256"].encode("ascii")
            )

        mismatch = json.loads(raw.decode("ascii"))
        mismatch["base_config"]["namespace"] = "wrong"
        mismatch["session_config_sha256"] = hashlib.sha256(
            _canonical({key: item for key, item in mismatch.items() if key != "session_config_sha256"})
        ).hexdigest()
        with self.assertRaises(session.SessionError):
            session._parse_session_config_bytes(_canonical(mismatch), mismatch["session_config_sha256"].encode("ascii"))

    def test_base_projection_is_fresh_and_uses_the_exact_projection_once(self) -> None:
        session = _session_module()
        admitted_test_value = _session_config()
        configuration = object.__new__(session.SessionConfig)
        object.__setattr__(configuration, "data", session._freeze_session_data(admitted_test_value))
        self.assertEqual(session._base_config_projection(configuration), _base_config())
        invalid_base = _base_config()
        invalid_base["nonce"] = "invalid"
        invalid_configuration = object.__new__(session.SessionConfig)
        object.__setattr__(invalid_configuration, "data", session._freeze_session_data({"base_config": invalid_base}))
        with self.assertRaises(session.attester.AttestationError):
            session._base_config_projection(invalid_configuration)
        captured: dict[str, object] = {}
        real_attester_config = session.attester.AttesterConfig

        def capture_config(value: object) -> object:
            captured["wrapped"] = value
            return real_attester_config(value)

        def capture_validate(value: object) -> object:
            captured["validated"] = value.data
            return value.data

        with mock.patch.object(session.attester, "AttesterConfig", side_effect=capture_config) as wrapped, mock.patch.object(
            session.attester, "validate_config", side_effect=capture_validate
        ) as validated:
            projection = session._base_config_projection(configuration)
        self.assertEqual(wrapped.call_count, 1)
        self.assertEqual(validated.call_count, 1)
        self.assertIs(captured["wrapped"], projection)
        self.assertIs(captured["validated"], projection)
        self.assertEqual(set(projection), {"schema", "namespace", "nonce", "config_sha256", "inputs"})
        projection["nonce"] = "f" * 32
        self.assertEqual(configuration.data["base_config"]["nonce"], "0123456789abcdef0123456789abcdef")
        isolated_base = session._freeze_session_data(_base_config())
        sibling_opaque = object.__new__(session.SessionConfig)
        object.__setattr__(sibling_opaque, "data", types.MappingProxyType({"base_config": isolated_base, "unused": object()}))
        self.assertEqual(session._base_config_projection(sibling_opaque), _base_config())
        forged_unfrozen = object.__new__(session.SessionConfig)
        object.__setattr__(forged_unfrozen, "data", {"base_config": isolated_base})
        with self.assertRaises(session.SessionError):
            session._base_config_projection(forged_unfrozen)

    def test_receipt_validation_precedes_encoding_with_the_same_owned_payload(self) -> None:
        session = _session_module()
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        payload = fixture["pre"]
        before = _canonical(payload)
        receipt, frame = session._validate_and_encode_receipt(payload, receipt_schema.ReceiptPhase.PRE, 0)
        decoded, consumed = protocol.decode_frame(frame)
        self.assertEqual(consumed, len(frame))
        self.assertEqual(decoded.payload, payload)
        self.assertEqual(before, _canonical(payload))
        self.assertIsNot(receipt.payload, payload)
        post_payload = fixture["post"]
        post_before = _canonical(post_payload)
        post_receipt, post_frame = session._validate_and_encode_receipt(post_payload, receipt_schema.ReceiptPhase.POST, 1)
        decoded_post, consumed_post = protocol.decode_frame(post_frame)
        self.assertEqual(consumed_post, len(post_frame))
        self.assertEqual(decoded_post.payload, post_payload)
        self.assertEqual(post_before, _canonical(post_payload))
        self.assertIsNot(post_receipt.payload, post_payload)

        events: list[tuple[str, object]] = []
        marker = object()

        class FakePhase:
            PRE = object()
            POST = object()

        class FakeReceiptSchema:
            ReceiptPhase = FakePhase
            ReceiptPayload = object

            @staticmethod
            def validate_pre_payload(value: object, sequence: object) -> object:
                events.append(("pre", value))
                self.assertIs(sequence, 0)
                return marker

            @staticmethod
            def validate_post_payload(value: object, sequence: object) -> object:
                events.append(("post", value))
                self.assertIs(sequence, 1)
                return marker

        class FakeFrameType:
            PRE = object()
            POST = object()

        class FakeProtocol:
            FrameType = FakeFrameType

            @staticmethod
            def encode_frame(kind: object, sequence: object, value: object) -> bytes:
                events.append(("encode", value))
                self.assertIs(kind, FakeFrameType.PRE if sequence == 0 else FakeFrameType.POST)
                self.assertIn(sequence, (0, 1))
                return b"frame"

        owned_payload = {"owned": "payload"}
        owned_before = _canonical(owned_payload)
        with mock.patch.object(session, "receipt_schema", FakeReceiptSchema), mock.patch.object(session, "protocol", FakeProtocol):
            returned_receipt, returned_frame = session._validate_and_encode_receipt(owned_payload, FakePhase.PRE, 0)
            owned_post = {"owned": "post"}
            returned_post_receipt, returned_post_frame = session._validate_and_encode_receipt(owned_post, FakePhase.POST, 1)
            with self.assertRaises(session.SessionError):
                session._validate_and_encode_receipt(owned_payload, FakePhase.PRE, 1)
            with self.assertRaises(session.SessionError):
                session._validate_and_encode_receipt(owned_payload, FakePhase.PRE, False)
            with self.assertRaises(session.SessionError):
                session._validate_and_encode_receipt(owned_post, FakePhase.POST, 1.0)
        self.assertIs(returned_receipt, marker)
        self.assertEqual(returned_frame, b"frame")
        self.assertIs(returned_post_receipt, marker)
        self.assertEqual(returned_post_frame, b"frame")
        self.assertEqual(events, [("pre", owned_payload), ("encode", owned_payload), ("post", owned_post), ("encode", owned_post)])
        self.assertEqual(owned_before, _canonical(owned_payload))


if __name__ == "__main__":
    unittest.main()
