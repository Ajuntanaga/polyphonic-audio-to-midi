"""Task 0B1 source/contract checks that never import an authored module."""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import unittest

import jsonschema


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = {
    "constructor": ROOT / "tools/reaper_v4_closure_constructor.py",
    "receipt": ROOT / "tools/reaper_v4_receipt_schema.py",
    "measurements": ROOT / "tools/reaper_v4_measurements.py",
    "runner": ROOT / "tools/reaper_v4_child_runner.py",
}
SCHEMAS = {
    "bundle": ROOT / "docs/superpowers/schemas/v4-closure-input-bundle.schema.json",
    "receipt": ROOT / "docs/superpowers/schemas/v4-receipt-exchange.schema.json",
}
FIXTURES = {
    "blocked": ROOT / "tests/fixtures/reaper_v4_closure/blocked-input-bundle.json",
    "receipt": ROOT / "tests/fixtures/reaper_v4_closure/receipt-exchange.json",
}
ARTIFACTS = {
    "bundle_schema": SCHEMAS["bundle"],
    "receipt_schema": SCHEMAS["receipt"],
    "blocked_fixture": FIXTURES["blocked"],
    "receipt_fixture": FIXTURES["receipt"],
}
TASK0A_HASHES = {
    "tools/reaper_v4_protocol.py": "82afbe01cf11f083481db26cc10927965cd1341b4b75367ceda25de0d82b8331",
    "tools/reaper_v4_attester.py": "1b6cae926421615fb6f42fe1ee40d4a09d1dd862296a90c38b8371ee42377891",
    "tests/test_reaper_v4_protocol.py": "809a0b71c65e1e24e5c3f03a247408cec9dfec619d559acbddd1ad5ef0233192",
}
TASK0B1_SOURCE_HASHES = {
    "constructor": "eaca2f2a26db7310fb9ad1a37e5c5b89d39857da7795cb0c57a08e796d0e0b60",
    "receipt": "ac8fb910a6bb0b06a0278cfe92e4f3e60ebe19a988048b3e11f9c320b32a6eff",
    "measurements": "834ffbf9dbfe3c061904588132ae2683ae788589128c4bc51d02b1d21f625054",
    "runner": "13f6e4f5a9139e45bbc593a79f363ccad5fc1e6ca283cfc7379b04f50d657b5c",
}
TASK0B1_ARTIFACT_HASHES = {
    "bundle_schema": "1fa7ee4032921b959d855a0c3e91804515fb253b99df96396eca67a4603ac1f8",
    "receipt_schema": "710adb3ecb257edf96588e67f69bd810bf1edc564cc53e475d79b50af1dc89e9",
    "blocked_fixture": "a71aa540857a06bced4237be5bfb08ecfb834aa333ffd8b1733ac73a60979229",
    "receipt_fixture": "7c8f0172949e58df66b80de3d44ad172528623b147240fd226d6e2619d40e393",
}
CATALOG_NAMES = (
    "resolver_policy",
    "startup_model",
    "module_catalog",
    "interpreter_module_registry",
    "frozen_effect_catalog",
    "elf_catalog",
    "branch_policy",
    "native_effect_catalog",
    "virtual_resource_catalog",
    "source_effect_catalog",
    "resource_policy",
)
PROVENANCE_IDENTITY_KEYS = (
    "kind",
    "raw_path",
    "mode",
    "device",
    "inode",
    "byte_size",
    "sha256",
    "version",
)
MODULE_SPECS = {
    "constructor": {
        "imports": {
            ("from", "__future__", "annotations"),
            ("import", "ast", ""),
            ("import", "dataclasses", ""),
            ("import", "enum", ""),
            ("import", "hashlib", ""),
            ("import", "json", ""),
            ("import", "os", ""),
            ("import", "stat", ""),
            ("import", "struct", ""),
            ("import", "types", ""),
            ("from", "collections.abc", "Mapping"),
        },
        "definitions": {
            "ClosureConstructionError",
            "_freeze_static_data",
            "_is_synthetic_path",
            "_normalise_frozen",
            "_canonical_json_bytes_from_frozen",
            "_sha256_frozen",
            "ClosureState",
            "ClosureInputBundle",
            "ClosureRecord",
            "canonical_json_bytes",
            "sha256_canonical",
            "load_input_bundle",
            "construct_closure",
        },
        "exports": {
            "ClosureConstructionError",
            "ClosureState",
            "ClosureInputBundle",
            "ClosureRecord",
            "canonical_json_bytes",
            "sha256_canonical",
            "load_input_bundle",
            "construct_closure",
        },
        "fields": {"ClosureInputBundle": ("bundle",), "ClosureRecord": ("record",)},
        "functions": {
            "_freeze_static_data": ("value",),
            "_is_synthetic_path": ("value",),
            "_normalise_frozen": ("item",),
            "_canonical_json_bytes_from_frozen": ("value",),
            "_sha256_frozen": ("value",),
            "canonical_json_bytes": ("value",),
            "sha256_canonical": ("value",),
            "load_input_bundle": ("path",),
            "construct_closure": ("input_bundle",),
        },
        "bases": {
            "ClosureConstructionError": ("ValueError",),
            "ClosureState": ("str", "enum.Enum"),
            "ClosureInputBundle": (),
            "ClosureRecord": (),
        },
        "dataclass_options": {
            "ClosureInputBundle": {"frozen": True},
            "ClosureRecord": {"frozen": True},
        },
    },
    "receipt": {
        "imports": {
            ("from", "__future__", "annotations"),
            ("import", "dataclasses", ""),
            ("import", "enum", ""),
            ("import", "types", ""),
            ("from", "collections.abc", "Mapping"),
            ("from", "tools", "reaper_v4_protocol"),
        },
        "definitions": {
            "ReceiptSchemaError",
            "ReceiptPhase",
            "ReceiptPayload",
            "_snapshot_receipt_payload",
            "_freeze_receipt_payload",
            "_validated_receipt_payload",
            "validate_pre_payload",
            "validate_ack_bytes",
            "validate_post_payload",
            "validate_exchange",
        },
        "exports": {
            "ReceiptSchemaError",
            "ReceiptPhase",
            "ReceiptPayload",
            "ACK_BYTE",
            "PRE_KEYS",
            "POST_KEYS",
            "ATTESTATION_KEYS",
            "validate_pre_payload",
            "validate_ack_bytes",
            "validate_post_payload",
            "validate_exchange",
        },
        "fields": {"ReceiptPayload": ("phase", "sequence", "payload")},
        "functions": {
            "_freeze_receipt_payload": ("value",),
            "_snapshot_receipt_payload": ("value",),
            "_validated_receipt_payload": ("phase", "sequence", "payload"),
            "validate_pre_payload": ("payload", "sequence"),
            "validate_ack_bytes": ("ack",),
            "validate_post_payload": ("payload", "sequence"),
            "validate_exchange": ("pre", "ack", "post"),
        },
        "bases": {
            "ReceiptSchemaError": ("ValueError",),
            "ReceiptPhase": ("enum.IntEnum",),
            "ReceiptPayload": (),
        },
        "dataclass_options": {"ReceiptPayload": {"frozen": True, "init": False}},
    },
    "measurements": {
        "imports": {
            ("from", "__future__", "annotations"),
            ("import", "dataclasses", ""),
            ("import", "os", ""),
            ("import", "pathlib", ""),
            ("import", "stat", ""),
            ("import", "types", ""),
            ("from", "collections.abc", "Mapping"),
        },
        "definitions": {
            "MeasurementError",
            "_freeze_measurement_data",
            "MeasurementPlan",
            "MeasurementSnapshot",
            "collect_namespace_measurements",
        },
        "exports": {
            "MeasurementError",
            "MeasurementPlan",
            "MeasurementSnapshot",
            "MEASUREMENT_KEYS",
            "collect_namespace_measurements",
        },
        "fields": {
            "MeasurementPlan": ("root_fd", "resources", "expected"),
            "MeasurementSnapshot": ("facts", "evidence"),
        },
        "functions": {
            "_freeze_measurement_data": ("value",),
            "collect_namespace_measurements": ("plan",),
        },
        "bases": {
            "MeasurementError": ("ValueError",),
            "MeasurementPlan": (),
            "MeasurementSnapshot": (),
        },
        "dataclass_options": {
            "MeasurementPlan": {"frozen": True},
            "MeasurementSnapshot": {"frozen": True},
        },
    },
    "runner": {
        "imports": {
            ("from", "__future__", "annotations"),
            ("import", "dataclasses", ""),
            ("import", "subprocess", ""),
            ("import", "time", ""),
        },
        "definitions": {
            "ChildRunnerError",
            "ChildSpec",
            "ChildOutcome",
            "run_child",
        },
        "exports": {
            "ChildRunnerError",
            "ChildSpec",
            "ChildOutcome",
            "run_child",
        },
        "fields": {
            "ChildSpec": ("argv", "cwd", "environment", "timeout_ms"),
            "ChildOutcome": ("child_pid", "returncode", "timed_out", "elapsed_ms"),
        },
        "functions": {"run_child": ("spec",)},
        "bases": {
            "ChildRunnerError": ("ValueError",),
            "ChildSpec": (),
            "ChildOutcome": (),
        },
        "dataclass_options": {
            "ChildSpec": {"frozen": True},
            "ChildOutcome": {"frozen": True},
        },
    },
}
FORBIDDEN_CALLS = {
    "run",
    "call",
    "check_call",
    "check_output",
    "getoutput",
    "getstatusoutput",
    "vars",
    "globals",
    "locals",
    "system",
    "popen",
    "posix_spawn",
    "posix_spawnp",
    "getattr",
    "__import__",
    "eval",
    "exec",
    "compile",
    "CDLL",
    "dlopen",
}


