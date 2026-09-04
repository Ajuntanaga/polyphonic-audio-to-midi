"""Controlled-descriptor evidence tests for Task 0B4b-evidence."""
from __future__ import annotations

import hashlib
import importlib
import os
import socket
import stat
import tempfile
import unittest
from unittest import mock

from tests.test_reaper_v4_task0b4b_admission import (
    _forged_config,
    _refresh_all_identities,
    _valid_config,
)
from tests.test_reaper_v4_task0b4b_static_contract import assert_b4b_source_contract


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _close_quietly(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


class _EvidenceFixture:
    def __init__(self, session: object) -> None:
        self._session = session
        self._temporary = tempfile.TemporaryDirectory()
        self._descriptors: list[int] = []
        self._socket: socket.socket | None = None
        self.config: object | None = None
        self.cwd = ""
        self.environment: dict[str, object] = {}
        self.inherited_fds: tuple[dict[str, object], ...] = ()
        self.mounts: tuple[dict[str, object], ...] = ()
        self.measurement_display = ""
        self.scan_plugin_a = ""
        self.scan_plugin_b = ""
        self.authority_path = ""
        self.socket_path = ""

    def __enter__(self) -> _EvidenceFixture:
        root = self._temporary.name
        measurement = os.path.join(root, "measurement")
        scan = os.path.join(root, "scan")
        home = os.path.join(root, "home")
        authority = os.path.join(root, "Xauthority")
        socket_path = os.path.join(root, "X0")
        self.authority_path = authority
        self.socket_path = socket_path
        os.mkdir(measurement)
        self.measurement_display = os.path.join(measurement, "display")
        with open(self.measurement_display, "wb"):
            pass
        os.chmod(self.measurement_display, 0o444)
        os.makedirs(os.path.join(scan, "a"))
        os.makedirs(os.path.join(scan, "b"))
        self.scan_plugin_a = os.path.join(scan, "a", "plugin.vst3")
        self.scan_plugin_b = os.path.join(scan, "b", "plugin.vst3")
        with open(self.scan_plugin_a, "wb") as stream:
            stream.write(b"A")
        with open(self.scan_plugin_b, "wb") as stream:
            stream.write(b"BC")
        os.chmod(self.scan_plugin_a, 0o444)
        os.chmod(self.scan_plugin_b, 0o444)
        os.mkdir(home)
        os.chmod(home, 0o700)
        os.mkdir(os.path.join(home, ".vst"))
        os.mkdir(os.path.join(home, ".vst3"))
        authority_bytes = b"controlled-xauthority-material"
        with open(authority, "wb") as stream:
            stream.write(authority_bytes)
        os.chmod(authority, 0o600)
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.bind(socket_path)
        os.chmod(socket_path, 0o777)

        measurement_fd = os.open(measurement, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        scan_fd = os.open(scan, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        home_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        authority_fd = os.open(authority, os.O_RDONLY | os.O_CLOEXEC)
        socket_fd = os.open(socket_path, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC)
        self._descriptors = [measurement_fd, scan_fd, home_fd, authority_fd, socket_fd]

        value = _valid_config()
        measurement_stat = os.fstat(measurement_fd)
        value["namespace_expectations"]["measurement_root"] = {
            "path": "/run/m3-v4/measurements",
            "device": measurement_stat.st_dev,
            "inode": measurement_stat.st_ino,
        }
        value["namespace_expectations"]["measurement_plan"] = {
            "resources": ["display"], "expected": {"display": {"mode": 0o444, "size": 0}},
        }
        scan_entries = value["namespace_expectations"]["scan_root"]["entries"]
        scan_entries[0].update({"mode": 0o444, "size": 1, "sha256": _sha256(b"A")})
        scan_entries[1].update({"mode": 0o444, "size": 2, "sha256": _sha256(b"BC")})
        value["direct_input_digests"] = {
            "fixture_input_a": _sha256(b"A"), "fixture_input_b": _sha256(b"BC"),
        }
        authority_stat = os.fstat(authority_fd)
        authority_config = value["namespace_expectations"]["x11_identity"]["authority"]
        authority_config.update({
            "destination_mode": stat.S_IMODE(authority_stat.st_mode),
            "destination_size": authority_stat.st_size,
            "sha256": _sha256(authority_bytes),
        })
        socket_stat = os.fstat(socket_fd)
        socket_config = value["namespace_expectations"]["x11_identity"]["socket"]
        socket_config.update({
            "uid": socket_stat.st_uid,
            "gid": socket_stat.st_gid,
            "mode": stat.S_IMODE(socket_stat.st_mode),
            "device": socket_stat.st_dev,
            "inode": socket_stat.st_ino,
        })
        _refresh_all_identities(value)
        self.config = _forged_config(self._session, value)
        self.cwd = value["namespace_expectations"]["cwd"]
        self.environment = dict(value["namespace_expectations"]["environment"])
        self.inherited_fds = tuple(
            dict(item) for item in value["namespace_expectations"]["descriptor_policy"]["inherited_fds"]
        )
        self.mounts = tuple(dict(item) for item in value["namespace_expectations"]["control_visibility"]["mounts"])
        return self

    @property
    def descriptors(self) -> tuple[int, int, int, int, int]:
        return tuple(self._descriptors)  # type: ignore[return-value]

    def capture(self) -> object:
        assert self.config is not None
        return self._session._capture_evidence_baseline(
            self.config, *self.descriptors, self.cwd, self.environment, self.inherited_fds, self.mounts,
        )

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        for descriptor in self._descriptors:
            _close_quietly(descriptor)
        if self._socket is not None:
            self._socket.close()
        self._temporary.cleanup()


def _session_module() -> object:
    assert_b4b_source_contract()
    return importlib.import_module("tools.reaper_v4_session")


class Task0B4bEvidenceTests(unittest.TestCase):
    def test_captures_rechecks_and_releases_a_controlled_baseline(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            with self.assertRaises(session.SessionError):
                session._EvidenceBaseline()
            baseline = fixture.capture()
            self.assertIs(type(baseline), session._EvidenceBaseline)
            self.assertFalse(baseline.released)
            self.assertEqual(set(baseline.measurement), {"device", "inode", "facts", "evidence"})
            self.assertEqual(set(baseline.scan), {"device", "inode", "entries"})
            self.assertEqual(set(baseline.private_tree), {"device", "inode", "mode", "empty_directories"})
            self.assertEqual(set(baseline.x11), {"authority", "socket"})
            self.assertNotIn("attestation", baseline.certificate)
            session._recheck_evidence_baseline(
                baseline, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
            )
            session._release_evidence_baseline(baseline)
            self.assertTrue(baseline.released)
            with self.assertRaises(session.SessionError):
                session._recheck_evidence_baseline(
                    baseline, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
                )
            with self.assertRaises(session.SessionError):
                session._release_evidence_baseline(baseline)

    def test_invalid_config_does_not_take_or_close_caller_descriptors(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            invalid = object.__new__(session.SessionConfig)
            with self.assertRaises(session.SessionError):
                session._capture_evidence_baseline(
                    invalid, *fixture.descriptors, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
                )
            for descriptor in fixture.descriptors:
                self.assertGreater(os.fstat(descriptor).st_ino, 0)

    def test_captures_exact_environment_and_cwd_without_ambient_reads(self) -> None:
        session = _session_module()
        forbidden = (
            "BASH_ENV", "CLAP_PATH", "DBUS_SESSION_BUS_ADDRESS", "ENV", "LD_AUDIT",
            "LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "SSH_AUTH_SOCK",
            "VST3_PATH", "VST_PATH", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR",
        )
        with _EvidenceFixture(session) as fixture:
            observed = session._capture_environment_baseline(
                fixture.config, fixture.cwd, fixture.environment,
            )
            self.assertEqual(set(observed), {"cwd", "environment"})
            self.assertEqual(tuple(observed["environment"]), (
                "DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY",
            ))
            with self.assertRaises(session.SessionError):
                session._capture_environment_baseline(fixture.config, "/unexpected", fixture.environment)
            missing = dict(fixture.environment)
            del missing["LANG"]
            with self.assertRaises(session.SessionError):
                session._capture_environment_baseline(fixture.config, fixture.cwd, missing)
            wrong = dict(fixture.environment)
            wrong["PWD"] = "/wrong"
            with self.assertRaises(session.SessionError):
                session._capture_environment_baseline(fixture.config, fixture.cwd, wrong)
            for name in forbidden:
                with self.subTest(forbidden=name):
                    forbidden_environment = dict(fixture.environment)
                    forbidden_environment[name] = "blocked"
                    with self.assertRaises(session.SessionError):
                        session._capture_environment_baseline(
                            fixture.config, fixture.cwd, forbidden_environment,
                        )
            baseline = fixture.capture()
            fixture.environment["LANG"] = "en_US.UTF-8"
            with self.assertRaises(session.SessionError):
                session._recheck_evidence_baseline(
                    baseline, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
                )
            session._release_evidence_baseline(baseline)

    def test_rejects_a_forged_baseline_without_closing_descriptors(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            forged = object.__new__(session._EvidenceBaseline)
            object.__setattr__(forged, "descriptors", fixture.descriptors)
            object.__setattr__(forged, "released", False)
            with self.assertRaises(session.SessionError):
                session._release_evidence_baseline(forged)
            with self.assertRaises(session.SessionError):
                session._recheck_evidence_baseline(
                    forged, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
                )
            for descriptor in fixture.descriptors:
                self.assertGreater(os.fstat(descriptor).st_ino, 0)

    def test_rejects_mutated_owned_descriptor_tuple_without_closing_any_fd(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            original = baseline.descriptors
            substituted = tuple(os.dup(descriptor) for descriptor in original)
            try:
                object.__setattr__(baseline, "descriptors", substituted)
                with self.assertRaises(session.SessionError):
                    session._release_evidence_baseline(baseline)
                for descriptor in original + substituted:
                    self.assertGreater(os.fstat(descriptor).st_ino, 0)
                object.__setattr__(baseline, "descriptors", original)
                session._release_evidence_baseline(baseline)
            finally:
                for descriptor in substituted:
                    _close_quietly(descriptor)

    def test_capture_reports_cleanup_uncertainty_after_transfer(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            with open(os.path.join(fixture._temporary.name, "scan", "unexpected"), "wb"):
                pass
            original_close = session.os.close
            failed_descriptor = fixture.descriptors[0]

            def close_with_one_failure(descriptor: int) -> None:
                if descriptor == failed_descriptor:
                    raise OSError("synthetic capture close failure")
                original_close(descriptor)

            with mock.patch.object(session.os, "close", side_effect=close_with_one_failure) as close:
                with self.assertRaisesRegex(session.SessionError, "cleanup is uncertain"):
                    fixture.capture()
            for descriptor in fixture.descriptors:
                self.assertEqual(
                    sum(call.args == (descriptor,) for call in close.call_args_list), 1,
                )
            self.assertGreater(os.fstat(failed_descriptor).st_ino, 0)
            for descriptor in fixture.descriptors[1:]:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)

    def test_rejects_scan_and_post_change_without_terminal_evidence(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            os.chmod(fixture.scan_plugin_b, 0o644)
            with open(fixture.scan_plugin_b, "wb") as stream:
                stream.write(b"ZZ")
            with self.assertRaises(session.SessionError):
                session._recheck_evidence_baseline(
                    baseline, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
                )
            session._release_evidence_baseline(baseline)
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            replaced = fixture.scan_plugin_b + ".old"
            os.rename(fixture.scan_plugin_b, replaced)
            with open(fixture.scan_plugin_b, "wb") as stream:
                stream.write(b"BC")
            os.chmod(fixture.scan_plugin_b, 0o444)
            with self.assertRaises(session.SessionError):
                session._recheck_evidence_baseline(
                    baseline, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
                )
            session._release_evidence_baseline(baseline)
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            private_directory = os.path.join(fixture._temporary.name, "home", ".vst")
            os.rmdir(private_directory)
            os.mkdir(private_directory)
            with self.assertRaises(session.SessionError):
                session._recheck_evidence_baseline(
                    baseline, fixture.cwd, fixture.environment, fixture.inherited_fds, fixture.mounts,
                )
            session._release_evidence_baseline(baseline)
        with _EvidenceFixture(session) as fixture:
            extra_path = os.path.join(fixture._temporary.name, "scan", "unexpected")
            with open(extra_path, "wb"):
                pass
            with self.assertRaises(session.SessionError):
                fixture.capture()
            for descriptor in fixture.descriptors:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)

    def test_rejects_private_x11_and_observation_mismatches(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            invalid_fds = fixture.inherited_fds + ({"fd": 3, "kind": "pipe", "role": "extra"},)
            with self.assertRaises(session.SessionError):
                session._validate_inherited_fd_census(fixture.config, invalid_fds)
            invalid_mounts = fixture.mounts[:-1]
            with self.assertRaises(session.SessionError):
                session._validate_mount_projection(fixture.config, invalid_mounts)
            os.mkdir(os.path.join(fixture._temporary.name, "home", ".vst", "unexpected"))
            with self.assertRaises(session.SessionError):
                fixture.capture()

    def test_rejects_measurement_scan_authority_and_socket_variants(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            os.chmod(fixture.measurement_display, 0o600)
            with self.assertRaises(session.SessionError):
                fixture.capture()
        with _EvidenceFixture(session) as fixture:
            os.unlink(fixture.scan_plugin_a)
            os.symlink("plugin.vst3", fixture.scan_plugin_a)
            with self.assertRaises(session.SessionError):
                fixture.capture()
        with _EvidenceFixture(session) as fixture:
            os.chmod(fixture.authority_path, 0o644)
            with self.assertRaises(session.SessionError):
                fixture.capture()
        with _EvidenceFixture(session) as fixture:
            os.chmod(fixture.socket_path, 0o700)
            with self.assertRaises(session.SessionError):
                fixture.capture()

    def test_certificate_projection_is_fresh_and_non_attesting(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            projection = session._certificate_applicability_projection(fixture.config)
            self.assertEqual(set(projection), {
                "runtime_manifest_sha256", "fixture_manifest_sha256", "bwrap", "namespace_policy_sha256",
                "mount_policy_sha256", "fd_policy_sha256", "user_namespace_policy_sha256", "certificates",
            })
            self.assertNotIn("attestation", projection)
            projection["bwrap"]["path"] = "/mutated"
            renewed = session._certificate_applicability_projection(fixture.config)
            self.assertNotEqual(renewed["bwrap"]["path"], "/mutated")

    def test_release_marks_consumed_and_reports_a_close_error_once(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            baseline = fixture.capture()
            original_close = session.os.close
            failed_descriptor = baseline.descriptors[0]

            def close_once(descriptor: int) -> None:
                if descriptor == failed_descriptor:
                    raise OSError("synthetic close failure")
                original_close(descriptor)

            with mock.patch.object(session.os, "close", side_effect=close_once) as close:
                with self.assertRaises(session.SessionError):
                    session._release_evidence_baseline(baseline)
            self.assertTrue(baseline.released)
            self.assertEqual(close.call_count, 5)


if __name__ == "__main__":
    unittest.main()
