"""Future V4 in-namespace PRE/ACK/child/POST session owner.

This module is intentionally source-authored before its execution gates.  Its
helpers encode the closed admission boundary; later tasks exercise them only
with separately approved fixtures.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import select
import stat
import time
import types
from collections.abc import Mapping
from tools import reaper_v4_attester as attester
from tools import reaper_v4_child_runner as child_runner
from tools import reaper_v4_measurements as measurements
from tools import reaper_v4_protocol as protocol
from tools import reaper_v4_receipt_schema as receipt_schema


__all__ = (
    "SessionError",
    "SessionConfig",
    "SessionResult",
    "load_session_config",
    "run_session",
)

SESSION_CONFIG_PATH = "/run/m3-v4/session-config.json"
SESSION_DIGEST_PATH = "/run/m3-v4/session-config.sha256"
SESSION_ENTRYPOINT_KIND = "session_entrypoint"
SESSION_ENTRYPOINT_ROLE = "same_namespace_pre_ack_child_post_owner"
DIAGNOSTIC_CODES = ("config", "preflight", "pre_write", "ack", "child", "post")
SESSION_CONFIG_MAX_BYTES = 8192
SESSION_CONFIG_MAX_NODES = 256
SESSION_CONFIG_MAX_DEPTH = 16
SIDECAR_BYTES = 64
MOUNTINFO_MAX_BYTES = 65536
MOUNTINFO_MAX_RECORDS = 128
INHERITED_FD_MAX_ENTRIES = 16
ID_MAP_MAX_RECORDS = 8
ID_MAP_MAX_BYTES = 256
XAUTHORITY_MAX_BYTES = 65536
SCAN_ENTRY_MAX_BYTES = 16777216
SCAN_TOTAL_MAX_BYTES = 33554432
HASH_CHUNK_BYTES = 65536
PRE_DEADLINE_MS = 5000
ACK_DEADLINE_MS = 5000
POST_DEADLINE_MS = 5000
DIAGNOSTIC_MAX_BYTES = 1024
MAX_FRAME_BYTES = 2064
CHILD_TIMEOUT_MS = 30000
CHILD_ENVIRONMENT_KEYS = ("DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY")
CHILD_ENVIRONMENT_ORDER = ("DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY")
SESSION_TOP_LEVEL_KEYS = (
    "schema", "namespace", "session_config_sha256", "base_config",
    "session_policy_sha256", "direct_input_digests", "row",
    "runtime_manifest_sha256", "run_input_manifest_sha256",
    "fixture_manifest_sha256", "namespace_policy_sha256",
    "fixture_certificates", "bwrap", "namespace_expectations", "child", "limits",
)
POLICY_KEYS = (
    "row", "direct_input_digests", "runtime_manifest_sha256",
    "run_input_manifest_sha256", "fixture_manifest_sha256",
    "namespace_policy_sha256", "fixture_certificates", "bwrap",
    "namespace_expectations", "child", "limits",
)
EVIDENCE_KEYS = (
    "user_namespace", "private_tree", "scan_root", "x11_identity",
    "descriptor_policy", "control_visibility", "measurement_root",
    "measurement_plan", "fixture_certificates",
)
ATTESTATION_KEYS = (
    "home", "pwd", "cwd", "environment_keys", "forbidden_env_absent",
    "runtime_manifest_sha256", "run_input_manifest_sha256", "bwrap_path",
    "bwrap_version", "bwrap_argv_sha256", "production_bundle_absent",
    "private_vst_empty", "private_vst3_empty", "private_home_private",
    "scan_root_readonly", "scan_descendants_readonly", "no_later_scan_mount",
    "x11_identity", "source_fds_absent", "control_root_absent",
    "dumpable_disabled", "capabilities_empty", "proc_receipt_blocked",
    "proc_mem_blocked",
)


class SessionError(RuntimeError):
    """A local session condition failed closed."""


@dataclasses.dataclass(frozen=True, init=False)
class SessionConfig:
    """A validated immutable snapshot; direct construction is forbidden."""

    data: Mapping[str, object]

    def __init__(self) -> None:
        raise SessionError("SessionConfig is validator-created")


@dataclasses.dataclass(frozen=True, init=False)
class SessionResult:
    """The in-memory terminal summary, not a durable receipt or acceptance."""

    child_pid: int
    child_returncode: int
    pre_monotonic_ns: int
    post_monotonic_ns: int

    def __init__(self) -> None:
        raise SessionError("SessionResult is session-created")


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SessionError("config is not canonical JSON") from error


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _freeze(value: object) -> object:
    if type(value) is dict:
        return types.MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) in (list, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _make_config(data: Mapping[str, object]) -> SessionConfig:
    instance = object.__new__(SessionConfig)
    object.__setattr__(instance, "data", _freeze(data))
    return instance


def _make_result(child_pid: int, child_returncode: int, pre_ns: int, post_ns: int) -> SessionResult:
    instance = object.__new__(SessionResult)
    object.__setattr__(instance, "child_pid", child_pid)
    object.__setattr__(instance, "child_returncode", child_returncode)
    object.__setattr__(instance, "pre_monotonic_ns", pre_ns)
    object.__setattr__(instance, "post_monotonic_ns", post_ns)
    return instance


def _reject_duplicate_keys(pairs: object) -> dict[str, object]:
    if type(pairs) is not list:
        raise SessionError("JSON object pairs are invalid")
    result: dict[str, object] = {}
    for pair in pairs:
        if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str or pair[0] in result:
            raise SessionError("JSON keys are invalid")
        result[pair[0]] = pair[1]
    return result


def _snapshot_json(value: object, depth: int, budget: list[int]) -> object:
    if depth > SESSION_CONFIG_MAX_DEPTH:
        raise SessionError("configuration nesting exceeds the fixed limit")
    budget[0] -= 1
    if budget[0] < 0:
        raise SessionError("configuration node limit exceeded")
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise SessionError("configuration keys are invalid")
        return {key: _snapshot_json(item, depth + 1, budget) for key, item in value.items()}
    if type(value) is list:
        return [_snapshot_json(item, depth + 1, budget) for item in value]
    if type(value) in (str, int, bool) or value is None:
        return value
    raise SessionError("configuration contains a non-built-in value")


def _read_regular_once(path: str, maximum: int) -> bytes:
    if path not in (SESSION_CONFIG_PATH, SESSION_DIGEST_PATH):
        raise SessionError("bootstrap path is not fixed")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > maximum:
            raise SessionError("bootstrap file is not bounded regular data")
        value = os.read(descriptor, maximum + 1)
        if len(value) > maximum or os.read(descriptor, 1):
            raise SessionError("bootstrap file is oversized or nonterminal")
        return value
    finally:
        os.close(descriptor)


def _prepare_diagnostic() -> bool:
    try:
        metadata = os.fstat(2)
        if not stat.S_ISFIFO(metadata.st_mode):
            return False
        os.set_blocking(2, False)
        return True
    except OSError:
        return False


def _diagnose(enabled: bool, code: str) -> None:
    if not enabled or code not in DIAGNOSTIC_CODES:
        return
    try:
        os.write(2, code.encode("ascii"))
    except OSError:
        pass


def _require_hex(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(letter not in "0123456789abcdef" for letter in value):
        raise SessionError("digest is invalid")
    return value


def _require_fixed_limits(limits: object) -> Mapping[str, object]:
    expected = {
        "pre_deadline_ms": PRE_DEADLINE_MS, "ack_deadline_ms": ACK_DEADLINE_MS,
        "post_deadline_ms": POST_DEADLINE_MS, "diagnostic_max_bytes": DIAGNOSTIC_MAX_BYTES,
        "max_frame_bytes": MAX_FRAME_BYTES, "child_timeout_ms": CHILD_TIMEOUT_MS,
    }
    if type(limits) is not dict or limits != expected:
        raise SessionError("limits are not the fixed session limits")
    return limits


def _require_absolute_path(path: object) -> str:
    if type(path) is not str or not path or len(path) > 512 or not path.startswith("/"):
        raise SessionError("path is invalid")
    parts = path.split("/")[1:]
    if not 1 <= len(parts) <= 16 or any(not 1 <= len(part) <= 64 or part in (".", "..") or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for char in part) for part in parts):
        raise SessionError("path components are invalid")
    return path


def _open_path_components(path: object, directory: bool) -> int:
    normalized = _require_absolute_path(path)
    descriptor = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        parts = normalized.split("/")[1:]
        for index, part in enumerate(parts):
            flags = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
            if directory or index != len(parts) - 1:
                flags |= os.O_DIRECTORY
            successor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = successor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _decode_mount_escape(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            output.append(value[index])
            index += 1
        elif value[index:index + 4] in ("\\040", "\\011", "\\012", "\\134"):
            output.append(chr(int(value[index + 1:index + 4], 8)))
            index += 4
        else:
            raise SessionError("mountinfo escape is invalid")
    return "".join(output)


def _read_bounded_chunks(descriptor: int, maximum: int) -> bytes:
    parts: list[bytes] = []
    total = 0
    while True:
        piece = os.read(descriptor, HASH_CHUNK_BYTES)
        if not piece:
            return b"".join(parts)
        total += len(piece)
        if total > maximum:
            raise SessionError("bounded read exceeded")
        parts.append(piece)


def _validate_session_data(data: object, sidecar: str) -> Mapping[str, object]:
    if type(data) is not dict or tuple(data) != SESSION_TOP_LEVEL_KEYS:
        raise SessionError("SessionConfig has an invalid closed shape")
    embedded = _require_hex(data["session_config_sha256"])
    without_digest = {key: value for key, value in data.items() if key != "session_config_sha256"}
    if embedded != sidecar or _sha256(without_digest) != embedded:
        raise SessionError("SessionConfig digest relationship is invalid")
    _require_fixed_limits(data["limits"])
    for key in ("runtime_manifest_sha256", "run_input_manifest_sha256", "fixture_manifest_sha256", "namespace_policy_sha256", "session_policy_sha256"):
        _require_hex(data[key])
    direct_inputs = data["direct_input_digests"]
    if type(direct_inputs) is not dict or not 1 <= len(direct_inputs) <= 15 or "session_policy" in direct_inputs:
        raise SessionError("direct input map is invalid")
    if any(type(name) is not str or _require_hex(digest) != digest for name, digest in direct_inputs.items()):
        raise SessionError("direct input digests are invalid")
    if _sha256({key: data[key] for key in POLICY_KEYS}) != data["session_policy_sha256"]:
        raise SessionError("session policy digest is invalid")
    expectations = data["namespace_expectations"]
    if type(expectations) is not dict or any(key not in expectations for key in EVIDENCE_KEYS):
        raise SessionError("admitted evidence projection is invalid")
    if _sha256(expectations) != data["namespace_policy_sha256"]:
        raise SessionError("namespace policy digest is invalid")
    return data


def load_session_config(config_path: str, digest_path: str) -> SessionConfig:
    diagnostic_ready = _prepare_diagnostic()
    try:
        if config_path != SESSION_CONFIG_PATH or digest_path != SESSION_DIGEST_PATH:
            raise SessionError("configuration paths must be fixed")
        sidecar = _read_regular_once(digest_path, SIDECAR_BYTES)
        if len(sidecar) != SIDECAR_BYTES:
            raise SessionError("digest sidecar is invalid")
        sidecar_text = sidecar.decode("ascii")
        _require_hex(sidecar_text)
        raw = _read_regular_once(config_path, SESSION_CONFIG_MAX_BYTES)
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
        snapshot = _snapshot_json(parsed, 0, [SESSION_CONFIG_MAX_NODES])
        return _make_config(_validate_session_data(snapshot, sidecar_text))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SessionError) as error:
        _diagnose(diagnostic_ready, "config")
        if type(error) is SessionError:
            raise
        raise SessionError("configuration admission failed") from error


def _deadline(origin_ns: int, milliseconds: int) -> int:
    return origin_ns + milliseconds * 1_000_000


def _write_complete(descriptor: int, payload: bytes, deadline_ns: int) -> None:
    if len(payload) > MAX_FRAME_BYTES or time.monotonic_ns() > deadline_ns:
        raise SessionError("write deadline or frame bound failed")
    writable = select.select([], [descriptor], [], max(0, (deadline_ns - time.monotonic_ns()) / 1_000_000_000))[1]
    if descriptor not in writable or os.write(descriptor, payload) != len(payload):
        raise SessionError("complete write failed")


def _read_ack_eof(deadline_ns: int) -> bytes:
    readable = select.select([0], [], [], max(0, (deadline_ns - time.monotonic_ns()) / 1_000_000_000))[0]
    if 0 not in readable:
        raise SessionError("ACK deadline failed")
    ack = os.read(0, 2)
    if ack != receipt_schema.ACK_BYTE or os.read(0, 1) != b"":
        raise SessionError("ACK must be one byte followed by EOF")
    return ack


def _preflight(config: SessionConfig) -> Mapping[str, object]:
    data = config.data
    barrier = attester.establish_protocol_barrier()
    if barrier is None:
        raise SessionError("protocol barrier failed")
    # Evidence is deliberately obtained only from the admitted closed projection.
    expectations = data["namespace_expectations"]
    plan = expectations["measurement_plan"]
    snapshot = measurements.collect_namespace_measurements(plan)
    if snapshot is None:
        raise SessionError("bounded evidence preflight failed")
    return {"barrier": barrier, "snapshot": snapshot}


def _receipt_payload(config: SessionConfig, phase: str, outcome: object, timestamps: object) -> dict[str, object]:
    data = config.data
    attestation = {key: data["namespace_expectations"].get(key) for key in ATTESTATION_KEYS}
    if set(attestation) != set(ATTESTATION_KEYS) or any(value is None for value in attestation.values()):
        raise SessionError("receipt evidence is not admitted")
    payload = {
        "schema": data["base_config"]["schema"], "namespace": data["base_config"]["namespace"],
        "nonce": data["base_config"]["nonce"], "config_sha256": data["base_config"]["config_sha256"],
        "inputs": data["base_config"]["inputs"], "row": data["row"], "phase": phase,
        "attestation": attestation,
    }
    if phase == "pre":
        payload["no_child_started"] = True
        return payload
    payload.update({"terminal": True, "child_pid": outcome.child_pid, "child_returncode": outcome.returncode, "pre_monotonic_ns": timestamps[0], "post_monotonic_ns": timestamps[1]})
    return payload


def _child_spec(config: SessionConfig) -> child_runner.ChildSpec:
    child = config.data["child"]
    environment = child["environment"]
    if type(environment) is not dict or tuple(sorted(environment)) != CHILD_ENVIRONMENT_ORDER or child["timeout_ms"] != CHILD_TIMEOUT_MS:
        raise SessionError("child environment or timeout is invalid")
    ordered = tuple((key, environment[key]) for key in CHILD_ENVIRONMENT_ORDER)
    return child_runner.ChildSpec(tuple(child["argv"]), child["cwd"], ordered, CHILD_TIMEOUT_MS)


def run_session(config: SessionConfig) -> SessionResult:
    diagnostic_ready = _prepare_diagnostic()
    pre_origin = time.monotonic_ns()
    try:
        if type(config) is not SessionConfig or type(config.data) is not types.MappingProxyType:
            raise SessionError("configuration is not validator-created")
        evidence = _preflight(config)
        pre_payload = _receipt_payload(config, "pre", None, None)
        pre = receipt_schema.validate_pre_payload(pre_payload, 0)
        pre_bytes = protocol.encode_frame(pre.payload)
    except (SessionError, ValueError, OSError) as error:
        _diagnose(diagnostic_ready, "preflight")
        if type(error) is SessionError:
            raise
        raise SessionError("preflight failed") from error
    pre_ns = time.monotonic_ns()
    try:
        _write_complete(1, pre_bytes, _deadline(pre_origin, PRE_DEADLINE_MS))
    except (OSError, SessionError) as error:
        _diagnose(diagnostic_ready, "pre_write")
        raise SessionError("PRE write failed") from error
    try:
        ack = _read_ack_eof(_deadline(time.monotonic_ns(), ACK_DEADLINE_MS))
    except (OSError, SessionError) as error:
        _diagnose(diagnostic_ready, "ack")
        raise SessionError("ACK exchange failed") from error
    try:
        outcome = child_runner.run_child(_child_spec(config))
        if outcome.timed_out or outcome.returncode < 0:
            raise SessionError("child outcome cannot produce POST")
    except (OSError, ValueError, SessionError) as error:
        _diagnose(diagnostic_ready, "child")
        if type(error) is SessionError:
            raise
        raise SessionError("child execution failed") from error
    post_origin = time.monotonic_ns()
    try:
        _preflight(config)
        post_ns = time.monotonic_ns()
        post_payload = _receipt_payload(config, "post", outcome, (pre_ns, post_ns))
        post = receipt_schema.validate_post_payload(post_payload, 1)
        receipt_schema.validate_exchange(pre, ack, post)
        post_bytes = protocol.encode_frame(post.payload)
        _write_complete(1, post_bytes, _deadline(post_origin, POST_DEADLINE_MS))
        os.close(1)
        return _make_result(outcome.child_pid, outcome.returncode, pre_ns, post_ns)
    except (OSError, ValueError, SessionError) as error:
        _diagnose(diagnostic_ready, "post")
        if type(error) is SessionError:
            raise
        raise SessionError("POST exchange failed") from error
