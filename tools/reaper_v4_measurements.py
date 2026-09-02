"""Explicit-plan namespace measurements for a later authorized component gate."""
from __future__ import annotations

import dataclasses
import os
import pathlib
import stat
import types
from collections.abc import Mapping


__all__ = (
    "MeasurementError",
    "MeasurementPlan",
    "MeasurementSnapshot",
    "MEASUREMENT_KEYS",
    "collect_namespace_measurements",
)

MEASUREMENT_KEYS = ("mode", "size")


class MeasurementError(ValueError):
    """The caller supplied a plan outside the narrowly declared measurement set."""


def _freeze_measurement_data(value: object) -> object:
    """Take a finite immutable snapshot of the narrow JSON-like measurement data."""
    remaining = [512]

    def freeze(item: object, ancestors: frozenset[int], depth: int) -> object:
        if depth > 32:
            raise MeasurementError("measurement data nesting exceeds 32 levels")
        if remaining[0] <= 0:
            raise MeasurementError("measurement data exceeds 512 structural nodes")

        if type(item) is dict:
            identity = id(item)
            if identity in ancestors:
                raise MeasurementError("measurement data must not contain cycles")
            if len(item) + 1 > remaining[0]:
                raise MeasurementError("measurement data exceeds 512 structural nodes")
            snapshot = dict(item)
            if len(snapshot) + 1 > remaining[0]:
                raise MeasurementError("measurement data exceeds 512 structural nodes")
            remaining[0] -= 1
            if not all(type(key) is str for key in snapshot):
                raise MeasurementError("measurement mapping keys must be strings")
            next_ancestors = ancestors | frozenset((identity,))
            return types.MappingProxyType(
                {key: freeze(child, next_ancestors, depth + 1) for key, child in snapshot.items()}
            )

        if type(item) is list:
            identity = id(item)
            if identity in ancestors:
                raise MeasurementError("measurement data must not contain cycles")
            if len(item) + 1 > remaining[0]:
                raise MeasurementError("measurement data exceeds 512 structural nodes")
            snapshot = list(item)
            if len(snapshot) + 1 > remaining[0]:
                raise MeasurementError("measurement data exceeds 512 structural nodes")
            remaining[0] -= 1
            next_ancestors = ancestors | frozenset((identity,))
            return tuple(freeze(child, next_ancestors, depth + 1) for child in snapshot)

        if type(item) is tuple:
            identity = id(item)
            if identity in ancestors:
                raise MeasurementError("measurement data must not contain cycles")
            if len(item) + 1 > remaining[0]:
                raise MeasurementError("measurement data exceeds 512 structural nodes")
            snapshot = tuple(item)
            if len(snapshot) + 1 > remaining[0]:
                raise MeasurementError("measurement data exceeds 512 structural nodes")
            remaining[0] -= 1
            next_ancestors = ancestors | frozenset((identity,))
            return tuple(freeze(child, next_ancestors, depth + 1) for child in snapshot)

        remaining[0] -= 1
        if type(item) in (type(None), bool, int, str):
            return item
        raise MeasurementError("measurement data contains an unsupported value")

    return freeze(value, frozenset(), 0)


@dataclasses.dataclass(frozen=True)
class MeasurementPlan:
    """A descriptor-rooted, finite resource plan supplied by a future session owner."""

    root_fd: int
    resources: tuple[str, ...]
    expected: Mapping[str, Mapping[str, int]]

    def __post_init__(self) -> None:
        if type(self.resources) is not tuple:
            raise MeasurementError("resources must be an exact tuple")
        if not isinstance(self.expected, Mapping):
            raise MeasurementError("expected facts must be a mapping")
        resources = _freeze_measurement_data(self.resources)
        if type(resources) is not tuple:
            raise MeasurementError("resources must be an exact tuple")
        object.__setattr__(self, "resources", resources)
        object.__setattr__(self, "expected", _freeze_measurement_data(self.expected))


@dataclasses.dataclass(frozen=True)
class MeasurementSnapshot:
    """Facts and matching evidence produced only when this callable is authorized."""

    facts: Mapping[str, Mapping[str, int]]
    evidence: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.facts, Mapping) or not isinstance(self.evidence, Mapping):
            raise MeasurementError("measurement snapshot must contain mappings")
        object.__setattr__(self, "facts", _freeze_measurement_data(self.facts))
        object.__setattr__(self, "evidence", _freeze_measurement_data(self.evidence))


def collect_namespace_measurements(plan: MeasurementPlan) -> MeasurementSnapshot:
    """Read a finite, no-follow set of regular files relative to an explicit directory fd."""
    if type(plan) is not MeasurementPlan:
        raise MeasurementError("plan must be a MeasurementPlan")
    root_fd = plan.root_fd
    resources = plan.resources
    expected_facts = plan.expected
    if isinstance(root_fd, bool) or not isinstance(root_fd, int):
        raise MeasurementError("root_fd must be an integer descriptor")
    try:
        root_stat = os.fstat(root_fd)
    except (OSError, OverflowError) as error:
        raise MeasurementError("root_fd cannot be inspected") from error
    if not stat.S_ISDIR(root_stat.st_mode):
        raise MeasurementError("root_fd must describe a directory")
    if type(resources) is not tuple or not 0 < len(resources) <= 16:
        raise MeasurementError("resources must be a bounded nonempty tuple")
    for resource in resources:
        if (
            type(resource) is not str
            or not resource
            or not all(32 <= ord(character) <= 126 for character in resource)
            or len(resource) > 256
        ):
            raise MeasurementError("resource names must be bounded strings")
        candidate = pathlib.PurePosixPath(resource)
        if (
            candidate.is_absolute()
            or ".." in candidate.parts
            or len(candidate.parts) != 1
            or candidate.as_posix() != resource
        ):
            raise MeasurementError("resource must be a single canonical relative name")
    if len(set(resources)) != len(resources):
        raise MeasurementError("resources must be unique")
    if not isinstance(expected_facts, Mapping) or set(expected_facts) != set(resources):
        raise MeasurementError("expected facts must match the declared resources")
    for resource in resources:
        expected = expected_facts[resource]
        if not isinstance(expected, Mapping) or set(expected) != {"mode", "size"}:
            raise MeasurementError("expected resource facts must be closed")
        expected_mode = expected["mode"]
        expected_size = expected["size"]
        if (
            isinstance(expected_mode, bool)
            or not isinstance(expected_mode, int)
            or not 0 <= expected_mode <= 0o7777
        ):
            raise MeasurementError("expected mode must be a finite permission value")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            raise MeasurementError("expected size must be a nonnegative integer")
    facts: dict[str, Mapping[str, int]] = {}
    evidence: dict[str, str] = {}
    for resource in resources:
        try:
            descriptor = os.open(
                resource,
                os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
        except OSError as error:
            raise MeasurementError("resource cannot be opened") from error
        try:
            try:
                resource_stat = os.fstat(descriptor)
            except OSError as error:
                raise MeasurementError("resource cannot be inspected") from error
        finally:
            try:
                os.close(descriptor)
            except OSError as error:
                raise MeasurementError("resource cannot be closed") from error
        if not stat.S_ISREG(resource_stat.st_mode):
            raise MeasurementError("resource must be a regular file")
        observed = {"mode": stat.S_IMODE(resource_stat.st_mode), "size": resource_stat.st_size}
        expected = expected_facts[resource]
        if observed != dict(expected):
            raise MeasurementError("resource facts differ from the explicit plan")
        facts[resource] = observed
        evidence[resource] = "descriptor-rooted-no-follow-regular-file"
    return MeasurementSnapshot(facts=facts, evidence=evidence)
