"""Controlled non-REAPER parent-harness protocol tests."""
from __future__ import annotations

import base64
import sys
import unittest

from tests.test_reaper_v4_task0b3b_receipt import exchange
from tools import reaper_v4_protocol as protocol


def _sentinel(pre: bytes, post: bytes) -> tuple[str, ...]:
    code = (
        "import base64, os, sys\n"
        f"pre = base64.b64decode({base64.b64encode(pre)!r})\n"
        f"post = base64.b64decode({base64.b64encode(post)!r})\n"
        "os.write(1, pre)\n"
        "ack = os.read(0, 1)\n"
        "trailing = os.read(0, 1)\n"
        "if ack != b'\\x06' or trailing:\n"
        "    sys.exit(23)\n"
        "os.write(1, post)\n"
    )
    return (sys.executable, "-I", "-S", "-B", "-c", code)


class Task0B4cHarnessTests(unittest.TestCase):
    def test_runs_one_pre_ack_eof_post_exchange_with_an_isolated_sentinel(self) -> None:
        from tools.reaper_v4_fixture_harness import run_controlled_fixture

        pre, ack, post = exchange()
        result = run_controlled_fixture(
            _sentinel(
                protocol.encode_frame(protocol.FrameType.PRE, 0, pre),
                protocol.encode_frame(protocol.FrameType.POST, 1, post),
            ),
            timeout_ms=1500,
        )

        self.assertEqual(ack, b"\x06")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.pre_payload, pre)
        self.assertEqual(result.post_payload, post)
        self.assertEqual(result.diagnostic, b"")

    def test_refuses_a_terminal_frame_before_pre(self) -> None:
        from tools.reaper_v4_fixture_harness import (
            FixtureHarnessError,
            run_controlled_fixture,
        )

        _pre, _ack, post = exchange()
        command = (
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import base64, os\n"
            f"os.write(1, base64.b64decode({base64.b64encode(protocol.encode_frame(protocol.FrameType.POST, 1, post))!r}))\n",
        )
        with self.assertRaisesRegex(FixtureHarnessError, "PRE"):
            run_controlled_fixture(command, timeout_ms=1500)

    def test_refuses_a_post_emitted_before_the_ack(self) -> None:
        from tools.reaper_v4_fixture_harness import (
            FixtureHarnessError,
            run_controlled_fixture,
        )

        pre, _ack, post = exchange()
        combined = protocol.encode_frame(protocol.FrameType.PRE, 0, pre) + protocol.encode_frame(
            protocol.FrameType.POST, 1, post,
        )
        command = (
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import base64, os\n"
            f"os.write(1, base64.b64decode({base64.b64encode(combined)!r}))\n",
        )
        with self.assertRaisesRegex(FixtureHarnessError, "before ACK"):
            run_controlled_fixture(command, timeout_ms=1500)

    def test_refuses_child_exit_before_any_pre_frame(self) -> None:
        from tools.reaper_v4_fixture_harness import (
            FixtureHarnessError,
            run_controlled_fixture,
        )

        command = (sys.executable, "-I", "-S", "-B", "-c", "raise SystemExit(17)")
        with self.assertRaisesRegex(FixtureHarnessError, "PRE"):
            run_controlled_fixture(command, timeout_ms=1500)


if __name__ == "__main__":
    unittest.main()
