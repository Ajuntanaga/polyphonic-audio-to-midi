"""Pre-import source contract for the future V4 session owner."""
from __future__ import annotations

import ast
import hashlib
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/reaper_v4_session.py"
FINAL_SHA256 = "364c615f512e37271ec1110ce28d40792662f5bc1fe57fa85ed77c9c4ba79f2c"


class SessionSourceContractTest(unittest.TestCase):
    def test_source_contract_before_any_target_import(self) -> None:
        self.assertTrue(SOURCE.is_file(), SOURCE)
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), FINAL_SHA256)
        tree = ast.parse(raw, filename=str(SOURCE))
        imports = set()
        definitions = set()
        constants = {}
        functions = {}
        classes = {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(("import", alias.name, alias.asname or ""))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.add(("from", node.module or "", alias.name, alias.asname or ""))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions.add(node.name)
                functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                definitions.add(node.name)
                classes[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value
            elif not isinstance(node, (ast.Expr, ast.AnnAssign)):
                self.fail(f"unexpected top-level node: {type(node).__name__}")
        self.assertEqual(imports, {
            ("from", "__future__", "annotations", ""),
            ("import", "dataclasses", ""), ("import", "hashlib", ""),
            ("import", "json", ""), ("import", "os", ""),
            ("import", "select", ""), ("import", "stat", ""),
            ("import", "time", ""), ("import", "types", ""),
            ("from", "collections.abc", "Mapping", ""),
            ("from", "tools", "reaper_v4_attester", "attester"),
            ("from", "tools", "reaper_v4_child_runner", "child_runner"),
            ("from", "tools", "reaper_v4_measurements", "measurements"),
            ("from", "tools", "reaper_v4_protocol", "protocol"),
            ("from", "tools", "reaper_v4_receipt_schema", "receipt_schema"),
        })
        self.assertEqual(
            ast.literal_eval(constants["__all__"]),
            ("SessionError", "SessionConfig", "SessionResult", "load_session_config", "run_session"),
        )
        self.assertEqual(set(classes), {"SessionError", "SessionConfig", "SessionResult"})
        self.assertEqual(set(definitions), {
            "SessionError", "SessionConfig", "SessionResult", "_canonical_json_bytes",
            "_sha256", "_freeze", "_make_config", "_make_result", "_reject_duplicate_keys",
            "_snapshot_json", "_read_regular_once", "_prepare_diagnostic", "_diagnose",
            "_require_hex", "_require_fixed_limits", "_require_absolute_path",
            "_open_path_components", "_decode_mount_escape", "_read_bounded_chunks",
            "_validate_session_data", "load_session_config", "_deadline", "_write_complete",
            "_read_ack_eof", "_preflight", "_receipt_payload", "_child_spec", "run_session",
        })
        self.assertEqual([ast.unparse(base) for base in classes["SessionError"].bases], ["RuntimeError"])
        for name in ("SessionConfig", "SessionResult"):
            self.assertEqual([ast.unparse(item) for item in classes[name].decorator_list], ["dataclasses.dataclass(frozen=True, init=False)"])
        self.assertEqual(sum(len(node.decorator_list) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))), 2)
        for function in functions.values():
            self.assertFalse(function.args.defaults or function.args.kw_defaults, function.name)
            self.assertFalse(isinstance(function, ast.AsyncFunctionDef), function.name)
        required_literals = {
            "SESSION_CONFIG_PATH": "/run/m3-v4/session-config.json",
            "SESSION_DIGEST_PATH": "/run/m3-v4/session-config.sha256",
            "SESSION_ENTRYPOINT_KIND": "session_entrypoint",
            "SESSION_ENTRYPOINT_ROLE": "same_namespace_pre_ack_child_post_owner",
            "PRE_DEADLINE_MS": 5000, "ACK_DEADLINE_MS": 5000, "POST_DEADLINE_MS": 5000,
            "DIAGNOSTIC_MAX_BYTES": 1024, "MAX_FRAME_BYTES": 2064, "CHILD_TIMEOUT_MS": 30000,
            "SESSION_CONFIG_MAX_BYTES": 8192, "SESSION_CONFIG_MAX_NODES": 256,
            "SESSION_CONFIG_MAX_DEPTH": 16, "SIDECAR_BYTES": 64,
        }
        for name, value in required_literals.items():
            self.assertEqual(ast.literal_eval(constants[name]), value)
        self.assertEqual(ast.literal_eval(constants["DIAGNOSTIC_CODES"]), ("config", "preflight", "pre_write", "ack", "child", "post"))
        self.assertEqual(ast.literal_eval(constants["CHILD_ENVIRONMENT_ORDER"]), ("DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY"))
        text = raw.decode("utf-8")
        for forbidden in (
            "__main__", "subprocess", "ctypes", "importlib", "runpy", "pathlib", "socket", "asyncio", "sys",
            "os.system", "os.popen", "posix_spawn", "fork", "exec(", "eval(", "compile(", "__import__",
            "control-root", "control_root_path", "bubblewrap", "systemd",
        ):
            self.assertNotIn(forbidden, text)
        calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertLess(calls.index("attester.establish_protocol_barrier"), calls.index("_write_complete"))
        self.assertLess(calls.index("_read_ack_eof"), calls.index("child_runner.run_child"))
        self.assertLess(calls.index("receipt_schema.validate_exchange"), len(calls) - 1)
        self.assertIn("child_runner.ChildSpec", calls)
        self.assertIn("measurements.collect_namespace_measurements", calls)
        self.assertNotIn("dict.fromkeys", text)


if __name__ == "__main__":
    unittest.main()
