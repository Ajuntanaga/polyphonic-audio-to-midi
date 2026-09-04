"""Pre-import source contract for Task 0B4b-evidence."""
from __future__ import annotations

import ast
import hashlib
import pathlib
import sys
import unittest


SESSION_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "reaper_v4_session.py"
EXPECTED_SOURCE_SHA256 = "6049ec3096cf9a2fc50678884180fe4e0ef6072032418931f0d48afa14f83a1f"
EXPECTED_IMPORTS = {
    "from __future__ import annotations",
    "import dataclasses",
    "import hashlib",
    "import json",
    "import os",
    "import stat",
    "import types",
    "from collections.abc import Mapping",
    "from tools import reaper_v4_attester as attester",
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
EXPECTED_FUNCTIONS = PURE_HELPERS | EVIDENCE_HELPERS | PUBLIC_FUNCTIONS
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
    "load_session_config": (("config_path", "digest_path"), ("str", "str"), "SessionConfig"),
    "run_session": (("config",), ("SessionConfig",), "SessionResult"),
}
FORBIDDEN_ROOTS = {
    "child_runner", "pathlib", "fcntl", "select", "time", "socket", "subprocess", "io", "sys",
    "importlib", "ctypes", "tempfile", "pickle", "marshal", "inspect", "platform", "threading", "signal",
}
FORBIDDEN_CALLS = {
    "__import__", "breakpoint", "compile", "eval", "exec", "getattr", "globals", "help", "input",
    "locals", "open", "setattr", "delattr", "vars", "os.write", "os.pipe", "os.dup",
}
OS_CALL_OWNERS = {
    "os.fstat": {"_capture_measurement_baseline", "_capture_scan_baseline", "_capture_private_tree_baseline", "_capture_x11_baseline"},
    "os.open": {"_capture_scan_baseline", "_capture_private_tree_baseline"},
    "os.close": {"_capture_scan_baseline", "_capture_private_tree_baseline", "_capture_evidence_baseline", "_release_evidence_baseline"},
    "os.read": {"_hash_regular_descriptor"},
    "os.lseek": {"_hash_regular_descriptor"},
    "os.listdir": {"_capture_scan_baseline", "_capture_private_tree_baseline"},
}
IMPORTED_ROOTS = {"attester", "dataclasses", "hashlib", "json", "measurements", "os", "protocol", "receipt_schema", "stat", "types"}
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
    "load_session_config": set(),
    "run_session": set(),
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
    "load_session_config": {"SessionError"},
    "run_session": {"SessionError"},
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
            assert not (isinstance(candidate.type, ast.Name) and candidate.type.id == "BaseException")
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
                    assert "dir_fd" in keywords
                    assert candidate.args and isinstance(candidate.args[0], ast.Name) and candidate.args[0].id == "name"
                    source = ast.unparse(candidate)
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
    for name in PUBLIC_FUNCTIONS:
        _assert_error_stub(functions[name], "session execution is not admitted")


class Task0B4bEvidenceStaticContractTests(unittest.TestCase):
    def test_preimport_evidence_source_contract(self) -> None:
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
