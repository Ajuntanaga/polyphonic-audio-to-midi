"""Pre-import source contract for the Task 0B4b-pure helper increment."""
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
    "from tools import reaper_v4_child_runner as child_runner",
    "from tools import reaper_v4_measurements as measurements",
    "from tools import reaper_v4_protocol as protocol",
    "from tools import reaper_v4_receipt_schema as receipt_schema",
}
EXPECTED_ASSIGNMENTS = {
    "__all__": (
        "SessionError", "SessionConfig", "SessionResult", "load_session_config", "run_session",
    ),
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
EXPECTED_CLASSES = {"SessionError", "SessionConfig", "SessionResult"}
EXPECTED_FUNCTIONS = {
    "_freeze_session_data",
    "_canonical_session_json_bytes",
    "_session_config_digest",
    "_parse_session_config_bytes",
    "_materialize_exact_builtins",
    "_base_config_projection",
    "_validate_and_encode_receipt",
    "load_session_config",
    "run_session",
}
EXPECTED_SIGNATURES = {
    "_freeze_session_data": (("value",), ("object",), "object"),
    "_canonical_session_json_bytes": (("value",), ("object",), "bytes"),
    "_session_config_digest": (("value",), ("object",), "str"),
    "_parse_session_config_bytes": (("config_bytes", "sidecar_bytes"), ("bytes", "bytes"), "Mapping[str, object]"),
    "_materialize_exact_builtins": (("value",), ("object",), "object"),
    "_base_config_projection": (("config",), ("SessionConfig",), "dict[str, object]"),
    "_validate_and_encode_receipt": (("payload", "phase", "sequence"), ("dict[str, object]", "receipt_schema.ReceiptPhase", "int"), "tuple[receipt_schema.ReceiptPayload, bytes]"),
    "load_session_config": (("config_path", "digest_path"), ("str", "str"), "SessionConfig"),
    "run_session": (("config",), ("SessionConfig",), "SessionResult"),
}
EXTERNAL_CALLS = {
    "_freeze_session_data": {"types.MappingProxyType": 1},
    "_canonical_session_json_bytes": {"json.dumps": 1},
    "_session_config_digest": {"hashlib.sha256": 1},
    "_parse_session_config_bytes": {"json.loads": 1},
    "_materialize_exact_builtins": {},
    "_base_config_projection": {"attester.AttesterConfig": 1, "attester.validate_config": 1},
    "_validate_and_encode_receipt": {
        "receipt_schema.validate_pre_payload": 1,
        "receipt_schema.validate_post_payload": 1,
        "protocol.encode_frame": 1,
    },
    "load_session_config": {},
    "run_session": {},
}
LOCAL_CALLS = {
    "_freeze_session_data": {},
    "_canonical_session_json_bytes": {"_materialize_exact_builtins": 1},
    "_session_config_digest": {"_materialize_exact_builtins": 1, "_canonical_session_json_bytes": 1},
    "_parse_session_config_bytes": {
        "_freeze_session_data": 1,
        "_canonical_session_json_bytes": 1,
        "_session_config_digest": 1,
    },
    "_materialize_exact_builtins": {},
    "_base_config_projection": {"_materialize_exact_builtins": 1},
    "_validate_and_encode_receipt": {},
    "load_session_config": {"SessionError": 1},
    "run_session": {"SessionError": 1},
}
RECURSIVE_HELPERS = {"_freeze_session_data", "_materialize_exact_builtins"}
BUILTIN_CALLS = {
    "_freeze_session_data": {"SessionError", "all", "dict", "id", "len", "list", "set", "str", "tuple", "type"},
    "_canonical_session_json_bytes": {"SessionError", "len", "type"},
    "_session_config_digest": {"SessionError", "dict", "type"},
    "_parse_session_config_bytes": {"SessionError", "all", "len", "set", "type"},
    "_materialize_exact_builtins": {"SessionError", "all", "dict", "id", "len", "list", "set", "str", "tuple", "type"},
    "_base_config_projection": {"SessionError", "dict", "set", "type"},
    "_validate_and_encode_receipt": {"SessionError", "type"},
    "load_session_config": set(),
    "run_session": set(),
}
METHOD_CALLS = {"add", "append", "decode", "encode", "hexdigest", "items", "pop", "values"}
IMPORTED_ROOTS = {"attester", "child_runner", "dataclasses", "measurements", "protocol", "receipt_schema", "types", "json", "hashlib"}
ALLOWED_IMPORTED_ATTRIBUTES = {
    "_freeze_session_data": {"types.MappingProxyType"},
    "_canonical_session_json_bytes": {"json.dumps"},
    "_session_config_digest": {"hashlib.sha256"},
    "_parse_session_config_bytes": {"json.loads", "json.JSONDecodeError"},
    "_materialize_exact_builtins": {"types.MappingProxyType"},
    "_base_config_projection": {"types.MappingProxyType", "attester.AttesterConfig", "attester.validate_config"},
    "_validate_and_encode_receipt": {
        "protocol.encode_frame", "protocol.FrameType", "protocol.FrameType.PRE", "protocol.FrameType.POST",
        "receipt_schema.ReceiptPhase", "receipt_schema.ReceiptPhase.PRE", "receipt_schema.ReceiptPhase.POST",
        "receipt_schema.ReceiptPayload", "receipt_schema.validate_pre_payload", "receipt_schema.validate_post_payload",
    },
    "load_session_config": set(),
    "run_session": set(),
}
FORBIDDEN_NODES = (ast.Assert, ast.Lambda, ast.NamedExpr, ast.Await, ast.Yield, ast.YieldFrom, ast.Global, ast.Nonlocal, ast.Delete, ast.With, ast.AsyncWith)


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
        if not isinstance(node, ast.Assign):
            continue
        assert len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        assert node.targets[0].id not in assignments
        assignments[node.targets[0].id] = node.value
    return assignments


def _assert_function_signature(name: str, node: ast.FunctionDef) -> None:
    arguments, annotations, expected_return = EXPECTED_SIGNATURES[name]
    assert tuple(argument.arg for argument in node.args.posonlyargs) == ()
    assert tuple(argument.arg for argument in node.args.args) == arguments
    assert tuple(ast.unparse(argument.annotation) for argument in node.args.args) == annotations
    assert tuple(argument.arg for argument in node.args.kwonlyargs) == ()
    assert not node.args.defaults and not node.args.kw_defaults
    assert node.args.vararg is None and node.args.kwarg is None
    assert not node.decorator_list
    assert ast.unparse(node.returns) == expected_return


def _calls(node: ast.FunctionDef) -> dict[str, int]:
    values: dict[str, int] = {}
    for candidate in ast.walk(node):
        if not isinstance(candidate, ast.Call):
            continue
        target = _attribute_name(candidate.func)
        assert target is not None, f"{node.name} uses a computed call target"
        values[target] = values.get(target, 0) + 1
    return values


def _assert_function_body(name: str, node: ast.FunctionDef) -> None:
    assert not any(isinstance(candidate, FORBIDDEN_NODES) for candidate in ast.walk(node))
    assert not any(
        isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom))
        for candidate in ast.walk(node) if candidate is not node
    )
    parents = {child: parent for parent in ast.walk(node) for child in ast.iter_child_nodes(parent)}
    for candidate in ast.walk(node):
        if isinstance(candidate, ast.Name):
            assert candidate.id != "__debug__"
        if isinstance(candidate, ast.Name) and candidate.id in IMPORTED_ROOTS:
            parent = parents.get(candidate)
            assert isinstance(parent, ast.Attribute) and parent.value is candidate
    for attribute in (candidate for candidate in ast.walk(node) if isinstance(candidate, ast.Attribute)):
        target = _attribute_name(attribute)
        if target is None:
            continue
        root = target.split(".", 1)[0]
        if root in IMPORTED_ROOTS:
            assert root not in {"child_runner", "measurements"}
            assert target in ALLOWED_IMPORTED_ATTRIBUTES[name]
    calls = _calls(node)
    expected = dict(EXTERNAL_CALLS[name])
    expected.update(LOCAL_CALLS[name])
    for target in calls:
        if "." in target:
            root = target.split(".", 1)[0]
            if root in IMPORTED_ROOTS:
                assert target in EXTERNAL_CALLS[name]
            else:
                assert target.rsplit(".", 1)[-1] in METHOD_CALLS
        else:
            assert target in BUILTIN_CALLS[name] | set(LOCAL_CALLS[name]) | ({name} if name in RECURSIVE_HELPERS else set())
    for target, count in expected.items():
        assert calls.get(target) == count, f"{name} must call {target} exactly {count} time(s)"
    for target in EXTERNAL_CALLS[name]:
        assert calls.get(target) == EXTERNAL_CALLS[name][target]
    if name in RECURSIVE_HELPERS:
        assert calls.get(name, 0) >= 1
    if name in {"load_session_config", "run_session"}:
        assert len(node.body) == 1 and isinstance(node.body[0], ast.Raise)
        assert isinstance(node.body[0].exc, ast.Call)
        assert isinstance(node.body[0].exc.func, ast.Name) and node.body[0].exc.func.id == "SessionError"
        assert len(node.body[0].exc.args) == 1 and ast.literal_eval(node.body[0].exc.args[0]) == "session execution is not admitted"


