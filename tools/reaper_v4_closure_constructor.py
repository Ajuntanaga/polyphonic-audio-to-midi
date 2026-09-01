"""Fail-closed, data-only V4 closure-record skeleton for a later component gate."""
from __future__ import annotations

import ast
import dataclasses
import enum
import hashlib
import json
import os
import stat
import struct
import types
from collections.abc import Mapping


__all__ = (
    "ClosureConstructionError",
    "ClosureState",
    "ClosureInputBundle",
    "ClosureRecord",
    "canonical_json_bytes",
    "sha256_canonical",
    "load_input_bundle",
    "construct_closure",
)

CATALOG_NAMES = (
    "resolver_policy",
    "startup_model",
    "module_catalog",
    "interpreter_module_registry",
    "frozen_effect_catalog",
    "elf_catalog",
    "branch_policy",
    "native_effect_catalog",
    "virtual_resource_catalog",
    "source_effect_catalog",
    "resource_policy",
)
ROOT_KEYS = ("id", "module", "kind", "sha256", "role")
IDENTITY_KEYS = (
    "kind",
    "raw_path",
    "mode",
    "device",
    "inode",
    "byte_size",
    "sha256",
    "version",
)
BUNDLE_KEYS = (
    "schema",
    "method_version",
    "method_spec_sha256",
    "constructor_identity",
    "parser_identity",
    "target_platform",
    "task0a_source_component_digest",
    "analysis_roots",
    "runtime_roots",
    "catalogs",
    "budgets",
)
RECORD_KEYS = (
    "schema",
    "method_version",
    "method_spec_sha256",
    "constructor_identity",
    "parser_identity",
    "resolver_policy_digest",
    "resource_policy_digest",
    "interpreter_module_registry_digest",
    "native_effect_catalog_digest",
    "frozen_effect_catalog_digest",
    "virtual_resource_catalog_digest",
    "source_effect_catalog_digest",
    "startup_model_digest",
    "input_bundle_digest",
    "target_platform",
    "task0a_source_component_digest",
    "analysis_root_identities",
    "runtime_root_identities",
    "module_catalog_digest",
    "elf_catalog_digest",
    "branch_policy_digest",
    "nodes",
    "edges",
    "branch_records",
    "unresolved",
    "budgets",
    "closure_state",
    "closure_digest",
)
RECORD_DIGEST_KEYS = (
    "method_spec_sha256",
    "resolver_policy_digest",
    "resource_policy_digest",
    "interpreter_module_registry_digest",
    "native_effect_catalog_digest",
    "frozen_effect_catalog_digest",
    "virtual_resource_catalog_digest",
    "source_effect_catalog_digest",
    "startup_model_digest",
    "input_bundle_digest",
    "task0a_source_component_digest",
    "module_catalog_digest",
    "elf_catalog_digest",
    "branch_policy_digest",
    "closure_digest",
)
RECORD_CATALOG_DIGEST_KEYS = (
    ("resolver_policy", "resolver_policy_digest"),
    ("startup_model", "startup_model_digest"),
    ("module_catalog", "module_catalog_digest"),
    ("interpreter_module_registry", "interpreter_module_registry_digest"),
    ("frozen_effect_catalog", "frozen_effect_catalog_digest"),
    ("elf_catalog", "elf_catalog_digest"),
    ("branch_policy", "branch_policy_digest"),
    ("native_effect_catalog", "native_effect_catalog_digest"),
    ("virtual_resource_catalog", "virtual_resource_catalog_digest"),
    ("source_effect_catalog", "source_effect_catalog_digest"),
    ("resource_policy", "resource_policy_digest"),
)
BLOCKED_UNRESOLVED_KEYS = ("code", "role", "analysis_root_ids", "evidence")
BLOCKED_EVIDENCE_KEYS = ("stage", "runtime_root_count", "graph_construction")
HEX = "0123456789abcdef"
REQUIRED_ANALYSIS_ROOTS = (
    ("tools.reaper_v4_protocol", "sealed_component"),
    ("tools.reaper_v4_receipt_schema", "runtime_library"),
    ("tools.reaper_v4_measurements", "runtime_library"),
    ("tools.reaper_v4_child_runner", "runtime_library"),
)
MAX_STATIC_NODES = 4096
MAX_STATIC_DEPTH = 64
MAX_STATIC_INPUT_BYTES = 6144
MAX_STATIC_STRING_BYTES = 1024
MAX_STATIC_INTEGER_BITS = 256
MAX_CANONICAL_JSON_BYTES = 65536
TASK0B1_RUNTIME_ROOTS_MAX = 0


