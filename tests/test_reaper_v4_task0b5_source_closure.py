"""Data-only source-closure tests for the future V4 fixture runtime."""
from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
OBSERVED_RUNTIME_CATALOG = ROOT / "tests/fixtures/reaper_v4_closure/observed-runtime-catalog.json"


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

    def test_catalog_pins_runtime_bytes_and_refuses_drift_on_manifest_build(self) -> None:
        """Changing a cataloged runtime file must refuse later manifest assembly."""
        from tools.reaper_v4_fixture_manifest import (
            FixtureManifestError,
            build_fixture_runtime_manifest_from_catalog,
            build_runtime_catalog,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            entry = self._write(root, "session_entry.py", "from tools import session\n")
            self._write(root, "tools/session.py", "VALUE = 1\n")
            runtime = self._write(root, "runtime/python", "runtime-v1\n")
            fixture_input = self._write(root, "fixture/a", "A")
            catalog = build_runtime_catalog(
                {"/usr/bin/python3": runtime},
                unresolved=("interpreter startup model is not sealed",),
            )
            manifest = build_fixture_runtime_manifest_from_catalog(
                root,
                entry,
                catalog,
                {"/fixture/a": fixture_input},
            )
            runtime.write_text("runtime-v2\n", encoding="utf-8")
            with self.assertRaisesRegex(FixtureManifestError, "no longer matches"):
                build_fixture_runtime_manifest_from_catalog(
                    root,
                    entry,
                    catalog,
                    {"/fixture/a": fixture_input},
                )

        self.assertEqual(catalog["state"], "OBSERVED_RUNTIME_CATALOG")
        self.assertEqual(catalog["completeness"], "UNRESOLVED")
        self.assertEqual(catalog["unresolved"], ("interpreter startup model is not sealed",))
        self.assertEqual(manifest["state"], "DECLARED_RUNTIME_MANIFEST")
        self.assertEqual(manifest["runtime_catalog_sha256"], catalog["runtime_catalog_sha256"])

    def test_runtime_catalog_json_round_trips_only_in_canonical_form(self) -> None:
        """A persisted catalog must preserve exact entries and reject byte drift."""
        from tools.reaper_v4_fixture_manifest import (
            FixtureManifestError,
            build_runtime_catalog,
            load_runtime_catalog_bytes,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            runtime = self._write(root, "runtime/python", "runtime\n")
            catalog = build_runtime_catalog(
                {"/usr/bin/python3": runtime},
                unresolved=("startup registry is not sealed",),
            )
            encoded = json.dumps(
                catalog,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            loaded = load_runtime_catalog_bytes(encoded)

        self.assertEqual(loaded, catalog)
        self.assertIs(type(loaded["entries"]), tuple)
        self.assertIs(type(loaded["unresolved"]), tuple)
        self.assertEqual(load_runtime_catalog_bytes(encoded + b"\n"), catalog)
        with self.assertRaisesRegex(FixtureManifestError, "not canonical"):
            load_runtime_catalog_bytes(b'{"schema": 1}')
        with self.assertRaisesRegex(FixtureManifestError, "not canonical"):
            load_runtime_catalog_bytes(encoded + b"\n\n")

    def test_checked_in_runtime_catalog_is_canonical_and_honestly_unresolved(self) -> None:
        """The catalog must remain a concrete review input, never a completion claim."""
        from tools.reaper_v4_fixture_manifest import load_runtime_catalog_bytes

        catalog = load_runtime_catalog_bytes(OBSERVED_RUNTIME_CATALOG.read_bytes())

        self.assertEqual(catalog["state"], "OBSERVED_RUNTIME_CATALOG")
        self.assertEqual(catalog["completeness"], "UNRESOLVED")
        self.assertGreater(catalog["resource_policy"]["regular_entry_count"], 16)
        self.assertEqual(
            tuple(entry["destination"] for entry in catalog["entries"]),
            tuple(sorted(entry["destination"] for entry in catalog["entries"])),
        )
        redacted_entries = tuple(
            entry
            for entry in catalog["entries"]
            if entry["source"].startswith("/REDACTED/")
        )
        self.assertEqual(len(redacted_entries), 7)
        self.assertTrue(
            all(entry["destination"].startswith("/REDACTED/") for entry in redacted_entries)
        )
        self.assertTrue(any("startup" in reason for reason in catalog["unresolved"]))

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
