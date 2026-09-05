"""Pre-import source contract for Task 0B4b-bootstrap-transport."""
from __future__ import annotations

import ast
import hashlib
import pathlib
import sys
import unittest


SESSION_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "reaper_v4_session.py"
EXPECTED_SOURCE_SHA256 = "6a2bbdfee29c26253ffb4a8f05c62feeab207ea21942aa40368a9ac9e8fcdc1c"
EXPECTED_IMPORTS = {
    "from __future__ import annotations",
    "import dataclasses",
    "import errno",
    "import fcntl",
    "import hashlib",
    "import json",
    "import os",
    "import resource as runtime_resource",
    "import select",
    "import stat",
    "import time",
    "import types",
    "from collections.abc import Mapping",
    "from tools import reaper_v4_attester as attester",
    "from tools import reaper_v4_child_runner as child_runner",
    "from tools import reaper_v4_measurements as measurements",
    "from tools import reaper_v4_protocol as protocol",
    "from tools import reaper_v4_receipt_schema as receipt_schema",
}
EXPECTED_ASSIGNMENTS = {
    "__all__": ("SessionError", "SessionConfig", "SessionResult", "load_session_config", "run_session"),
    "SESSION_ENTRYPOINT_KIND": "session_entrypoint",
    "SESSION_ENTRYPOINT_ROLE": "same_namespace_pre_ack_child_post_owner",
    "SESSION_CONFIG_PATH": "/run/m3-v4/session-config.json",
    "SESSION_DIGEST_PATH": "/run/m3-v4/session-config.sha256",
    "SESSION_CONFIG_KEYS": (
        "schema", "namespace", "session_config_sha256", "base_config",
        "session_policy_sha256", "direct_input_digests", "row",
        "runtime_manifest_sha256", "run_input_manifest_sha256",
        "fixture_manifest_sha256", "namespace_policy_sha256",
        "fixture_certificates", "bwrap", "namespace_expectations", "child", "limits",
    ),
    "MAX_SESSION_CONFIG_BYTES": 8192,
    "MAX_SESSION_NODES": 256,
    "MAX_SESSION_DEPTH": 16,
    "MAX_SESSION_STRING_BYTES": 512,
    "MIN_SESSION_INTEGER": -9223372036854775808,
    "MAX_SESSION_INTEGER": 9223372036854775807,
    "MAX_RUNTIME_DESCRIPTOR_LIMIT": 64,
    "MAX_RUNTIME_MOUNTINFO_BYTES": 65536,
    "RUNTIME_MOUNTINFO_PATH": "/proc/self/mountinfo",
    "_EVIDENCE_OWNERS": {},
}
PUBLIC_FUNCTIONS = {"load_session_config", "run_session"}
PURE_HELPERS = {
    "_freeze_session_data", "_canonical_session_json_bytes", "_session_config_digest",
    "_parse_session_config_bytes", "_materialize_exact_builtins", "_base_config_projection",
    "_validate_and_encode_receipt", "_canonical_session_sha256", "_require_mapping",
    "_require_ascii", "_require_digest", "_require_integer", "_require_absolute_path",
    "_require_relative_path", "_validate_id_map", "_mapped_outer_id", "_validate_certificate",
    "_child_spec_projection", "_validate_session_config_relations", "_admit_session_config",
}
EVIDENCE_HELPERS = {
    "_hash_regular_descriptor", "_capture_environment_baseline", "_capture_measurement_baseline", "_capture_scan_baseline",
    "_capture_private_tree_baseline", "_capture_x11_baseline", "_validate_inherited_fd_census",
    "_validate_mount_projection", "_certificate_applicability_projection",
    "_require_owned_evidence_baseline", "_capture_evidence_baseline", "_recheck_evidence_baseline", "_release_evidence_baseline",
}
BOOTSTRAP_HELPERS = {
    "_setup_diagnostic_fd", "_emit_diagnostic_once", "_read_fixed_regular",
    "_load_fixed_session_config", "_wait_fixed_pipe", "_write_frame_once",
    "_read_ack_eof",
}
STATE_HELPERS = {
    "_capture_runtime_evidence", "_recheck_runtime_evidence", "_release_runtime_evidence",
    "_open_runtime_evidence_descriptors", "_observe_runtime_descriptor_census",
    "_read_runtime_mountinfo", "_observe_runtime_mount_projection",
    "_shared_receipt_attestation", "_assemble_pre_payload", "_assemble_post_payload", "_child_spec_from_config",
    "_validate_child_outcome", "_finalize_post_payload",
}
EXPECTED_FUNCTIONS = PURE_HELPERS | EVIDENCE_HELPERS | BOOTSTRAP_HELPERS | STATE_HELPERS | PUBLIC_FUNCTIONS
EXPECTED_SIGNATURES = {
    "_freeze_session_data": (("value",), ("object",), "object"),
    "_canonical_session_json_bytes": (("value",), ("object",), "bytes"),
    "_session_config_digest": (("value",), ("object",), "str"),
    "_parse_session_config_bytes": (("config_bytes", "sidecar_bytes"), ("bytes", "bytes"), "Mapping[str, object]"),
    "_materialize_exact_builtins": (("value",), ("object",), "object"),
    "_base_config_projection": (("config",), ("SessionConfig",), "dict[str, object]"),
    "_validate_and_encode_receipt": (("payload", "phase", "sequence"), ("dict[str, object]", "receipt_schema.ReceiptPhase", "int"), "tuple[receipt_schema.ReceiptPayload, bytes]"),
    "_canonical_session_sha256": (("value",), ("object",), "str"),
    "_require_mapping": (("value", "expected", "label"), ("object", "tuple[str, ...]", "str"), "Mapping[str, object]"),
    "_require_ascii": (("value", "label", "minimum", "maximum"), ("object", "str", "int", "int"), "str"),
    "_require_digest": (("value", "label"), ("object", "str"), "str"),
    "_require_integer": (("value", "label", "minimum", "maximum"), ("object", "str", "int", "int"), "int"),
    "_require_absolute_path": (("value", "label"), ("object", "str"), "str"),
    "_require_relative_path": (("value", "label", "components", "allow_dot"), ("object", "str", "int", "bool"), "str"),
    "_validate_id_map": (("value", "label"), ("object", "str"), "list[Mapping[str, object]]"),
    "_mapped_outer_id": (("records", "inside", "label"), ("list[Mapping[str, object]]", "int", "str"), "int"),
    "_validate_certificate": (("value", "kind", "config"), ("object", "str", "Mapping[str, object]"), "None"),
    "_child_spec_projection": (("value",), ("Mapping[str, object]",), "dict[str, object]"),
    "_validate_session_config_relations": (("value",), ("Mapping[str, object]",), "None"),
    "_admit_session_config": (("config",), ("SessionConfig",), "SessionConfig"),
    "_hash_regular_descriptor": (("descriptor", "size"), ("int", "int"), "str"),
    "_capture_environment_baseline": (("config", "cwd", "environment"), ("SessionConfig", "str", "Mapping[str, object]"), "Mapping[str, object]"),
    "_capture_measurement_baseline": (("config", "root_fd"), ("SessionConfig", "int"), "Mapping[str, object]"),
    "_capture_scan_baseline": (("config", "root_fd"), ("SessionConfig", "int"), "Mapping[str, object]"),
    "_capture_private_tree_baseline": (("config", "home_fd"), ("SessionConfig", "int"), "Mapping[str, object]"),
    "_capture_x11_baseline": (("config", "authority_fd", "socket_fd"), ("SessionConfig", "int", "int"), "Mapping[str, object]"),
    "_validate_inherited_fd_census": (("config", "observed"), ("SessionConfig", "tuple[Mapping[str, object], ...]"), "tuple[Mapping[str, object], ...]"),
    "_validate_mount_projection": (("config", "observed"), ("SessionConfig", "tuple[Mapping[str, object], ...]"), "tuple[Mapping[str, object], ...]"),
    "_certificate_applicability_projection": (("config",), ("SessionConfig",), "dict[str, object]"),
    "_require_owned_evidence_baseline": (("baseline",), ("_EvidenceBaseline",), "tuple[int, int, int, int, int]"),
    "_capture_evidence_baseline": (("config", "measurement_root_fd", "scan_root_fd", "home_fd", "authority_fd", "socket_fd", "cwd", "environment", "inherited_fds", "mounts"), ("SessionConfig", "int", "int", "int", "int", "int", "str", "Mapping[str, object]", "tuple[Mapping[str, object], ...]", "tuple[Mapping[str, object], ...]"), "_EvidenceBaseline"),
    "_recheck_evidence_baseline": (("baseline", "cwd", "environment", "inherited_fds", "mounts"), ("_EvidenceBaseline", "str", "Mapping[str, object]", "tuple[Mapping[str, object], ...]", "tuple[Mapping[str, object], ...]"), "None"),
    "_release_evidence_baseline": (("baseline",), ("_EvidenceBaseline",), "None"),
    "_setup_diagnostic_fd": ((), (), "None"),
    "_emit_diagnostic_once": (("code",), ("str",), "None"),
    "_read_fixed_regular": (("path", "maximum"), ("str", "int"), "bytes"),
    "_load_fixed_session_config": ((), (), "SessionConfig"),
    "_wait_fixed_pipe": (("fd", "event", "deadline_ns"), ("int", "int", "int"), "None"),
    "_write_frame_once": (("frame", "deadline_ns"), ("bytes", "int"), "None"),
    "_read_ack_eof": (("deadline_ns",), ("int",), "bytes"),
    "_capture_runtime_evidence": (("config",), ("SessionConfig",), "_EvidenceBaseline"),
    "_recheck_runtime_evidence": (("baseline",), ("_EvidenceBaseline",), "None"),
    "_release_runtime_evidence": (("baseline",), ("_EvidenceBaseline",), "None"),
    "_open_runtime_evidence_descriptors": (("config",), ("SessionConfig",), "tuple[int, int, int, int, int]"),
    "_observe_runtime_descriptor_census": (("config", "retained"), ("SessionConfig", "tuple[int, ...]"), "tuple[Mapping[str, object], ...]"),
    "_read_runtime_mountinfo": ((), (), "bytes"),
    "_observe_runtime_mount_projection": (("config",), ("SessionConfig",), "tuple[Mapping[str, object], ...]"),
    "_shared_receipt_attestation": (("config", "baseline"), ("SessionConfig", "_EvidenceBaseline"), "dict[str, object]"),
    "_assemble_pre_payload": (("config", "baseline"), ("SessionConfig", "_EvidenceBaseline"), "dict[str, object]"),
    "_assemble_post_payload": (("config", "baseline", "outcome", "pre_monotonic_ns", "post_monotonic_ns"), ("SessionConfig", "_EvidenceBaseline", "child_runner.ChildOutcome", "int", "int"), "dict[str, object]"),
    "_child_spec_from_config": (("config",), ("SessionConfig",), "child_runner.ChildSpec"),
    "_validate_child_outcome": (("outcome",), ("child_runner.ChildOutcome",), "child_runner.ChildOutcome"),
    "_finalize_post_payload": (("pre_payload", "ack", "post_payload"), ("dict[str, object]", "bytes", "dict[str, object]"), "bytes"),
    "load_session_config": (("config_path", "digest_path"), ("str", "str"), "SessionConfig"),
    "run_session": (("config",), ("SessionConfig",), "SessionResult"),
}
FORBIDDEN_ROOTS = {
    "pathlib", "socket", "subprocess", "io", "sys",
    "importlib", "ctypes", "tempfile", "pickle", "marshal", "inspect", "platform", "threading", "signal",
}
FORBIDDEN_CALLS = {
    "__import__", "breakpoint", "compile", "eval", "exec", "getattr", "globals", "help", "input",
    "locals", "open", "setattr", "delattr", "vars", "os.pipe", "os.dup",
}
OS_CALL_OWNERS = {
    "os.fstat": {"_capture_measurement_baseline", "_capture_scan_baseline", "_capture_private_tree_baseline", "_capture_x11_baseline", "_observe_runtime_descriptor_census", "_read_runtime_mountinfo", "_setup_diagnostic_fd", "_wait_fixed_pipe", "_write_frame_once", "_read_ack_eof", "_read_fixed_regular"},
    "os.fstatvfs": {"_read_fixed_regular"},
    "os.open": {"_capture_scan_baseline", "_capture_private_tree_baseline", "_open_runtime_evidence_descriptors", "_read_runtime_mountinfo", "_read_fixed_regular"},
    "os.close": {"_capture_scan_baseline", "_capture_private_tree_baseline", "_capture_evidence_baseline", "_release_evidence_baseline", "_open_runtime_evidence_descriptors", "_read_runtime_mountinfo", "_capture_runtime_evidence", "_read_fixed_regular", "run_session"},
    "os.read": {"_hash_regular_descriptor", "_read_runtime_mountinfo", "_read_fixed_regular", "_read_ack_eof"},
    "os.lseek": {"_hash_regular_descriptor"},
    "os.listdir": {"_capture_scan_baseline", "_capture_private_tree_baseline"},
    "os.write": {"_emit_diagnostic_once", "_write_frame_once"},
    "os.fpathconf": {"_write_frame_once"},
    "os.getcwd": {"_capture_runtime_evidence", "_recheck_runtime_evidence"},
}
IMPORTED_ROOTS = {"attester", "child_runner", "dataclasses", "errno", "fcntl", "hashlib", "json", "measurements", "os", "protocol", "receipt_schema", "runtime_resource", "select", "stat", "time", "types"}
ALLOWED_IMPORTED_ATTRIBUTES = {
    "_freeze_session_data": {"types.MappingProxyType"},
    "_canonical_session_json_bytes": {"json.dumps"},
    "_session_config_digest": {"hashlib.sha256"},
    "_parse_session_config_bytes": {"json.JSONDecodeError", "json.loads"},
    "_materialize_exact_builtins": {"types.MappingProxyType"},
    "_base_config_projection": {"attester.AttesterConfig", "attester.validate_config", "types.MappingProxyType"},
    "_validate_and_encode_receipt": {
        "protocol.FrameType", "protocol.FrameType.PRE", "protocol.FrameType.POST", "protocol.encode_frame",
        "receipt_schema.ReceiptPhase", "receipt_schema.ReceiptPhase.PRE", "receipt_schema.ReceiptPhase.POST",
        "receipt_schema.ReceiptPayload", "receipt_schema.validate_pre_payload", "receipt_schema.validate_post_payload",
    },
    "_canonical_session_sha256": {"hashlib.sha256"},
    "_require_mapping": {"types.MappingProxyType"},
    "_require_ascii": set(),
    "_require_digest": set(),
    "_require_integer": set(),
    "_require_absolute_path": set(),
    "_require_relative_path": set(),
    "_validate_id_map": set(),
    "_mapped_outer_id": set(),
    "_validate_certificate": set(),
    "_child_spec_projection": set(),
    "_validate_session_config_relations": {"attester.AttesterConfig", "attester.validate_config", "protocol.MAX_FRAME_BYTES", "types.MappingProxyType"},
    "_admit_session_config": {"types.MappingProxyType"},
    "_hash_regular_descriptor": {"hashlib.sha256", "os.SEEK_SET", "os.lseek", "os.read"},
    "_capture_environment_baseline": set(),
    "_capture_measurement_baseline": {"measurements.MeasurementError", "measurements.MeasurementPlan", "measurements.collect_namespace_measurements", "os.fstat", "stat.S_ISDIR"},
    "_capture_scan_baseline": {"os.O_CLOEXEC", "os.O_DIRECTORY", "os.O_NOFOLLOW", "os.O_RDONLY", "os.close", "os.fstat", "os.listdir", "os.open", "stat.S_IMODE", "stat.S_ISDIR", "stat.S_ISREG", "types.MappingProxyType"},
    "_capture_private_tree_baseline": {"os.O_CLOEXEC", "os.O_DIRECTORY", "os.O_NOFOLLOW", "os.O_RDONLY", "os.close", "os.fstat", "os.listdir", "os.open", "stat.S_IMODE", "stat.S_ISDIR"},
    "_capture_x11_baseline": {"os.fstat", "stat.S_IMODE", "stat.S_ISREG", "stat.S_ISSOCK"},
    "_validate_inherited_fd_census": set(),
    "_validate_mount_projection": set(),
    "_certificate_applicability_projection": set(),
    "_require_owned_evidence_baseline": set(),
    "_capture_evidence_baseline": {"os.close"},
    "_recheck_evidence_baseline": set(),
    "_release_evidence_baseline": {"os.close"},
    "_setup_diagnostic_fd": {"fcntl.F_GETFL", "fcntl.F_SETFL", "fcntl.fcntl", "os.O_NONBLOCK", "os.fstat", "stat.S_ISFIFO"},
    "_emit_diagnostic_once": {"os.write"},
    "_read_fixed_regular": {"fcntl.FD_CLOEXEC", "fcntl.F_GETFD", "fcntl.F_GETFL", "fcntl.fcntl", "os.O_ACCMODE", "os.O_CLOEXEC", "os.O_NOFOLLOW", "os.O_RDONLY", "os.ST_RDONLY", "os.close", "os.fstat", "os.fstatvfs", "os.open", "os.read", "stat.S_ISREG"},
    "_load_fixed_session_config": set(),
    "_wait_fixed_pipe": {"fcntl.F_GETFL", "fcntl.F_SETFL", "fcntl.fcntl", "os.O_NONBLOCK", "os.fstat", "select.POLLERR", "select.POLLHUP", "select.POLLIN", "select.POLLNVAL", "select.POLLOUT", "select.poll", "stat.S_ISFIFO", "time.monotonic_ns"},
    "_write_frame_once": {"os.fpathconf", "os.fstat", "os.write", "protocol.MAX_FRAME_BYTES", "select.POLLOUT", "stat.S_ISFIFO"},
    "_read_ack_eof": {"os.fstat", "os.read", "receipt_schema.validate_ack_bytes", "select.POLLIN", "stat.S_ISFIFO"},
    "_open_runtime_evidence_descriptors": {
        "os.O_CLOEXEC", "os.O_DIRECTORY", "os.O_NOFOLLOW", "os.O_PATH", "os.O_RDONLY",
        "os.close", "os.open",
    },
    "_observe_runtime_descriptor_census": {
        "errno.EBADF", "fcntl.F_GETFD", "fcntl.fcntl", "os.fstat",
        "runtime_resource.RLIMIT_NOFILE", "runtime_resource.getrlimit", "stat.S_ISFIFO", "types.MappingProxyType",
    },
    "_read_runtime_mountinfo": {
        "os.O_CLOEXEC", "os.O_NOFOLLOW", "os.O_RDONLY", "os.close", "os.fstat", "os.open",
        "os.read", "stat.S_ISREG",
    },
    "_observe_runtime_mount_projection": {"types.MappingProxyType"},
    "_capture_runtime_evidence": {"os.close", "os.environ", "os.getcwd"},
    "_recheck_runtime_evidence": {"os.environ", "os.getcwd"},
    "_release_runtime_evidence": set(),
    "_shared_receipt_attestation": set(),
    "_assemble_pre_payload": set(),
    "_assemble_post_payload": {"child_runner.ChildOutcome"},
    "_child_spec_from_config": {"child_runner.ChildSpec"},
    "_validate_child_outcome": {"child_runner.ChildOutcome"},
    "_finalize_post_payload": {
        "protocol.FrameType", "protocol.FrameType.POST", "protocol.encode_frame",
        "receipt_schema.validate_exchange", "receipt_schema.validate_post_payload",
    },
    "load_session_config": set(),
    "run_session": {
        "attester.establish_protocol_barrier", "child_runner.run_child", "os.close",
        "protocol.FrameType", "protocol.FrameType.PRE", "protocol.encode_frame",
        "receipt_schema.validate_pre_payload", "time.monotonic_ns", "types.MappingProxyType",
    },
}
ALLOWED_CALLS = {
    "_freeze_session_data": {
        "SessionError", "_freeze_session_data", "all", "id", "item.encode", "item.items",
        "key.encode", "keys.add", "len", "pending.append", "pending.pop", "seen.add", "set",
        "str", "tuple", "type", "types.MappingProxyType", "value.items",
    },
    "_canonical_session_json_bytes": {"SessionError", "_materialize_exact_builtins", "json.dumps", "len", "text.encode"},
    "_session_config_digest": {"SessionError", "_canonical_session_json_bytes", "_materialize_exact_builtins", "dict", "digest.hexdigest", "hashlib.sha256", "projection.pop", "type"},
    "_parse_session_config_bytes": {"SessionError", "_canonical_session_json_bytes", "_freeze_session_data", "_session_config_digest", "all", "config_bytes.decode", "embedded.encode", "json.loads", "len", "set", "type"},
    "_materialize_exact_builtins": {"SessionError", "_materialize_exact_builtins", "all", "id", "item.encode", "item.items", "key.encode", "len", "pending.append", "pending.pop", "seen.add", "set", "str", "type", "value.items"},
    "_base_config_projection": {"SessionError", "_materialize_exact_builtins", "attester.AttesterConfig", "attester.validate_config", "dict", "set", "type"},
    "_validate_and_encode_receipt": {"SessionError", "protocol.encode_frame", "receipt_schema.validate_post_payload", "receipt_schema.validate_pre_payload", "type"},
    "_canonical_session_sha256": {"_canonical_session_json_bytes", "digest.hexdigest", "hashlib.sha256"},
    "_require_mapping": {"SessionError", "set", "type"},
    "_require_ascii": {"SessionError", "all", "len", "type", "value.encode"},
    "_require_digest": {"SessionError", "_require_ascii", "all"},
    "_require_integer": {"SessionError", "type"},
    "_require_absolute_path": {"SessionError", "_require_ascii", "all", "len", "path.endswith", "path.startswith", "suffix.split"},
    "_require_relative_path": {"SessionError", "_require_ascii", "all", "len", "path.endswith", "path.split", "path.startswith"},
    "_validate_id_map": {"SessionError", "_require_integer", "_require_mapping", "len", "records.append", "type"},
    "_mapped_outer_id": {"SessionError", "_require_integer"},
    "_validate_certificate": {"SessionError", "_canonical_session_sha256", "_mapped_outer_id", "_require_absolute_path", "_require_ascii", "_require_digest", "_require_integer", "_require_mapping", "_validate_id_map", "all", "any", "canonical.pop", "dict", "enumerate", "tuple"},
    "_child_spec_projection": {"SessionError", "_require_absolute_path", "_require_ascii", "_require_integer", "_require_mapping", "argv.append", "dict", "enumerate", "environment_pairs.append", "len", "sorted", "tuple", "type"},
    "_validate_session_config_relations": {"SessionError", "_canonical_session_sha256", "_child_spec_projection", "_mapped_outer_id", "_require_absolute_path", "_require_ascii", "_require_digest", "_require_integer", "_require_mapping", "_require_relative_path", "_session_config_digest", "_validate_certificate", "_validate_id_map", "all", "attester.AttesterConfig", "attester.validate_config", "dict", "direct_inputs.items", "direct_names.add", "entry_names.add", "entry_paths.append", "enumerate", "expected_limits.items", "len", "mount_paths.append", "path.startswith", "required_scan_mounts.add", "resource_names.add", "second_entry_path.startswith", "set", "sorted", "type"},
    "_admit_session_config": {"SessionError", "_freeze_session_data", "_materialize_exact_builtins", "_validate_session_config_relations", "object.__new__", "object.__setattr__", "type"},
    "_hash_regular_descriptor": {"SessionError", "digest.hexdigest", "digest.update", "hashlib.sha256", "len", "min", "os.lseek", "os.read", "type"},
    "_capture_environment_baseline": {"SessionError", "_admit_session_config", "_freeze_session_data", "any", "dict", "tuple", "type"},
    "_capture_measurement_baseline": {"SessionError", "_admit_session_config", "_freeze_session_data", "_materialize_exact_builtins", "measurements.MeasurementPlan", "measurements.collect_namespace_measurements", "os.fstat", "stat.S_ISDIR", "tuple", "type"},
    "_capture_scan_baseline": {"SessionError", "_admit_session_config", "_freeze_session_data", "_hash_regular_descriptor", "current.get", "observed.append", "opened.add", "opened.remove", "os.close", "os.fstat", "os.listdir", "os.open", "pending.append", "pending.pop", "relative_path.split", "set", "sorted", "stat.S_IMODE", "stat.S_ISDIR", "stat.S_ISREG", "tuple", "type"},
    "_capture_private_tree_baseline": {"SessionError", "_admit_session_config", "_freeze_session_data", "observed_directories.append", "os.close", "os.fstat", "os.listdir", "os.open", "stat.S_IMODE", "stat.S_ISDIR", "type"},
    "_capture_x11_baseline": {"SessionError", "_admit_session_config", "_freeze_session_data", "_hash_regular_descriptor", "os.fstat", "stat.S_IMODE", "stat.S_ISREG", "stat.S_ISSOCK", "type"},
    "_validate_inherited_fd_census": {"SessionError", "_admit_session_config", "_freeze_session_data", "list", "type"},
    "_validate_mount_projection": {"SessionError", "_admit_session_config", "_freeze_session_data", "home_path.startswith", "len", "list", "type"},
    "_certificate_applicability_projection": {"_admit_session_config", "_materialize_exact_builtins", "dict"},
    "_require_owned_evidence_baseline": {"SessionError", "_EVIDENCE_OWNERS.get", "id", "len", "set", "type"},
    "_capture_evidence_baseline": {"SessionError", "_admit_session_config", "_capture_environment_baseline", "_capture_measurement_baseline", "_capture_private_tree_baseline", "_capture_scan_baseline", "_capture_x11_baseline", "_certificate_applicability_projection", "_freeze_session_data", "_validate_inherited_fd_census", "_validate_mount_projection", "any", "id", "len", "object.__new__", "object.__setattr__", "os.close", "set", "type"},
    "_recheck_evidence_baseline": {"SessionError", "_admit_session_config", "_capture_environment_baseline", "_capture_measurement_baseline", "_capture_private_tree_baseline", "_capture_scan_baseline", "_capture_x11_baseline", "_certificate_applicability_projection", "_freeze_session_data", "_require_owned_evidence_baseline", "_validate_inherited_fd_census", "_validate_mount_projection"},
    "_release_evidence_baseline": {"SessionError", "_EVIDENCE_OWNERS.pop", "_require_owned_evidence_baseline", "id", "object.__setattr__", "os.close"},
    "_setup_diagnostic_fd": {"SessionError", "fcntl.fcntl", "os.fstat", "stat.S_ISFIFO"},
    "_emit_diagnostic_once": {"SessionError", "all", "len", "os.write", "type", "code.encode"},
    "_read_fixed_regular": {"SessionError", "bytearray", "bytes", "data.extend", "fcntl.fcntl", "len", "min", "os.close", "os.fstat", "os.fstatvfs", "os.open", "os.read", "path.__eq__", "stat.S_ISREG", "type"},
    "_load_fixed_session_config": {"SessionError", "_admit_session_config", "_parse_session_config_bytes", "_read_fixed_regular", "_setup_diagnostic_fd", "object.__new__", "object.__setattr__"},
    "_wait_fixed_pipe": {"SessionError", "fcntl.fcntl", "int", "os.fstat", "poll.poll", "poll.register", "select.poll", "stat.S_ISFIFO", "time.monotonic_ns", "type"},
    "_write_frame_once": {"SessionError", "_wait_fixed_pipe", "len", "os.fpathconf", "os.fstat", "os.write", "stat.S_ISFIFO", "type"},
    "_read_ack_eof": {"SessionError", "_wait_fixed_pipe", "os.fstat", "os.read", "receipt_schema.validate_ack_bytes", "stat.S_ISFIFO", "type"},
    "_open_runtime_evidence_descriptors": {
        "SessionError", "_admit_session_config", "any", "descriptors.append", "len", "os.close",
        "os.open", "set", "type",
    },
    "_observe_runtime_descriptor_census": {
        "SessionError", "_admit_session_config", "any", "expected_ids.add", "fcntl.fcntl", "len",
        "live.add", "observed.append", "os.fstat", "range", "runtime_resource.getrlimit", "set",
        "stat.S_ISFIFO", "tuple", "type",
    },
    "_read_runtime_mountinfo": {
        "SessionError", "bytearray", "bytes", "data.extend", "len", "min", "os.close", "os.fstat",
        "os.open", "os.read", "stat.S_ISREG",
    },
    "_observe_runtime_mount_projection": {
        "SessionError", "_admit_session_config", "_read_runtime_mountinfo", "any", "fields.index", "len",
        "option_text.split", "ord", "path.startswith", "projection.append", "raw.decode", "set",
        "text.endswith", "text.splitlines", "line.split", "tuple", "type",
    },
    "_capture_runtime_evidence": {
        "SessionError", "_admit_session_config", "_capture_evidence_baseline", "_observe_runtime_descriptor_census",
        "_observe_runtime_mount_projection", "_open_runtime_evidence_descriptors", "dict", "os.close",
        "os.getcwd",
    },
    "_recheck_runtime_evidence": {
        "SessionError", "_admit_session_config", "_observe_runtime_descriptor_census",
        "_observe_runtime_mount_projection", "_recheck_evidence_baseline", "_require_owned_evidence_baseline",
        "dict", "os.getcwd",
    },
    "_release_runtime_evidence": {"_release_evidence_baseline"},
    "_shared_receipt_attestation": {
        "SessionError", "_admit_session_config", "_certificate_applicability_projection",
        "_materialize_exact_builtins", "_require_owned_evidence_baseline", "any", "item.get",
        "len", "list", "measurement.get", "measurement_evidence.values", "observed_by_path.get",
        "private_tree.get", "scan.get", "set", "tuple", "type", "x11.get",
    },
    "_assemble_pre_payload": {
        "SessionError", "_admit_session_config", "_materialize_exact_builtins",
        "_shared_receipt_attestation", "dict", "type",
    },
    "_assemble_post_payload": {
        "SessionError", "_admit_session_config", "_materialize_exact_builtins",
        "_shared_receipt_attestation", "_validate_child_outcome", "dict", "type",
    },
    "_child_spec_from_config": {"SessionError", "_admit_session_config", "_child_spec_projection", "child_runner.ChildSpec"},
    "_validate_child_outcome": {"SessionError", "type"},
    "_finalize_post_payload": {"SessionError", "protocol.encode_frame", "receipt_schema.validate_exchange", "receipt_schema.validate_post_payload", "type"},
    "load_session_config": {"SessionError", "_load_fixed_session_config", "type"},
    "run_session": {
        "SessionError", "_admit_session_config", "_assemble_post_payload", "_assemble_pre_payload",
        "_base_config_projection", "_capture_runtime_evidence", "_child_spec_from_config",
        "_emit_diagnostic_once", "_finalize_post_payload", "_read_ack_eof", "_recheck_runtime_evidence",
        "_release_runtime_evidence", "_setup_diagnostic_fd", "_validate_child_outcome", "_write_frame_once",
        "attester.establish_protocol_barrier", "child_runner.run_child", "object.__new__", "object.__setattr__",
        "os.close", "protocol.encode_frame", "receipt_schema.validate_pre_payload", "time.monotonic_ns", "type",
    },
}
EXACT_CALL_COUNTS = {
    "_canonical_session_json_bytes": {"_materialize_exact_builtins": 1, "json.dumps": 1},
    "_session_config_digest": {"_materialize_exact_builtins": 1, "_canonical_session_json_bytes": 1, "hashlib.sha256": 1},
    "_parse_session_config_bytes": {"json.loads": 1, "_freeze_session_data": 1, "_canonical_session_json_bytes": 1, "_session_config_digest": 1},
    "_base_config_projection": {"_materialize_exact_builtins": 1, "attester.AttesterConfig": 1, "attester.validate_config": 1},
    "_validate_and_encode_receipt": {"receipt_schema.validate_pre_payload": 1, "receipt_schema.validate_post_payload": 1, "protocol.encode_frame": 1},
    "_canonical_session_sha256": {"_canonical_session_json_bytes": 1, "hashlib.sha256": 1, "digest.hexdigest": 1},
    "_validate_session_config_relations": {"attester.AttesterConfig": 1, "attester.validate_config": 1, "_child_spec_projection": 1, "_validate_certificate": 2, "_session_config_digest": 1},
    "_admit_session_config": {"_materialize_exact_builtins": 1, "_freeze_session_data": 1, "_validate_session_config_relations": 1, "object.__new__": 1, "object.__setattr__": 1},
    "_setup_diagnostic_fd": {"os.fstat": 1, "fcntl.fcntl": 2},
    "_emit_diagnostic_once": {"os.write": 1},
    "_read_fixed_regular": {"os.open": 1, "os.fstat": 1, "fcntl.fcntl": 2, "os.fstatvfs": 1, "os.read": 1},
    "_load_fixed_session_config": {"_setup_diagnostic_fd": 1, "_read_fixed_regular": 2, "_parse_session_config_bytes": 1, "_admit_session_config": 1, "object.__new__": 1, "object.__setattr__": 1},
    "_wait_fixed_pipe": {"os.fstat": 1, "fcntl.fcntl": 2, "time.monotonic_ns": 1, "select.poll": 1, "poll.register": 1, "poll.poll": 1},
    "_write_frame_once": {"os.fstat": 1, "os.fpathconf": 1, "_wait_fixed_pipe": 1, "os.write": 1},
    "_read_ack_eof": {"os.fstat": 1, "_wait_fixed_pipe": 2, "os.read": 2, "receipt_schema.validate_ack_bytes": 1},
    "_open_runtime_evidence_descriptors": {"_admit_session_config": 1, "os.open": 1},
    "_observe_runtime_descriptor_census": {"_admit_session_config": 1, "runtime_resource.getrlimit": 1, "fcntl.fcntl": 1, "os.fstat": 1},
    "_read_runtime_mountinfo": {"os.open": 1, "os.fstat": 1, "os.read": 1},
    "_observe_runtime_mount_projection": {"_admit_session_config": 1, "_read_runtime_mountinfo": 1},
    "_capture_runtime_evidence": {
        "_admit_session_config": 1, "_observe_runtime_descriptor_census": 1,
        "_observe_runtime_mount_projection": 1, "_open_runtime_evidence_descriptors": 1,
        "_capture_evidence_baseline": 1,
    },
    "_recheck_runtime_evidence": {
        "_require_owned_evidence_baseline": 1, "_admit_session_config": 1,
        "_observe_runtime_descriptor_census": 1, "_observe_runtime_mount_projection": 1,
        "_recheck_evidence_baseline": 1,
    },
    "_release_runtime_evidence": {"_release_evidence_baseline": 1},
    "_shared_receipt_attestation": {
        "_admit_session_config": 1,
        "_require_owned_evidence_baseline": 1,
        "_materialize_exact_builtins": 9,
        "_certificate_applicability_projection": 1,
    },
    "_assemble_pre_payload": {
        "_admit_session_config": 1,
        "_materialize_exact_builtins": 1,
        "_shared_receipt_attestation": 1,
    },
    "_assemble_post_payload": {
        "_admit_session_config": 1,
        "_validate_child_outcome": 1,
        "_materialize_exact_builtins": 1,
        "_shared_receipt_attestation": 1,
    },
    "_child_spec_from_config": {"_admit_session_config": 1, "_child_spec_projection": 1, "child_runner.ChildSpec": 1},
    "_finalize_post_payload": {"receipt_schema.validate_post_payload": 1, "receipt_schema.validate_exchange": 1, "protocol.encode_frame": 1},
    "load_session_config": {"_load_fixed_session_config": 1},
    "run_session": {"_read_ack_eof": 1, "child_runner.run_child": 1, "_finalize_post_payload": 1, "os.close": 1},
}
FORBIDDEN_NODES = (
    ast.Assert, ast.AsyncFunctionDef, ast.Await, ast.Delete, ast.Global, ast.Lambda, ast.NamedExpr,
    ast.Nonlocal, ast.With, ast.AsyncWith, ast.Yield, ast.YieldFrom,
)


