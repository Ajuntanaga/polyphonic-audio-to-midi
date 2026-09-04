"""Pre-import source contract for Task 0B4b-admission-pure."""
from __future__ import annotations

import ast
import pathlib
import sys
import unittest


SESSION_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "reaper_v4_session.py"
EXPECTED_IMPORTS = {
    "from __future__ import annotations",
    "import dataclasses",
    "import hashlib",
    "import json",
    "import types",
    "from collections.abc import Mapping",
    "from tools import reaper_v4_attester as attester",
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
}
PUBLIC_FUNCTIONS = {"load_session_config", "run_session"}
EXISTING_HELPERS = {
    "_freeze_session_data",
    "_canonical_session_json_bytes",
    "_session_config_digest",
    "_parse_session_config_bytes",
    "_materialize_exact_builtins",
    "_base_config_projection",
    "_validate_and_encode_receipt",
}
ADMISSION_HELPERS = {
    "_canonical_session_sha256",
    "_require_mapping",
    "_require_ascii",
    "_require_digest",
    "_require_integer",
    "_require_absolute_path",
    "_require_relative_path",
    "_validate_id_map",
    "_mapped_outer_id",
    "_validate_certificate",
    "_child_spec_projection",
    "_validate_session_config_relations",
    "_admit_session_config",
}
EXPECTED_FUNCTIONS = EXISTING_HELPERS | ADMISSION_HELPERS | PUBLIC_FUNCTIONS
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
    "load_session_config": (("config_path", "digest_path"), ("str", "str"), "SessionConfig"),
    "run_session": (("config",), ("SessionConfig",), "SessionResult"),
}
IMPORTED_ROOTS = {"attester", "dataclasses", "hashlib", "json", "protocol", "receipt_schema", "types"}
FORBIDDEN_NODES = (
    ast.Assert, ast.AsyncFunctionDef, ast.Await, ast.Delete, ast.Global,
    ast.Lambda, ast.NamedExpr, ast.Nonlocal, ast.With, ast.AsyncWith,
    ast.Yield, ast.YieldFrom,
)
FORBIDDEN_ROOTS = {
    "child_runner", "measurements", "os", "pathlib", "stat", "fcntl", "select",
    "time", "socket", "subprocess", "io", "sys", "importlib", "ctypes",
    "tempfile", "pickle", "marshal", "inspect", "platform", "threading", "signal",
}
FORBIDDEN_CALLS = {
    "__import__", "breakpoint", "compile", "eval", "exec", "getattr", "globals",
    "help", "input", "locals", "open", "setattr", "delattr", "vars",
}
ALLOWED_IMPORTED_ATTRIBUTES = {
    "_freeze_session_data": {"types.MappingProxyType"},
    "_canonical_session_json_bytes": {"json.dumps"},
    "_session_config_digest": {"hashlib.sha256"},
    "_parse_session_config_bytes": {"json.loads", "json.JSONDecodeError"},
    "_materialize_exact_builtins": {"types.MappingProxyType"},
    "_base_config_projection": {
        "types.MappingProxyType", "attester.AttesterConfig", "attester.validate_config",
    },
    "_validate_and_encode_receipt": {
        "protocol.FrameType", "protocol.FrameType.PRE", "protocol.FrameType.POST",
        "protocol.encode_frame", "receipt_schema.ReceiptPhase", "receipt_schema.ReceiptPhase.PRE",
        "receipt_schema.ReceiptPhase.POST", "receipt_schema.ReceiptPayload",
        "receipt_schema.validate_pre_payload", "receipt_schema.validate_post_payload",
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
    "_validate_session_config_relations": {
        "attester.AttesterConfig", "attester.validate_config", "protocol.MAX_FRAME_BYTES",
        "types.MappingProxyType",
    },
    "_admit_session_config": {"types.MappingProxyType"},
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


def _attribute_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attribute_name(node.value)
        return None if prefix is None else f"{prefix}.{node.attr}"
    return None


def _assignment_map(tree: ast.Module) -> dict[str, ast.expr]:
    assignments: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assert len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            assert node.targets[0].id not in assignments
            assignments[node.targets[0].id] = node.value
    return assignments


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    values = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    result = {node.name: node for node in values}
    assert len(values) == len(result) and set(result) == EXPECTED_FUNCTIONS
    return result


def _assert_signature(name: str, node: ast.FunctionDef) -> None:
    arguments, annotations, expected_return = EXPECTED_SIGNATURES[name]
    assert not node.args.posonlyargs and not node.args.kwonlyargs
    assert tuple(argument.arg for argument in node.args.args) == arguments
    assert tuple(ast.unparse(argument.annotation) for argument in node.args.args) == annotations
    assert not node.args.defaults and not node.args.kw_defaults
    assert node.args.vararg is None and node.args.kwarg is None
    assert not node.decorator_list and ast.unparse(node.returns) == expected_return


def _assert_no_hidden_capability(name: str, node: ast.FunctionDef) -> None:
    assert not any(isinstance(candidate, FORBIDDEN_NODES) for candidate in ast.walk(node))
    assert not any(
        isinstance(candidate, (ast.ClassDef, ast.FunctionDef, ast.Import, ast.ImportFrom))
        for candidate in ast.walk(node) if candidate is not node
    )
    parents = {child: parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}
    calls: dict[str, int] = {}
    for candidate in ast.walk(node):
        if isinstance(candidate, ast.GeneratorExp):
            parent = parents.get(candidate)
            assert isinstance(parent, ast.Call)
            assert _attribute_name(parent.func) in {"all", "any"} or (
                name == "_freeze_session_data" and _attribute_name(parent.func) == "tuple"
            )
            assert candidate in parent.args
        if isinstance(candidate, ast.Name):
            assert candidate.id != "__debug__"
            assert candidate.id not in FORBIDDEN_ROOTS
            if candidate.id in IMPORTED_ROOTS:
                parent = parents.get(candidate)
                assert isinstance(parent, ast.Attribute) and parent.value is candidate
        if isinstance(candidate, ast.Attribute):
            target = _attribute_name(candidate)
            assert target is not None, "computed attribute target is forbidden"
            root = target.split(".")[0]
            assert root not in FORBIDDEN_ROOTS
            if root in IMPORTED_ROOTS:
                assert target in ALLOWED_IMPORTED_ATTRIBUTES[name]
            if candidate.attr.startswith("__") or candidate.attr.endswith("__"):
                assert name == "_admit_session_config" and target in {"object.__new__", "object.__setattr__"}
        if isinstance(candidate, ast.ExceptHandler):
            assert not (isinstance(candidate.type, ast.Name) and candidate.type.id == "BaseException")
        if isinstance(candidate, ast.Call):
            call_name = _attribute_name(candidate.func)
            assert call_name is not None, "computed call target is forbidden"
            assert call_name.split(".")[0] not in FORBIDDEN_CALLS
            assert call_name in ALLOWED_CALLS[name], f"{name} may not call {call_name}"
            calls[call_name] = calls.get(call_name, 0) + 1
    for target, count in EXACT_CALL_COUNTS.get(name, {}).items():
        assert calls.get(target) == count, f"{name} must call {target} exactly {count} time(s)"


def _assert_one_statement_error(node: ast.FunctionDef, message: str) -> None:
    assert len(node.body) == 1 and isinstance(node.body[0], ast.Raise)
    expression = node.body[0].exc
    assert isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name)
    assert expression.func.id == "SessionError" and len(expression.args) == 1 and not expression.keywords
    assert ast.literal_eval(expression.args[0]) == message


def _assert_signature_constructor(node: ast.FunctionDef) -> None:
    assert node.name == "__init__" and not node.args.posonlyargs and not node.args.kwonlyargs
    assert tuple(item.arg for item in node.args.args) == ("self",)
    assert not node.args.defaults and not node.args.kw_defaults and node.args.vararg is None and node.args.kwarg is None
    assert not node.decorator_list and ast.unparse(node.returns) == "None"
    _assert_one_statement_error(node, "session execution is not admitted")


def _assert_classes(tree: ast.Module) -> None:
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    values = {node.name: node for node in classes}
    assert len(classes) == len(values) and set(values) == {"SessionError", "SessionConfig", "SessionResult"}
    error = values["SessionError"]
    assert [ast.unparse(base) for base in error.bases] == ["RuntimeError"]
    assert len(error.body) == 1 and isinstance(error.body[0], ast.Pass)
    expected = {
        "SessionConfig": (("data",), ("Mapping[str, object]",)),
        "SessionResult": (("child_pid", "child_returncode", "pre_monotonic_ns", "post_monotonic_ns"), ("int", "int", "int", "int")),
    }
    for name, (field_names, annotations) in expected.items():
        value = values[name]
        assert len(value.decorator_list) == 1 and isinstance(value.decorator_list[0], ast.Call)
        decorator = value.decorator_list[0]
        assert ast.unparse(decorator.func) == "dataclasses.dataclass" and not decorator.args
        assert {item.arg: ast.literal_eval(item.value) for item in decorator.keywords} == {"frozen": True, "init": False}
        fields = [item for item in value.body if isinstance(item, ast.AnnAssign)]
        assert tuple(item.target.id for item in fields) == field_names
        assert tuple(ast.unparse(item.annotation) for item in fields) == annotations
        assert all(item.value is None for item in fields)
        constructor = [item for item in value.body if isinstance(item, ast.FunctionDef)]
        assert len(constructor) == 1 and len(value.body) == len(fields) + 1
        _assert_signature_constructor(constructor[0])


def _calls(node: ast.AST) -> list[str]:
    return [
        _attribute_name(candidate.func)
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Call) and _attribute_name(candidate.func) is not None
    ]


