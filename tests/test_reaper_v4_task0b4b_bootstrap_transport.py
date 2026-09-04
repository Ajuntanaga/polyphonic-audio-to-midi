"""Controlled bootstrap and standard-stream tests for Task 0B4b."""
from __future__ import annotations

import importlib
import json
import os
import stat
import unittest
from unittest import mock

from tests.test_reaper_v4_task0b4b_admission import _valid_config
from tests.test_reaper_v4_task0b4b_static_contract import assert_b4b_source_contract


class _Stat:
    def __init__(self, mode: int, links: int = 1) -> None:
        self.st_mode = mode
        self.st_nlink = links


class _StatVfs:
    def __init__(self, flags: int) -> None:
        self.f_flag = flags


class _Poll:
    def __init__(self, events: list[tuple[int, int]]) -> None:
        self._events = events
        self.registered: list[tuple[int, int]] = []
        self.timeouts: list[int] = []

    def register(self, descriptor: int, event: int) -> None:
        self.registered.append((descriptor, event))

    def poll(self, timeout: int) -> list[tuple[int, int]]:
        self.timeouts.append(timeout)
        return list(self._events)


def _session_module() -> object:
    assert_b4b_source_contract()
    return importlib.import_module("tools.reaper_v4_session")


def _canonical_config_bytes() -> tuple[bytes, bytes]:
    value = _valid_config()
    config = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return value["session_config_sha256"].encode("ascii"), config