def _assert_constructor(node: ast.FunctionDef) -> None:
    assert node.name == "__init__"
    assert tuple(argument.arg for argument in node.args.posonlyargs) == ()
    assert tuple(argument.arg for argument in node.args.args) == ("self",)
    assert tuple(argument.arg for argument in node.args.kwonlyargs) == ()
    assert not node.args.defaults and not node.args.kw_defaults
    assert node.args.vararg is None and node.args.kwarg is None and not node.decorator_list
    assert ast.unparse(node.returns) == "None"
    assert len(node.body) == 1 and isinstance(node.body[0], ast.Raise)
    assert isinstance(node.body[0].exc, ast.Call)
    assert isinstance(node.body[0].exc.func, ast.Name) and node.body[0].exc.func.id == "SessionError"
    assert len(node.body[0].exc.args) == 1 and ast.literal_eval(node.body[0].exc.args[0]) == "session execution is not admitted"


def _assert_bounded_preflight(functions: dict[str, ast.FunctionDef]) -> None:
    """Require each bounded walker to reject before it expands pending work."""
    branch_specs = {
        "_freeze_session_data": (
            ("item_type is dict", True),
            ("item_type is list", False),
            ("item_type is tuple", True),
        ),
        "_materialize_exact_builtins": (
            ("item_type is dict or item_type is types.MappingProxyType", True),
            ("item_type is list or item_type is tuple", False),
        ),
    }

    def first_index(statements: list[ast.stmt], condition: str) -> int:
        matches = [
            index
            for index, statement in enumerate(statements)
            if isinstance(statement, ast.If) and ast.unparse(statement.test) == condition
        ]
        assert len(matches) == 1
        return matches[0]

    def has_pending_append(statement: ast.stmt) -> bool:
        return any(
            isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Attribute)
            and isinstance(candidate.func.value, ast.Name)
            and candidate.func.value.id == "pending"
            and candidate.func.attr == "append"
            for candidate in ast.walk(statement)
        )

    depth_guards = {
        "_freeze_session_data": "depth == MAX_SESSION_DEPTH and (item_type is dict or item_type is list or item_type is tuple)",
        "_materialize_exact_builtins": "depth == MAX_SESSION_DEPTH and (item_type is dict or item_type is list or item_type is tuple or (item_type is types.MappingProxyType))",
    }
    for name, branches in branch_specs.items():
        node = functions[name]
        loops = [
            candidate
            for candidate in ast.walk(node)
            if isinstance(candidate, ast.While) and isinstance(candidate.test, ast.Name) and candidate.test.id == "pending"
        ]
        assert len(loops) == 1
        loop = loops[0]
        item_type_index = next(
            index
            for index, statement in enumerate(loop.body)
            if isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "item_type"
            and ast.unparse(statement.value) == "type(item)"
        )
        depth_guard_index = next(
            index
            for index, statement in enumerate(loop.body)
            if isinstance(statement, ast.If) and ast.unparse(statement.test) == depth_guards[name]
        )
        node_count_index = next(
            index
            for index, statement in enumerate(loop.body)
            if isinstance(statement, ast.AugAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "node_count"
            and isinstance(statement.op, ast.Add)
        )
        assert item_type_index < depth_guard_index < node_count_index
        string_branch = next(
            candidate
            for candidate in ast.walk(node)
            if isinstance(candidate, ast.If) and ast.unparse(candidate.test) == "item_type is str"
        )
        string_limit = first_index(string_branch.body, "len(item) > MAX_SESSION_STRING_BYTES")
        string_encode = next(
            index
            for index, statement in enumerate(string_branch.body)
            if any(
                isinstance(candidate, ast.Call)
                and isinstance(candidate.func, ast.Attribute)
                and isinstance(candidate.func.value, ast.Name)
                and candidate.func.value.id == "item"
                and candidate.func.attr == "encode"
                for candidate in ast.walk(statement)
            )
        )
        assert string_limit < string_encode
        for branch_test, expects_key in branches:
            branch = next(
                candidate
                for candidate in ast.walk(node)
                if isinstance(candidate, ast.If) and ast.unparse(candidate.test) == branch_test
            )
            node_limit = first_index(branch.body, "len(item) > MAX_SESSION_NODES - node_count - len(pending)")
            byte_limit = first_index(branch.body, "byte_count + 2 + len(item) > MAX_SESSION_CONFIG_BYTES")
            expansions = [
                (index, statement)
                for index, statement in enumerate(branch.body)
                if isinstance(statement, ast.For) and has_pending_append(statement)
            ]
            assert len(expansions) == 1
            expansion_index, expansion = expansions[0]
            assert node_limit < expansion_index and byte_limit < expansion_index
            if expects_key:
                key_limit = first_index(expansion.body, "len(key) > MAX_SESSION_STRING_BYTES")
                key_byte_limit = first_index(expansion.body, "byte_count + len(key) > MAX_SESSION_CONFIG_BYTES")
                key_encode = next(
                    index
                    for index, statement in enumerate(expansion.body)
                    if any(
                        isinstance(candidate, ast.Call)
                        and isinstance(candidate.func, ast.Attribute)
                        and isinstance(candidate.func.value, ast.Name)
                        and candidate.func.value.id == "key"
                        and candidate.func.attr == "encode"
                        for candidate in ast.walk(statement)
                    )
                )
                pending_append = next(index for index, statement in enumerate(expansion.body) if has_pending_append(statement))
                assert key_limit < key_encode
                assert key_limit < pending_append and key_byte_limit < pending_append


def _assert_external_call_arguments(functions: dict[str, ast.FunctionDef]) -> None:
    """Pin data-only arguments so an allowed callee cannot become a capability seam."""
    def external_call(node: ast.FunctionDef, target: str) -> ast.Call:
        matches = [candidate for candidate in ast.walk(node) if isinstance(candidate, ast.Call) and _attribute_name(candidate.func) == target]
        assert len(matches) == 1
        return matches[0]

    def keyword_values(call: ast.Call) -> dict[str, ast.expr]:
        assert all(keyword.arg is not None for keyword in call.keywords)
        return {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg is not None}

    freeze = external_call(functions["_freeze_session_data"], "types.MappingProxyType")
    assert len(freeze.args) == 1 and isinstance(freeze.args[0], ast.DictComp) and not freeze.keywords

    canonical = external_call(functions["_canonical_session_json_bytes"], "json.dumps")
    assert tuple(ast.unparse(argument) for argument in canonical.args) == ("materialized",)
    assert {key: ast.literal_eval(value) for key, value in keyword_values(canonical).items()} == {
        "sort_keys": True,
        "separators": (",", ":"),
        "ensure_ascii": True,
        "allow_nan": False,
    }

    digest = external_call(functions["_session_config_digest"], "hashlib.sha256")
    assert tuple(ast.unparse(argument) for argument in digest.args) == ("canonical",) and not digest.keywords

    parser = external_call(functions["_parse_session_config_bytes"], "json.loads")
    assert tuple(ast.unparse(argument) for argument in parser.args) == ("config_bytes.decode('ascii')",)
    parser_keywords = keyword_values(parser)
    assert set(parser_keywords) == {"object_pairs_hook"}
    assert isinstance(parser_keywords["object_pairs_hook"], ast.Name) and parser_keywords["object_pairs_hook"].id == "tuple"

    base_constructor = external_call(functions["_base_config_projection"], "attester.AttesterConfig")
    assert tuple(ast.unparse(argument) for argument in base_constructor.args) == ("projection",) and not base_constructor.keywords
    base_validator = external_call(functions["_base_config_projection"], "attester.validate_config")
    assert tuple(ast.unparse(argument) for argument in base_validator.args) == ("attester.AttesterConfig(projection)",) and not base_validator.keywords

    receipt = functions["_validate_and_encode_receipt"]
    for target in ("receipt_schema.validate_pre_payload", "receipt_schema.validate_post_payload"):
        validator = external_call(receipt, target)
        assert tuple(ast.unparse(argument) for argument in validator.args) == ("payload", "sequence") and not validator.keywords
    encoder = external_call(receipt, "protocol.encode_frame")
    assert tuple(ast.unparse(argument) for argument in encoder.args) == ("frame_type", "sequence", "payload") and not encoder.keywords


def assert_b4b_source_contract() -> None:
    """Check source shape without importing the target module."""
    if sys.flags.optimize:
        raise AssertionError("Task 0B4b static contract must not run with Python optimization")
    source = SESSION_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SESSION_PATH))
    import_nodes = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    imports = {ast.unparse(node) for node in import_nodes}
    assert imports == EXPECTED_IMPORTS
    assert len(import_nodes) == len(imports)
    assignments = _assignment_map(tree)
    assert set(assignments) == set(EXPECTED_ASSIGNMENTS)
    for name, expected in EXPECTED_ASSIGNMENTS.items():
        assert ast.literal_eval(assignments[name]) == expected
    allowed_top_level = (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign, ast.ClassDef, ast.FunctionDef)
    assert all(isinstance(node, allowed_top_level) for node in tree.body)
    expressions = [node for node in tree.body if isinstance(node, ast.Expr)]
    assert len(expressions) == 1 and isinstance(expressions[0].value, ast.Constant)
    assert type(expressions[0].value.value) is str

    function_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    functions = {node.name: node for node in function_nodes}
    assert set(functions) == EXPECTED_FUNCTIONS
    assert len(function_nodes) == len(functions)
    assert not any(isinstance(node, ast.AsyncFunctionDef) for node in tree.body)
    for name, node in functions.items():
        _assert_function_signature(name, node)
        _assert_function_body(name, node)
    _assert_bounded_preflight(functions)
    _assert_external_call_arguments(functions)

    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    classes = {node.name: node for node in class_nodes}
    assert set(classes) == EXPECTED_CLASSES
    assert len(class_nodes) == len(classes)
    session_error = classes["SessionError"]
    assert [ast.unparse(base) for base in session_error.bases] == ["RuntimeError"]
    assert not session_error.keywords and not session_error.decorator_list
    assert len(session_error.body) == 1 and isinstance(session_error.body[0], ast.Pass)
    expected_fields = {
        "SessionConfig": (("data",), ("Mapping[str, object]",)),
        "SessionResult": (("child_pid", "child_returncode", "pre_monotonic_ns", "post_monotonic_ns"), ("int", "int", "int", "int")),
    }
    for class_name, (field_names, field_annotations) in expected_fields.items():
        class_node = classes[class_name]
        assert not class_node.bases and not class_node.keywords
        assert len(class_node.decorator_list) == 1
        decorator = class_node.decorator_list[0]
        assert isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == "dataclasses.dataclass"
        assert not decorator.args
        assert {keyword.arg: ast.literal_eval(keyword.value) for keyword in decorator.keywords} == {"frozen": True, "init": False}
        fields = [node for node in class_node.body if isinstance(node, ast.AnnAssign)]
        assert tuple(node.target.id for node in fields) == field_names
        assert tuple(ast.unparse(node.annotation) for node in fields) == field_annotations
        assert all(node.value is None for node in fields)
        constructors = [node for node in class_node.body if isinstance(node, ast.FunctionDef)]
        assert len(constructors) == 1 and len(class_node.body) == len(fields) + 1
        _assert_constructor(constructors[0])


class Task0B4bStaticContractTests(unittest.TestCase):
    def test_preimport_source_contract(self) -> None:
        if sys.flags.optimize:
            self.fail("Task 0B4b static contract must not run with Python optimization")
        assert_b4b_source_contract()


if __name__ == "__main__":
    unittest.main()
