"""Non-admissible pure compatibility helpers for the future V4 session root."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from tools import reaper_v4_attester as attester
from tools import reaper_v4_child_runner as child_runner
from tools import reaper_v4_measurements as measurements
from tools import reaper_v4_protocol as protocol
from tools import reaper_v4_receipt_schema as receipt_schema


__all__ = (
    "SessionError", "SessionConfig", "SessionResult", "load_session_config", "run_session",
)
SESSION_ENTRYPOINT_KIND = "session_entrypoint"
SESSION_ENTRYPOINT_ROLE = "same_namespace_pre_ack_child_post_owner"
SESSION_CONFIG_PATH = "/run/m3-v4/session-config.json"
SESSION_DIGEST_PATH = "/run/m3-v4/session-config.sha256"
SESSION_CONFIG_KEYS = (
    "schema", "namespace", "session_config_sha256", "base_config",
    "session_policy_sha256", "direct_input_digests", "row",
    "runtime_manifest_sha256", "run_input_manifest_sha256",
    "fixture_manifest_sha256", "namespace_policy_sha256",
    "fixture_certificates", "bwrap", "namespace_expectations", "child", "limits",
)
MAX_SESSION_CONFIG_BYTES = 8192
MAX_SESSION_NODES = 256
MAX_SESSION_DEPTH = 16
MAX_SESSION_STRING_BYTES = 512
MIN_SESSION_INTEGER = -9223372036854775808
MAX_SESSION_INTEGER = 9223372036854775807


class SessionError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True, init=False)
class SessionConfig:
    data: Mapping[str, object]

    def __init__(self) -> None:
        raise SessionError("session execution is not admitted")


@dataclasses.dataclass(frozen=True, init=False)
class SessionResult:
    child_pid: int
    child_returncode: int
    pre_monotonic_ns: int
    post_monotonic_ns: int

    def __init__(self) -> None:
        raise SessionError("session execution is not admitted")


def _freeze_session_data(value: object) -> object:
    pending = [(value, 0)]
    seen = set()
    node_count = 0
    byte_count = 0
    while pending:
        item, depth = pending.pop()
        if depth > MAX_SESSION_DEPTH:
            raise SessionError("session data exceeds the bounded nesting depth")
        item_type = type(item)
        if depth == MAX_SESSION_DEPTH and (item_type is dict or item_type is list or item_type is tuple):
            raise SessionError("session data exceeds the bounded nesting depth")
        node_count += 1
        if node_count > MAX_SESSION_NODES:
            raise SessionError("session data exceeds the bounded node budget")
        if item_type is str:
            if len(item) > MAX_SESSION_STRING_BYTES:
                raise SessionError("session strings must be printable ASCII")
            try:
                item_bytes = item.encode("ascii")
            except UnicodeEncodeError as error:
                raise SessionError("session strings must be printable ASCII") from error
            if not all(32 <= byte <= 126 for byte in item_bytes):
                raise SessionError("session strings must be printable ASCII")
            if byte_count + len(item) > MAX_SESSION_CONFIG_BYTES:
                raise SessionError("session data exceeds the bounded byte budget")
            byte_count += len(item)
        elif item_type is bool:
            byte_count += 4 if item else 5
        elif item is None:
            byte_count += 4
        elif item_type is int:
            if not MIN_SESSION_INTEGER <= item <= MAX_SESSION_INTEGER:
                raise SessionError("session integer is outside the bounded range")
            item_text = str(item)
            byte_count += len(item_text)
        elif item_type is dict:
            if len(item) > MAX_SESSION_NODES - node_count - len(pending):
                raise SessionError("session data exceeds the bounded node budget")
            if byte_count + 2 + len(item) > MAX_SESSION_CONFIG_BYTES:
                raise SessionError("session data exceeds the bounded byte budget")
            identity = id(item)
            if identity in seen:
                raise SessionError("session data cannot contain aliases or cycles")
            seen.add(identity)
            byte_count += 2 + len(item)
            for key, child in item.items():
                if type(key) is not str:
                    raise SessionError("session object keys must be strings")
                if len(key) > MAX_SESSION_STRING_BYTES:
                    raise SessionError("session object keys must be printable ASCII")
                try:
                    key_bytes = key.encode("ascii")
                except UnicodeEncodeError as error:
                    raise SessionError("session object keys must be printable ASCII") from error
                if not all(32 <= byte <= 126 for byte in key_bytes):
                    raise SessionError("session object keys must be printable ASCII")
                if byte_count + len(key) > MAX_SESSION_CONFIG_BYTES:
                    raise SessionError("session data exceeds the bounded byte budget")
                byte_count += len(key)
                pending.append((child, depth + 1))
        elif item_type is list:
            if len(item) > MAX_SESSION_NODES - node_count - len(pending):
                raise SessionError("session data exceeds the bounded node budget")
            if byte_count + 2 + len(item) > MAX_SESSION_CONFIG_BYTES:
                raise SessionError("session data exceeds the bounded byte budget")
            identity = id(item)
            if identity in seen:
                raise SessionError("session data cannot contain aliases or cycles")
            seen.add(identity)
            byte_count += 2 + len(item)
            for child in item:
                pending.append((child, depth + 1))
        elif item_type is tuple:
            if len(item) > MAX_SESSION_NODES - node_count - len(pending):
                raise SessionError("session data exceeds the bounded node budget")
            if byte_count + 2 + len(item) > MAX_SESSION_CONFIG_BYTES:
                raise SessionError("session data exceeds the bounded byte budget")
            if item:
                identity = id(item)
                if identity in seen:
                    raise SessionError("session data cannot contain aliases or cycles")
                seen.add(identity)
            keys = set()
            byte_count += 2 + len(item)
            for pair in item:
                if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str:
                    raise SessionError("session JSON object pairs are invalid")
                key = pair[0]
                if key in keys:
                    raise SessionError("session JSON object has duplicate keys")
                keys.add(key)
                if len(key) > MAX_SESSION_STRING_BYTES:
                    raise SessionError("session object keys must be printable ASCII")
                try:
                    key_bytes = key.encode("ascii")
                except UnicodeEncodeError as error:
                    raise SessionError("session object keys must be printable ASCII") from error
                if not all(32 <= byte <= 126 for byte in key_bytes):
                    raise SessionError("session object keys must be printable ASCII")
                if byte_count + len(key) > MAX_SESSION_CONFIG_BYTES:
                    raise SessionError("session data exceeds the bounded byte budget")
                byte_count += len(key)
                pending.append((pair[1], depth + 1))
        else:
            raise SessionError("session data contains an unsupported value")
        if byte_count > MAX_SESSION_CONFIG_BYTES:
            raise SessionError("session data exceeds the bounded byte budget")
    if type(value) is list:
        return tuple(_freeze_session_data(item) for item in value)
    if type(value) is dict:
        pairs = value.items()
    elif type(value) is tuple:
        pairs = value
    else:
        return value
    return types.MappingProxyType({key: _freeze_session_data(item) for key, item in pairs})


def _canonical_session_json_bytes(value: object) -> bytes:
    materialized = _materialize_exact_builtins(value)
    try:
        text = json.dumps(materialized, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        result = text.encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SessionError("session data is not canonical JSON") from error
    if len(result) > MAX_SESSION_CONFIG_BYTES:
        raise SessionError("session data exceeds the canonical byte budget")
    return result


def _session_config_digest(value: object) -> str:
    materialized = _materialize_exact_builtins(value)
    if (
        type(materialized) is not dict
        or "session_config_sha256" not in materialized
        or type(materialized["session_config_sha256"]) is not str
    ):
        raise SessionError("session configuration must be an object")
    projection = dict(materialized)
    projection.pop("session_config_sha256", None)
    canonical = _canonical_session_json_bytes(projection)
    digest = hashlib.sha256(canonical)
    return digest.hexdigest()


def _parse_session_config_bytes(config_bytes: bytes, sidecar_bytes: bytes) -> Mapping[str, object]:
    if type(config_bytes) is not bytes or not config_bytes or len(config_bytes) > MAX_SESSION_CONFIG_BYTES:
        raise SessionError("session configuration bytes are invalid")
    if type(sidecar_bytes) is not bytes or len(sidecar_bytes) != 64:
        raise SessionError("session digest sidecar is invalid")
    if not all(48 <= byte <= 57 or 97 <= byte <= 102 for byte in sidecar_bytes):
        raise SessionError("session digest sidecar is invalid")
    try:
        parsed = json.loads(config_bytes.decode("ascii"), object_pairs_hook=tuple)
    except (RecursionError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SessionError("session configuration is not canonical JSON") from error
    if type(parsed) is not tuple:
        raise SessionError("session configuration must be an object")
    frozen = _freeze_session_data(parsed)
    if _canonical_session_json_bytes(frozen) != config_bytes:
        raise SessionError("session configuration bytes are not canonical")
    if set(frozen) != set(SESSION_CONFIG_KEYS) or type(frozen["schema"]) is not int or frozen["schema"] != 1:
        raise SessionError("session configuration top-level shape is invalid")
    base_config = frozen["base_config"]
    if type(base_config) is not type(frozen) or set(base_config) != {"schema", "namespace", "nonce", "config_sha256", "inputs"}:
        raise SessionError("session base configuration shape is invalid")
    if frozen["namespace"] != base_config["namespace"] or frozen["schema"] != base_config["schema"]:
        raise SessionError("session base configuration identity is invalid")
    embedded = frozen["session_config_sha256"]
    if type(embedded) is not str or embedded.encode("ascii") != sidecar_bytes or _session_config_digest(frozen) != embedded:
        raise SessionError("session configuration digest does not match")
    return frozen


def _materialize_exact_builtins(value: object) -> object:
    pending = [(value, 0)]
    seen = set()
    node_count = 0
    byte_count = 0
    while pending:
        item, depth = pending.pop()
        if depth > MAX_SESSION_DEPTH:
            raise SessionError("session data exceeds the bounded nesting depth")
        item_type = type(item)
        if depth == MAX_SESSION_DEPTH and (
            item_type is dict or item_type is list or item_type is tuple or item_type is types.MappingProxyType
        ):
            raise SessionError("session data exceeds the bounded nesting depth")
        node_count += 1
        if node_count > MAX_SESSION_NODES:
            raise SessionError("session data exceeds the bounded node budget")
        if item_type is str:
            if len(item) > MAX_SESSION_STRING_BYTES:
                raise SessionError("session strings must be printable ASCII")
            try:
                item_bytes = item.encode("ascii")
            except UnicodeEncodeError as error:
                raise SessionError("session strings must be printable ASCII") from error
            if not all(32 <= byte <= 126 for byte in item_bytes):
                raise SessionError("session strings must be printable ASCII")
            if byte_count + len(item) > MAX_SESSION_CONFIG_BYTES:
                raise SessionError("session data exceeds the bounded byte budget")
            byte_count += len(item)
        elif item_type is bool:
            byte_count += 4 if item else 5
        elif item is None:
            byte_count += 4
        elif item_type is int:
            if not MIN_SESSION_INTEGER <= item <= MAX_SESSION_INTEGER:
                raise SessionError("session integer is outside the bounded range")
            item_text = str(item)
            byte_count += len(item_text)
        elif item_type is dict or item_type is types.MappingProxyType:
            if len(item) > MAX_SESSION_NODES - node_count - len(pending):
                raise SessionError("session data exceeds the bounded node budget")
            if byte_count + 2 + len(item) > MAX_SESSION_CONFIG_BYTES:
                raise SessionError("session data exceeds the bounded byte budget")
            identity = id(item)
            if identity in seen:
                raise SessionError("session data cannot contain aliases or cycles")
            seen.add(identity)
            byte_count += 2 + len(item)
            for key, child in item.items():
                if type(key) is not str:
                    raise SessionError("session object keys must be strings")
                if len(key) > MAX_SESSION_STRING_BYTES:
                    raise SessionError("session object keys must be printable ASCII")
                try:
                    key_bytes = key.encode("ascii")
                except UnicodeEncodeError as error:
                    raise SessionError("session object keys must be printable ASCII") from error
                if not all(32 <= byte <= 126 for byte in key_bytes):
                    raise SessionError("session object keys must be printable ASCII")
                if byte_count + len(key) > MAX_SESSION_CONFIG_BYTES:
                    raise SessionError("session data exceeds the bounded byte budget")
                byte_count += len(key)
                pending.append((child, depth + 1))
        elif item_type is list or item_type is tuple:
            if len(item) > MAX_SESSION_NODES - node_count - len(pending):
                raise SessionError("session data exceeds the bounded node budget")
            if byte_count + 2 + len(item) > MAX_SESSION_CONFIG_BYTES:
                raise SessionError("session data exceeds the bounded byte budget")
            if item_type is list or item:
                identity = id(item)
                if identity in seen:
                    raise SessionError("session data cannot contain aliases or cycles")
                seen.add(identity)
            byte_count += 2 + len(item)
            for child in item:
                pending.append((child, depth + 1))
        else:
            raise SessionError("session data contains an unsupported value")
        if byte_count > MAX_SESSION_CONFIG_BYTES:
            raise SessionError("session data exceeds the bounded byte budget")
    if type(value) is dict or type(value) is types.MappingProxyType:
        return {key: _materialize_exact_builtins(item) for key, item in value.items()}
    if type(value) is list or type(value) is tuple:
        return [_materialize_exact_builtins(item) for item in value]
    return value


def _base_config_projection(config: SessionConfig) -> dict[str, object]:
    if type(config) is not SessionConfig:
        raise SessionError("session configuration is invalid")
    if type(config.data) is not types.MappingProxyType:
        raise SessionError("session configuration is invalid")
    try:
        base_value = config.data["base_config"]
    except (KeyError, TypeError) as error:
        raise SessionError("session configuration is invalid")
    base_config = _materialize_exact_builtins(base_value)
    if type(base_config) is not dict or set(base_config) != {"schema", "namespace", "nonce", "config_sha256", "inputs"}:
        raise SessionError("session base configuration is invalid")
    projection = dict(base_config)
    attester.validate_config(attester.AttesterConfig(projection))
    return projection


def _validate_and_encode_receipt(
    payload: dict[str, object], phase: receipt_schema.ReceiptPhase, sequence: int
) -> tuple[receipt_schema.ReceiptPayload, bytes]:
    if type(payload) is not dict or type(sequence) is not int:
        raise SessionError("receipt payload must use exact built-in containers")
    if phase is receipt_schema.ReceiptPhase.PRE and sequence == 0:
        receipt = receipt_schema.validate_pre_payload(payload, sequence)
        frame_type = protocol.FrameType.PRE
    elif phase is receipt_schema.ReceiptPhase.POST and sequence == 1:
        receipt = receipt_schema.validate_post_payload(payload, sequence)
        frame_type = protocol.FrameType.POST
    else:
        raise SessionError("receipt phase and sequence are invalid")
    return receipt, protocol.encode_frame(frame_type, sequence, payload)


def load_session_config(config_path: str, digest_path: str) -> SessionConfig:
    raise SessionError("session execution is not admitted")


def run_session(config: SessionConfig) -> SessionResult:
    raise SessionError("session execution is not admitted")
