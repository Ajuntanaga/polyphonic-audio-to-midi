"""Mock-only transition tests for the one V4 session runtime root."""
from __future__ import annotations

import copy
import importlib
import unittest
from unittest import mock

from tests.test_reaper_v4_task0b3b_receipt import exchange
from tests.test_reaper_v4_task0b4b_admission import _forged_config, _valid_config
from tests.test_reaper_v4_task0b4b_static_contract import assert_b4b_source_contract
from tools import reaper_v4_protocol as protocol


def _session_module() -> object:
    assert_b4b_source_contract()
    return importlib.import_module("tools.reaper_v4_session")


def _receipt_pair(config: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    """Rebind the sealed pure vector to the synthetic admitted configuration."""
    pre, _ack, post = exchange()
    base = config["base_config"]
    expectations = config["namespace_expectations"]
    bwrap = config["bwrap"]
    for payload in (pre, post):
        payload["schema"] = base["schema"]
        payload["namespace"] = base["namespace"]
        payload["nonce"] = base["nonce"]
        payload["config_sha256"] = base["config_sha256"]
        payload["inputs"] = copy.deepcopy(base["inputs"])
        payload["row"] = copy.deepcopy(config["row"])
        attestation = payload["attestation"]
        attestation["home"] = expectations["home"]
        attestation["pwd"] = expectations["pwd"]
        attestation["cwd"] = expectations["cwd"]
        attestation["environment_keys"] = ["DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY"]
        attestation["forbidden_env_absent"] = ["PATH"]
        attestation["runtime_manifest_sha256"] = config["runtime_manifest_sha256"]
        attestation["run_input_manifest_sha256"] = config["run_input_manifest_sha256"]
        attestation["bwrap_path"] = bwrap["path"]
        attestation["bwrap_version"] = bwrap["version"]
        attestation["bwrap_argv_sha256"] = bwrap["argv_sha256"]
        x11 = expectations["x11_identity"]
        attestation["x11_identity"] = {
            "display": x11["display"],
            "authority": x11["authority"]["path"],
            "socket": x11["socket"]["path"],
            "screen": x11["screen"],
            "protocol": x11["protocol"],
        }
    return pre, post


class Task0B4bStateTests(unittest.TestCase):
    def _success_patches(self, session: object) -> tuple[dict[str, object], list[str], list[bytes], list[object]]:
        value = _valid_config()
        config = _forged_config(session, value)
        pre, post = _receipt_pair(value)
        order: list[str] = []
        frames: list[bytes] = []
        specs: list[object] = []
        baseline = object()

        def capture(_config: object) -> object:
            order.append("capture")
            return baseline

        def barrier(_base: object) -> None:
            order.append("barrier")

        def pre_payload(_config: object, received: object) -> dict[str, object]:
            self.assertIs(received, baseline)
            order.append("pre_payload")
            return pre

        def write(frame: bytes, _deadline: int) -> None:
            frames.append(frame)
            order.append(f"write_{len(frames)}")

        def ack(_deadline: int) -> bytes:
            order.append("ack")
            return b"\x06"

        def child(spec: object) -> object:
            specs.append(spec)
            order.append("child")
            return session.child_runner.ChildOutcome(123, 0, False, 4)

        def recheck(received: object) -> None:
            self.assertIs(received, baseline)
            order.append("recheck")

        def post_payload(
            _config: object, received: object, outcome: object, pre_clock: int, post_clock: int
        ) -> dict[str, object]:
            self.assertIs(received, baseline)
            self.assertEqual(outcome.child_pid, 123)
            self.assertGreaterEqual(post_clock, pre_clock)
            order.append("post_payload")
            post["child_pid"] = outcome.child_pid
            post["child_returncode"] = outcome.returncode
            post["pre_monotonic_ns"] = pre_clock
            post["post_monotonic_ns"] = post_clock
            return post

        def close(_fd: int) -> None:
            order.append("close_stdout")

        def release(received: object) -> None:
            self.assertIs(received, baseline)
            order.append("release")

        patches = (
            mock.patch.object(session, "_setup_diagnostic_fd", side_effect=lambda: order.append("diagnostic_setup")),
            mock.patch.object(session, "_capture_runtime_evidence", side_effect=capture),
            mock.patch.object(session.attester, "validate_config", side_effect=lambda _config: order.append("base_validate")),
            mock.patch.object(session.attester, "establish_protocol_barrier", side_effect=barrier),
            mock.patch.object(session, "_assemble_pre_payload", side_effect=pre_payload),
            mock.patch.object(session, "_write_frame_once", side_effect=write),
            mock.patch.object(session, "_read_ack_eof", side_effect=ack),
            mock.patch.object(session.child_runner, "run_child", side_effect=child),
            mock.patch.object(session, "_recheck_runtime_evidence", side_effect=recheck),
            mock.patch.object(session, "_assemble_post_payload", side_effect=post_payload),
            mock.patch.object(session.os, "close", side_effect=close),
            mock.patch.object(session, "_release_runtime_evidence", side_effect=release),
            mock.patch.object(session.time, "monotonic_ns", return_value=1000),
            mock.patch.object(session, "_emit_diagnostic_once", side_effect=lambda code: order.append(f"diagnostic_{code}")),
        )
        return config, order, frames, specs, patches  # type: ignore[return-value]

    def test_success_is_pre_ack_child_post_close_then_result(self) -> None:
        session = _session_module()
        config, order, frames, specs, patches = self._success_patches(session)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12], patches[13]:
            result = session.run_session(config)
        self.assertEqual(
            order,
            [
                "diagnostic_setup", "base_validate", "capture", "base_validate", "barrier", "pre_payload",
                "write_1", "ack", "base_validate", "child", "recheck", "post_payload", "write_2",
                "close_stdout", "release",
            ],
        )
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].argv, ("/usr/bin/true",))
        self.assertEqual(specs[0].environment, (
            ("DISPLAY", ":0"), ("HOME", "/home/vst"), ("LANG", "C"),
            ("PWD", "/home/vst"), ("TZ", "UTC"), ("XAUTHORITY", "/run/m3-v4/Xauthority"),
        ))
        pre_frame, pre_used = protocol.decode_frame(frames[0])
        post_frame, post_used = protocol.decode_frame(frames[1])
        self.assertEqual((pre_frame.frame_type, pre_frame.sequence, pre_used), (protocol.FrameType.PRE, 0, len(frames[0])))
        self.assertEqual((post_frame.frame_type, post_frame.sequence, post_used), (protocol.FrameType.POST, 1, len(frames[1])))
        self.assertEqual((result.child_pid, result.child_returncode, result.pre_monotonic_ns, result.post_monotonic_ns), (123, 0, 1000, 1000))

    def test_pre_ack_failures_never_start_a_child_or_post(self) -> None:
        session = _session_module()
        failures = (
            (session, "_capture_runtime_evidence"),
            (session, "_base_config_projection"),
            (session.attester, "establish_protocol_barrier"),
            (session, "_assemble_pre_payload"),
            (session, "_write_frame_once"),
            (session, "_read_ack_eof"),
        )
        for owner, name in failures:
            with self.subTest(name=name):
                config, _order, frames, specs, patches = self._success_patches(session)
                failing = mock.patch.object(owner, name, side_effect=session.SessionError(name))
                with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12], patches[13], failing:
                    with self.assertRaises(session.SessionError):
                        session.run_session(config)
                self.assertEqual(specs, [])
                self.assertLessEqual(len(frames), 1)
                self.assertEqual(_order.count("release"), 0 if name == "_capture_runtime_evidence" else 1)

    def test_invalid_config_never_reaches_capture_or_child(self) -> None:
        session = _session_module()
        captured: list[object] = []
        children: list[object] = []
        with (
            mock.patch.object(session, "_setup_diagnostic_fd"),
            mock.patch.object(session, "_capture_runtime_evidence", side_effect=captured.append),
            mock.patch.object(session.child_runner, "run_child", side_effect=children.append),
            mock.patch.object(session, "_emit_diagnostic_once"),
        ):
            with self.assertRaises(session.SessionError):
                session.run_session(object())
        self.assertEqual(captured, [])
        self.assertEqual(children, [])

    def test_bad_child_outcomes_are_pre_only_and_do_not_post(self) -> None:
        session = _session_module()
        outcomes = (
            session.child_runner.ChildOutcome(123, 0, True, 4),
            session.child_runner.ChildOutcome(123, -9, False, 4),
            object(),
        )
        for outcome in outcomes:
            with self.subTest(outcome=outcome):
                config, _order, frames, _specs, patches = self._success_patches(session)
                observed_specs: list[object] = []
                def child(spec: object) -> object:
                    observed_specs.append(spec)
                    return outcome
                with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], mock.patch.object(session.child_runner, "run_child", side_effect=child), patches[8], patches[9], patches[10], patches[11], patches[12], patches[13]:
                    with self.assertRaises(session.SessionError):
                        session.run_session(config)
                self.assertEqual(len(observed_specs), 1)
                self.assertEqual(len(frames), 1)
                self.assertEqual(_order.count("release"), 1)

    def test_post_failures_never_return_or_retry_the_terminal_write(self) -> None:
        session = _session_module()
        for name in ("_recheck_runtime_evidence", "_assemble_post_payload", "_finalize_post_payload"):
            with self.subTest(name=name):
                config, _order, frames, _specs, patches = self._success_patches(session)
                failing = mock.patch.object(session, name, side_effect=session.SessionError(name))
                with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12], patches[13], failing:
                    with self.assertRaises(session.SessionError):
                        session.run_session(config)
                self.assertEqual(len(frames), 1)
                self.assertEqual(_order.count("release"), 1)

    def test_terminal_write_close_and_child_interruption_are_nonterminal(self) -> None:
        session = _session_module()
        for failure in ("write", "close", "interrupt"):
            with self.subTest(failure=failure):
                config, _order, frames, _specs, patches = self._success_patches(session)
                if failure == "write":
                    calls = {"count": 0}
                    def write(frame: bytes, _deadline: int) -> None:
                        calls["count"] += 1
                        if calls["count"] == 2:
                            raise session.SessionError("post write")
                        frames.append(frame)
                    failing = mock.patch.object(session, "_write_frame_once", side_effect=write)
                elif failure == "close":
                    failing = mock.patch.object(session.os, "close", side_effect=OSError("close"))
                else:
                    failing = mock.patch.object(session.child_runner, "run_child", side_effect=KeyboardInterrupt("stop"))
                with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12], patches[13], failing:
                    if failure == "interrupt":
                        with self.assertRaises(KeyboardInterrupt):
                            session.run_session(config)
                    else:
                        with self.assertRaises(session.SessionError):
                            session.run_session(config)
                self.assertEqual(len(frames), 2 if failure == "close" else 1)

    def test_post_finalizer_validates_post_then_exchange_then_encodes(self) -> None:
        session = _session_module()
        order: list[str] = []
        with (
            mock.patch.object(session.receipt_schema, "validate_post_payload", side_effect=lambda _payload, _sequence: order.append("post")),
            mock.patch.object(session.receipt_schema, "validate_exchange", side_effect=lambda _pre, _ack, _post: order.append("exchange")),
            mock.patch.object(session.protocol, "encode_frame", side_effect=lambda _kind, _sequence, _payload: order.append("encode") or b"POST"),
        ):
            self.assertEqual(session._finalize_post_payload({}, b"\x06", {}), b"POST")
        self.assertEqual(order, ["post", "exchange", "encode"])

    def test_fixed_public_loader_rejects_other_paths_and_delegates_once(self) -> None:
        session = _session_module()
        expected = _forged_config(session, _valid_config())
        with mock.patch.object(session, "_load_fixed_session_config", return_value=expected) as load:
            self.assertIs(session.load_session_config(session.SESSION_CONFIG_PATH, session.SESSION_DIGEST_PATH), expected)
        load.assert_called_once_with()
        with self.assertRaises(session.SessionError):
            session.load_session_config("/other", session.SESSION_DIGEST_PATH)


if __name__ == "__main__":
    unittest.main()