def _config_data_reads(node: ast.AST) -> list[ast.Attribute]:
    return [
        candidate for candidate in ast.walk(node)
        if isinstance(candidate, ast.Attribute)
        and isinstance(candidate.value, ast.Name)
        and candidate.value.id == "config"
        and candidate.attr == "data"
    ]


def _assert_phase_b(functions: dict[str, ast.FunctionDef]) -> None:
    for name in ADMISSION_HELPERS:
        assert not (
            len(functions[name].body) == 1
            and isinstance(functions[name].body[0], ast.Raise)
        ), f"{name} must not remain an inert admission stub"
    for name in PUBLIC_FUNCTIONS:
        _assert_one_statement_error(functions[name], "session execution is not admitted")
    admission = functions["_admit_session_config"]
    reads = _config_data_reads(admission)
    assert len(reads) == 1
    assignments = [
        node for node in ast.walk(admission)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "untrusted_data"
        and node.value is reads[0]
    ]
    assert len(assignments) == 1
    call_names = _calls(admission)
    assert call_names.count("_materialize_exact_builtins") == 1
    assert call_names.count("_freeze_session_data") == 1
    assert call_names.count("_validate_session_config_relations") == 1
    assert call_names.count("object.__new__") == 1
    assert call_names.count("object.__setattr__") == 1
    materialize = [
        node for node in ast.walk(admission)
        if isinstance(node, ast.Call) and _attribute_name(node.func) == "_materialize_exact_builtins"
    ]
    assert len(materialize) == 1 and len(materialize[0].args) == 1
    assert isinstance(materialize[0].args[0], ast.Name) and materialize[0].args[0].id == "untrusted_data"