def _attribute_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attribute_name(node.value)
        return None if prefix is None else f"{prefix}.{node.attr}"
    return None


def _imports(tree: ast.Module) -> set[str]:
    values: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            values.update(f"import {alias.name}" if alias.asname is None else f"import {alias.name} as {alias.asname}" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            values.update(f"from {prefix} import {alias.name}" if alias.asname is None else f"from {prefix} import {alias.name} as {alias.asname}" for alias in node.names)
    return values


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    values = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    result = {node.name: node for node in values}
    assert len(values) == len(result) and set(result) == EXPECTED_FUNCTIONS
    return result


def _assert_signature(name: str, node: ast.FunctionDef) -> None:
    if name not in EXPECTED_SIGNATURES:
        return
    arguments, annotations, expected_return = EXPECTED_SIGNATURES[name]
    assert not node.args.posonlyargs and not node.args.kwonlyargs
    assert tuple(argument.arg for argument in node.args.args) == arguments
    assert tuple(ast.unparse(argument.annotation) for argument in node.args.args) == annotations
    assert not node.args.defaults and not node.args.kw_defaults and node.args.vararg is None and node.args.kwarg is None
    assert not node.decorator_list and ast.unparse(node.returns) == expected_return


def _assert_error_stub(node: ast.FunctionDef, message: str) -> None:
    assert len(node.body) == 1 and isinstance(node.body[0], ast.Raise)
    expression = node.body[0].exc
    assert isinstance(expression, ast.Call) and _attribute_name(expression.func) == "SessionError"
    assert len(expression.args) == 1 and not expression.keywords
    assert ast.literal_eval(expression.args[0]) == message


def _assert_classes(tree: ast.Module) -> None:
    values = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    assert set(values) == {"SessionError", "SessionConfig", "SessionResult", "_EvidenceBaseline"}
    assert len(values["SessionError"].body) == 1 and isinstance(values["SessionError"].body[0], ast.Pass)
    for name, fields in {
        "SessionConfig": {"data": "Mapping[str, object]"},
        "SessionResult": {"child_pid": "int", "child_returncode": "int", "pre_monotonic_ns": "int", "post_monotonic_ns": "int"},
    }.items():
        node = values[name]
        assert ast.unparse(node.decorator_list[0]) == "dataclasses.dataclass(frozen=True, init=False)"
        annotations = {child.target.id: ast.unparse(child.annotation) for child in node.body if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)}
        assert annotations == fields
        constructors = [child for child in node.body if isinstance(child, ast.FunctionDef) and child.name == "__init__"]
        assert len(constructors) == 1
        _assert_error_stub(constructors[0], "session execution is not admitted")
    evidence = values["_EvidenceBaseline"]
    assert ast.unparse(evidence.decorator_list[0]) == "dataclasses.dataclass(frozen=True, init=False)"
    evidence_fields = {child.target.id for child in evidence.body if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)}
    assert evidence_fields == {"config", "descriptors", "environment", "measurement", "scan", "private_tree", "x11", "inherited_fds", "mounts", "certificate", "released"}
    constructors = [child for child in evidence.body if isinstance(child, ast.FunctionDef) and child.name == "__init__"]
    assert len(constructors) == 1
    assert tuple(argument.arg for argument in constructors[0].args.args) == ("self",)
    assert not constructors[0].args.posonlyargs and not constructors[0].args.kwonlyargs
    assert not constructors[0].args.defaults and not constructors[0].args.kw_defaults
    assert constructors[0].args.vararg is None and constructors[0].args.kwarg is None
    assert ast.unparse(constructors[0].returns) == "None"
    _assert_error_stub(constructors[0], "evidence baseline is internal")


