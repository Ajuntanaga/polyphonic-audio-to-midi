"""Pre-import source contract for the unimplemented Task 0B4a session helpers."""
from __future__ import annotations

import ast
import hashlib
import pathlib
import unittest


SESSION_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "reaper_v4_session.py"
B3A_SKELETON_SHA256 = "f3867a75817670916f2a450f7d7024f5c1bf1932d97fb65d34c4ca251a9f5c60"
REQUIRED_HELPERS = {
    "_freeze_session_data",
    "_canonical_session_json_bytes",
    "_session_config_digest",
    "_parse_session_config_bytes",
    "_materialize_exact_builtins",
    "_base_config_projection",
    "_validate_and_encode_receipt",
}
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
EXPECTED_FUNCTIONS = REQUIRED_HELPERS | {"load_session_config", "run_session"}
EXPECTED_CLASSES = {"SessionError", "SessionConfig", "SessionResult"}
EXPECTED_ARGUMENTS = {
    "_freeze_session_data": ("value",),
    "_canonical_session_json_bytes": ("value",),
    "_session_config_digest": ("value",),
    "_parse_session_config_bytes": ("config_bytes", "sidecar_bytes"),
    "_materialize_exact_builtins": ("value",),
    "_base_config_projection": ("config",),
    "_validate_and_encode_receipt": ("payload", "phase", "sequence"),
    "load_session_config": ("config_path", "digest_path"),
    "run_session": ("config",),
}
EXPECTED_CONSTANTS = {
    "SESSION_ENTRYPOINT_KIND": "session_entrypoint",
    "SESSION_ENTRYPOINT_ROLE": "same_namespace_pre_ack_child_post_owner",
    "SESSION_CONFIG_PATH": "/run/m3-v4/session-config.json",
    "SESSION_DIGEST_PATH": "/run/m3-v4/session-config.sha256",
}
FORBIDDEN_CALL_NAMES = {
    "__import__", "compile", "eval", "exec", "getattr", "globals", "locals",
    "open", "popen", "run", "call", "system", "vars",
}


class Task0B4aStaticContractTests(unittest.TestCase):
    def _source_bytes(self) -> bytes:
        return SESSION_PATH.read_bytes()

    def _source(self) -> str:
        return self._source_bytes().decode("utf-8")

    def _tree(self) -> ast.Module:
        return ast.parse(self._source(), filename=str(SESSION_PATH))

    def test_b3a_skeleton_bytes_remain_unchanged_during_b4a(self) -> None:
        self.assertEqual(
            hashlib.sha256(self._source_bytes()).hexdigest(),
            B3A_SKELETON_SHA256,
        )

    @unittest.expectedFailure
    def test_b4a_private_compatibility_surface_is_declared_before_import(self) -> None:
        tree = self._tree()
        definitions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = sorted(REQUIRED_HELPERS - definitions)
        self.assertEqual(
            missing,
            [],
            f"Task 0B4a private compatibility surface is missing: {', '.join(missing)}",
        )

    @unittest.expectedFailure
    def test_b4a_source_has_the_exact_pure_definition_and_import_boundary(self) -> None:
        tree = self._tree()
        imports = {
            ast.unparse(node)
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertEqual(imports, EXPECTED_IMPORTS)
        self.assertEqual(functions, EXPECTED_FUNCTIONS)
        self.assertEqual(classes, EXPECTED_CLASSES)

        function_nodes = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        for name, expected_arguments in EXPECTED_ARGUMENTS.items():
            node = function_nodes[name]
            self.assertEqual(tuple(argument.arg for argument in node.args.args), expected_arguments)
            self.assertFalse(node.args.defaults)
            self.assertFalse(node.args.kw_defaults)
            self.assertIsNone(node.args.vararg)
            self.assertIsNone(node.args.kwarg)
            self.assertFalse(node.decorator_list)

        assignments = {
            target.id: node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for name, expected_value in EXPECTED_CONSTANTS.items():
            self.assertIn(name, assignments)
            self.assertEqual(ast.literal_eval(assignments[name]), expected_value)

        public_api = ast.literal_eval(assignments["__all__"])
        self.assertEqual(
            public_api,
            ("SessionError", "SessionConfig", "SessionResult", "load_session_config", "run_session"),
        )
        class_nodes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertEqual([ast.unparse(base) for base in class_nodes["SessionError"].bases], ["RuntimeError"])
        expected_fields = {
            "SessionConfig": ("data",),
            "SessionResult": ("child_pid", "child_returncode", "pre_monotonic_ns", "post_monotonic_ns"),
        }
        for class_name, expected_field_names in expected_fields.items():
            class_node = class_nodes[class_name]
            decorator = class_node.decorator_list[0]
            self.assertEqual(ast.unparse(decorator.func), "dataclasses.dataclass")
            self.assertEqual(
                {keyword.arg: ast.literal_eval(keyword.value) for keyword in decorator.keywords},
                {"frozen": True, "init": False},
            )
            fields = [node.target.id for node in class_node.body if isinstance(node, ast.AnnAssign)]
            self.assertEqual(fields, list(expected_field_names))
            constructors = [node for node in class_node.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"]
            self.assertEqual(len(constructors), 1)
            self.assertEqual(tuple(argument.arg for argument in constructors[0].args.args), ("self",))

        allowed_top_level = (ast.Expr, ast.Import, ast.ImportFrom, ast.Assign, ast.ClassDef, ast.FunctionDef)
        self.assertTrue(all(isinstance(node, allowed_top_level) for node in tree.body))
        expressions = [node for node in tree.body if isinstance(node, ast.Expr)]
        self.assertEqual(len(expressions), 1)
        self.assertIsInstance(expressions[0].value, ast.Constant)
        self.assertIsInstance(expressions[0].value.value, str)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                self.fail("Task 0B4a source may not use computed call targets")
            self.assertNotIn(name, FORBIDDEN_CALL_NAMES)
            self.assertFalse(name.startswith(("exec", "fork", "spawn")))


if __name__ == "__main__":
    unittest.main()