def call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def imports(tree: ast.Module) -> set[tuple[str, str | None, str]]:
    top_level = [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    all_imports = [
        node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    if len(top_level) != len(all_imports):
        raise AssertionError("nested imports are outside the author-only source contract")
    result: list[tuple[str, str | None, str]] = []
    for node in top_level:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    raise AssertionError("module imports must be unaliased")
                result.append(("import", alias.name, ""))
        else:
            if node.level != 0 or node.module is None:
                raise AssertionError("from imports must be absolute")
            for alias in node.names:
                if alias.asname is not None:
                    raise AssertionError("from imports must be unaliased")
                result.append(("from", node.module, alias.name))
    if len(result) != len(set(result)):
        raise AssertionError("imports must be unique")
    return set(result)


def exported_names(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
                raise AssertionError("__all__ must be a literal tuple of strings")
            return set(value)
    raise AssertionError("missing literal __all__")


def dataclass_fields(
    tree: ast.Module, class_name: str, options: dict[str, bool]
) -> tuple[str, ...]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            decorators = node.decorator_list
            if len(decorators) != 1 or not isinstance(decorators[0], ast.Call):
                raise AssertionError(f"{class_name} must be a frozen dataclass")
            decorator = decorators[0]
            if not (
                isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "dataclasses"
                and decorator.func.attr == "dataclass"
                and not decorator.args
                and {
                    keyword.arg: keyword.value.value
                    for keyword in decorator.keywords
                    if isinstance(keyword.value, ast.Constant)
                }
                == options
                and len(decorator.keywords) == len(options)
            ):
                raise AssertionError(f"{class_name} must be a frozen dataclass")
            return tuple(
                member.target.id
                for member in node.body
                if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name)
            )
    raise AssertionError(f"missing dataclass {class_name}")


def subscript_key(node: ast.expr) -> str | None:
    if not (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "value"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    ):
        return None
    return node.slice.value


def static_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(static_literal(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            key is not None
            and static_literal(key)
            and static_literal(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    return False


def dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return None if parent is None else f"{parent}.{node.attr}"
    return None


def assignment_targets(node: ast.Assign | ast.AnnAssign) -> tuple[ast.expr, ...]:
    return tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)


def bit_or_names(node: ast.expr) -> tuple[str, ...] | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = bit_or_names(node.left)
        right = bit_or_names(node.right)
        return None if left is None or right is None else (*left, *right)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    ):
        return (node.attr,)
    return None


def assert_source_shape(name: str, path: pathlib.Path) -> None:
    spec = MODULE_SPECS[name]
    if not path.is_file():
        raise AssertionError(f"missing Task 0B1 source: {path.name}")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    permitted_top_level = (
        ast.Import,
        ast.ImportFrom,
        ast.Assign,
        ast.AnnAssign,
        ast.ClassDef,
        ast.FunctionDef,
        ast.Expr,
    )
    if not all(isinstance(node, permitted_top_level) for node in tree.body):
        raise AssertionError(f"{name} has an unapproved top-level form")
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Expr) and not (
            index == 0 and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        ):
            raise AssertionError(f"{name} has a top-level expression")
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if not all(isinstance(target, ast.Name) for target in assignment_targets(node)):
                raise AssertionError(f"{name} has an import-time assignment target")
            if node.value is not None and not static_literal(node.value):
                raise AssertionError(f"{name} has an import-time binding")
    for class_node in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        if class_node.keywords or tuple(dotted_name(base) for base in class_node.bases) != spec["bases"][class_node.name]:
            raise AssertionError(f"{name} has a dynamic class base or metaclass")
        if class_node.decorator_list and class_node.name not in spec["fields"]:
            raise AssertionError(f"{name} has an unapproved class decorator")
        for member in class_node.body:
            if isinstance(member, ast.FunctionDef):
                continue
            if isinstance(member, ast.Expr):
                if isinstance(member.value, ast.Constant) and isinstance(member.value.value, str):
                    continue
                raise AssertionError(f"{name} has a class-body expression")
            if isinstance(member, ast.Pass):
                continue
            if isinstance(member, (ast.Assign, ast.AnnAssign)):
                value = member.value
                if not all(isinstance(target, ast.Name) for target in assignment_targets(member)):
                    raise AssertionError(f"{name} has an executable class binding target")
                if value is not None and not static_literal(value):
                    raise AssertionError(f"{name} has an import-time class binding")
                continue
            raise AssertionError(f"{name} has an unapproved class-body form")
    expected_imports = {
        (kind, module, symbol) for kind, module, symbol in spec["imports"]
    }
    actual_imports = imports(tree)
    if actual_imports != expected_imports:
        raise AssertionError(f"{name} imports differ from the sealed contract")
    definitions = {
        node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    if definitions != spec["definitions"]:
        raise AssertionError(f"{name} definitions differ from the sealed contract")
    for function_name, arguments in spec["functions"].items():
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        actual_arguments = tuple(
            argument.arg for argument in (*function.args.posonlyargs, *function.args.args)
        )
        if (
            actual_arguments != arguments
            or function.args.vararg is not None
            or function.args.kwarg is not None
            or function.args.kwonlyargs
        ):
            raise AssertionError(f"{name}.{function_name} signature differs from the sealed contract")
    if exported_names(tree) != spec["exports"]:
        raise AssertionError(f"{name} exports differ from the sealed contract")
    for class_name, fields in spec["fields"].items():
        if dataclass_fields(tree, class_name, spec["dataclass_options"][class_name]) != fields:
            raise AssertionError(f"{class_name} fields differ from the sealed contract")
    if any(isinstance(node, ast.Name) and node.id == "__name__" for node in ast.walk(tree)):
        raise AssertionError(f"{name} has a main-path guard")
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        if function.decorator_list or function.args.defaults or function.args.kw_defaults:
            raise AssertionError(f"{name} has a function decorator/default")
    popen_calls: list[ast.Call] = []
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        called = call_name(call)
        if (
            isinstance(call.func, ast.Subscript)
            or called in FORBIDDEN_CALLS
            or (called and called.startswith(("spawn", "fork", "exec")))
        ):
            raise AssertionError(f"{name} contains forbidden call {called}")
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "subprocess"
            and call.func.attr == "Popen"
        ):
            popen_calls.append(call)
    if name != "runner" and popen_calls:
        raise AssertionError(f"{name} contains a process call")
    if name == "measurements":
        measurement_freezer = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_freeze_measurement_data"
        )
        measurement_freezer_source = ast.get_source_segment(
            path.read_text(encoding="utf-8"), measurement_freezer
        )
        if (
            measurement_freezer_source is None
            or "type(item) is dict" not in measurement_freezer_source
            or "type(item) is list" not in measurement_freezer_source
            or "type(item) is tuple" not in measurement_freezer_source
            or "depth > 32" not in measurement_freezer_source
            or "remaining = [512]" not in measurement_freezer_source
            or "if len(snapshot) + 1 > remaining[0]" not in measurement_freezer_source
            or "measurement data must not contain cycles" not in measurement_freezer_source
            or "type(self.resources) is not tuple" not in path.read_text(encoding="utf-8")
            or "_freeze_measurement_data(self.resources)" not in path.read_text(encoding="utf-8")
            or 'object.__setattr__(self, "resources", resources)' not in path.read_text(encoding="utf-8")
            or "_freeze_measurement_data(self.expected)" not in path.read_text(encoding="utf-8")
            or "_freeze_measurement_data(self.facts)" not in path.read_text(encoding="utf-8")
            or "_freeze_measurement_data(self.evidence)" not in path.read_text(encoding="utf-8")
        ):
            raise AssertionError("measurement snapshots must be bounded and immutable before use")
        open_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "open"
        ]
        if len(open_calls) != 1 or len(open_calls[0].args) != 2:
            raise AssertionError("measurement collector must contain one fixed os.open call")
        flags = bit_or_names(open_calls[0].args[1])
        if flags is None or set(flags) != {"O_PATH", "O_NOFOLLOW", "O_CLOEXEC"} or len(flags) != 3:
            raise AssertionError("measurement open flags must be exactly no-follow metadata-only flags")
        if not (
            len(open_calls[0].keywords) == 1
            and open_calls[0].keywords[0].arg == "dir_fd"
            and isinstance(open_calls[0].keywords[0].value, ast.Attribute)
            and isinstance(open_calls[0].keywords[0].value.value, ast.Name)
            and open_calls[0].keywords[0].value.value.id == "plan"
            and open_calls[0].keywords[0].value.attr == "root_fd"
        ):
            raise AssertionError("measurement open must remain descriptor-rooted")
    if name == "constructor":
        constructor = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "construct_closure"
        )
        if any(
            (
                isinstance(node, ast.Attribute)
                and node.attr == "COMPLETE_FIXTURE_CANDIDATE"
            )
            or (
                isinstance(node, ast.Constant)
                and node.value == "COMPLETE_FIXTURE_CANDIDATE"
            )
            for node in ast.walk(constructor)
        ):
            raise AssertionError("Task 0B1 constructor must remain unconditionally fail-closed")
        closure_record_source = ast.get_source_segment(
            path.read_text(encoding="utf-8"),
            next(
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "ClosureRecord"
            ),
        )
        input_bundle_source = ast.get_source_segment(
            path.read_text(encoding="utf-8"),
            next(
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "ClosureInputBundle"
            ),
        )
        canonical_source = ast.get_source_segment(
            path.read_text(encoding="utf-8"),
            next(
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "canonical_json_bytes"
            ),
        )
        frozen_canonical_source = ast.get_source_segment(
            path.read_text(encoding="utf-8"),
            next(
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "_canonical_json_bytes_from_frozen"
            ),
        )
        if (
            closure_record_source is None
            or input_bundle_source is None
            or canonical_source is None
            or frozen_canonical_source is None
            or "set(value) != set(RECORD_KEYS)" not in closure_record_source
            or 'type(value["closure_state"]) is not str' not in closure_record_source
            or 'value["closure_state"] != ClosureState.BLOCKED_UNRESOLVED.value' not in closure_record_source
            or 'or value["nodes"]' not in closure_record_source
            or 'len(value["unresolved"]) != 1' not in closure_record_source
            or "closure record digest is invalid" not in closure_record_source
            or 'type(bundle["schema"]) is not int' not in path.read_text(encoding="utf-8")
            or 'type(catalog["schema"]) is not int' not in path.read_text(encoding="utf-8")
            or 'type(catalog["kind"]) is not str' not in path.read_text(encoding="utf-8")
            or "root_identifiers" not in closure_record_source
            or "root_modules" not in closure_record_source
            or "RECORD_CATALOG_DIGEST_KEYS" not in closure_record_source
            or "expected_input_bundle_digest = _sha256_frozen" not in closure_record_source
            or 'value["input_bundle_digest"] != expected_input_bundle_digest' not in closure_record_source
            or "_freeze_static_data" not in closure_record_source
            or "_is_synthetic_path" not in closure_record_source
            or "value = _freeze_static_data(self.record)" not in closure_record_source
            or "MAX_STATIC_DEPTH" not in path.read_text(encoding="utf-8")
            or "MAX_STATIC_INPUT_BYTES" not in path.read_text(encoding="utf-8")
            or "MAX_STATIC_STRING_BYTES" not in path.read_text(encoding="utf-8")
            or "MAX_STATIC_INTEGER_BITS" not in path.read_text(encoding="utf-8")
            or "MAX_CANONICAL_JSON_BYTES" not in path.read_text(encoding="utf-8")
            or "REQUIRED_ANALYSIS_ROOTS" not in path.read_text(encoding="utf-8")
            or "IDENTITY_KEYS" not in path.read_text(encoding="utf-8")
            or "def _is_synthetic_path" not in path.read_text(encoding="utf-8")
            or 'part not in ("", ".", "..")' not in path.read_text(encoding="utf-8")
            or '_is_synthetic_path(item["raw_path"])' not in closure_record_source
            or '_is_synthetic_path(identity["raw_path"])' not in path.read_text(encoding="utf-8")
            or "if isinstance(item, Mapping):" not in path.read_text(encoding="utf-8")
            or "static data mappings must have exact built-in containers" not in path.read_text(encoding="utf-8")
            or "type(item) is not dict" not in path.read_text(encoding="utf-8")
            or "static data sequences must have exact built-in containers" not in path.read_text(encoding="utf-8")
            or "_freeze_static_data(self.bundle)" not in input_bundle_source
            or "return _canonical_json_bytes_from_frozen(_freeze_static_data(value))" not in canonical_source
            or "len(encoded) > MAX_CANONICAL_JSON_BYTES" not in frozen_canonical_source
            or "_canonical_json_bytes_from_frozen" not in path.read_text(encoding="utf-8")
            or "_sha256_frozen" not in closure_record_source
            or "type(item) in (str, int, bool)" not in path.read_text(encoding="utf-8")
            or "except (TypeError, UnicodeEncodeError, ValueError)" not in path.read_text(encoding="utf-8")
        ):
            raise AssertionError("ClosureRecord must refuse direct incomplete or candidate records")
    if name == "runner":
        runner_source = path.read_text(encoding="utf-8")
        if (
            "type(spec) is not ChildSpec" not in runner_source
            or "argv = spec.argv" not in runner_source
            or "cwd = spec.cwd" not in runner_source
            or "environment_entries = spec.environment" not in runner_source
            or "timeout_ms = spec.timeout_ms" not in runner_source
            or "type(argv) is not tuple" not in runner_source
            or "type(environment_entries) is not tuple" not in runner_source
            or "process = subprocess.Popen(\n            argv," not in runner_source
            or "cwd=cwd," not in runner_source
            or "returncode = process.wait(timeout=timeout_ms / 1000)" not in runner_source
        ):
            raise AssertionError("runner must bind one exact ChildSpec snapshot before launch")
        if len(popen_calls) != 1:
            raise AssertionError("runner must contain exactly one subprocess.Popen call")
        popen = popen_calls[0]
        owner = next(
            (
                function
                for function in tree.body
                if isinstance(function, ast.FunctionDef)
                and function.name == "run_child"
                and popen in ast.walk(function)
            ),
            None,
        )
        if owner is None:
            raise AssertionError("subprocess.Popen must be inside run_child")
        subprocess_attributes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "subprocess"
        ]
        if any(
            attribute.attr not in {"Popen", "DEVNULL", "SubprocessError", "TimeoutExpired"}
            for attribute in subprocess_attributes
        ) or any(
            attribute.attr == "Popen"
            and not any(call.func is attribute for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)))
            for attribute in subprocess_attributes
        ):
            raise AssertionError("runner must not alias or dynamically derive a launch primitive")
        if sum(attribute.attr == "Popen" for attribute in subprocess_attributes) != 1:
            raise AssertionError("runner must contain one direct Popen attribute reference")
        for assignment in (
            node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
        ):
            value = assignment.value
            if value is not None and not isinstance(value, ast.Call) and any(
                isinstance(node, ast.Name) and node.id == "subprocess"
                for node in ast.walk(value)
            ):
                raise AssertionError("runner must not alias subprocess")
        keywords = {keyword.arg: keyword.value for keyword in popen.keywords}
        if set(keywords) != {"cwd", "env", "shell", "stdin", "stdout", "stderr", "close_fds", "pass_fds"}:
            raise AssertionError("runner Popen keywords differ from the sealed contract")
        for key in ("shell", "close_fds"):
            if not (isinstance(keywords[key], ast.Constant) and keywords[key].value is (key == "close_fds")):
                raise AssertionError(f"runner Popen {key} is unsafe")
        if not (
            isinstance(keywords["pass_fds"], ast.Tuple) and not keywords["pass_fds"].elts
        ):
            raise AssertionError("runner Popen must have empty pass_fds")
        for key in ("stdin", "stdout", "stderr"):
            value = keywords[key]
            if not (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "subprocess"
                and value.attr == "DEVNULL"
            ):
                raise AssertionError(f"runner Popen {key} is not DEVNULL")
        waits = [
            call
            for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "wait"
        ]
        if not waits or any(
            not any(keyword.arg == "timeout" for keyword in call.keywords)
            for call in waits
        ):
            raise AssertionError("runner cleanup waits must remain bounded")
        base_exception_handlers = [
            handler
            for node in owner.body
            if isinstance(node, ast.Try)
            for handler in node.handlers
            if isinstance(handler.type, ast.Name) and handler.type.id == "BaseException"
        ]
        if len(base_exception_handlers) != 1:
            raise AssertionError("runner must catch every BaseException after launch")
        stop_and_reap = next(
            (
                function
                for function in ast.walk(owner)
                if isinstance(function, ast.FunctionDef) and function.name == "stop_and_reap"
            ),
            None,
        )
        if stop_and_reap is None or not any(
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_"
            and isinstance(node.iter, ast.Call)
            and call_name(node.iter) == "range"
            and len(node.iter.args) == 1
            and isinstance(node.iter.args[0], ast.Constant)
            and node.iter.args[0].value == 2
            for node in ast.walk(stop_and_reap)
        ):
            raise AssertionError("runner cleanup must retry bounded kill/reap attempts")
        helper_base_exception_handlers = [
            handler
            for handler in ast.walk(stop_and_reap)
            if isinstance(handler, ast.ExceptHandler)
            and isinstance(handler.type, ast.Name)
            and handler.type.id == "BaseException"
        ]
        if len(helper_base_exception_handlers) != 2:
            raise AssertionError("runner cleanup must retain interruption-safe kill and wait handlers")
        cleanup_loops = [node for node in stop_and_reap.body if isinstance(node, ast.For)]
        if len(cleanup_loops) != 1 or len(cleanup_loops[0].body) != 2:
            raise AssertionError("runner cleanup attempt must have a fixed kill-then-wait shape")
        kill_try, wait_try = cleanup_loops[0].body
        if not isinstance(kill_try, ast.Try) or not isinstance(wait_try, ast.Try):
            raise AssertionError("runner cleanup attempt must guard both kill and wait")
        if not any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "process"
            and call.func.attr == "kill"
            for call in ast.walk(kill_try)
        ) or not any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "process"
            and call.func.attr == "wait"
            and any(
                keyword.arg == "timeout"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == 1
                for keyword in call.keywords
            )
            for call in ast.walk(wait_try)
        ):
            raise AssertionError("runner cleanup must kill then bounded-wait in every attempt")
        if any(
            isinstance(node, (ast.Continue, ast.Raise, ast.Return))
            for handler in kill_try.handlers
            for node in ast.walk(handler)
        ):
            raise AssertionError("runner cleanup must reach wait after every kill failure")
        if not any(
            isinstance(node, ast.Nonlocal) and node.names == ["cleanup_started"]
            for node in ast.walk(stop_and_reap)
        ):
            raise AssertionError("runner cleanup must retain the one-time cleanup guard")
        if not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "stop_and_reap"
            for node in ast.walk(base_exception_handlers[0])
        ):
            raise AssertionError("runner BaseException path must use the bounded cleanup helper")
        outer_handler_source = ast.get_source_segment(
            path.read_text(encoding="utf-8"), base_exception_handlers[0]
        )
        if outer_handler_source is None or "if not cleanup_started:" not in outer_handler_source:
            raise AssertionError("runner BaseException path must prevent repeated cleanup attempts")
        if "except UnicodeEncodeError" not in path.read_text(encoding="utf-8"):
            raise AssertionError("runner must refuse malformed Unicode before launch")
    if name == "measurements" and ".encode(" in path.read_text(encoding="utf-8"):
        raise AssertionError("measurement resources must reject malformed Unicode before byte conversion")