def _assert_no_hidden_capability(name: str, node: ast.FunctionDef) -> None:
    assert not any(isinstance(candidate, FORBIDDEN_NODES) for candidate in ast.walk(node))
    assert not any(isinstance(candidate, (ast.ClassDef, ast.FunctionDef, ast.Import, ast.ImportFrom)) for candidate in ast.walk(node) if candidate is not node)
    parents = {
        child: parent
        for parent in ast.walk(node)
        for child in ast.iter_child_nodes(parent)
    }
    calls: dict[str, int] = {}
    for candidate in ast.walk(node):
        if isinstance(candidate, ast.GeneratorExp):
            parent = parents.get(candidate)
            assert isinstance(parent, ast.Call) and candidate in parent.args
            assert _attribute_name(parent.func) in {"all", "any"} or (
                name == "_freeze_session_data" and _attribute_name(parent.func) == "tuple"
            )
        if isinstance(candidate, ast.Name):
            assert candidate.id != "__debug__" and candidate.id not in FORBIDDEN_ROOTS
            if candidate.id in IMPORTED_ROOTS:
                parent = parents.get(candidate)
                assert isinstance(parent, ast.Attribute) and parent.value is candidate, (
                    f"bare imported module reference is forbidden in {name}: {candidate.id}"
                )
        if isinstance(candidate, ast.Attribute):
            target = _attribute_name(candidate)
            assert target is not None, "computed attribute target is forbidden"
            assert target.split(".")[0] not in FORBIDDEN_ROOTS
            assert not (candidate.attr.startswith("__") or candidate.attr.endswith("__")) or target in {"object.__new__", "object.__setattr__"}
            if target.split(".")[0] in IMPORTED_ROOTS:
                assert target in ALLOWED_IMPORTED_ATTRIBUTES[name], (
                    f"imported attribute is forbidden in {name}: {target}"
                )
        if isinstance(candidate, ast.ExceptHandler):
            if isinstance(candidate.type, ast.Name) and candidate.type.id == "BaseException":
                assert name in {"_open_runtime_evidence_descriptors", "_capture_runtime_evidence", "run_session"}
        if isinstance(candidate, ast.Call):
            target = _attribute_name(candidate.func)
            assert target is not None, "computed call target is forbidden"
            assert target not in FORBIDDEN_CALLS
            assert target in ALLOWED_CALLS[name], f"{name} may not call {target}"
            calls[target] = calls.get(target, 0) + 1
            if target.startswith("os."):
                assert name in OS_CALL_OWNERS.get(target, set()), f"{target} is not allowed in {name}"
                if target == "os.open":
                    keywords = {item.arg: ast.unparse(item.value) for item in candidate.keywords if item.arg is not None}
                    if name == "_read_fixed_regular":
                        assert "dir_fd" not in keywords
                        expected_first = "path"
                    elif name == "_read_runtime_mountinfo":
                        assert "dir_fd" not in keywords
                        assert candidate.args and isinstance(candidate.args[0], ast.Name)
                        assert candidate.args[0].id == "RUNTIME_MOUNTINFO_PATH"
                        expected_first = None
                    elif name == "_open_runtime_evidence_descriptors":
                        assert "dir_fd" not in keywords
                        expected_first = "path"
                    else:
                        assert "dir_fd" in keywords
                        expected_first = "name"
                    if expected_first is not None:
                        assert candidate.args and isinstance(candidate.args[0], ast.Name) and candidate.args[0].id == expected_first
                    source = ast.unparse(candidate)
                    if name == "_open_runtime_evidence_descriptors":
                        assert len(candidate.args) == 2 and isinstance(candidate.args[1], ast.Name)
                        assert candidate.args[1].id == "flags"
                    else:
                        assert "os.O_NOFOLLOW" in source and "os.O_CLOEXEC" in source
    for target, count in EXACT_CALL_COUNTS.get(name, {}).items():
        assert calls.get(target) == count, f"{name} must call {target} exactly {count} time(s)"