class Task0B4bBootstrapTransportTests(unittest.TestCase):
    def test_diagnostic_setup_and_emission_are_fd2_only_and_best_effort(self) -> None:
        """Removing fd-2 nonblocking setup or turning a short diagnostic into fatal fails this."""
        session = _session_module()
        flags = {"value": 0}
        writes: list[tuple[int, bytes]] = []

        def fake_fcntl(descriptor: int, command: int, value: int | None = None) -> int:
            self.assertEqual(descriptor, 2)
            if command == session.fcntl.F_GETFL:
                return flags["value"]
            self.assertEqual(command, session.fcntl.F_SETFL)
            self.assertIsNotNone(value)
            flags["value"] = value  # type: ignore[assignment]
            return 0

        with (
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFIFO | 0o600)),
            mock.patch.object(session.fcntl, "fcntl", side_effect=fake_fcntl),
        ):
            session._setup_diagnostic_fd()
        self.assertNotEqual(flags["value"] & session.os.O_NONBLOCK, 0)

        with mock.patch.object(session.os, "write", side_effect=lambda fd, data: writes.append((fd, data)) or 1):
            session._emit_diagnostic_once("BAD_ACK")
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][0], 2)
        self.assertIn(b"BAD_ACK", writes[0][1])
        self.assertLessEqual(len(writes[0][1]), 1024)

        with mock.patch.object(session.os, "write", side_effect=OSError("closed")):
            session._emit_diagnostic_once("BAD_ACK")
        with mock.patch.object(session.os, "write") as write:
            with self.assertRaises(session.SessionError):
                session._emit_diagnostic_once("bad\x00ack")
            write.assert_not_called()

    def test_fixed_regular_reader_requires_fixed_readonly_complete_regular_input(self) -> None:
        """Removing a fixed-path, descriptor, EOF, or close check fails this."""
        session = _session_module()
        payload = b"digest"
        reads = [payload, b""]
        closes: list[int] = []

        def fake_fcntl(descriptor: int, command: int) -> int:
            self.assertEqual(descriptor, 37)
            if command == session.fcntl.F_GETFD:
                return session.fcntl.FD_CLOEXEC
            self.assertEqual(command, session.fcntl.F_GETFL)
            return session.os.O_RDONLY

        with (
            mock.patch.object(session.os, "open", return_value=37),
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFREG | 0o444)),
            mock.patch.object(session.os, "fstatvfs", return_value=_StatVfs(session.os.ST_RDONLY)),
            mock.patch.object(session.os, "read", side_effect=lambda _fd, _count: reads.pop(0)),
            mock.patch.object(session.os, "close", side_effect=closes.append),
            mock.patch.object(session.fcntl, "fcntl", side_effect=fake_fcntl),
        ):
            self.assertEqual(session._read_fixed_regular(session.SESSION_DIGEST_PATH, 64), payload)
        self.assertEqual(closes, [37])

        with self.assertRaises(session.SessionError):
            session._read_fixed_regular("/not-an-admitted-path", 64)

    def test_fixed_reader_preserves_async_interruption_while_closing(self) -> None:
        """Replacing the original interruption with a close error fails this."""
        session = _session_module()

        def fake_fcntl(_descriptor: int, command: int) -> int:
            if command == session.fcntl.F_GETFD:
                return session.fcntl.FD_CLOEXEC
            return session.os.O_RDONLY

        with (
            mock.patch.object(session.os, "open", return_value=37),
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFREG | 0o444)),
            mock.patch.object(session.os, "fstatvfs", return_value=_StatVfs(session.os.ST_RDONLY)),
            mock.patch.object(session.os, "read", side_effect=KeyboardInterrupt("stop")),
            mock.patch.object(session.os, "close", side_effect=OSError("close")),
            mock.patch.object(session.fcntl, "fcntl", side_effect=fake_fcntl),
        ):
            with self.assertRaises(KeyboardInterrupt):
                session._read_fixed_regular(session.SESSION_DIGEST_PATH, 64)

    def test_loader_reads_sidecar_before_config_then_parses_and_admits(self) -> None:
        """Swapping the read order or skipping parse/admission fails this."""
        session = _session_module()
        sidecar, config = _canonical_config_bytes()
        paths: list[tuple[str, int]] = []

        def fake_read(path: str, maximum: int) -> bytes:
            paths.append((path, maximum))
            return sidecar if path == session.SESSION_DIGEST_PATH else config

        with (
            mock.patch.object(session, "_setup_diagnostic_fd"),
            mock.patch.object(session, "_read_fixed_regular", side_effect=fake_read),
        ):
            loaded = session._load_fixed_session_config()
        self.assertIs(type(loaded), session.SessionConfig)
        self.assertEqual(loaded.data["session_config_sha256"], sidecar.decode("ascii"))
        self.assertEqual(paths, [
            (session.SESSION_DIGEST_PATH, 64),
            (session.SESSION_CONFIG_PATH, session.MAX_SESSION_CONFIG_BYTES),
        ])

    def test_pipe_wait_and_single_frame_write_refuse_uncertain_output(self) -> None:
        """Skipping pipe validation, PIPE_BUF, deadline, or short-write refusal fails this."""
        session = _session_module()
        poll = _Poll([(1, session.select.POLLOUT)])
        frame = b"frame"
        writes: list[tuple[int, bytes]] = []
        with (
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFIFO | 0o600)),
            mock.patch.object(session.select, "poll", return_value=poll),
            mock.patch.object(session.time, "monotonic_ns", return_value=1_000),
        ):
            session._wait_fixed_pipe(1, session.select.POLLOUT, 2_000)
        self.assertEqual(poll.registered, [(1, session.select.POLLOUT)])

        with (
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFIFO | 0o600)),
            mock.patch.object(session.os, "fpathconf", return_value=len(frame)),
            mock.patch.object(session, "_wait_fixed_pipe"),
            mock.patch.object(session.os, "write", side_effect=lambda fd, data: writes.append((fd, data)) or len(data)),
        ):
            session._write_frame_once(frame, 2_000)
        self.assertEqual(writes, [(1, frame)])

        with (
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFIFO | 0o600)),
            mock.patch.object(session.os, "fpathconf", return_value=len(frame)),
            mock.patch.object(session, "_wait_fixed_pipe"),
            mock.patch.object(session.os, "write", return_value=len(frame) - 1),
        ):
            with self.assertRaises(session.SessionError):
                session._write_frame_once(frame, 2_000)

    def test_ack_requires_one_byte_then_distinct_eof(self) -> None:
        """Accepting a bare ACK without an EOF observation fails this."""
        session = _session_module()
        with (
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFIFO | 0o600)),
            mock.patch.object(session, "_wait_fixed_pipe"),
            mock.patch.object(session.os, "read", side_effect=[b"\x06", b""]),
        ):
            self.assertEqual(session._read_ack_eof(2_000), b"\x06")
        with (
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFIFO | 0o600)),
            mock.patch.object(session, "_wait_fixed_pipe"),
            mock.patch.object(session.os, "read", side_effect=[b"\x06", b"x"]),
        ):
            with self.assertRaises(session.SessionError):
                session._read_ack_eof(2_000)

    def test_ack_accepts_kernel_hangup_when_the_second_read_observes_eof(self) -> None:
        """A FIFO HUP is the normal readiness signal for a distinct EOF read."""
        session = _session_module()
        polls = [
            _Poll([(0, session.select.POLLIN)]),
            _Poll([(0, session.select.POLLHUP)]),
        ]
        with (
            mock.patch.object(session.os, "fstat", return_value=_Stat(stat.S_IFIFO | 0o600)),
            mock.patch.object(session.select, "poll", side_effect=polls),
            mock.patch.object(session.time, "monotonic_ns", return_value=1_000),
            mock.patch.object(session.os, "read", side_effect=[b"\x06", b""]),
        ):
            self.assertEqual(session._read_ack_eof(2_000), b"\x06")


if __name__ == "__main__":
    unittest.main()
