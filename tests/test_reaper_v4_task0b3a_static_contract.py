"""AST-only guard for a non-admissible source skeleton, not runtime behavior."""
from __future__ import annotations

import ast
import hashlib
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/reaper_v4_session.py"
FINAL_SHA256 = "f3867a75817670916f2a450f7d7024f5c1bf1932d97fb65d34c4ca251a9f5c60"
EXPECTED_IMPORTS = {
    ("from", "__future__", "annotations", ""),
    ("import", "dataclasses", "", ""),
    ("from", "collections.abc", "Mapping", ""),
    ("from", "tools", "reaper_v4_attester", "attester"),
    ("from", "tools", "reaper_v4_child_runner", "child_runner"),
    ("from", "tools", "reaper_v4_measurements", "measurements"),
    ("from", "tools", "reaper_v4_protocol", "protocol"),
    ("from", "tools", "reaper_v4_receipt_schema", "receipt_schema"),
}
EXPECTED_CONSTANTS = {
    "SESSION_ENTRYPOINT_KIND": "session_entrypoint",
    "SESSION_ENTRYPOINT_ROLE": "same_namespace_pre_ack_child_post_owner",
    "SESSION_CONFIG_PATH": "/run/m3-v4/session-config.json",
    "SESSION_DIGEST_PATH": "/run/m3-v4/session-config.sha256",
}


class SessionSourceContractTest(unittest.TestCase):
    def test_non_admissible_skeleton_before_target_import(self) -> None:
        self.assertTrue(SOURCE.is_file(), SOURCE)
        raw = SOURCE.read_bytes()
        tree = ast.parse(raw, filename=str(SOURCE))
        imports, constants, classes, functions = self._top_level(tree)
        self.assertEqual(imports, EXPECTED_IMPORTS)
        self.assertEqual(set(constants), {"__all__", *EXPECTED_CONSTANTS})
        self.assertEqual(
            ast.literal_eval(constants["__all__"]),
            ("SessionError", "SessionConfig", "SessionResult", "load_session_config", "run_session"),
        )
        self.assertEqual({name: ast.literal_eval(constants[name]) for name in EXPECTED_CONSTANTS}, EXPECTED_CONSTANTS)
        self.assertEqual(set(classes), {"SessionError", "SessionConfig", "SessionResult"})
        self.assertEqual(set(functions), {"load_session_config", "run_session"})
        self.assertEqual([ast.unparse(item) for item in classes["SessionError"].bases], ["RuntimeError"])
        self._assert_dataclass(classes["SessionConfig"], ("data",))
        self._assert_dataclass(classes["SessionResult"], ("child_pid", "child_returncode", "pre_monotonic_ns", "post_monotonic_ns"))
        self._assert_signature(functions["load_session_config"], ("config_path", "digest_path"))
        self._assert_signature(functions["run_session"], ("config",))
        aliases = {"attester", "child_runner", "measurements", "protocol", "receipt_schema"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self.assertNotIn(node.id, aliases)
            if isinstance(node, ast.Call):
                self.assertIn(ast.unparse(node.func), {"SessionError", "dataclasses.dataclass"})
            if isinstance(node, ast.Attribute):
                self.assertEqual(ast.unparse(node), "dataclasses.dataclass")
        self.assertNotIn("__main__", raw.decode("utf-8"))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FINAL_SHA256)

    def _top_level(self, tree: ast.Module) -> tuple[set[tuple[str, str, str, str]], dict[str, ast.expr], dict[str, ast.ClassDef], dict[str, ast.FunctionDef]]:
        imports, constants, classes, functions = set(), {}, {}, {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(("import", alias.name, alias.asname or "", ""))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.add(("from", node.module or "", alias.name, alias.asname or ""))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value
            elif isinstance(node, ast.ClassDef):
                classes[node.name] = node
            elif isinstance(node, ast.FunctionDef):
                functions[node.name] = node
            else:
                self.fail(f"unexpected top-level node: {type(node).__name__}")
        return imports, constants, classes, functions

    def _assert_dataclass(self, node: ast.ClassDef, fields: tuple[str, ...]) -> None:
        self.assertEqual([ast.unparse(item) for item in node.decorator_list], ["dataclasses.dataclass(frozen=True, init=False)"])
        self.assertEqual([item.target.id for item in node.body if isinstance(item, ast.AnnAssign)], list(fields))
        methods = [item for item in node.body if isinstance(item, ast.FunctionDef)]
        self.assertEqual([item.name for item in methods], ["__init__"])
        self._assert_unconditional_raise(methods[0])

    def _assert_signature(self, node: ast.FunctionDef, names: tuple[str, ...]) -> None:
        self.assertEqual(tuple(argument.arg for argument in node.args.args), names)
        self.assertIsNone(node.args.vararg)
        self.assertIsNone(node.args.kwarg)
        self.assertFalse(node.args.defaults or node.args.kw_defaults)
        self._assert_unconditional_raise(node)

    def _assert_unconditional_raise(self, node: ast.FunctionDef) -> None:
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.Raise)
        self.assertEqual(ast.unparse(node.body[0].exc.func), "SessionError")