def _assert_assignments(tree: ast.Module) -> None:
    assignments: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assert len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            assert node.targets[0].id not in assignments
            assignments[node.targets[0].id] = node.value
    assert set(assignments) == set(EXPECTED_ASSIGNMENTS)
    for name, expected in EXPECTED_ASSIGNMENTS.items():
        assert ast.literal_eval(assignments[name]) == expected


def _assert_bounded_walkers(functions: dict[str, ast.FunctionDef]) -> None:
    """Keep the existing bounded snapshot walkers fail-before-expansion."""
    for name in ("_freeze_session_data", "_materialize_exact_builtins"):
        node = functions[name]
        loops = [
            candidate for candidate in ast.walk(node)
            if isinstance(candidate, ast.While)
            and isinstance(candidate.test, ast.Name)
            and candidate.test.id == "pending"
        ]
        assert len(loops) == 1
        loop = loops[0]
        item_type_index = next(
            index for index, statement in enumerate(loop.body)
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "item_type"
            and ast.unparse(statement.value) == "type(item)"
        )
        depth_index = next(
            index for index, statement in enumerate(loop.body)
            if isinstance(statement, ast.If)
            and "depth == MAX_SESSION_DEPTH" in ast.unparse(statement.test)
        )
        node_count_index = next(
            index for index, statement in enumerate(loop.body)
            if isinstance(statement, ast.AugAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "node_count"
        )
        assert item_type_index < depth_index < node_count_index
        branches = [
            candidate for candidate in ast.walk(loop)
            if isinstance(candidate, ast.If)
            and any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "pending"
                and call.func.attr == "append"
                for call in ast.walk(candidate)
            )
        ]
        assert len(branches) >= 2
        for branch in branches:
            expansions = [
                (index, statement) for index, statement in enumerate(branch.body)
                if isinstance(statement, ast.For)
                and any(
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "pending"
                    and call.func.attr == "append"
                    for call in ast.walk(statement)
                )
            ]
            if not expansions:
                continue
            expansion_index, expansion = expansions[0]
            preflight = [
                index for index, statement in enumerate(branch.body[:expansion_index])
                if isinstance(statement, ast.If)
                and (
                    "MAX_SESSION_NODES - node_count - len(pending)" in ast.unparse(statement.test)
                    or "MAX_SESSION_CONFIG_BYTES" in ast.unparse(statement.test)
                )
            ]
            assert len(preflight) >= 2
            for statement in expansion.body:
                if not isinstance(statement, ast.If):
                    continue
                if "len(key) > MAX_SESSION_STRING_BYTES" not in ast.unparse(statement.test):
                    continue
                key_index = expansion.body.index(statement)
                append_index = next(
                    index for index, child in enumerate(expansion.body)
                    if any(
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and isinstance(call.func.value, ast.Name)
                        and call.func.value.id == "pending"
                        and call.func.attr == "append"
                        for call in ast.walk(child)
                    )
                )
                assert key_index < append_index