def _assert_bounded_walkers(functions: dict[str, ast.FunctionDef]) -> None:
    """Keep the sealed bounded walkers fail-before-expansion."""
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
                condition = ast.unparse(statement.test)
                if "len(key) > MAX_SESSION_STRING_BYTES" not in condition:
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
    """Check the final admission source shape without importing the target."""
    if sys.flags.optimize:
        raise AssertionError("Task 0B4b static contract must not run with Python optimization")
    source = SESSION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SESSION_PATH))
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    import_text = {ast.unparse(node) for node in imports}
    assert import_text == EXPECTED_IMPORTS and len(imports) == len(import_text)
    assignments = _assignment_map(tree)
    assert set(assignments) == set(EXPECTED_ASSIGNMENTS)
    for name, expected in EXPECTED_ASSIGNMENTS.items():
        assert ast.literal_eval(assignments[name]) == expected
    allowed_top_level = (ast.Assign, ast.ClassDef, ast.Expr, ast.FunctionDef, ast.Import, ast.ImportFrom)
    assert all(isinstance(node, allowed_top_level) for node in tree.body)
    expressions = [node for node in tree.body if isinstance(node, ast.Expr)]
    assert len(expressions) == 1 and isinstance(expressions[0].value, ast.Constant)
    assert type(expressions[0].value.value) is str
    functions = _functions(tree)
    for name, node in functions.items():
        _assert_signature(name, node)
        _assert_no_hidden_capability(name, node)
    _assert_classes(tree)
    _assert_bounded_walkers(functions)
    _assert_phase_b(functions)


class Task0B4bAdmissionStaticContractTests(unittest.TestCase):
    def test_preimport_final_admission_source_contract(self) -> None:
        if sys.flags.optimize:
            self.fail("Task 0B4b static contract must not run with Python optimization")
        assert_b4b_source_contract()


if __name__ == "__main__":
    unittest.main()
