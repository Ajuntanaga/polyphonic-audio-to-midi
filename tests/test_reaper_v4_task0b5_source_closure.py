"""Data-only source-closure tests for the future V4 fixture runtime."""
from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class Task0B5SourceClosureTests(unittest.TestCase):
    def _write(self, root: pathlib.Path, relative: str, text: str) -> pathlib.Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_builds_a_deterministic_closed_tools_source_graph(self) -> None:
        """The builder reads source bytes only and follows literal tools imports."""
        from tools.reaper_v4_fixture_manifest import build_session_source_closure

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            entry = self._write(
                root,
                "session_entry.py",
                "from tools import session\n\ndef main():\n    return session.run()\n",
            )
            session = self._write(
                root,
                "tools/session.py",
                "from tools import protocol\nfrom tools import receipts\n\ndef run():\n    return protocol.VALUE + receipts.VALUE\n",
            )
            protocol = self._write(root, "tools/protocol.py", "VALUE = 1\n")
            receipts = self._write(root, "tools/receipts.py", "VALUE = 2\n")

            first = build_session_source_closure(root, entry)
            second = build_session_source_closure(root, entry)
            entry_sha256 = hashlib.sha256(entry.read_bytes()).hexdigest()

        expected_paths = (
            "/app/session_entry.py",
            "/app/tools/protocol.py",
            "/app/tools/receipts.py",
            "/app/tools/session.py",
        )
        self.assertEqual(tuple(entry["destination"] for entry in first["entries"]), expected_paths)
        self.assertEqual(
            tuple((edge["from"], edge["to"]) for edge in first["edges"]),
            (
                ("/app/session_entry.py", "/app/tools/session.py"),
                ("/app/tools/session.py", "/app/tools/protocol.py"),
                ("/app/tools/session.py", "/app/tools/receipts.py"),
            ),
        )
        self.assertEqual(first, second)
        self.assertEqual(first["root"], "/app/session_entry.py")
        self.assertEqual(first["entries"][0]["sha256"], entry_sha256)
        self.assertEqual(first["state"], "SOURCE_CLOSURE_COMPLETE")

    def test_current_session_entry_has_the_complete_declared_tools_closure(self) -> None:
        """The eventual fixture root is source-closed through every V4 component."""
        from tools.reaper_v4_fixture_manifest import build_session_source_closure

        closure = build_session_source_closure(
            ROOT,
            ROOT / "tools/reaper_v4_session_entry.py",
        )

        self.assertEqual(closure["root"], "/app/tools/reaper_v4_session_entry.py")
        self.assertEqual(
            tuple(entry["destination"] for entry in closure["entries"]),
            (
                "/app/tools/reaper_v4_attester.py",
                "/app/tools/reaper_v4_child_runner.py",
                "/app/tools/reaper_v4_measurements.py",
                "/app/tools/reaper_v4_protocol.py",
                "/app/tools/reaper_v4_receipt_schema.py",
                "/app/tools/reaper_v4_session.py",
                "/app/tools/reaper_v4_session_entry.py",
            ),
        )
        self.assertEqual(closure["state"], "SOURCE_CLOSURE_COMPLETE")

    def test_refuses_missing_literal_tools_dependency(self) -> None:
        from tools.reaper_v4_fixture_manifest import (
            FixtureManifestError,
            build_session_source_closure,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            entry = self._write(root, "session_entry.py", "from tools import absent\n")
            with self.assertRaisesRegex(FixtureManifestError, "cannot be resolved"):
                build_session_source_closure(root, entry)

    def test_builds_a_declared_runtime_manifest_without_the_bootstrap_pair(self) -> None:
        """Config and digest stay outside their self-referential fixture manifest."""
        from tools.reaper_v4_fixture_manifest import build_fixture_runtime_manifest

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            entry = self._write(root, "session_entry.py", "from tools import session\n")
            self._write(root, "tools/session.py", "VALUE = 1\n")
            runtime = self._write(root, "runtime/python", "runtime\n")
            fixture_input = self._write(root, "fixture/a", "A")

            manifest = build_fixture_runtime_manifest(
                root,
                entry,
                {"/usr/bin/python3": runtime},
                {"/fixture/a": fixture_input},
            )

        self.assertEqual(manifest["state"], "DECLARED_RUNTIME_MANIFEST")
        self.assertEqual(manifest["entrypoint"], "/app/session_entry.py")
        self.assertEqual(
            tuple(entry["destination"] for entry in manifest["entries"]),
            ("/app/session_entry.py", "/app/tools/session.py", "/fixture/a", "/usr/bin/python3"),
        )
        self.assertEqual(manifest["resource_policy"]["regular_entry_count"], 4)
        self.assertEqual(
            manifest["resource_policy"]["largest_regular_entry"],
            max(entry["byte_size"] for entry in manifest["entries"]),
        )
        self.assertEqual(len(manifest["fixture_manifest_sha256"]), 64)

    def test_refuses_bootstrap_paths_inside_the_manifest(self) -> None:
        from tools.reaper_v4_fixture_manifest import (
            FixtureManifestError,
            build_fixture_runtime_manifest,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            entry = self._write(root, "session_entry.py", "VALUE = 1\n")
            bootstrap = self._write(root, "bootstrap/config.json", "{}")
            with self.assertRaisesRegex(FixtureManifestError, "bootstrap pair"):
                build_fixture_runtime_manifest(
                    root,
                    entry,
                    {},
                    {"/run/m3-v4/session-config.json": bootstrap},
                )

    def test_refuses_dynamic_imports_in_the_fixture_root_graph(self) -> None:
        from tools.reaper_v4_fixture_manifest import (
            FixtureManifestError,
            build_session_source_closure,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            entry = self._write(root, "session_entry.py", "__import__('tools.session')\n")
            with self.assertRaisesRegex(FixtureManifestError, "dynamic import"):
                build_session_source_closure(root, entry)


if __name__ == "__main__":
    unittest.main()