def _assert_fixed_pipe_nonblocking(functions: dict[str, ast.FunctionDef]) -> None:
    """Every raw-frame poll must leave its fixed pipe descriptor nonblocking."""
    calls = [
        candidate for candidate in ast.walk(functions["_wait_fixed_pipe"])
        if isinstance(candidate, ast.Call) and _attribute_name(candidate.func) == "fcntl.fcntl"
    ]
    assert len(calls) == 2
    get_flags, set_flags = calls
    assert tuple(ast.unparse(argument) for argument in get_flags.args) == ("fd", "fcntl.F_GETFL")
    assert not get_flags.keywords
    assert tuple(ast.unparse(argument) for argument in set_flags.args) == (
        "fd", "fcntl.F_SETFL", "flags | os.O_NONBLOCK",
    )
    assert not set_flags.keywords
    assert get_flags.lineno < set_flags.lineno
    poll_call = next(
        candidate for candidate in ast.walk(functions["_wait_fixed_pipe"])
        if isinstance(candidate, ast.Call) and _attribute_name(candidate.func) == "select.poll"
    )
    assert set_flags.lineno < poll_call.lineno


def _assert_state_entrypoints(functions: dict[str, ast.FunctionDef]) -> None:
    runtime = {
        name: functions[name]
        for name in (
            "_open_runtime_evidence_descriptors", "_observe_runtime_descriptor_census",
            "_read_runtime_mountinfo", "_observe_runtime_mount_projection",
            "_capture_runtime_evidence", "_recheck_runtime_evidence", "_release_runtime_evidence",
        )
    }
    for name, node in runtime.items():
        assert not (
            len(node.body) == 1
            and isinstance(node.body[0], ast.Raise)
            and isinstance(node.body[0].exc, ast.Call)
            and _attribute_name(node.body[0].exc.func) == "SessionError"
        ), f"{name} must be a bounded runtime-observation helper"
    open_helper = runtime["_open_runtime_evidence_descriptors"]
    open_literals = {
        _attribute_name(candidate)
        for candidate in ast.walk(open_helper)
        if isinstance(candidate, ast.Attribute)
    }
    assert {"os.O_CLOEXEC", "os.O_DIRECTORY", "os.O_NOFOLLOW", "os.O_PATH", "os.O_RDONLY"} <= open_literals
    census = runtime["_observe_runtime_descriptor_census"]
    assert any(
        isinstance(candidate, ast.Call) and _attribute_name(candidate.func) == "runtime_resource.getrlimit"
        for candidate in ast.walk(census)
    )
    assert any(
        isinstance(candidate, ast.Name) and candidate.id == "MAX_RUNTIME_DESCRIPTOR_LIMIT"
        for candidate in ast.walk(census)
    )
    mount_reader = runtime["_read_runtime_mountinfo"]
    assert any(
        isinstance(candidate, ast.Name) and candidate.id == "RUNTIME_MOUNTINFO_PATH"
        for candidate in ast.walk(mount_reader)
    )
    assert any(
        isinstance(candidate, ast.Name) and candidate.id == "MAX_RUNTIME_MOUNTINFO_BYTES"
        for candidate in ast.walk(mount_reader)
    )
    capture = runtime["_capture_runtime_evidence"]
    capture_calls = [
        _attribute_name(candidate.func)
        for candidate in ast.walk(capture)
        if isinstance(candidate, ast.Call)
    ]
    assert capture_calls.count("_observe_runtime_descriptor_census") == 1
    assert capture_calls.count("_observe_runtime_mount_projection") == 1
    assert capture_calls.count("_open_runtime_evidence_descriptors") == 1
    assert capture_calls.count("_capture_evidence_baseline") == 1
    recheck = runtime["_recheck_runtime_evidence"]
    recheck_calls = [
        _attribute_name(candidate.func)
        for candidate in ast.walk(recheck)
        if isinstance(candidate, ast.Call)
    ]
    assert recheck_calls.count("_require_owned_evidence_baseline") == 1
    assert recheck_calls.count("_recheck_evidence_baseline") == 1
    release = runtime["_release_runtime_evidence"]
    release_calls = [
        _attribute_name(candidate.func)
        for candidate in ast.walk(release)
        if isinstance(candidate, ast.Call)
    ]
    assert release_calls == ["_release_evidence_baseline"]
    shared = functions["_shared_receipt_attestation"]
    pre = functions["_assemble_pre_payload"]
    post = functions["_assemble_post_payload"]
    assert not any(
        isinstance(candidate, ast.Raise)
        and isinstance(candidate.exc, ast.Call)
        and _attribute_name(candidate.exc.func) == "SessionError"
        and len(candidate.exc.args) == 1
        and isinstance(candidate.exc.args[0], ast.Constant)
        and candidate.exc.args[0].value == "runtime evidence is not admitted"
        for candidate in ast.walk(shared)
    )
    for name, node in {"_assemble_pre_payload": pre, "_assemble_post_payload": post}.items():
        assert not (
            len(node.body) == 1
            and isinstance(node.body[0], ast.Raise)
            and isinstance(node.body[0].exc, ast.Call)
            and _attribute_name(node.body[0].exc.func) == "SessionError"
        ), f"{name} must assemble an owned receipt payload"
    shared_strings = {
        candidate.value
        for candidate in ast.walk(shared)
        if isinstance(candidate, ast.Constant) and type(candidate.value) is str
    }
    pre_strings = {
        candidate.value
        for candidate in ast.walk(pre)
        if isinstance(candidate, ast.Constant) and type(candidate.value) is str
    }
    post_strings = {
        candidate.value
        for candidate in ast.walk(post)
        if isinstance(candidate, ast.Constant) and type(candidate.value) is str
    }
    assert "scan_root_unchanged" not in shared_strings | pre_strings
    assert post_strings & {"scan_root_unchanged"} == {"scan_root_unchanged"}
    assert {"pre", "no_child_started", "attestation"} <= pre_strings
    assert {"post", "terminal", "child_pid", "child_returncode", "pre_monotonic_ns", "post_monotonic_ns", "attestation"} <= post_strings
    loader_calls = [
        _attribute_name(candidate.func)
        for candidate in ast.walk(functions["load_session_config"])
        if isinstance(candidate, ast.Call)
    ]
    assert loader_calls.count("_load_fixed_session_config") == 1
    run = functions["run_session"]
    calls = sorted(
        (
            candidate.lineno,
            candidate.col_offset,
            _attribute_name(candidate.func),
        )
        for candidate in ast.walk(run)
        if isinstance(candidate, ast.Call)
    )
    direct = [target for _line, _column, target in calls]
    required_order = (
        "_setup_diagnostic_fd", "_admit_session_config", "_capture_runtime_evidence",
        "_base_config_projection", "attester.establish_protocol_barrier",
        "_assemble_pre_payload", "receipt_schema.validate_pre_payload", "protocol.encode_frame",
        "time.monotonic_ns", "_write_frame_once", "_read_ack_eof", "_child_spec_from_config",
        "_validate_child_outcome", "_recheck_runtime_evidence",
        "_assemble_post_payload", "_finalize_post_payload", "os.close", "object.__new__",
        "object.__setattr__",
    )
    cursor = 0
    for target in required_order:
        cursor = direct.index(target, cursor) + 1
    outcome_calls = [
        candidate for candidate in ast.walk(run)
        if isinstance(candidate, ast.Call) and _attribute_name(candidate.func) == "_validate_child_outcome"
    ]
    assert len(outcome_calls) == 1
    assert len(outcome_calls[0].args) == 1 and isinstance(outcome_calls[0].args[0], ast.Call)
    assert _attribute_name(outcome_calls[0].args[0].func) == "child_runner.run_child"
    assert "receipt_schema.validate_post_payload" not in direct
    assert "receipt_schema.validate_exchange" not in direct
    terminal_releases = [
        candidate for candidate in ast.walk(run)
        if isinstance(candidate, ast.Call)
        and _attribute_name(candidate.func) == "_release_runtime_evidence"
        and len(candidate.args) == 1
        and isinstance(candidate.args[0], ast.Name)
        and candidate.args[0].id == "released_baseline"
    ]
    assert len(terminal_releases) == 1
    assert any(
        isinstance(candidate, ast.Assign)
        and len(candidate.targets) == 1
        and isinstance(candidate.targets[0], ast.Name)
        and candidate.targets[0].id == "baseline"
        and isinstance(candidate.value, ast.Constant)
        and candidate.value.value is None
        and candidate.lineno < terminal_releases[0].lineno
        for candidate in ast.walk(run)
    )
    assert any(isinstance(node, ast.Return) for node in ast.walk(run))
    assert not any(isinstance(node, ast.Try) and node.finalbody for node in ast.walk(run))


