"""Non-admissible, in-memory grammar for V4 PRE/ACK/POST receipts."""
from __future__ import annotations

import dataclasses
import enum
import types
from collections.abc import Mapping
from tools import reaper_v4_protocol

__all__ = (
    "ReceiptSchemaError", "ReceiptPhase", "ReceiptPayload", "ACK_BYTE", "PRE_KEYS",
    "POST_KEYS", "ATTESTATION_KEYS", "validate_pre_payload", "validate_ack_bytes",
    "validate_post_payload", "validate_exchange",
)

ACK_BYTE = b"\x06"
INPUT_NAME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789_-"
PRE_KEYS = ("schema", "namespace", "nonce", "config_sha256", "inputs", "row", "phase", "no_child_started", "attestation")
POST_KEYS = ("schema", "namespace", "nonce", "config_sha256", "inputs", "row", "phase", "terminal", "child_pid", "child_returncode", "pre_monotonic_ns", "post_monotonic_ns", "attestation")
ROW_KEYS = ("sample_rate_hz", "block_size")
MAX_RECEIPT_NODES = 512
MAX_RECEIPT_DEPTH = 32
MAX_RECEIPT_INPUT_BYTES = 8192
MAX_RECEIPT_STRING_CHARS = 256
ATTESTATION_KEYS = (
    "home", "pwd", "cwd", "environment_keys", "forbidden_env_absent",
    "runtime_manifest_sha256", "run_input_manifest_sha256", "bwrap_path",
    "bwrap_version", "bwrap_argv_sha256",
    "production_bundle_absent", "private_vst_empty", "private_vst3_empty",
    "private_home_private", "scan_root_readonly", "scan_descendants_readonly",
    "no_later_scan_mount", "x11_identity", "source_fds_absent", "control_root_absent",
    "dumpable_disabled", "capabilities_empty", "proc_receipt_blocked", "proc_mem_blocked",
)


class ReceiptSchemaError(ValueError):
    pass


class ReceiptPhase(enum.IntEnum):
    PRE = 1
    POST = 2


@dataclasses.dataclass(frozen=True, init=False)
class ReceiptPayload:
    """A validator-created immutable receipt value; direct initialization is forbidden."""

    phase: ReceiptPhase
    sequence: int
    payload: Mapping[str, object]

    def __init__(self) -> None:
        raise ReceiptSchemaError("ReceiptPayload is validator-created")


