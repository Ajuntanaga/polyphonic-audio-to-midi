"""Synthetic descriptor-boundary checks for the V4 measurement collector."""
from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from tools import reaper_v4_measurements as measurements


class MeasurementDescriptorGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary_directory.name)
        self.root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        tone = self.root / "tone"
        tone.write_bytes(b"m3\n")
        tone.chmod(0o640)

    def tearDown(self) -> None:
        os.close(self.root_fd)
        self.temporary_directory.cleanup()

    def plan(self, resources: tuple[str, ...] = ("tone",), expected: object = None) -> measurements.MeasurementPlan:
        if expected is None:
            expected = {"tone": {"mode": 0o640, "size": 3}}
        return measurements.MeasurementPlan(
            root_fd=self.root_fd,
            resources=resources,
            expected=expected,
        )

    def test_public_measurement_keys_are_closed(self) -> None:
        self.assertEqual(measurements.MEASUREMENT_KEYS, ("mode", "size"))

    def test_collects_immutable_descriptor_rooted_regular_file_facts(self) -> None:
        expected = {"tone": {"mode": 0o640, "size": 3}}
        snapshot = measurements.collect_namespace_measurements(self.plan(expected=expected))
        expected["tone"]["size"] = 99

        self.assertEqual(snapshot.facts, {"tone": {"mode": 0o640, "size": 3}})
        self.assertEqual(snapshot.evidence, {"tone": "descriptor-rooted-no-follow-regular-file"})
        with self.assertRaises(TypeError):
            snapshot.facts["tone"] = {"mode": 0, "size": 0}
        with self.assertRaises(TypeError):
            snapshot.facts["tone"]["size"] = 0

    def test_retained_directory_descriptor_is_anchored_across_pathname_replacement(self) -> None:
        original_directory = self.root / "anchored"
        moved_directory = self.root / "moved"
        original_directory.mkdir()
        descriptor = os.open(original_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            original_tone = original_directory / "tone"
            original_tone.write_bytes(b"m3\n")
            original_tone.chmod(0o600)
            original_directory.rename(moved_directory)

            replacement_directory = self.root / "anchored"
            replacement_directory.mkdir()
            replacement_tone = replacement_directory / "tone"
            replacement_tone.write_bytes(b"replacement")
            replacement_tone.chmod(0o644)

            snapshot = measurements.collect_namespace_measurements(
                measurements.MeasurementPlan(
                    root_fd=descriptor,
                    resources=("tone",),
                    expected={"tone": {"mode": 0o600, "size": 3}},
                )
            )
        finally:
            os.close(descriptor)

        self.assertEqual(snapshot.facts, {"tone": {"mode": 0o600, "size": 3}})

    def test_rejects_wrong_mode_or_size(self) -> None:
        for expected in (
            {"tone": {"mode": 0o600, "size": 3}},
            {"tone": {"mode": 0o640, "size": 4}},
        ):
            with self.subTest(expected=expected):
                with self.assertRaises(measurements.MeasurementError):
                    measurements.collect_namespace_measurements(self.plan(expected=expected))

    def test_rejects_symlink_directory_and_missing_resource(self) -> None:
        (self.root / "directory").mkdir()
        os.symlink("tone", self.root / "link")
        for resource in ("directory", "link", "missing"):
            with self.subTest(resource=resource):
                plan = self.plan(
                    resources=(resource,),
                    expected={resource: {"mode": 0o640, "size": 3}},
                )
                with self.assertRaises(measurements.MeasurementError):
                    measurements.collect_namespace_measurements(plan)

    def test_rejects_closed_and_non_directory_root_descriptors(self) -> None:
        closed_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        os.close(closed_fd)
        plan = measurements.MeasurementPlan(
            root_fd=closed_fd,
            resources=("tone",),
            expected={"tone": {"mode": 0o640, "size": 3}},
        )
        with self.assertRaises(measurements.MeasurementError):
            measurements.collect_namespace_measurements(plan)

        file_fd = os.open(self.root / "tone", os.O_RDONLY | os.O_CLOEXEC)
        try:
            plan = measurements.MeasurementPlan(
                root_fd=file_fd,
                resources=("tone",),
                expected={"tone": {"mode": 0o640, "size": 3}},
            )
            with self.assertRaises(measurements.MeasurementError):
                measurements.collect_namespace_measurements(plan)
        finally:
            os.close(file_fd)

    def test_rejects_malformed_plans_and_non_local_names(self) -> None:
        with self.assertRaises(measurements.MeasurementError):
            measurements.MeasurementPlan(self.root_fd, ["tone"], {"tone": {"mode": 0o640, "size": 3}})
        for resources, expected in (
            ((), {}),
            (("tone", "tone"), {"tone": {"mode": 0o640, "size": 3}}),
            (("tone",), {}),
            (("../tone",), {"../tone": {"mode": 0o640, "size": 3}}),
            (("nested/tone",), {"nested/tone": {"mode": 0o640, "size": 3}}),
            (("/tone",), {"/tone": {"mode": 0o640, "size": 3}}),
            (("tone",), {"tone": {"mode": True, "size": 3}}),
            (("tone",), {"tone": {"mode": 0o640, "size": True}}),
            (("tone",), {"tone": {"mode": 0o640, "size": 3, "resource": "tone"}}),
        ):
            with self.subTest(resources=resources, expected=expected):
                with self.assertRaises(measurements.MeasurementError):
                    measurements.collect_namespace_measurements(self.plan(resources, expected))

    def test_rejects_duplicate_resources_before_opening_any_resource(self) -> None:
        plan = self.plan(
            resources=("tone", "tone"),
            expected={"tone": {"mode": 0o640, "size": 3}},
        )
        with mock.patch.object(measurements.os, "open") as resource_open:
            with self.assertRaises(measurements.MeasurementError):
                measurements.collect_namespace_measurements(plan)
        resource_open.assert_not_called()

    def test_rejects_plan_subclass_before_opening_any_resource(self) -> None:
        class AttributeMutablePlan(measurements.MeasurementPlan):
            pass

        plan = AttributeMutablePlan(
            root_fd=self.root_fd,
            resources=("tone",),
            expected={"tone": {"mode": 0o640, "size": 3}},
        )
        with mock.patch.object(measurements.os, "open", side_effect=OSError("must not open")) as resource_open:
            with self.assertRaises(measurements.MeasurementError):
                measurements.collect_namespace_measurements(plan)
        resource_open.assert_not_called()

    def test_rejects_unhashable_resource_before_opening_any_resource(self) -> None:
        plan = measurements.MeasurementPlan(
            root_fd=self.root_fd,
            resources=({},),
            expected={},
        )
        with mock.patch.object(measurements.os, "open") as resource_open:
            caught: BaseException | None = None
            try:
                measurements.collect_namespace_measurements(plan)
            except BaseException as error:
                caught = error
        resource_open.assert_not_called()
        self.assertIsInstance(caught, measurements.MeasurementError)

    def test_rejects_noncanonical_current_directory_name(self) -> None:
        plan = self.plan(
            resources=("./tone",),
            expected={"./tone": {"mode": 0o640, "size": 3}},
        )
        with mock.patch.object(measurements.os, "open") as resource_open:
            with self.assertRaises(measurements.MeasurementError):
                measurements.collect_namespace_measurements(plan)
        resource_open.assert_not_called()

    def test_rejects_huge_root_descriptor_as_measurement_error(self) -> None:
        plan = measurements.MeasurementPlan(
            root_fd=1 << 200,
            resources=("tone",),
            expected={"tone": {"mode": 0o640, "size": 3}},
        )
        with self.assertRaises(measurements.MeasurementError):
            measurements.collect_namespace_measurements(plan)

    def test_close_failure_is_measurement_error_without_retry(self) -> None:
        original_close = measurements.os.close

        def close_then_fail(descriptor: int) -> None:
            original_close(descriptor)
            raise OSError("synthetic close failure")

        with mock.patch.object(measurements.os, "close", side_effect=close_then_fail) as close:
            caught: BaseException | None = None
            try:
                measurements.collect_namespace_measurements(self.plan())
            except BaseException as error:
                caught = error

        self.assertIsInstance(caught, measurements.MeasurementError)
        close.assert_called_once()