class ClosureConstructionError(ValueError):
    """Raised when supplied static closure data is not closed and canonical."""


def _freeze_static_data(value: object) -> object:
    """Snapshot bounded static caller data before any semantic validation."""
    remaining_nodes = [MAX_STATIC_NODES]
    remaining_bytes = [MAX_STATIC_INPUT_BYTES]

    def charge(amount: int) -> None:
        remaining_bytes[0] -= amount
        if remaining_bytes[0] < 0:
            raise ClosureConstructionError("static data exceeds the bounded byte budget")

    def text_size(text: str) -> int:
        if len(text) > MAX_STATIC_STRING_BYTES:
            raise ClosureConstructionError("static data string exceeds the bounded byte budget")
        try:
            return len(text.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ClosureConstructionError("static data string is not valid UTF-8") from error

    def freeze(item: object, ancestors: frozenset[int], depth: int) -> object:
        if depth >= MAX_STATIC_DEPTH:
            raise ClosureConstructionError("static data exceeds the bounded nesting depth")
        if isinstance(item, Mapping):
            if type(item) is not dict:
                raise ClosureConstructionError("static data mappings must have exact built-in containers")
            identity = id(item)
            if identity in ancestors:
                raise ClosureConstructionError("static data cannot contain cycles")
            if len(item) > MAX_STATIC_NODES:
                raise ClosureConstructionError("static data exceeds the bounded node budget")
            try:
                snapshot = dict(item)
            except (TypeError, ValueError, RuntimeError) as error:
                raise ClosureConstructionError("static data mapping cannot be snapshotted") from error
            if len(snapshot) > MAX_STATIC_NODES:
                raise ClosureConstructionError("static data exceeds the bounded node budget")
            remaining_nodes[0] -= len(snapshot) + 1
            if remaining_nodes[0] < 0:
                raise ClosureConstructionError("static data exceeds the bounded node budget")
            if not all(type(key) is str for key in snapshot):
                raise ClosureConstructionError("static data mapping keys must be strings")
            charge(2 + len(snapshot))
            for key in snapshot:
                charge(text_size(key) + 2)
            return types.MappingProxyType({
                key: freeze(child, ancestors | {identity}, depth + 1)
                for key, child in snapshot.items()
            })
        if isinstance(item, (list, tuple)):
            if type(item) not in (list, tuple):
                raise ClosureConstructionError("static data sequences must have exact built-in containers")
            identity = id(item)
            if identity in ancestors:
                raise ClosureConstructionError("static data cannot contain cycles")
            if len(item) > MAX_STATIC_NODES:
                raise ClosureConstructionError("static data exceeds the bounded node budget")
            try:
                snapshot = tuple(item)
            except (TypeError, ValueError, RuntimeError) as error:
                raise ClosureConstructionError("static data sequence cannot be snapshotted") from error
            if len(snapshot) > MAX_STATIC_NODES:
                raise ClosureConstructionError("static data exceeds the bounded node budget")
            remaining_nodes[0] -= len(snapshot) + 1
            if remaining_nodes[0] < 0:
                raise ClosureConstructionError("static data exceeds the bounded node budget")
            charge(2 + len(snapshot))
            return tuple(freeze(child, ancestors | {identity}, depth + 1) for child in snapshot)
        if type(item) is str:
            charge(text_size(item) + 2)
            return item
        if type(item) is int:
            if item.bit_length() > MAX_STATIC_INTEGER_BITS:
                raise ClosureConstructionError("static data integer exceeds the bounded bit length")
            charge(max(1, (item.bit_length() * 30103 + 99999) // 100000))
            return item
        if type(item) is bool:
            charge(5)
            return item
        if item is None:
            charge(4)
            return item
        raise ClosureConstructionError("static data has an unsupported value")

    return freeze(value, frozenset(), 0)


def _is_synthetic_path(value: object) -> bool:
    """Accept only the inert synthetic provenance namespace without traversal."""
    return (
        type(value) is str
        and (value == "/synthetic" or value.startswith("/synthetic/"))
        and all(part not in ("", ".", "..") for part in value.split("/")[1:])
    )


def _normalise_frozen(item: object) -> object:
    """Normalise a trusted immutable snapshot or a private construction mapping."""
    if isinstance(item, float):
        raise ClosureConstructionError("canonical closure data cannot contain floats")
    if type(item) in (dict, types.MappingProxyType):
        if not all(type(key) is str for key in item):
            raise ClosureConstructionError("canonical closure object keys must be strings")
        return {key: _normalise_frozen(child) for key, child in item.items()}
    if type(item) in (list, tuple):
        return [_normalise_frozen(child) for child in item]
    if type(item) in (str, int, bool) or item is None:
        return item
    raise ClosureConstructionError("canonical closure data has an unsupported value")


def _canonical_json_bytes_from_frozen(value: object) -> bytes:
    """Encode a trusted frozen snapshot without revisiting caller-owned containers."""
    try:
        encoded = json.dumps(
            _normalise_frozen(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_CANONICAL_JSON_BYTES:
            raise ClosureConstructionError("canonical closure data exceeds the bounded byte budget")
        return encoded
    except (TypeError, UnicodeEncodeError, ValueError) as error:
        raise ClosureConstructionError("canonical closure data is not JSON") from error


def _sha256_frozen(value: object) -> str:
    """Hash a private frozen snapshot or construction mapping."""
    return hashlib.sha256(_canonical_json_bytes_from_frozen(value)).hexdigest()


class ClosureState(str, enum.Enum):
    """The only two terminal states defined by the governing closure method."""

    BLOCKED_UNRESOLVED = "BLOCKED_UNRESOLVED"
    COMPLETE_FIXTURE_CANDIDATE = "COMPLETE_FIXTURE_CANDIDATE"


@dataclasses.dataclass(frozen=True)
class ClosureInputBundle:
    """A deep-frozen, caller-supplied static input bundle."""

    bundle: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.bundle, Mapping):
            raise ClosureConstructionError("input bundle must be a mapping")
        object.__setattr__(self, "bundle", _freeze_static_data(self.bundle))


@dataclasses.dataclass(frozen=True)
class ClosureRecord:
    """A deep-frozen, canonical static closure record."""

    record: Mapping[str, object]

    def __post_init__(self) -> None:
        def is_digest(item: object) -> bool:
            return (
                type(item) is str
                and len(item) == 64
                and all(character in HEX for character in item)
            )

        def identity(item: object, expected_kind: str) -> bool:
            return (
                isinstance(item, Mapping)
                and set(item) == set(IDENTITY_KEYS)
                and type(item["kind"]) is str
                and item["kind"] == expected_kind
                and 1 <= len(item["kind"]) <= 64
                and all(32 <= ord(character) <= 126 for character in item["kind"])
                and type(item["raw_path"]) is str
                and _is_synthetic_path(item["raw_path"])
                and 1 <= len(item["raw_path"]) <= 1024
                and all(32 <= ord(character) <= 126 for character in item["raw_path"])
                and type(item["mode"]) is int
                and 0 <= item["mode"] <= 0o177777
                and type(item["device"]) is int
                and 1 <= item["device"] <= 9223372036854775807
                and type(item["inode"]) is int
                and 1 <= item["inode"] <= 9223372036854775807
                and type(item["byte_size"]) is int
                and 0 <= item["byte_size"] <= 9223372036854775807
                and is_digest(item["sha256"])
                and type(item["version"]) is str
                and 1 <= len(item["version"]) <= 128
                and all(32 <= ord(character) <= 126 for character in item["version"])
            )

        def platform(item: object) -> bool:
            return (
                isinstance(item, Mapping)
                and set(item) == {"architecture", "system"}
                and all(
                    type(item[key]) is str
                    and 1 <= len(item[key]) <= 128
                    and all(32 <= ord(character) <= 126 for character in item[key])
                    for key in ("architecture", "system")
                )
            )

        def budget(item: object) -> bool:
            return (
                isinstance(item, Mapping)
                and set(item) == {"maximum_edges", "maximum_nodes"}
                and all(
                    type(item[key]) is int and item[key] >= 0
                    for key in ("maximum_edges", "maximum_nodes")
                )
            )

        root_identifiers: set[str] = set()
        root_modules: dict[str, str] = {}

        def roots(
            items: object,
            kind: str,
            roles: tuple[str, ...],
            minimum: int,
            maximum: int,
        ) -> bool:
            if type(items) not in (list, tuple) or not minimum <= len(items) <= maximum:
                return False
            for root in items:
                if not isinstance(root, Mapping) or set(root) != set(ROOT_KEYS):
                    return False
                root_id = root["id"]
                module = root["module"]
                root_digest = root["sha256"]
                if (
                    type(root_id) is not str
                    or not root_id
                    or len(root_id) > 128
                    or root_id[0] not in "abcdefghijklmnopqrstuvwxyz0123456789"
                    or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in root_id)
                    or type(module) is not str
                    or not module
                    or len(module) > 256
                    or any(
                        not part
                        or part[0] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
                        or any(
                            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
                            for character in part[1:]
                        )
                        for part in module.split(".")
                    )
                    or not is_digest(root_digest)
                    or type(root["kind"]) is not str
                    or root["kind"] != kind
                    or type(root["role"]) is not str
                    or root["role"] not in roles
                    or root_id in root_identifiers
                    or (module in root_modules and root_modules[module] != root_digest)
                ):
                    return False
                root_identifiers.add(root_id)
                root_modules[module] = root_digest
            if kind == "analysis_source" and tuple(
                (root["module"], root["role"]) for root in items
            ) != REQUIRED_ANALYSIS_ROOTS:
                return False
            return True

        if not isinstance(self.record, Mapping):
            raise ClosureConstructionError("closure record must be a mapping")
        value = _freeze_static_data(self.record)
        if set(value) != set(RECORD_KEYS):
            raise ClosureConstructionError("closure record keys do not match the closure method")
        if (
            type(value["schema"]) is not int
            or value["schema"] != 1
            or type(value["method_version"]) is not str
            or value["method_version"] != "v4-task0b0"
            or type(value["closure_state"]) is not str
            or value["closure_state"] != ClosureState.BLOCKED_UNRESOLVED.value
        ):
            raise ClosureConstructionError("closure record cannot claim a candidate state in Task 0B1")
        expected_input_bundle_digest = _sha256_frozen(
            {
                "analysis_roots": value["analysis_root_identities"],
                "runtime_roots": value["runtime_root_identities"],
                "catalog_digests": {
                    catalog: value[record_key]
                    for catalog, record_key in RECORD_CATALOG_DIGEST_KEYS
                },
            }
        )
        closure_digest = value["closure_digest"]
        if (
            not all(is_digest(value[key]) for key in RECORD_DIGEST_KEYS)
            or type(value["nodes"]) not in (list, tuple)
            or type(value["edges"]) not in (list, tuple)
            or type(value["branch_records"]) not in (list, tuple)
            or value["nodes"]
            or value["edges"]
            or value["branch_records"]
            or type(value["unresolved"]) not in (list, tuple)
            or len(value["unresolved"]) != 1
            or not identity(value["constructor_identity"], "synthetic-constructor")
            or not identity(value["parser_identity"], "synthetic-parser")
            or not platform(value["target_platform"])
            or not budget(value["budgets"])
            or not roots(
                value["analysis_root_identities"],
                "analysis_source",
                ("sealed_component", "runtime_library"),
                len(REQUIRED_ANALYSIS_ROOTS),
                len(REQUIRED_ANALYSIS_ROOTS),
            )
            or not roots(
                value["runtime_root_identities"],
                "session_entrypoint",
                ("same_namespace_pre_ack_child_post_owner",),
                0,
                TASK0B1_RUNTIME_ROOTS_MAX,
            )
            or value["input_bundle_digest"] != expected_input_bundle_digest
            or closure_digest != _sha256_frozen(
                {key: item for key, item in value.items() if key != "closure_digest"}
            )
        ):
            raise ClosureConstructionError("closure record digest is invalid")
        unresolved = value["unresolved"][0]
        if (
            not isinstance(unresolved, Mapping)
            or set(unresolved) != set(BLOCKED_UNRESOLVED_KEYS)
            or type(unresolved["code"]) is not str
            or unresolved["code"] != "runtime_session_entrypoint_unresolved"
            or type(unresolved["role"]) is not str
            or unresolved["role"] != "same_namespace_pre_ack_child_post_owner"
            or type(unresolved["analysis_root_ids"]) not in (list, tuple)
            or not all(type(root_id) is str for root_id in unresolved["analysis_root_ids"])
            or tuple(unresolved["analysis_root_ids"]) != tuple(
                root["id"] for root in value["analysis_root_identities"]
            )
            or not isinstance(unresolved["evidence"], Mapping)
            or set(unresolved["evidence"]) != set(BLOCKED_EVIDENCE_KEYS)
            or type(unresolved["evidence"]["stage"]) is not str
            or unresolved["evidence"]["stage"] != "task0b1-author-only"
            or type(unresolved["evidence"]["runtime_root_count"]) is not int
            or unresolved["evidence"]["runtime_root_count"] != len(value["runtime_root_identities"])
            or type(unresolved["evidence"]["graph_construction"]) is not str
            or unresolved["evidence"]["graph_construction"] != "unavailable"
        ):
            raise ClosureConstructionError("closure record blocked state is invalid")
        object.__setattr__(self, "record", value)


def canonical_json_bytes(value: object) -> bytes:
    """Encode finite JSON data in the method's deterministic wire form."""
    return _canonical_json_bytes_from_frozen(_freeze_static_data(value))


def sha256_canonical(value: object) -> str:
    """Return the lowercase SHA-256 for canonical closure data."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_input_bundle(path: str) -> ClosureInputBundle:
    """Refuse ambient pathname loading until Task 0B2 supplies retained directory FDs."""
    if type(path) is not str or not path:
        raise ClosureConstructionError("input bundle path must be a nonempty string")
    raise ClosureConstructionError("Task 0B1 does not authorize input-bundle file loading")


def construct_closure(input_bundle: ClosureInputBundle) -> ClosureRecord:
    """Return only a full blocked record until a reviewed session and graph builder exist."""
    if not isinstance(input_bundle, ClosureInputBundle):
        raise ClosureConstructionError("input bundle must be a ClosureInputBundle")
    bundle = input_bundle.bundle
    if set(bundle) != set(BUNDLE_KEYS):
        raise ClosureConstructionError("input bundle keys do not match the closure method")
    if (
        type(bundle["schema"]) is not int
        or bundle["schema"] != 1
        or type(bundle["method_version"]) is not str
        or bundle["method_version"] != "v4-task0b0"
    ):
        raise ClosureConstructionError("input bundle version is not supported")
    def digest(value: object) -> bool:
        return (
            type(value) is str
            and len(value) == 64
            and all(character in HEX for character in value)
        )

    for key in ("method_spec_sha256", "task0a_source_component_digest"):
        if not digest(bundle[key]):
            raise ClosureConstructionError("input bundle digest is invalid")
    for key, expected_kind in (
        ("constructor_identity", "synthetic-constructor"),
        ("parser_identity", "synthetic-parser"),
    ):
        identity = bundle[key]
        if (
            not isinstance(identity, Mapping)
            or set(identity) != set(IDENTITY_KEYS)
            or type(identity["kind"]) is not str
            or identity["kind"] != expected_kind
            or not all(32 <= ord(character) <= 126 for character in identity["kind"])
            or not 1 <= len(identity["kind"]) <= 64
            or type(identity["raw_path"]) is not str
            or not (
                _is_synthetic_path(identity["raw_path"])
            )
            or not all(32 <= ord(character) <= 126 for character in identity["raw_path"])
            or not 1 <= len(identity["raw_path"]) <= 1024
            or type(identity["mode"]) is not int
            or not 0 <= identity["mode"] <= 0o177777
            or type(identity["device"]) is not int
            or not 1 <= identity["device"] <= 9223372036854775807
            or type(identity["inode"]) is not int
            or not 1 <= identity["inode"] <= 9223372036854775807
            or type(identity["byte_size"]) is not int
            or not 0 <= identity["byte_size"] <= 9223372036854775807
            or not digest(identity["sha256"])
            or type(identity["version"]) is not str
            or not all(32 <= ord(character) <= 126 for character in identity["version"])
            or not 1 <= len(identity["version"]) <= 128
        ):
            raise ClosureConstructionError("input bundle producer identity is invalid")
    target_platform = bundle["target_platform"]
    if (
        not isinstance(target_platform, Mapping)
        or set(target_platform) != {"architecture", "system"}
        or any(
            type(target_platform[key]) is not str
            or not all(32 <= ord(character) <= 126 for character in target_platform[key])
            or not 1 <= len(target_platform[key]) <= 128
            for key in ("architecture", "system")
        )
    ):
        raise ClosureConstructionError("input bundle target platform is invalid")
    budgets = bundle["budgets"]
    if (
        not isinstance(budgets, Mapping)
        or set(budgets) != {"maximum_edges", "maximum_nodes"}
        or any(
            isinstance(budgets[key], bool)
            or not isinstance(budgets[key], int)
            or budgets[key] < 0
            for key in ("maximum_edges", "maximum_nodes")
        )
    ):
        raise ClosureConstructionError("input bundle budgets are invalid")
    catalogs = bundle["catalogs"]
    if not isinstance(catalogs, Mapping) or set(catalogs) != set(CATALOG_NAMES):
        raise ClosureConstructionError("input bundle catalog names are not closed")
    catalog_digests: dict[str, str] = {}
    for name in CATALOG_NAMES:
        catalog = catalogs[name]
        if (
            not isinstance(catalog, Mapping)
            or set(catalog) != {"schema", "kind", "records"}
            or type(catalog["schema"]) is not int
            or catalog["schema"] != 1
            or type(catalog["kind"]) is not str
            or catalog["kind"] != name
            or not isinstance(catalog["records"], tuple)
            or catalog["records"]
        ):
            raise ClosureConstructionError("Task 0B1 accepts only closed empty catalog vectors")
        catalog_digests[name] = _sha256_frozen(catalog)

    root_ids: set[str] = set()
    root_modules: dict[str, str] = {}

    def roots(
        value: object,
        kind: str,
        allowed_roles: tuple[str, ...],
        minimum: int,
        maximum: int,
    ) -> tuple[Mapping[str, object], ...]:
        if not isinstance(value, tuple) or not minimum <= len(value) <= maximum:
            raise ClosureConstructionError("root collection is invalid")
        result: list[Mapping[str, object]] = []
        for root in value:
            if not isinstance(root, Mapping) or set(root) != set(ROOT_KEYS):
                raise ClosureConstructionError("root shape is invalid")
            root_id = root["id"]
            module = root["module"]
            digest = root["sha256"]
            if (
                type(root_id) is not str
                or not root_id
                or len(root_id) > 128
                or root_id[0] not in "abcdefghijklmnopqrstuvwxyz0123456789"
                or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in root_id)
                or type(module) is not str
                or not module
                or len(module) > 256
                or any(
                    not part
                    or part[0] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
                    or any(
                        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
                        for character in part[1:]
                    )
                    for part in module.split(".")
                )
                or type(digest) is not str
                or len(digest) != 64
                or any(char not in HEX for char in digest)
                or type(root["kind"]) is not str
                or root["kind"] != kind
                or type(root["role"]) is not str
                or root["role"] not in allowed_roles
                or len(root["role"]) > 128
            ):
                raise ClosureConstructionError("root identity is invalid")
            if root_id in root_ids or (
                module in root_modules and root_modules[module] != digest
            ):
                raise ClosureConstructionError("root identity conflicts")
            root_ids.add(root_id)
            root_modules[module] = digest
            result.append(root)
        if kind == "analysis_source" and tuple(
            (root["module"], root["role"]) for root in result
        ) != REQUIRED_ANALYSIS_ROOTS:
            raise ClosureConstructionError("analysis root set is not the sealed Task 0B1 set")
        return tuple(result)

    analysis_roots = roots(
        bundle["analysis_roots"],
        "analysis_source",
        ("sealed_component", "runtime_library"),
        len(REQUIRED_ANALYSIS_ROOTS),
        len(REQUIRED_ANALYSIS_ROOTS),
    )
    runtime_roots = roots(
        bundle["runtime_roots"],
        "session_entrypoint",
        ("same_namespace_pre_ack_child_post_owner",),
        0,
        TASK0B1_RUNTIME_ROOTS_MAX,
    )
    input_bundle_digest = _sha256_frozen(
        {
            "analysis_roots": analysis_roots,
            "runtime_roots": runtime_roots,
            "catalog_digests": catalog_digests,
        }
    )
    record = {
        "schema": bundle["schema"],
        "method_version": bundle["method_version"],
        "method_spec_sha256": bundle["method_spec_sha256"],
        "constructor_identity": bundle["constructor_identity"],
        "parser_identity": bundle["parser_identity"],
        "resolver_policy_digest": catalog_digests["resolver_policy"],
        "resource_policy_digest": catalog_digests["resource_policy"],
        "interpreter_module_registry_digest": catalog_digests["interpreter_module_registry"],
        "native_effect_catalog_digest": catalog_digests["native_effect_catalog"],
        "frozen_effect_catalog_digest": catalog_digests["frozen_effect_catalog"],
        "virtual_resource_catalog_digest": catalog_digests["virtual_resource_catalog"],
        "source_effect_catalog_digest": catalog_digests["source_effect_catalog"],
        "startup_model_digest": catalog_digests["startup_model"],
        "input_bundle_digest": input_bundle_digest,
        "target_platform": bundle["target_platform"],
        "task0a_source_component_digest": bundle["task0a_source_component_digest"],
        "analysis_root_identities": analysis_roots,
        "runtime_root_identities": runtime_roots,
        "module_catalog_digest": catalog_digests["module_catalog"],
        "elf_catalog_digest": catalog_digests["elf_catalog"],
        "branch_policy_digest": catalog_digests["branch_policy"],
        "nodes": [],
        "edges": [],
        "branch_records": [],
        "unresolved": [
            {
                "code": "runtime_session_entrypoint_unresolved",
                "role": "same_namespace_pre_ack_child_post_owner",
                "analysis_root_ids": [root["id"] for root in analysis_roots],
                "evidence": {
                    "stage": "task0b1-author-only",
                    "runtime_root_count": len(runtime_roots),
                    "graph_construction": "unavailable",
                },
            }
        ],
        "budgets": bundle["budgets"],
        "closure_state": ClosureState.BLOCKED_UNRESOLVED.value,
    }
    record["closure_digest"] = _sha256_frozen(record)
    return ClosureRecord(record=_normalise_frozen(record))
