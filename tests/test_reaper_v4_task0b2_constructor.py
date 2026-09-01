"""Task 0B2 data-only constructor behavior over the sealed blocked vector."""
from __future__ import annotations

import hashlib
import json
import pathlib
import unittest
from collections.abc import Mapping


ROOT = pathlib.Path(__file__).resolve().parents[1]
VECTOR = ROOT / "tests/fixtures/reaper_v4_closure/blocked-input-bundle.json"
VECTOR_SHA256 = "a71aa540857a06bced4237be5bfb08ecfb834aa333ffd8b1733ac73a60979229"
CONSTRUCTOR = ROOT / "tools/reaper_v4_closure_constructor.py"
CONSTRUCTOR_SHA256 = "2f8b1f02f5a730c70e38b6ebe06a99ec8abbd3c70a05851f66d6be6c5e2a97f7"
EXPECTED_ANALYSIS_ROOTS = (
    ("task0a-protocol", "tools.reaper_v4_protocol", "analysis_source", "sealed_component"),
    ("task0b1-receipts", "tools.reaper_v4_receipt_schema", "analysis_source", "runtime_library"),
    ("task0b1-measurements", "tools.reaper_v4_measurements", "analysis_source", "runtime_library"),
    ("task0b1-runner", "tools.reaper_v4_child_runner", "analysis_source", "runtime_library"),
)
EXPECTED_RECORD_KEYS = {
    "schema", "method_version", "method_spec_sha256", "constructor_identity",
    "parser_identity", "resolver_policy_digest", "resource_policy_digest",
    "interpreter_module_registry_digest", "native_effect_catalog_digest",
    "frozen_effect_catalog_digest", "virtual_resource_catalog_digest",
    "source_effect_catalog_digest", "startup_model_digest", "input_bundle_digest",
    "target_platform", "task0a_source_component_digest", "analysis_root_identities",
    "runtime_root_identities", "module_catalog_digest", "elf_catalog_digest",
    "branch_policy_digest", "nodes", "edges", "branch_records", "unresolved",
    "budgets", "closure_state", "closure_digest",
}
EXPECTED_CLOSURE_DIGEST = "0fdb65aa2467554f85fb21e2e570850921cb1615bfe56ebb4b1a0b5d5fb185bf"


def plain_data(item: object) -> object:
    if isinstance(item, Mapping):
        return {key: plain_data(child) for key, child in item.items()}
    if isinstance(item, (list, tuple)):
        return [plain_data(child) for child in item]
    return item


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        plain_data(value), ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def expected_record_from_bundle(bundle: dict[str, object]) -> dict[str, object]:
    """Project the sealed vector into its full blocked-record contract."""
    catalogs = bundle["catalogs"]
    assert isinstance(catalogs, dict)
    catalog_digests = {
        name: canonical_digest(catalog)
        for name, catalog in catalogs.items()
    }
    analysis_roots = bundle["analysis_roots"]
    runtime_roots = bundle["runtime_roots"]
    assert isinstance(analysis_roots, list)
    assert isinstance(runtime_roots, list)
    return {
        "schema": bundle["schema"],
        "method_version": bundle["method_version"],
        "method_spec_sha256": bundle["method_spec_sha256"],
        "constructor_identity": bundle["constructor_identity"],
        "parser_identity": bundle["parser_identity"],
        "resolver_policy_digest": catalog_digests["resolver_policy"],
        "resource_policy_digest": catalog_digests["resource_policy"],
        "interpreter_module_registry_digest": catalog_digests[
            "interpreter_module_registry"
        ],
        "native_effect_catalog_digest": catalog_digests["native_effect_catalog"],
        "frozen_effect_catalog_digest": catalog_digests["frozen_effect_catalog"],
        "virtual_resource_catalog_digest": catalog_digests[
            "virtual_resource_catalog"
        ],
        "source_effect_catalog_digest": catalog_digests["source_effect_catalog"],
        "startup_model_digest": catalog_digests["startup_model"],
        "input_bundle_digest": canonical_digest({
            "analysis_roots": analysis_roots,
            "runtime_roots": runtime_roots,
            "catalog_digests": catalog_digests,
        }),
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
        "unresolved": [{
            "code": "runtime_session_entrypoint_unresolved",
            "role": "same_namespace_pre_ack_child_post_owner",
            "analysis_root_ids": [root["id"] for root in analysis_roots],
            "evidence": {
                "stage": "task0b1-author-only",
                "runtime_root_count": len(runtime_roots),
                "graph_construction": "unavailable",
            },
        }],
        "budgets": bundle["budgets"],
        "closure_state": "BLOCKED_UNRESOLVED",
        "closure_digest": EXPECTED_CLOSURE_DIGEST,
    }


class Task0B2ConstructorTest(unittest.TestCase):
    def test_sealed_blocked_vector_constructs_the_deterministic_unresolved_record(self) -> None:
        raw = VECTOR.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), VECTOR_SHA256)
        self.assertEqual(
            hashlib.sha256(CONSTRUCTOR.read_bytes()).hexdigest(), CONSTRUCTOR_SHA256,
        )
        vector = json.loads(raw)

        from tools.reaper_v4_closure_constructor import (
            ClosureInputBundle,
            construct_closure,
        )

        first = construct_closure(ClosureInputBundle(vector["input_bundle"]))
        second = construct_closure(ClosureInputBundle(vector["input_bundle"]))
        record = first.record
        expected = expected_record_from_bundle(vector["input_bundle"])

        self.assertEqual(set(record), EXPECTED_RECORD_KEYS)
        self.assertEqual(
            tuple(
                (root["id"], root["module"], root["kind"], root["role"])
                for root in record["analysis_root_identities"]
            ),
            EXPECTED_ANALYSIS_ROOTS,
        )
        self.assertEqual(
            canonical_digest({
                key: value for key, value in expected.items()
                if key != "closure_digest"
            }),
            EXPECTED_CLOSURE_DIGEST,
        )
        self.assertEqual(plain_data(record), expected)
        self.assertEqual(record["closure_digest"], EXPECTED_CLOSURE_DIGEST)
        self.assertEqual(first.record, second.record)
        self.assertEqual(record["closure_digest"], second.record["closure_digest"])
        with self.assertRaises(TypeError):
            record["closure_state"] = "COMPLETE_FIXTURE_CANDIDATE"
        with self.assertRaises(TypeError):
            record["unresolved"][0]["code"] = "altered"
        with self.assertRaises(AttributeError):
            record["nodes"].append({})
        with self.assertRaises(AttributeError):
            record["analysis_root_identities"].append({})


if __name__ == "__main__":
    unittest.main()