def assert_b4b_source_contract() -> None:
    if sys.flags.optimize:
        raise AssertionError("the pre-import source contract may not run under optimization")
    source = SESSION_PATH.read_bytes()
    if EXPECTED_SOURCE_SHA256 is not None:
        assert hashlib.sha256(source).hexdigest() == EXPECTED_SOURCE_SHA256
    tree = ast.parse(source.decode("utf-8"), filename=str(SESSION_PATH))
    assert _imports(tree) == EXPECTED_IMPORTS
    assert all(isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign, ast.ClassDef, ast.FunctionDef)) for node in tree.body)
    _assert_assignments(tree)
    _assert_classes(tree)
    functions = _functions(tree)
    for name, node in functions.items():
        _assert_signature(name, node)
        _assert_no_hidden_capability(name, node)
    _assert_bounded_walkers(functions)
    _assert_fixed_pipe_nonblocking(functions)
    _assert_state_entrypoints(functions)


class Task0B4bStateStaticContractTests(unittest.TestCase):
    def test_preimport_state_source_contract(self) -> None:
        self.assertTrue(__debug__, "the contract may not run under optimization")
        assert_b4b_source_contract()

    def test_rejects_an_absolute_descriptor_open_argument(self) -> None:
        node = ast.parse(
            "def _capture_scan_baseline():\n"
            "    os.open('/host/path', os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)\n"
        ).body[0]
        self.assertIsInstance(node, ast.FunctionDef)
        with self.assertRaises(AssertionError):
            _assert_no_hidden_capability("_capture_scan_baseline", node)


if __name__ == "__main__":
    unittest.main()
