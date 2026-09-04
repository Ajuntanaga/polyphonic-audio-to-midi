"""Non-admissible pure compatibility helpers for the future V4 session root."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from tools import reaper_v4_attester as attester
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


def _canonical_session_sha256(value: object) -> str:
    digest = hashlib.sha256(_canonical_session_json_bytes(value))
    return digest.hexdigest()


def _require_mapping(value: object, expected: tuple[str, ...], label: str) -> Mapping[str, object]:
    if type(value) is not types.MappingProxyType or set(value) != set(expected):
        raise SessionError(f"{label} shape is invalid")
    return value


def _require_ascii(value: object, label: str, minimum: int, maximum: int) -> str:
    if type(value) is not str or not minimum <= len(value) <= maximum:
        raise SessionError(f"{label} is invalid")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise SessionError(f"{label} is invalid") from error
    if not all(32 <= byte <= 126 for byte in encoded):
        raise SessionError(f"{label} is invalid")
    return value


def _require_digest(value: object, label: str) -> str:
    digest = _require_ascii(value, label, 64, 64)
    if not all(character in "0123456789abcdef" for character in digest):
        raise SessionError(f"{label} is invalid")
    return digest


def _require_integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SessionError(f"{label} is invalid")
    return value


def _require_absolute_path(value: object, label: str) -> str:
    path = _require_ascii(value, label, 1, MAX_SESSION_STRING_BYTES)
    if path == "/":
        return path
    if not path.startswith("/") or path.endswith("/") or "//" in path:
        raise SessionError(f"{label} is invalid")
    suffix = path[1:]
    components = suffix.split("/")
    if not 1 <= len(components) <= 16:
        raise SessionError(f"{label} is invalid")
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
    if not all(
        1 <= len(component) <= 64
        and component not in {".", ".."}
        and all(character in allowed for character in component)
        for component in components
    ):
        raise SessionError(f"{label} is invalid")
    return path


def _require_relative_path(value: object, label: str, components: int, allow_dot: bool) -> str:
    path = _require_ascii(value, label, 1, MAX_SESSION_STRING_BYTES)
    if allow_dot and path == ".":
        return path
    if path.startswith("/") or path.endswith("/") or "//" in path:
        raise SessionError(f"{label} is invalid")
    members = path.split("/")
    if not 1 <= len(members) <= components:
        raise SessionError(f"{label} is invalid")
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
    if not all(
        1 <= len(member) <= 64
        and member not in {".", ".."}
        and all(character in allowed for character in member)
        for member in members
    ):
        raise SessionError(f"{label} is invalid")
    return path


def _validate_id_map(value: object, label: str) -> list[Mapping[str, object]]:
    if type(value) is not tuple or not 1 <= len(value) <= 8:
        raise SessionError(f"{label} is invalid")
    records: list[Mapping[str, object]] = []
    prior_inside_end = -1
    prior_outside_end = -1
    for record in value:
        entry = _require_mapping(record, ("inside_id", "outside_id", "length"), label)
        inside_id = _require_integer(entry["inside_id"], label, 0, 2147483647)
        outside_id = _require_integer(entry["outside_id"], label, 0, 2147483647)
        length = _require_integer(entry["length"], label, 1, 2147483647)
        inside_end = inside_id + length - 1
        outside_end = outside_id + length - 1
        if (
            inside_end > 2147483647
            or outside_end > 2147483647
            or inside_id <= prior_inside_end
            or outside_id <= prior_outside_end
        ):
            raise SessionError(f"{label} is invalid")
        prior_inside_end = inside_end
        prior_outside_end = outside_end
        records.append(entry)
    return records


def _mapped_outer_id(records: list[Mapping[str, object]], inside: int, label: str) -> int:
    identifier = _require_integer(inside, label, 0, 2147483647)
    for record in records:
        inside_id = _require_integer(record["inside_id"], label, 0, 2147483647)
        outside_id = _require_integer(record["outside_id"], label, 0, 2147483647)
        length = _require_integer(record["length"], label, 1, 2147483647)
        if inside_id <= identifier < inside_id + length:
            return outside_id + identifier - inside_id
    raise SessionError(f"{label} does not cover the effective identifier")


def _validate_certificate(value: object, kind: str, config: Mapping[str, object]) -> None:
    certificate = _require_mapping(value, (
        "schema", "kind", "certificate_sha256", "fixture_evidence_sha256",
        "session_source_sha256", "runtime_manifest_sha256", "fixture_manifest_sha256",
        "bwrap_path", "bwrap_version", "bwrap_argv_sha256", "namespace_policy_sha256",
        "mount_policy_sha256", "fd_policy_sha256", "kernel_release", "boot_id", "uid",
        "user_namespace_policy_sha256", "result",
    ), "fixture certificate")
    if _require_integer(certificate["schema"], "fixture certificate schema", 1, 1) != 1:
        raise SessionError("fixture certificate schema is invalid")
    if _require_ascii(certificate["kind"], "fixture certificate kind", 1, 128) != kind:
        raise SessionError("fixture certificate kind is invalid")
    certificate_digest = _require_digest(certificate["certificate_sha256"], "fixture certificate digest")
    for key in (
        "fixture_evidence_sha256", "session_source_sha256", "runtime_manifest_sha256",
        "fixture_manifest_sha256", "bwrap_argv_sha256", "namespace_policy_sha256",
        "mount_policy_sha256", "fd_policy_sha256", "user_namespace_policy_sha256",
    ):
        _require_digest(certificate[key], f"fixture certificate {key}")
    _require_absolute_path(certificate["bwrap_path"], "fixture certificate Bubblewrap path")
    _require_ascii(certificate["bwrap_version"], "fixture certificate Bubblewrap version", 1, 128)
    _require_ascii(certificate["kernel_release"], "fixture certificate kernel release", 1, 128)
    boot_id = _require_ascii(certificate["boot_id"], "fixture certificate boot identifier", 36, 36)
    if (
        any(boot_id[position] != "-" for position in (8, 13, 18, 23))
        or not all(
            character in "0123456789abcdef"
            for position, character in enumerate(boot_id)
            if position not in {8, 13, 18, 23}
        )
    ):
        raise SessionError("fixture certificate boot identifier is invalid")
    _require_integer(certificate["uid"], "fixture certificate uid", 0, 2147483647)
    expected_result = (
        {"proc_receipt_blocked": True, "proc_mem_blocked": True}
        if kind == "proc_ptrace_barrier"
        else {"control_root_absent": True, "mount_mutation_blocked": True}
    )
    if kind not in {"proc_ptrace_barrier", "control_visibility"}:
        raise SessionError("fixture certificate kind is invalid")
    result = _require_mapping(certificate["result"], tuple(expected_result), "fixture certificate result")
    if dict(result) != expected_result:
        raise SessionError("fixture certificate result is invalid")
    canonical = dict(certificate)
    canonical.pop("certificate_sha256")
    if _canonical_session_sha256(canonical) != certificate_digest:
        raise SessionError("fixture certificate digest is invalid")
    bwrap = _require_mapping(config["bwrap"], ("path", "version", "argv_sha256"), "Bubblewrap record")
    expectations = _require_mapping(config["namespace_expectations"], (
        "home", "pwd", "cwd", "environment", "user_namespace", "x11_identity",
        "measurement_root", "measurement_plan", "private_tree", "scan_root",
        "descriptor_policy", "control_visibility",
    ), "namespace expectations")
    descriptor = _require_mapping(expectations["descriptor_policy"], ("fd_policy_sha256", "inherited_fds"), "descriptor policy")
    control = _require_mapping(expectations["control_visibility"], ("mount_policy_sha256", "namespace_root_kind", "mounts"), "control visibility")
    user_namespace = _require_mapping(expectations["user_namespace"], (
        "policy_sha256", "effective_uid", "effective_gid", "uid_map", "gid_map", "setgroups",
    ), "user namespace")
    if (
        certificate["runtime_manifest_sha256"] != config["runtime_manifest_sha256"]
        or certificate["fixture_manifest_sha256"] != config["fixture_manifest_sha256"]
        or certificate["bwrap_path"] != bwrap["path"]
        or certificate["bwrap_version"] != bwrap["version"]
        or certificate["bwrap_argv_sha256"] != bwrap["argv_sha256"]
        or certificate["namespace_policy_sha256"] != config["namespace_policy_sha256"]
        or certificate["mount_policy_sha256"] != control["mount_policy_sha256"]
        or certificate["fd_policy_sha256"] != descriptor["fd_policy_sha256"]
        or certificate["user_namespace_policy_sha256"] != user_namespace["policy_sha256"]
    ):
        raise SessionError("fixture certificate binding is invalid")
    expected_uid = _mapped_outer_id(
        _validate_id_map(user_namespace["uid_map"], "uid map"),
        _require_integer(user_namespace["effective_uid"], "effective uid", 0, 2147483647),
        "uid map",
    )
    if certificate["uid"] != expected_uid:
        raise SessionError("fixture certificate uid is invalid")


def _child_spec_projection(value: Mapping[str, object]) -> dict[str, object]:
    config = _require_mapping(value, SESSION_CONFIG_KEYS, "session configuration")
    expectations = _require_mapping(config["namespace_expectations"], (
        "home", "pwd", "cwd", "environment", "user_namespace", "x11_identity",
        "measurement_root", "measurement_plan", "private_tree", "scan_root",
        "descriptor_policy", "control_visibility",
    ), "namespace expectations")
    child = _require_mapping(config["child"], ("argv", "cwd", "environment", "timeout_ms"), "child")
    environment = _require_mapping(expectations["environment"], (
        "DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY",
    ), "session environment")
    child_environment = _require_mapping(child["environment"], (
        "DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY",
    ), "child environment")
    environment_keys = ("DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY")
    if tuple(environment) != environment_keys or tuple(child_environment) != environment_keys:
        raise SessionError("environment order is invalid")
    for key in environment_keys:
        _require_ascii(environment[key], f"session environment {key}", 1, MAX_SESSION_STRING_BYTES)
        _require_ascii(child_environment[key], f"child environment {key}", 1, MAX_SESSION_STRING_BYTES)
    if dict(environment) != dict(child_environment):
        raise SessionError("child environment is invalid")
    home = _require_absolute_path(expectations["home"], "home")
    pwd = _require_absolute_path(expectations["pwd"], "pwd")
    cwd = _require_absolute_path(expectations["cwd"], "cwd")
    child_cwd = _require_absolute_path(child["cwd"], "child cwd")
    if not (home == pwd == cwd == environment["HOME"] == environment["PWD"] == child_cwd):
        raise SessionError("child home and working directory are invalid")
    if type(child["argv"]) is not tuple or not 1 <= len(child["argv"]) <= 16:
        raise SessionError("child argv is invalid")
    argv: list[str] = []
    for index, argument in enumerate(child["argv"]):
        text = _require_ascii(argument, "child argv", 1, MAX_SESSION_STRING_BYTES)
        argv.append(text)
        if index == 0:
            _require_absolute_path(text, "child argv[0]")
    timeout_ms = _require_integer(child["timeout_ms"], "child timeout", 30000, 30000)
    environment_pairs: list[tuple[str, str]] = []
    for key in sorted(environment):
        environment_pairs.append((key, child_environment[key]))
    return {"argv": tuple(argv), "cwd": child_cwd, "environment": tuple(environment_pairs), "timeout_ms": timeout_ms}


def _validate_session_config_relations(value: Mapping[str, object]) -> None:
    config = _require_mapping(value, SESSION_CONFIG_KEYS, "session configuration")
    if _require_integer(config["schema"], "session schema", 1, 1) != 1:
        raise SessionError("session schema is invalid")
    namespace = _require_ascii(config["namespace"], "session namespace", 1, 128)
    session_digest = _require_digest(config["session_config_sha256"], "session configuration digest")
    session_policy_digest = _require_digest(config["session_policy_sha256"], "session policy digest")
    for key in ("runtime_manifest_sha256", "run_input_manifest_sha256", "fixture_manifest_sha256", "namespace_policy_sha256"):
        _require_digest(config[key], key)
    direct_inputs = config["direct_input_digests"]
    if type(direct_inputs) is not types.MappingProxyType or not 1 <= len(direct_inputs) <= 15:
        raise SessionError("direct input digests are invalid")
    direct_names = set()
    for name, digest in direct_inputs.items():
        input_name = _require_ascii(name, "direct input name", 1, 128)
        if (
            input_name == "session_policy"
            or input_name[0] not in "abcdefghijklmnopqrstuvwxyz"
            or not all(character in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in input_name[1:])
        ):
            raise SessionError("direct input name is invalid")
        direct_names.add(input_name)
        _require_digest(digest, "direct input digest")
    base_config = _require_mapping(config["base_config"], ("schema", "namespace", "nonce", "config_sha256", "inputs"), "base configuration")
    if _require_integer(base_config["schema"], "base configuration schema", 1, 1) != config["schema"]:
        raise SessionError("base configuration schema is invalid")
    if _require_ascii(base_config["namespace"], "base configuration namespace", 1, 128) != namespace:
        raise SessionError("base configuration namespace is invalid")
    nonce = _require_ascii(base_config["nonce"], "base configuration nonce", 32, 32)
    if not all(character in "0123456789abcdef" for character in nonce):
        raise SessionError("base configuration nonce is invalid")
    base_digest = _require_digest(base_config["config_sha256"], "base configuration digest")
    if base_digest == session_digest:
        raise SessionError("session and base configuration digests are invalid")
    base_inputs = base_config["inputs"]
    if type(base_inputs) is not types.MappingProxyType:
        raise SessionError("base configuration inputs are invalid")
    expected_base_inputs = dict(direct_inputs)
    expected_base_inputs["session_policy"] = session_policy_digest
    if dict(base_inputs) != expected_base_inputs:
        raise SessionError("base configuration inputs are invalid")
    base_projection = {
        "schema": config["schema"],
        "namespace": namespace,
        "nonce": nonce,
        "config_sha256": base_digest,
        "inputs": dict(base_inputs),
    }
    attester.validate_config(attester.AttesterConfig(base_projection))
    row = _require_mapping(config["row"], ("sample_rate_hz", "block_size"), "row")
    if (
        _require_integer(row["sample_rate_hz"], "sample rate", 44100, 44100) != 44100
        or _require_integer(row["block_size"], "block size", 32, 32) != 32
    ):
        raise SessionError("row is invalid")
    bwrap = _require_mapping(config["bwrap"], ("path", "version", "argv_sha256"), "Bubblewrap record")
    _require_absolute_path(bwrap["path"], "Bubblewrap path")
    _require_ascii(bwrap["version"], "Bubblewrap version", 1, 128)
    _require_digest(bwrap["argv_sha256"], "Bubblewrap argv digest")
    expectations = _require_mapping(config["namespace_expectations"], (
        "home", "pwd", "cwd", "environment", "user_namespace", "x11_identity",
        "measurement_root", "measurement_plan", "private_tree", "scan_root",
        "descriptor_policy", "control_visibility",
    ), "namespace expectations")
    user_namespace = _require_mapping(expectations["user_namespace"], (
        "policy_sha256", "effective_uid", "effective_gid", "uid_map", "gid_map", "setgroups",
    ), "user namespace")
    uid_map = _validate_id_map(user_namespace["uid_map"], "uid map")
    gid_map = _validate_id_map(user_namespace["gid_map"], "gid map")
    effective_uid = _require_integer(user_namespace["effective_uid"], "effective uid", 0, 2147483647)
    effective_gid = _require_integer(user_namespace["effective_gid"], "effective gid", 0, 2147483647)
    _mapped_outer_id(uid_map, effective_uid, "uid map")
    _mapped_outer_id(gid_map, effective_gid, "gid map")
    if _require_ascii(user_namespace["setgroups"], "setgroups", 4, 4) != "deny":
        raise SessionError("setgroups is invalid")
    user_policy = {
        "effective_uid": effective_uid,
        "effective_gid": effective_gid,
        "uid_map": user_namespace["uid_map"],
        "gid_map": user_namespace["gid_map"],
        "setgroups": user_namespace["setgroups"],
    }
    if _canonical_session_sha256(user_policy) != _require_digest(user_namespace["policy_sha256"], "user namespace policy digest"):
        raise SessionError("user namespace policy digest is invalid")
    measurement_root = _require_mapping(expectations["measurement_root"], ("path", "device", "inode"), "measurement root")
    _require_absolute_path(measurement_root["path"], "measurement root path")
    _require_integer(measurement_root["device"], "measurement root device", 1, MAX_SESSION_INTEGER)
    _require_integer(measurement_root["inode"], "measurement root inode", 1, MAX_SESSION_INTEGER)
    measurement_plan = _require_mapping(expectations["measurement_plan"], ("resources", "expected"), "measurement plan")
    resources = measurement_plan["resources"]
    if type(resources) is not tuple or not 1 <= len(resources) <= 16:
        raise SessionError("measurement resources are invalid")
    resource_names = set()
    for resource in resources:
        resource_name = _require_relative_path(resource, "measurement resource", 1, False)
        if resource_name in resource_names:
            raise SessionError("measurement resources are invalid")
        resource_names.add(resource_name)
    expected_resources = measurement_plan["expected"]
    if type(expected_resources) is not types.MappingProxyType or set(expected_resources) != resource_names:
        raise SessionError("measurement expected values are invalid")
    for resource in resources:
        facts = _require_mapping(expected_resources[resource], ("mode", "size"), "measurement expected facts")
        _require_integer(facts["mode"], "measurement mode", 0, 0o7777)
        _require_integer(facts["size"], "measurement size", 0, 16777216)
    private_tree = _require_mapping(expectations["private_tree"], ("home_mount", "empty_directories"), "private tree")
    home_mount = _require_mapping(private_tree["home_mount"], ("path", "filesystem_type", "mode", "writable"), "private home mount")
    home = _require_absolute_path(expectations["home"], "home")
    if (
        _require_absolute_path(home_mount["path"], "private home path") != home
        or _require_ascii(home_mount["filesystem_type"], "private home filesystem", 1, 128) != "tmpfs"
        or _require_integer(home_mount["mode"], "private home mode", 0o700, 0o700) != 0o700
        or type(home_mount["writable"]) is not bool
        or home_mount["writable"] is not True
    ):
        raise SessionError("private home mount is invalid")
    if private_tree["empty_directories"] != (".vst", ".vst3"):
        raise SessionError("private tree is invalid")
    x11_identity = _require_mapping(expectations["x11_identity"], (
        "display", "display_number", "screen", "protocol", "authority", "socket",
    ), "X11 identity")
    display = _require_ascii(x11_identity["display"], "X11 display", 2, 128)
    display_number = _require_integer(x11_identity["display_number"], "X11 display number", 0, 2147483647)
    screen = _require_integer(x11_identity["screen"], "X11 screen", 0, 2147483647)
    if not (
        (display == f":{display_number}" and screen == 0)
        or display == f":{display_number}.{screen}"
    ):
        raise SessionError("X11 display is invalid")
    if _require_ascii(x11_identity["protocol"], "X11 protocol", 18, 18) != "MIT-MAGIC-COOKIE-1":
        raise SessionError("X11 protocol is invalid")
    authority = _require_mapping(x11_identity["authority"], (
        "path", "source_device", "source_inode", "destination_mode", "destination_size", "sha256",
    ), "X11 authority")
    authority_path = _require_absolute_path(authority["path"], "X11 authority path")
    _require_integer(authority["source_device"], "X11 authority source device", 1, MAX_SESSION_INTEGER)
    _require_integer(authority["source_inode"], "X11 authority source inode", 1, MAX_SESSION_INTEGER)
    _require_integer(authority["destination_mode"], "X11 authority destination mode", 0, 0o7777)
    _require_integer(authority["destination_size"], "X11 authority destination size", 0, 65536)
    _require_digest(authority["sha256"], "X11 authority digest")
    session_environment = _require_mapping(expectations["environment"], (
        "DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY",
    ), "session environment")
    if display != session_environment["DISPLAY"] or authority_path != session_environment["XAUTHORITY"]:
        raise SessionError("X11 environment binding is invalid")
    x_socket = _require_mapping(x11_identity["socket"], ("path", "kind", "uid", "gid", "mode", "device", "inode"), "X11 socket")
    if _require_absolute_path(x_socket["path"], "X11 socket path") != f"/tmp/.X11-unix/X{display_number}":
        raise SessionError("X11 socket path is invalid")
    if _require_ascii(x_socket["kind"], "X11 socket kind", 11, 11) != "unix_socket":
        raise SessionError("X11 socket kind is invalid")
    _require_integer(x_socket["uid"], "X11 socket uid", 0, 2147483647)
    _require_integer(x_socket["gid"], "X11 socket gid", 0, 2147483647)
    _require_integer(x_socket["mode"], "X11 socket mode", 0, 0o7777)
    _require_integer(x_socket["device"], "X11 socket device", 1, MAX_SESSION_INTEGER)
    _require_integer(x_socket["inode"], "X11 socket inode", 1, MAX_SESSION_INTEGER)
    scan_root = _require_mapping(expectations["scan_root"], ("path", "entries", "mount_points"), "scan root")
    scan_path = _require_absolute_path(scan_root["path"], "scan root path")
    entries = scan_root["entries"]
    if type(entries) is not tuple or len(entries) != 2:
        raise SessionError("scan root entries are invalid")
    entry_paths: list[str] = []
    entry_names = set()
    total_size = 0
    for entry in entries:
        record = _require_mapping(entry, ("relative_path", "input_name", "mode", "size", "sha256"), "scan root entry")
        relative_path = _require_relative_path(record["relative_path"], "scan root relative path", 8, False)
        input_name = _require_ascii(record["input_name"], "scan root input name", 1, 128)
        if input_name not in direct_names or input_name in entry_names:
            raise SessionError("scan root input name is invalid")
        digest = _require_digest(record["sha256"], "scan root digest")
        if digest != direct_inputs[input_name]:
            raise SessionError("scan root digest is invalid")
        _require_integer(record["mode"], "scan root mode", 0, 0o7777)
        size = _require_integer(record["size"], "scan root size", 0, 16777216)
        total_size += size
        entry_paths.append(relative_path)
        entry_names.add(input_name)
    first_entry_path = entry_paths[0]
    second_entry_path = entry_paths[1]
    if (
        entry_paths != sorted(entry_paths)
        or first_entry_path == second_entry_path
        or second_entry_path.startswith(first_entry_path + "/")
    ):
        raise SessionError("scan root entries are invalid")
    if total_size > 33554432:
        raise SessionError("scan root size is invalid")
    mount_points = scan_root["mount_points"]
    if type(mount_points) is not tuple or len(mount_points) != 3:
        raise SessionError("scan root mount points are invalid")
    expected_mount_points = (".", entry_paths[0], entry_paths[1])
    for index, mount_point in enumerate(mount_points):
        record = _require_mapping(mount_point, ("relative_path", "readonly"), "scan root mount point")
        relative_path = _require_relative_path(record["relative_path"], "scan root mount relative path", 8, True)
        if relative_path != expected_mount_points[index] or type(record["readonly"]) is not bool or record["readonly"] is not True:
            raise SessionError("scan root mount point is invalid")
    descriptor_policy = _require_mapping(expectations["descriptor_policy"], ("fd_policy_sha256", "inherited_fds"), "descriptor policy")
    descriptors = descriptor_policy["inherited_fds"]
    if type(descriptors) is not tuple or len(descriptors) != 3:
        raise SessionError("descriptor policy is invalid")
    expected_descriptors = ((0, "ack_input"), (1, "receipt_output"), (2, "diagnostic_output"))
    for index, descriptor in enumerate(descriptors):
        record = _require_mapping(descriptor, ("fd", "kind", "role"), "inherited descriptor")
        if (
            _require_integer(record["fd"], "inherited descriptor fd", expected_descriptors[index][0], expected_descriptors[index][0]) != expected_descriptors[index][0]
            or _require_ascii(record["kind"], "inherited descriptor kind", 4, 4) != "pipe"
            or _require_ascii(record["role"], "inherited descriptor role", 1, 128) != expected_descriptors[index][1]
        ):
            raise SessionError("inherited descriptor is invalid")
    if _canonical_session_sha256({"inherited_fds": descriptors}) != _require_digest(descriptor_policy["fd_policy_sha256"], "descriptor policy digest"):
        raise SessionError("descriptor policy digest is invalid")
    control_visibility = _require_mapping(expectations["control_visibility"], ("mount_policy_sha256", "namespace_root_kind", "mounts"), "control visibility")
    if _require_ascii(control_visibility["namespace_root_kind"], "namespace root kind", 18, 18) != "private_tmpfs_root":
        raise SessionError("namespace root kind is invalid")
    mounts = control_visibility["mounts"]
    if type(mounts) is not tuple or not 1 <= len(mounts) <= 64:
        raise SessionError("mount projection is invalid")
    mount_readonly: dict[str, bool] = {}
    mount_paths: list[str] = []
    for mount in mounts:
        record = _require_mapping(mount, ("path", "filesystem_type", "readonly"), "mount projection")
        path = _require_absolute_path(record["path"], "mount path")
        _require_ascii(record["filesystem_type"], "mount filesystem type", 1, 128)
        if type(record["readonly"]) is not bool or path in mount_readonly:
            raise SessionError("mount projection is invalid")
        mount_readonly[path] = record["readonly"]
        mount_paths.append(path)
    if mount_paths != sorted(mount_paths):
        raise SessionError("mount projection is invalid")
    required_scan_mounts = set()
    for mount_point in mount_points:
        relative_path = mount_point["relative_path"]
        absolute_path = scan_path if relative_path == "." else f"{scan_path}/{relative_path}"
        required_scan_mounts.add(absolute_path)
        if absolute_path not in mount_readonly or mount_readonly[absolute_path] != mount_point["readonly"]:
            raise SessionError("scan root mount binding is invalid")
    for path in mount_paths:
        if path.startswith(scan_path + "/") and path not in required_scan_mounts:
            raise SessionError("mount projection is invalid")
    if _canonical_session_sha256({"namespace_root_kind": control_visibility["namespace_root_kind"], "mounts": mounts}) != _require_digest(control_visibility["mount_policy_sha256"], "mount policy digest"):
        raise SessionError("mount policy digest is invalid")
    if _canonical_session_sha256(expectations) != _require_digest(config["namespace_policy_sha256"], "namespace policy digest"):
        raise SessionError("namespace policy digest is invalid")
    limits = _require_mapping(config["limits"], (
        "pre_deadline_ms", "ack_deadline_ms", "post_deadline_ms", "diagnostic_max_bytes", "max_frame_bytes", "child_timeout_ms",
    ), "limits")
    expected_limits = {
        "pre_deadline_ms": 5000, "ack_deadline_ms": 5000, "post_deadline_ms": 5000,
        "diagnostic_max_bytes": 1024, "max_frame_bytes": 2064, "child_timeout_ms": 30000,
    }
    for key, expected in expected_limits.items():
        if _require_integer(limits[key], key, expected, expected) != expected:
            raise SessionError("limits are invalid")
    if limits["max_frame_bytes"] != protocol.MAX_FRAME_BYTES:
        raise SessionError("frame limit is invalid")
    _child_spec_projection(config)
    certificates = _require_mapping(config["fixture_certificates"], ("proc_ptrace_barrier", "control_visibility"), "fixture certificates")
    _validate_certificate(certificates["proc_ptrace_barrier"], "proc_ptrace_barrier", config)
    _validate_certificate(certificates["control_visibility"], "control_visibility", config)
    policy = {
        "row": config["row"],
        "direct_input_digests": config["direct_input_digests"],
        "runtime_manifest_sha256": config["runtime_manifest_sha256"],
        "run_input_manifest_sha256": config["run_input_manifest_sha256"],
        "fixture_manifest_sha256": config["fixture_manifest_sha256"],
        "namespace_policy_sha256": config["namespace_policy_sha256"],
        "fixture_certificates": config["fixture_certificates"],
        "bwrap": config["bwrap"],
        "namespace_expectations": config["namespace_expectations"],
        "child": config["child"],
        "limits": config["limits"],
    }
    if _canonical_session_sha256(policy) != session_policy_digest:
        raise SessionError("session policy digest is invalid")
    if _session_config_digest(config) != session_digest:
        raise SessionError("session configuration digest is invalid")


def _admit_session_config(config: SessionConfig) -> SessionConfig:
    if type(config) is not SessionConfig:
        raise SessionError("session configuration is invalid")
    try:
        untrusted_data = config.data
        if type(untrusted_data) is not types.MappingProxyType:
            raise SessionError("session configuration is invalid")
        materialized = _materialize_exact_builtins(untrusted_data)
        frozen = _freeze_session_data(materialized)
        _validate_session_config_relations(frozen)
        admitted = object.__new__(SessionConfig)
        object.__setattr__(admitted, "data", frozen)
        return admitted
    except SessionError:
        raise
    except Exception as error:
        raise SessionError("session configuration is invalid") from error


def load_session_config(config_path: str, digest_path: str) -> SessionConfig:
    raise SessionError("session execution is not admitted")


def run_session(config: SessionConfig) -> SessionResult:
    raise SessionError("session execution is not admitted")
