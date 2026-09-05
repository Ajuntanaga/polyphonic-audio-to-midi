"""Test-first runtime-observation coverage for the V4 session root."""
from __future__ import annotations

import importlib
import errno
import os
import stat
import unittest
from unittest import mock

from tests.test_reaper_v4_task0b4b_evidence import _EvidenceFixture
from tests.test_reaper_v4_task0b4b_static_contract import assert_b4b_source_contract


def _session_module() -> object:
    assert_b4b_source_contract()
    return importlib.import_module("tools.reaper_v4_session")


class Task0B4bRuntimeObservationTests(unittest.TestCase):
    def test_captures_rechecks_and_releases_runtime_observations(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            paths = {
                "/run/m3-v4/measurements": fixture.descriptors[0],
                "/home/vst/scan": fixture.descriptors[1],
                "/home/vst": fixture.descriptors[2],
                "/run/m3-v4/Xauthority": fixture.descriptors[3],
                "/tmp/.X11-unix/X0": fixture.descriptors[4],
            }
            original_open = session.os.open

            def open_fixture_path(path: object, flags: object, *args: object, **kwargs: object) -> int:
                if type(path) is str and path in paths:
                    return os.dup(paths[path])
                return original_open(path, flags, *args, **kwargs)

            with (
                mock.patch.object(session.os, "open", side_effect=open_fixture_path),
                mock.patch.object(
                    session, "_observe_runtime_descriptor_census", create=True,
                    return_value=fixture.inherited_fds,
                ),
                mock.patch.object(
                    session, "_observe_runtime_mount_projection", create=True,
                    return_value=fixture.mounts,
                ),
                mock.patch.object(session.os, "getcwd", return_value=fixture.cwd),
                mock.patch.object(session.os, "environ", fixture.environment),
            ):
                baseline = session._capture_runtime_evidence(fixture.config)
                try:
                    self.assertIs(type(baseline), session._EvidenceBaseline)
                    session._recheck_runtime_evidence(baseline)
                finally:
                    session._release_runtime_evidence(baseline)
            self.assertTrue(baseline.released)

    def test_descriptor_census_is_bounded_and_closed_over_expected_fds(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            class Facts:
                st_mode = stat.S_IFIFO

            def only_standard_pipes(descriptor: int, command: int) -> int:
                self.assertEqual(command, session.fcntl.F_GETFD)
                if descriptor in {0, 1, 2}:
                    return 0
                raise OSError(errno.EBADF, "closed")

            with (
                mock.patch.object(session.runtime_resource, "getrlimit", return_value=(16, 16)),
                mock.patch.object(session.fcntl, "fcntl", side_effect=only_standard_pipes),
                mock.patch.object(session.os, "fstat", return_value=Facts()),
            ):
                observed = session._observe_runtime_descriptor_census(fixture.config, ())
            self.assertEqual(observed, fixture.inherited_fds)

            def unexpected_descriptor(descriptor: int, command: int) -> int:
                self.assertEqual(command, session.fcntl.F_GETFD)
                if descriptor in {0, 1, 2, 7}:
                    return 0
                raise OSError(errno.EBADF, "closed")

            with (
                mock.patch.object(session.runtime_resource, "getrlimit", return_value=(16, 16)),
                mock.patch.object(session.fcntl, "fcntl", side_effect=unexpected_descriptor),
            ):
                with self.assertRaises(session.SessionError):
                    session._observe_runtime_descriptor_census(fixture.config, ())
            with mock.patch.object(session.runtime_resource, "getrlimit", return_value=(65, 65)):
                with self.assertRaises(session.SessionError):
                    session._observe_runtime_descriptor_census(fixture.config, ())

    def test_mount_projection_accepts_only_configured_paths_and_mounts(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            lines: list[str] = []
            for index, record in enumerate(fixture.mounts, start=1):
                root = "/" if record["filesystem_type"] != "bind" else f"/source-{index}"
                options = "ro" if record["readonly"] else "rw"
                filesystem_type = "tmpfs" if record["filesystem_type"] == "bind" else record["filesystem_type"]
                lines.append(
                    f"{index} 0 0:{index} {root} {record['path']} {options} - {filesystem_type} fixture {options}\n"
                )
            raw = "".join(lines).encode("ascii")
            with mock.patch.object(session, "_read_runtime_mountinfo", return_value=raw):
                observed = session._observe_runtime_mount_projection(fixture.config)
            self.assertEqual(observed, fixture.mounts)
            extra = raw + (
                "99 0 0:99 /source-extra /home/vst/scan/unexpected ro - tmpfs fixture ro\n"
            ).encode("ascii")
            with mock.patch.object(session, "_read_runtime_mountinfo", return_value=extra):
                with self.assertRaises(session.SessionError):
                    session._observe_runtime_mount_projection(fixture.config)

    def test_runtime_path_open_failure_closes_the_partial_descriptor(self) -> None:
        session = _session_module()
        with _EvidenceFixture(session) as fixture:
            duplicated: list[int] = []

            def first_then_fail(_path: object, _flags: object) -> int:
                if not duplicated:
                    descriptor = os.dup(fixture.descriptors[0])
                    duplicated.append(descriptor)
                    return descriptor
                raise OSError("synthetic open failure")

            with mock.patch.object(session.os, "open", side_effect=first_then_fail):
                with self.assertRaises(session.SessionError):
                    session._open_runtime_evidence_descriptors(fixture.config)
            self.assertEqual(len(duplicated), 1)
            with self.assertRaises(OSError):
                os.fstat(duplicated[0])

    def test_invalid_admission_has_no_runtime_observation_side_effect(self) -> None:
        session = _session_module()
        invalid = object.__new__(session.SessionConfig)
        with (
            mock.patch.object(session, "_observe_runtime_descriptor_census") as census,
            mock.patch.object(session, "_observe_runtime_mount_projection") as mounts,
            mock.patch.object(session, "_open_runtime_evidence_descriptors") as opener,
        ):
            with self.assertRaises(session.SessionError):
                session._capture_runtime_evidence(invalid)
        census.assert_not_called()
        mounts.assert_not_called()
        opener.assert_not_called()

    def test_mountinfo_reader_requires_regular_eof_delimited_bytes_and_closes_once(self) -> None:
        session = _session_module()

        class Facts:
            st_mode = stat.S_IFREG

        with (
            mock.patch.object(session.os, "open", return_value=73) as opener,
            mock.patch.object(session.os, "fstat", return_value=Facts()),
            mock.patch.object(session.os, "read", side_effect=[b"1 0 0:1 / / rw - tmpfs tmpfs rw\n", b""]),
            mock.patch.object(session.os, "close") as closer,
        ):
            observed = session._read_runtime_mountinfo()
        self.assertEqual(observed, b"1 0 0:1 / / rw - tmpfs tmpfs rw\n")
        opener.assert_called_once()
        closer.assert_called_once_with(73)


if __name__ == "__main__":
    unittest.main()
