"""Bounded parent-side PRE/ACK/POST harness for the non-REAPER fixture."""
from __future__ import annotations

import dataclasses
import os
import select
import struct
import subprocess
import time

from tools import reaper_v4_protocol as protocol
from tools import reaper_v4_receipt_schema as receipt_schema


__all__ = ("FixtureHarnessError", "FixtureResult", "run_controlled_fixture")

_HEADER = struct.Struct(">8sBBHI")
_MAX_DIAGNOSTIC_BYTES = 1024
_MAX_OUTPUT_BYTES = protocol.MAX_FRAME_BYTES * 2


class FixtureHarnessError(RuntimeError):
    """The bounded parent-side exchange did not end in one accepted receipt."""


@dataclasses.dataclass(frozen=True)
class FixtureResult:
    """The only accepted non-REAPER fixture result."""

    returncode: int
    pre_payload: dict[str, object]
    post_payload: dict[str, object]
    diagnostic: bytes


def _next_frame(buffer: bytearray) -> tuple[protocol.Frame, int] | None:
    if len(buffer) < _HEADER.size:
        return None
    _magic, _schema, _kind, _sequence, size = _HEADER.unpack(buffer[:_HEADER.size])
    if size > protocol.MAX_PAYLOAD_BYTES:
        raise FixtureHarnessError("fixture frame exceeds the declared bound")
    frame_size = _HEADER.size + size
    if len(buffer) < frame_size:
        return None
    try:
        frame, used = protocol.decode_frame(bytes(buffer[:frame_size]))
    except protocol.ProtocolError as error:
        raise FixtureHarnessError("fixture frame is invalid") from error
    if used != frame_size:
        raise FixtureHarnessError("fixture frame length is invalid")
    return frame, frame_size


def _close_stream(stream: object) -> None:
    try:
        close = getattr(stream, "close")
        close()
    except (AttributeError, OSError, ValueError):
        pass


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_controlled_fixture(command: tuple[str, ...], timeout_ms: int) -> FixtureResult:
    """Accept exactly one PRE, send ACK+EOF, then accept one terminal POST."""
    if (
        type(command) is not tuple
        or not 1 <= len(command) <= 32
        or any(type(argument) is not str or not argument for argument in command)
        or not command[0].startswith("/")
        or type(timeout_ms) is not int
        or not 1 <= timeout_ms <= 30000
    ):
        raise FixtureHarnessError("fixture command is invalid")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            pass_fds=(),
            env={"LC_ALL": "C"},
        )
    except OSError as error:
        raise FixtureHarnessError("fixture command cannot be started") from error

    stdin_closed = False
    raw_stdin: object | None = None
    stdout_closed = False
    stderr_closed = False
    pre_payload: dict[str, object] | None = None
    post_payload: dict[str, object] | None = None
    output = bytearray()
    diagnostic = bytearray()
    deadline_ns = time.monotonic_ns() + timeout_ms * 1_000_000
    try:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise FixtureHarnessError("fixture pipes are unavailable")
        raw_stdin = process.stdin.detach()
        stdin_fd = raw_stdin.fileno()
        stdout_fd = process.stdout.fileno()
        stderr_fd = process.stderr.fileno()
        os.set_blocking(stdout_fd, False)
        os.set_blocking(stderr_fd, False)
        stage = "pre"
        while True:
            if time.monotonic_ns() > deadline_ns:
                raise FixtureHarnessError("fixture exchange timed out")
            parsed = _next_frame(output)
            if parsed is not None:
                frame, used = parsed
                del output[:used]
                if stage == "pre":
                    if frame.frame_type is not protocol.FrameType.PRE or frame.sequence != 0:
                        raise FixtureHarnessError("fixture did not emit PRE first")
                    if output:
                        raise FixtureHarnessError("fixture emitted bytes before ACK")
                    try:
                        receipt_schema.validate_pre_payload(frame.payload, 0)
                    except receipt_schema.ReceiptSchemaError as error:
                        raise FixtureHarnessError("fixture PRE payload is invalid") from error
                    try:
                        written = os.write(stdin_fd, receipt_schema.ACK_BYTE)
                    except OSError as error:
                        raise FixtureHarnessError("fixture ACK cannot be written") from error
                    if written != len(receipt_schema.ACK_BYTE):
                        raise FixtureHarnessError("fixture ACK write was short")
                    raw_stdin.close()
                    stdin_closed = True
                    pre_payload = frame.payload
                    stage = "post"
                    continue
                if stage == "post":
                    if frame.frame_type is not protocol.FrameType.POST or frame.sequence != 1:
                        raise FixtureHarnessError("fixture terminal POST is invalid")
                    if output:
                        raise FixtureHarnessError("fixture emitted trailing stdout bytes")
                    if pre_payload is None:
                        raise FixtureHarnessError("fixture POST lacks PRE")
                    try:
                        receipt_schema.validate_exchange(
                            pre_payload,
                            receipt_schema.ACK_BYTE,
                            frame.payload,
                        )
                    except receipt_schema.ReceiptSchemaError as error:
                        raise FixtureHarnessError("fixture receipt exchange is invalid") from error
                    post_payload = frame.payload
                    stage = "terminal"
                    continue
                raise FixtureHarnessError("fixture emitted more than two receipt frames")
            if len(output) > _MAX_OUTPUT_BYTES:
                raise FixtureHarnessError("fixture stdout exceeds the declared bound")
            if stage == "terminal" and stdout_closed and stderr_closed:
                break
            readable = []
            if not stdout_closed:
                readable.append(stdout_fd)
            if not stderr_closed:
                readable.append(stderr_fd)
            if not readable:
                break
            remaining = max(0, deadline_ns - time.monotonic_ns()) / 1_000_000_000
            ready, _writable, _exceptional = select.select(readable, (), (), remaining)
            if not ready:
                raise FixtureHarnessError("fixture exchange timed out")
            for descriptor in ready:
                try:
                    chunk = os.read(descriptor, 4096)
                except BlockingIOError:
                    continue
                except OSError as error:
                    raise FixtureHarnessError("fixture pipe cannot be read") from error
                if descriptor == stdout_fd:
                    if chunk:
                        output.extend(chunk)
                    else:
                        stdout_closed = True
                        if stage == "pre":
                            raise FixtureHarnessError("fixture stdout closed before PRE")
                        if stage != "terminal":
                            raise FixtureHarnessError("fixture stdout closed before terminal POST")
                else:
                    if chunk:
                        diagnostic.extend(chunk)
                        if len(diagnostic) > _MAX_DIAGNOSTIC_BYTES:
                            raise FixtureHarnessError("fixture diagnostic exceeds the declared bound")
                    else:
                        stderr_closed = True
        if pre_payload is None or post_payload is None or process.wait(timeout=0) != 0:
            raise FixtureHarnessError("fixture did not complete a clean exchange")
        return FixtureResult(process.returncode, pre_payload, post_payload, bytes(diagnostic))
    except FixtureHarnessError:
        raise
    except Exception as error:
        raise FixtureHarnessError("fixture exchange failed") from error
    finally:
        if not stdin_closed:
            _close_stream(raw_stdin if raw_stdin is not None else process.stdin)
        _stop_process(process)
        if process.stdout is not None:
            _close_stream(process.stdout)
        if process.stderr is not None:
            _close_stream(process.stderr)