def _snapshot_receipt_payload(value: object) -> object:
    """Copy bounded plain receipt data before validation can inspect it."""
    remaining = [MAX_RECEIPT_NODES]
    remaining_bytes = [MAX_RECEIPT_INPUT_BYTES]

    def charge(amount: int) -> None:
        remaining_bytes[0] -= amount
        if remaining_bytes[0] < 0:
            raise ReceiptSchemaError("receipt payload exceeds the bounded byte budget")

    def text_size(text: str) -> int:
        if len(text) > MAX_RECEIPT_STRING_CHARS:
            raise ReceiptSchemaError("receipt payload string exceeds the bounded byte budget")
        return len(text) * 4

    def snapshot(item: object, ancestors: frozenset[int], depth: int) -> object:
        if depth >= MAX_RECEIPT_DEPTH:
            raise ReceiptSchemaError("receipt payload exceeds the bounded nesting depth")
        if isinstance(item, Mapping):
            if type(item) is not dict:
                raise ReceiptSchemaError("receipt mappings must have exact built-in containers")
            identity = id(item)
            if identity in ancestors:
                raise ReceiptSchemaError("receipt payload cannot contain cycles")
            if len(item) > MAX_RECEIPT_NODES:
                raise ReceiptSchemaError("receipt payload exceeds the bounded node budget")
            try:
                copied = dict(item)
            except (TypeError, ValueError, RuntimeError) as error:
                raise ReceiptSchemaError("receipt mapping cannot be snapshotted") from error
            if len(copied) > MAX_RECEIPT_NODES:
                raise ReceiptSchemaError("receipt payload exceeds the bounded node budget")
            remaining[0] -= len(copied) + 1
            if remaining[0] < 0:
                raise ReceiptSchemaError("receipt payload exceeds the bounded node budget")
            if not all(type(key) is str for key in copied):
                raise ReceiptSchemaError("receipt payload keys must be strings")
            charge(2 + len(copied))
            for key in copied:
                charge(text_size(key))
            return {
                key: snapshot(item, ancestors | {identity}, depth + 1)
                for key, item in copied.items()
            }
        if isinstance(item, (list, tuple)):
            if type(item) not in (list, tuple):
                raise ReceiptSchemaError("receipt sequences must have exact built-in containers")
            identity = id(item)
            if identity in ancestors:
                raise ReceiptSchemaError("receipt payload cannot contain cycles")
            if len(item) > MAX_RECEIPT_NODES:
                raise ReceiptSchemaError("receipt payload exceeds the bounded node budget")
            try:
                copied = tuple(item)
            except (TypeError, ValueError, RuntimeError) as error:
                raise ReceiptSchemaError("receipt sequence cannot be snapshotted") from error
            if len(copied) > MAX_RECEIPT_NODES:
                raise ReceiptSchemaError("receipt payload exceeds the bounded node budget")
            remaining[0] -= len(copied) + 1
            if remaining[0] < 0:
                raise ReceiptSchemaError("receipt payload exceeds the bounded node budget")
            charge(2 + len(copied))
            values = tuple(snapshot(item, ancestors | {identity}, depth + 1) for item in copied)
            return list(values) if type(item) is list else values
        if type(item) is str:
            charge(text_size(item))
            return item
        if type(item) is int:
            charge(max(1, (item.bit_length() * 30103 + 99999) // 100000))
            return item
        if type(item) is bool:
            charge(5)
            return item
        if item is None:
            charge(4)
            return item
        raise ReceiptSchemaError("receipt payload has an unsupported value")

    return snapshot(value, frozenset(), 0)


def _freeze_receipt_payload(value: object) -> object:
    if type(value) is dict:
        return types.MappingProxyType({
            key: _freeze_receipt_payload(item) for key, item in value.items()
        })
    if type(value) in (list, tuple):
        return tuple(_freeze_receipt_payload(item) for item in value)
    return value


def _validated_receipt_payload(
    phase: ReceiptPhase, sequence: int, payload: Mapping[str, object]
) -> ReceiptPayload:
    if (
        type(phase) is not ReceiptPhase
        or type(sequence) is not int
        or sequence != (0 if phase is ReceiptPhase.PRE else 1)
        or type(payload) is not dict
    ):
        raise ReceiptSchemaError("validated receipt construction is invalid")
    receipt = object.__new__(ReceiptPayload)
    object.__setattr__(receipt, "phase", phase)
    object.__setattr__(receipt, "sequence", sequence)
    object.__setattr__(receipt, "payload", _freeze_receipt_payload(payload))
    return receipt


def validate_pre_payload(payload: Mapping[str, object], sequence: int) -> ReceiptPayload:
    if type(sequence) is not int or sequence != 0:
        raise ReceiptSchemaError("PRE sequence is invalid")
    if type(payload) is not dict:
        raise ReceiptSchemaError("PRE payload is invalid")
    try:
        value = _snapshot_receipt_payload(payload)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise ReceiptSchemaError("PRE payload is invalid") from exc
    if value is None or set(value) != set(PRE_KEYS):
        raise ReceiptSchemaError("PRE keys are invalid")
    if (
        type(value["schema"]) is not int
        or type(value["namespace"]) is not str
        or type(value["nonce"]) is not str
        or type(value["config_sha256"]) is not str
    ):
        raise ReceiptSchemaError("PRE identity types are invalid")
    if (
        type(value["phase"]) is not str
        or value["phase"] != "pre"
        or value["no_child_started"] is not True
    ):
        raise ReceiptSchemaError("PRE phase is invalid")
    row = value["row"]
    if (
        type(row) is not dict
        or set(row) != set(ROW_KEYS)
        or type(row["sample_rate_hz"]) is not int
        or row["sample_rate_hz"] != 44100
        or type(row["block_size"]) is not int
        or row["block_size"] != 32
    ):
        raise ReceiptSchemaError("PRE row is invalid")
    inputs = value["inputs"]
    if (
        type(inputs) is not dict
        or not inputs
        or len(inputs) > 16
        or any(
            type(key) is not str
            or not key
            or key[0] not in "abcdefghijklmnopqrstuvwxyz"
            or any(character not in INPUT_NAME_CHARS for character in key)
            or not 1 <= len(key) <= 128
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for key, digest in inputs.items()
        )
    ):
        raise ReceiptSchemaError("PRE input names are invalid")
    try:
        reaper_v4_protocol.validate_config({key: value[key] for key in ("schema", "namespace", "nonce", "config_sha256", "inputs")})
    except (KeyError, TypeError, reaper_v4_protocol.ProtocolError) as exc:
        raise ReceiptSchemaError("PRE identity is invalid") from exc
    attestation = value["attestation"]
    if type(attestation) is not dict or set(attestation) != set(ATTESTATION_KEYS):
        raise ReceiptSchemaError("PRE attestation keys are invalid")
    if any(attestation[key] is not True for key in (
        "production_bundle_absent", "private_vst_empty", "private_vst3_empty", "private_home_private",
        "scan_root_readonly", "scan_descendants_readonly", "no_later_scan_mount", "source_fds_absent",
        "control_root_absent", "dumpable_disabled", "capabilities_empty", "proc_receipt_blocked", "proc_mem_blocked",
    )):
        raise ReceiptSchemaError("PRE containment attestation is invalid")
    for key in ("home", "pwd", "cwd", "bwrap_path"):
        item = attestation[key]
        if (
            type(item) is not str
            or not all(32 <= ord(character) <= 126 for character in item)
            or not 1 <= len(item) <= 256
        ):
            raise ReceiptSchemaError("PRE string attestation is invalid")
    if (
        type(attestation["bwrap_version"]) is not str
        or not all(32 <= ord(character) <= 126 for character in attestation["bwrap_version"])
        or not 1 <= len(attestation["bwrap_version"]) <= 128
    ):
        raise ReceiptSchemaError("PRE bwrap version is invalid")
    for key in ("runtime_manifest_sha256", "run_input_manifest_sha256", "bwrap_argv_sha256"):
        item = attestation[key]
        if type(item) is not str or len(item) != 64 or any(char not in "0123456789abcdef" for char in item):
            raise ReceiptSchemaError("PRE digest attestation is invalid")
    for key, limit in (("environment_keys", 32), ("forbidden_env_absent", 32)):
        items = attestation[key]
        if type(items) is not list or len(items) > limit:
            raise ReceiptSchemaError("PRE list attestation is invalid")
        if any(
            type(item) is not str
            or not all(32 <= ord(character) <= 126 for character in item)
            or not 1 <= len(item) <= 128
            for item in items
        ):
            raise ReceiptSchemaError("PRE list attestation is invalid")
        if len(set(items)) != len(items):
            raise ReceiptSchemaError("PRE list attestation is invalid")
    x11 = attestation["x11_identity"]
    if type(x11) is not dict or set(x11) != {"display", "authority", "socket", "screen", "protocol"}:
        raise ReceiptSchemaError("PRE X11 attestation is invalid")
    for key in ("display", "authority", "socket", "protocol"):
        item = x11[key]
        if (
            type(item) is not str
            or not all(32 <= ord(character) <= 126 for character in item)
            or not 1 <= len(item) <= 256
        ):
            raise ReceiptSchemaError("PRE X11 attestation is invalid")
    if type(x11["screen"]) is not int or not 0 <= x11["screen"] <= 2147483647:
        raise ReceiptSchemaError("PRE X11 attestation is invalid")
    try:
        frame = reaper_v4_protocol.encode_frame(reaper_v4_protocol.FrameType.PRE, sequence, value)
    except (TypeError, ValueError, reaper_v4_protocol.ProtocolError) as exc:
        raise ReceiptSchemaError("PRE frame is invalid") from exc
    if len(frame) > reaper_v4_protocol.MAX_FRAME_BYTES:
        raise ReceiptSchemaError("PRE frame exceeds limit")
    return _validated_receipt_payload(ReceiptPhase.PRE, sequence, value)


def validate_ack_bytes(ack: bytes) -> bytes:
    if type(ack) is not bytes or ack != ACK_BYTE:
        raise ReceiptSchemaError("ACK must be exactly one 0x06 byte")
    return ack


def validate_post_payload(payload: Mapping[str, object], sequence: int) -> ReceiptPayload:
    if type(sequence) is not int or sequence != 1:
        raise ReceiptSchemaError("POST sequence is invalid")
    if type(payload) is not dict:
        raise ReceiptSchemaError("POST payload is invalid")
    try:
        value = _snapshot_receipt_payload(payload)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise ReceiptSchemaError("POST payload is invalid") from exc
    if value is None or set(value) != set(POST_KEYS):
        raise ReceiptSchemaError("POST keys are invalid")
    if (
        type(value["schema"]) is not int
        or type(value["namespace"]) is not str
        or type(value["nonce"]) is not str
        or type(value["config_sha256"]) is not str
    ):
        raise ReceiptSchemaError("POST identity types are invalid")
    if (
        type(value["phase"]) is not str
        or value["phase"] != "post"
        or value["terminal"] is not True
    ):
        raise ReceiptSchemaError("POST phase is invalid")
    row = value["row"]
    if (
        type(row) is not dict
        or set(row) != set(ROW_KEYS)
        or type(row["sample_rate_hz"]) is not int
        or row["sample_rate_hz"] != 44100
        or type(row["block_size"]) is not int
        or row["block_size"] != 32
    ):
        raise ReceiptSchemaError("POST row is invalid")
    if type(value["child_pid"]) is not int or not 1 <= value["child_pid"] <= 2147483647:
        raise ReceiptSchemaError("POST child pid is invalid")
    if type(value["child_returncode"]) is not int or not -255 <= value["child_returncode"] <= 255:
        raise ReceiptSchemaError("POST child return code is invalid")
    if type(value["pre_monotonic_ns"]) is not int or not 1 <= value["pre_monotonic_ns"] <= 9223372036854775807:
        raise ReceiptSchemaError("POST pre clock is invalid")
    if type(value["post_monotonic_ns"]) is not int or not 1 <= value["post_monotonic_ns"] <= 9223372036854775807:
        raise ReceiptSchemaError("POST post clock is invalid")
    if value["post_monotonic_ns"] < value["pre_monotonic_ns"]:
        raise ReceiptSchemaError("POST clock precedes PRE clock")
    try:
        reaper_v4_protocol.validate_config({key: value[key] for key in ("schema", "namespace", "nonce", "config_sha256", "inputs")})
    except (KeyError, TypeError, reaper_v4_protocol.ProtocolError) as exc:
        raise ReceiptSchemaError("POST identity is invalid") from exc
    attestation = value["attestation"]
    if type(attestation) is not dict or set(attestation) != set((*ATTESTATION_KEYS, "scan_root_unchanged")):
        raise ReceiptSchemaError("POST attestation keys are invalid")
    if attestation["scan_root_unchanged"] is not True:
        raise ReceiptSchemaError("POST scan root attestation is invalid")
    try:
        validate_pre_payload({
            "schema": value["schema"], "namespace": value["namespace"], "nonce": value["nonce"],
            "config_sha256": value["config_sha256"], "inputs": value["inputs"], "row": value["row"], "phase": "pre",
            "no_child_started": True, "attestation": {key: attestation[key] for key in ATTESTATION_KEYS},
        }, 0)
    except (KeyError, TypeError, ReceiptSchemaError) as exc:
        raise ReceiptSchemaError("POST shared attestation is invalid") from exc
    try:
        frame = reaper_v4_protocol.encode_frame(reaper_v4_protocol.FrameType.POST, sequence, value)
    except (TypeError, ValueError, reaper_v4_protocol.ProtocolError) as exc:
        raise ReceiptSchemaError("POST frame is invalid") from exc
    if len(frame) > reaper_v4_protocol.MAX_FRAME_BYTES:
        raise ReceiptSchemaError("POST frame exceeds limit")
    return _validated_receipt_payload(ReceiptPhase.POST, sequence, value)


def validate_exchange(pre: Mapping[str, object], ack: bytes, post: Mapping[str, object]) -> tuple[ReceiptPayload, ReceiptPayload]:
    pre_receipt = validate_pre_payload(pre, 0)
    validate_ack_bytes(ack)
    post_receipt = validate_post_payload(post, 1)
    if any(pre_receipt.payload[key] != post_receipt.payload[key] for key in ("schema", "namespace", "nonce", "config_sha256", "inputs", "row")):
        raise ReceiptSchemaError("PRE and POST identities differ")
    if any(
        pre_receipt.payload["attestation"][key] != post_receipt.payload["attestation"][key]
        for key in ATTESTATION_KEYS
    ):
        raise ReceiptSchemaError("PRE and POST shared attestations differ")
    if post_receipt.payload["post_monotonic_ns"] < post_receipt.payload["pre_monotonic_ns"]:
        raise ReceiptSchemaError("POST clock precedes PRE clock")
    return pre_receipt, post_receipt
