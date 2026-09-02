"""AST-only guard proving neither runtime order nor behavior."""
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
FORBIDDEN_NAMES = {
    "os", "subprocess", "ctypes", "importlib", "runpy", "pathlib", "socket",
    "asyncio", "sys", "shutil", "glob", "exec", "eval", "compile", "__import__",
    "getattr", "spawn", "fork", "open", "read", "write", "time", "select",
}


class SessionSourceContractTest(unittest.TestCase):
    def test_non_admissible_skeleton_before_target_import(self) -> None:
        self.assertIn("neither runtime order nor behavior", __doc__ or "")
        self.assertTrue(SOURCE.is_file(), SOURCE)
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FINAL_SHA256)
        tree = ast.parse(raw, filename=str(SOURCE))
        imports, assignments, classes, functions = self._top_level(tree)
        self.assertEqual(imports, EXPECTED_IMPORTS)
        self._assert_assignments(assignments)
        self.assertEqual(set(classes), {"SessionError", "SessionConfig", "SessionResult"})
        self.assertEqual(set(functions), {"load_session_config", "run_session"})
        self._assert_error_class(classes["SessionError"])
        initializers = set()
        self._assert_dataclass(classes["SessionConfig"], (("data", "Mapping[str, object]"),), initializers)
        self._assert_dataclass(classes["SessionResult"], (("child_pid", "int"), ("child_returncode", "int"), ("pre_monotonic_ns", "int"), ("post_monotonic_ns", "int")), initializers)
        self._assert_function(functions["load_session_config"], (("config_path", "str"), ("digest_path", "str")), "SessionConfig")
        self._assert_function(functions["run_session"], (("config", "SessionConfig"),), "SessionResult")
        self._assert_no_hidden_surface(tree, set(classes.values()), set(functions.values()), initializers)

    def _top_level(self, tree: ast.Module) -> tuple[set[tuple[str, str, str, str]], list[ast.Assign], dict[str, ast.ClassDef], dict[str, ast.FunctionDef]]:
        imports, assignments, classes, functions = set(), [], {}, {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(("import", alias.name, alias.asname or "", ""))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.add(("from", node.module or "", alias.name, alias.asname or ""))
            elif isinstance(node, ast.Assign):
                assignments.append(node)
            elif isinstance(node, ast.ClassDef):
                classes[node.name] = node
            elif isinstance(node, ast.FunctionDef):
                functions[node.name] = node
            else:
                self.fail(f"unexpected top-level node: {type(node).__name__}")
        return imports, assignments, classes, functions

    def _assert_assignments(self, assignments: list[ast.Assign]) -> None:
        values = {}
        for node in assignments:
            self.assertEqual(len(node.targets), 1)
            self.assertIsInstance(node.targets[0], ast.Name)
            self.assertIsNone(node.type_comment)
            values[node.targets[0].id] = ast.literal_eval(node.value)
        self.assertEqual(set(values), {"__all__", *EXPECTED_CONSTANTS})
        self.assertEqual(values["__all__"], ("SessionError", "SessionConfig", "SessionResult", "load_session_config", "run_session"))
        self.assertEqual({name: values[name] for name in EXPECTED_CONSTANTS}, EXPECTED_CONSTANTS)

    def _assert_error_class(self, node: ast.ClassDef) -> None:
        self.assertEqual([ast.unparse(item) for item in node.bases], ["RuntimeError"])
        self.assertFalse(node.keywords or node.decorator_list)
        self.assertEqual(len(node.body), 1)
        self.assertIsInstance(node.body[0], ast.Pass)

    def _assert_dataclass(self, node: ast.ClassDef, fields: tuple[tuple[str, str], ...], initializers: set[ast.FunctionDef]) -> None:
        self.assertEqual(node.bases, [])
        self.assertFalse(node.keywords)
        self.assertEqual(len(node.decorator_list), 1)
        decorator = node.decorator_list[0]
        self.assertIsInstance(decorator, ast.Call)
        self.assertEqual(ast.unparse(decorator.func), "dataclasses.dataclass")
        self.assertFalse(decorator.args)
        self.assertEqual([(item.arg, ast.literal_eval(item.value)) for item in decorator.keywords], [("frozen", True), ("init", False)])
        self.assertEqual(len(node.body), len(fields) + 1)
        for item, (name, annotation) in zip(node.body[:-1], fields):
            self.assertIsInstance(item, ast.AnnAssign)
            self.assertEqual(ast.unparse(item.target), name)
            self.assertEqual(ast.unparse(item.annotation), annotation)
            self.assertIsNone(item.value)
            self.assertEqual(item.simple, 1)
        initializer = node.body[-1]
        self.assertIsInstance(initializer, ast.FunctionDef)
        self.assertEqual(initializer.name, "__init__")
        self._assert_function(initializer, (("self", None),), "None")
        initializers.add(initializer)

    def _assert_function(self, node: ast.FunctionDef, arguments: tuple[tuple[str, str | None], ...], result: str | None) -> None:
        self.assertFalse(node.decorator_list or node.args.posonlyargs or node.args.kwonlyargs)
        self.assertIsNone(node.args.vararg)
        self.assertIsNone(node.args.kwarg)
        self.assertFalse(node.args.defaults or node.args.kw_defaults)
        self.assertEqual([(item.arg, None if item.annotation is None else ast.unparse(item.annotation)) for item in node.args.args], list(arguments))
        self.assertEqual(None if node.returns is None else ast.unparse(node.returns), result)
        self.assertEqual(len(node.body), 1)
        statement = node.body[0]
        self.assertIsInstance(statement, ast.Raise)
        self.assertIsNone(statement.cause)
        self.assertIsInstance(statement.exc, ast.Call)
        self.assertEqual(ast.unparse(statement.exc.func), "SessionError")
        self.assertEqual(len(statement.exc.args), 1)
        self.assertFalse(statement.exc.keywords)
        literal = statement.exc.args[0]
        self.assertIsInstance(literal, ast.Constant)
        self.assertIsInstance(literal.value, str)
        self.assertTrue(literal.value.isascii())

    def _assert_no_hidden_surface(self, tree: ast.Module, classes: set[ast.ClassDef], functions: set[ast.FunctionDef], initializers: set[ast.FunctionDef]) -> None:
        aliases = {"attester", "child_runner", "measurements", "protocol", "receipt_schema"}
        permitted_functions = functions | initializers
        for node in ast.walk(tree):
            if isinstance(node, (ast.Yield, ast.YieldFrom, ast.AsyncFunctionDef, ast.Lambda, ast.Global, ast.Nonlocal, ast.AugAssign)):
                self.fail(f"forbidden capability node: {type(node).__name__}")
            if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in tree.body:
                self.fail("nested import")
            if isinstance(node, ast.ClassDef) and node not in classes:
                self.fail("nested or alternate class")
            if isinstance(node, ast.FunctionDef) and node not in permitted_functions:
                self.fail("nested or alternate function")
            if isinstance(node, ast.Assign) and node not in tree.body:
                self.fail("nested assignment")
            if isinstance(node, ast.AnnAssign) and not any(node in item.body for item in classes):
                self.fail("non-field annotated assignment")
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, FORBIDDEN_NAMES)
                if isinstance(node.ctx, ast.Load):
                    self.assertNotIn(node.id, aliases)
            if isinstance(node, ast.Attribute):
                self.assertEqual(ast.unparse(node), "dataclasses.dataclass")
            if isinstance(node, ast.Call):
                self.assertIn(ast.unparse(node.func), {"dataclasses.dataclass", "SessionError"})