class Task0B1StaticContractTests(unittest.TestCase):
    def test_static_gate_walks_nested_imports_and_rejects_impure_bindings(self):
        nested_import = ast.parse("def delayed():\n    import socket\n")
        with self.assertRaises(AssertionError):
            imports(nested_import)
        with self.assertRaises(AssertionError):
            imports(ast.parse("import socket\nimport socket\n"))
        with self.assertRaises(AssertionError):
            imports(ast.parse("import socket as net\n"))
        with self.assertRaises(AssertionError):
            dataclass_fields(
                ast.parse(
                    "@dataclasses.dataclass(effect(), frozen=True)\n"
                    "class Example:\n    field: str\n"
                ),
                "Example",
                {"frozen": True},
            )
        self.assertFalse(static_literal(ast.parse("os.environ['HOME']").body[0].value))
        self.assertFalse(static_literal(ast.parse("object.__dict__").body[0].value))

    def test_task0a_component_hashes_remain_sealed(self):
        for relative_path, expected in TASK0A_HASHES.items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(), expected
            )

    def test_task0b1_authored_source_hashes_are_sealed(self):
        for name, expected in TASK0B1_SOURCE_HASHES.items():
            self.assertEqual(
                hashlib.sha256(SOURCES[name].read_bytes()).hexdigest(), expected
            )

    def test_task0b1_schema_and_fixture_hashes_are_sealed(self):
        self.assertEqual(set(TASK0B1_ARTIFACT_HASHES), set(ARTIFACTS))
        for name, expected in TASK0B1_ARTIFACT_HASHES.items():
            self.assertEqual(
                hashlib.sha256(ARTIFACTS[name].read_bytes()).hexdigest(), expected
            )

    def test_task0b1_source_modules_are_noninvoking_and_exact(self):
        for name, path in SOURCES.items():
            assert_source_shape(name, path)

    def test_catalog_vector_is_inert_and_declares_the_session_block(self):
        for path in (*SCHEMAS.values(), *FIXTURES.values()):
            self.assertTrue(path.is_file(), f"missing Task 0B1 contract artifact: {path.name}")
        bundle_schema = json.loads(SCHEMAS["bundle"].read_text(encoding="utf-8"))
        receipt_schema = json.loads(SCHEMAS["receipt"].read_text(encoding="utf-8"))
        for schema in (bundle_schema, receipt_schema):
            self.assertEqual(schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(schema.get("additionalProperties", True))
        self.assertEqual(
            set(bundle_schema["required"]),
            {
                "schema",
                "method_version",
                "method_spec_sha256",
                "constructor_identity",
                "parser_identity",
                "target_platform",
                "task0a_source_component_digest",
                "analysis_roots",
                "runtime_roots",
                "catalogs",
                "budgets",
            },
        )
        analysis_roots_schema = bundle_schema["properties"]["analysis_roots"]
        self.assertEqual(analysis_roots_schema["minItems"], 4)
        self.assertEqual(analysis_roots_schema["maxItems"], 4)
        self.assertFalse(analysis_roots_schema["items"])
        self.assertEqual(
            [item["$ref"] for item in analysis_roots_schema["prefixItems"]],
            [
                "#/$defs/task0a_protocol_root",
                "#/$defs/task0b1_receipt_root",
                "#/$defs/task0b1_measurement_root",
                "#/$defs/task0b1_runner_root",
            ],
        )
        self.assertEqual(bundle_schema["properties"]["runtime_roots"]["maxItems"], 0)
        provenance_schema = bundle_schema["$defs"]["identity"]
        self.assertEqual(tuple(provenance_schema["required"]), PROVENANCE_IDENTITY_KEYS)
        self.assertEqual(set(provenance_schema["properties"]), set(PROVENANCE_IDENTITY_KEYS))
        catalog_schema = bundle_schema["$defs"]["catalogs"]
        self.assertEqual(tuple(catalog_schema["required"]), CATALOG_NAMES)
        for name in CATALOG_NAMES:
            catalog = catalog_schema["properties"][name]
            self.assertEqual(catalog["allOf"][1]["properties"]["kind"]["const"], name)
            self.assertEqual(
                bundle_schema["$defs"]["empty_catalog"]["properties"]["records"]["maxItems"],
                0,
            )
        vector = json.loads(FIXTURES["blocked"].read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(bundle_schema)
        validator.validate(vector["input_bundle"])
        self.assertEqual(
            set(vector), {"schema", "case", "input_bundle", "expected_outcome_projection"}
        )
        self.assertEqual(vector["case"], "runtime-session-entrypoint-unresolved")
        bundle = vector["input_bundle"]
        self.assertEqual(bundle["runtime_roots"], [])
        for identity_name in ("constructor_identity", "parser_identity"):
            identity = bundle[identity_name]
            self.assertEqual(tuple(identity), PROVENANCE_IDENTITY_KEYS)
            self.assertTrue(identity["raw_path"].startswith("/synthetic/"))
            self.assertIsInstance(identity["mode"], int)
            self.assertGreater(identity["device"], 0)
            self.assertGreater(identity["inode"], 0)
            self.assertGreaterEqual(identity["byte_size"], 0)
        self.assertEqual(
            [(root["module"], root["role"]) for root in bundle["analysis_roots"]],
            [
                ("tools.reaper_v4_protocol", "sealed_component"),
                ("tools.reaper_v4_receipt_schema", "runtime_library"),
                ("tools.reaper_v4_measurements", "runtime_library"),
                ("tools.reaper_v4_child_runner", "runtime_library"),
            ],
        )
        constructor_tree = ast.parse(SOURCES["constructor"].read_text(encoding="utf-8"))
        constructor_literals = {
            target.id: ast.literal_eval(node.value)
            for node in constructor_tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance((target := node.targets[0]), ast.Name)
            and target.id
            in {
                "REQUIRED_ANALYSIS_ROOTS",
                "IDENTITY_KEYS",
                "MAX_STATIC_NODES",
                "MAX_STATIC_DEPTH",
                "MAX_STATIC_INPUT_BYTES",
                "MAX_STATIC_STRING_BYTES",
                "MAX_STATIC_INTEGER_BITS",
                "MAX_CANONICAL_JSON_BYTES",
                "TASK0B1_RUNTIME_ROOTS_MAX",
            }
        }
        self.assertEqual(
            constructor_literals["REQUIRED_ANALYSIS_ROOTS"],
            (
                ("tools.reaper_v4_protocol", "sealed_component"),
                ("tools.reaper_v4_receipt_schema", "runtime_library"),
                ("tools.reaper_v4_measurements", "runtime_library"),
                ("tools.reaper_v4_child_runner", "runtime_library"),
            ),
        )
        self.assertEqual(
            constructor_literals["IDENTITY_KEYS"], PROVENANCE_IDENTITY_KEYS
        )
        self.assertEqual(
            {
                key: constructor_literals[key]
                for key in (
                    "MAX_STATIC_NODES",
                    "MAX_STATIC_DEPTH",
                    "MAX_STATIC_INPUT_BYTES",
                    "MAX_STATIC_STRING_BYTES",
                    "MAX_STATIC_INTEGER_BITS",
                    "MAX_CANONICAL_JSON_BYTES",
                    "TASK0B1_RUNTIME_ROOTS_MAX",
                )
            },
            {
                "MAX_STATIC_NODES": 4096,
                "MAX_STATIC_DEPTH": 64,
                "MAX_STATIC_INPUT_BYTES": 6144,
                "MAX_STATIC_STRING_BYTES": 1024,
                "MAX_STATIC_INTEGER_BITS": 256,
                "MAX_CANONICAL_JSON_BYTES": 65536,
                "TASK0B1_RUNTIME_ROOTS_MAX": 0,
            },
        )
        self.assertEqual(tuple(bundle["catalogs"]), CATALOG_NAMES)
        projection = vector["expected_outcome_projection"]
        self.assertEqual(projection["closure_state"], "BLOCKED_UNRESOLVED")
        self.assertEqual(
            projection["unresolved"],
            [{
                "code": "runtime_session_entrypoint_unresolved",
                "role": "same_namespace_pre_ack_child_post_owner",
            }],
        )
        invalid = json.loads(json.dumps(vector["input_bundle"]))
        invalid["constructor_identity"]["kind"] = "a" * 63 + "é"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(invalid)
        invalid = json.loads(json.dumps(vector["input_bundle"]))
        invalid["target_platform"]["architecture"] = "a" * 127 + "é"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(invalid)
        invalid = json.loads(json.dumps(vector["input_bundle"]))
        invalid["constructor_identity"]["raw_path"] = "/synthetic/../../home/user/real.py"
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(invalid)

    def test_receipt_vector_uses_the_one_byte_ack_and_matching_identity(self):
        vector = json.loads(FIXTURES["receipt"].read_text(encoding="utf-8"))
        receipt_schema = json.loads(SCHEMAS["receipt"].read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(receipt_schema)
        validator.validate(vector)
        self.assertEqual(set(vector), {"schema", "pre", "ack_hex", "post"})
        self.assertEqual(vector["ack_hex"], "06")
        self.assertEqual(
            vector["pre"]["row"], {"sample_rate_hz": 44100, "block_size": 32}
        )
        self.assertEqual(vector["pre"]["row"], vector["post"]["row"])
        for key in ("schema", "namespace", "nonce", "config_sha256", "inputs"):
            self.assertEqual(vector["pre"][key], vector["post"][key])
        preimage = {
            key: value
            for key, value in vector["pre"].items()
            if key in {"schema", "namespace", "nonce", "inputs"}
        }
        digest = hashlib.sha256(
            json.dumps(
                preimage,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(vector["pre"]["config_sha256"], digest)
        definitions = receipt_schema["$defs"]
        self.assertEqual(definitions["pre"]["allOf"][0], {"$ref": "#/$defs/identity"})
        self.assertEqual(definitions["post"]["allOf"][0], {"$ref": "#/$defs/identity"})
        self.assertEqual(
            definitions["row"],
            {
                "type": "object",
                "properties": {
                    "sample_rate_hz": {"const": 44100},
                    "block_size": {"const": 32},
                },
                "required": ["sample_rate_hz", "block_size"],
                "additionalProperties": False,
            },
        )
        self.assertFalse(definitions["pre_attestation"].get("unevaluatedProperties", True))
        self.assertFalse(definitions["post_attestation"].get("unevaluatedProperties", True))
        receipt_tree = ast.parse(SOURCES["receipt"].read_text(encoding="utf-8"))
        receipt_source = SOURCES["receipt"].read_text(encoding="utf-8")
        receipt_literals = {
            target.id: ast.literal_eval(node.value)
            for node in receipt_tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance((target := node.targets[0]), ast.Name)
            and target.id in {
                "PRE_KEYS",
                "POST_KEYS",
                "ATTESTATION_KEYS",
                "ROW_KEYS",
                "MAX_RECEIPT_NODES",
                "MAX_RECEIPT_DEPTH",
                "MAX_RECEIPT_INPUT_BYTES",
                "MAX_RECEIPT_STRING_CHARS",
            }
        }
        self.assertEqual(receipt_literals["ROW_KEYS"], ("sample_rate_hz", "block_size"))
        self.assertEqual(
            {
                key: receipt_literals[key]
                for key in (
                    "MAX_RECEIPT_NODES",
                    "MAX_RECEIPT_DEPTH",
                    "MAX_RECEIPT_INPUT_BYTES",
                    "MAX_RECEIPT_STRING_CHARS",
                )
            },
            {
                "MAX_RECEIPT_NODES": 512,
                "MAX_RECEIPT_DEPTH": 32,
                "MAX_RECEIPT_INPUT_BYTES": 8192,
                "MAX_RECEIPT_STRING_CHARS": 256,
            },
        )
        self.assertEqual(
            set(receipt_literals["ATTESTATION_KEYS"]),
            set(definitions["common_attestation"]["properties"]),
        )
        self.assertEqual(
            set(receipt_literals["ATTESTATION_KEYS"]),
            set(definitions["common_attestation"]["required"]),
        )
        self.assertEqual(
            set(definitions["common_attestation"]["properties"]),
            set(definitions["common_attestation"]["required"]),
        )
        self.assertNotIn("private_scan_root", receipt_literals["ATTESTATION_KEYS"])
        self.assertNotIn("probe_entries", receipt_literals["ATTESTATION_KEYS"])
        identity_keys = definitions["identity"]["required"]
        self.assertEqual(set(definitions["identity"]["properties"]), set(identity_keys))
        pre_extension = definitions["pre"]["allOf"][1]
        post_extension = definitions["post"]["allOf"][1]
        self.assertEqual(
            set(receipt_literals["PRE_KEYS"]),
            set((*identity_keys, *pre_extension["required"])),
        )
        self.assertEqual(
            set(receipt_literals["POST_KEYS"]),
            set((*identity_keys, *post_extension["required"])),
        )
        self.assertEqual(set(pre_extension["properties"]), set(pre_extension["required"]))
        self.assertEqual(set(post_extension["properties"]), set(post_extension["required"]))
        post_attestation_extension = definitions["post_attestation"]["allOf"][1]
        self.assertEqual(
            set(post_attestation_extension["properties"]), {"scan_root_unchanged"}
        )
        self.assertEqual(
            set(post_attestation_extension["required"]), {"scan_root_unchanged"}
        )
        self.assertEqual(set(vector["pre"]), set(receipt_literals["PRE_KEYS"]))
        self.assertEqual(set(vector["post"]), set(receipt_literals["POST_KEYS"]))
        self.assertEqual(
            set(vector["pre"]["attestation"]), set(receipt_literals["ATTESTATION_KEYS"])
        )
        self.assertEqual(
            set(vector["post"]["attestation"]),
            set((*receipt_literals["ATTESTATION_KEYS"], "scan_root_unchanged")),
        )
        for invalid_value in ("synthetic-home\n", "synthetic-home\x00"):
            invalid = json.loads(json.dumps(vector))
            invalid["pre"]["attestation"]["home"] = invalid_value
            with self.assertRaises(jsonschema.ValidationError):
                validator.validate(invalid)
        invalid = json.loads(json.dumps(vector))
        for phase in ("pre", "post"):
            digest = next(iter(invalid[phase]["inputs"].values()))
            invalid[phase]["inputs"] = {"synthetic\n": digest}
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(invalid)
        self.assertNotIn(".encode(", receipt_source)
        receipt_calls = [call_name(call) for call in ast.walk(receipt_tree) if isinstance(call, ast.Call)]
        self.assertNotIn("isascii", receipt_calls)
        printable_range_checks = [
            node
            for node in ast.walk(receipt_tree)
            if isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Constant)
            and node.left.value == 32
            and len(node.ops) == 2
            and all(isinstance(operator, ast.LtE) for operator in node.ops)
            and len(node.comparators) == 2
            and isinstance(node.comparators[0], ast.Call)
            and call_name(node.comparators[0]) == "ord"
            and isinstance(node.comparators[1], ast.Constant)
            and node.comparators[1].value == 126
        ]
        self.assertGreaterEqual(len(printable_range_checks), 4)
        post_validator = next(
            node
            for node in receipt_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "validate_post_payload"
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Compare)
                and subscript_key(node.left) == "post_monotonic_ns"
                and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Lt)
                and len(node.comparators) == 1
                and subscript_key(node.comparators[0]) == "pre_monotonic_ns"
                for node in ast.walk(post_validator)
            ),
            "validate_post_payload must reject a regressing monotonic interval",
        )
        pre_reuse_calls = [
            node
            for node in ast.walk(post_validator)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "validate_pre_payload"
        ]
        self.assertEqual(len(pre_reuse_calls), 1)
        self.assertEqual(len(pre_reuse_calls[0].args), 2)
        self.assertIsInstance(pre_reuse_calls[0].args[1], ast.Constant)
        self.assertEqual(pre_reuse_calls[0].args[1].value, 0)
        exchange_validator = next(
            node
            for node in receipt_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "validate_exchange"
        )
        exchange_source = ast.get_source_segment(
            receipt_source, exchange_validator
        )
        self.assertIsNotNone(exchange_source)
        self.assertIn("for key in ATTESTATION_KEYS", exchange_source)
        self.assertIn(
            'pre_receipt.payload["attestation"][key] != post_receipt.payload["attestation"][key]',
            exchange_source,
        )
        for validator_name in ("validate_pre_payload", "validate_post_payload"):
            validator = next(
                node
                for node in receipt_tree.body
                if isinstance(node, ast.FunctionDef) and node.name == validator_name
            )
            validator_source = ast.get_source_segment(receipt_source, validator)
            self.assertIsNotNone(validator_source)
            for identity_member in ("schema", "namespace", "nonce", "config_sha256"):
                self.assertIn(
                    f'type(value["{identity_member}"]) is not',
                    validator_source,
                    f"{validator_name} must reject subclass-controlled {identity_member}",
                )
        payload_class = next(
            node
            for node in receipt_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ReceiptPayload"
        )
        payload_source = ast.get_source_segment(receipt_source, payload_class)
        self.assertIsNotNone(payload_source)
        self.assertIn("ReceiptPayload is validator-created", payload_source)
        self.assertIn("init=False", receipt_source)
        self.assertIn("def _validated_receipt_payload", receipt_source)
        self.assertIn("object.__new__(ReceiptPayload)", receipt_source)
        self.assertIn("def _snapshot_receipt_payload", receipt_source)
        self.assertIn("value = _snapshot_receipt_payload(payload)", receipt_source)
        snapshot_source = ast.get_source_segment(
            receipt_source,
            next(
                node
                for node in receipt_tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "_snapshot_receipt_payload"
            ),
        )
        self.assertIsNotNone(snapshot_source)
        self.assertIn("remaining_bytes = [MAX_RECEIPT_INPUT_BYTES]", snapshot_source)
        self.assertIn("if len(text) > MAX_RECEIPT_STRING_CHARS", snapshot_source)
        self.assertIn("charge(text_size(key))", snapshot_source)
        self.assertIn('ROW_KEYS = ("sample_rate_hz", "block_size")', receipt_source)
        self.assertNotIn("private_scan_root", receipt_source)
        self.assertNotIn("probe_entries", receipt_source)
        self.assertIn('"inputs", "row"', exchange_source)
