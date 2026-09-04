"""Pure, synthetic admission tests for Task 0B4b-admission-pure."""
from __future__ import annotations

import hashlib
import importlib
import json
import types
import unittest

from tests.test_reaper_v4_task0b4b_static_contract import assert_b4b_source_contract
from tools import reaper_v4_protocol as protocol


NAMESPACE = "native-vst3-probe-v4-scan-isolated"
HEX = {
    "input_a": "1" * 64,
    "input_b": "2" * 64,
    "runtime": "3" * 64,
    "run_input": "4" * 64,
    "fixture": "5" * 64,
    "bwrap": "6" * 64,
    "authority": "7" * 64,
    "fixture_evidence": "8" * 64,
    "source": "9" * 64,
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _base_config(inputs: dict[str, str]) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": 1,
        "namespace": NAMESPACE,
        "nonce": "0123456789abcdef0123456789abcdef",
        "config_sha256": "0" * 64,
        "inputs": inputs,
    }
    value["config_sha256"] = protocol.config_sha256(value)
    return value


def _valid_config() -> dict[str, object]:
    direct = {"fixture_input_a": HEX["input_a"], "fixture_input_b": HEX["input_b"]}
    user_namespace: dict[str, object] = {
        "policy_sha256": "0" * 64,
        "effective_uid": 1000,
        "effective_gid": 1000,
        "uid_map": [{"inside_id": 0, "outside_id": 1000, "length": 2001}],
        "gid_map": [{"inside_id": 0, "outside_id": 1000, "length": 2001}],
        "setgroups": "deny",
    }
    user_namespace["policy_sha256"] = _sha256({
        "effective_uid": user_namespace["effective_uid"],
        "effective_gid": user_namespace["effective_gid"],
        "uid_map": user_namespace["uid_map"],
        "gid_map": user_namespace["gid_map"],
        "setgroups": user_namespace["setgroups"],
    })
    inherited_fds = [
        {"fd": 0, "kind": "pipe", "role": "ack_input"},
        {"fd": 1, "kind": "pipe", "role": "receipt_output"},
        {"fd": 2, "kind": "pipe", "role": "diagnostic_output"},
    ]
    descriptor_policy = {
        "fd_policy_sha256": _sha256({"inherited_fds": inherited_fds}),
        "inherited_fds": inherited_fds,
    }
    mounts = [
        {"path": "/", "filesystem_type": "tmpfs", "readonly": False},
        {"path": "/home/vst/scan", "filesystem_type": "tmpfs", "readonly": True},
        {"path": "/home/vst/scan/a/plugin.vst3", "filesystem_type": "bind", "readonly": True},
        {"path": "/home/vst/scan/b/plugin.vst3", "filesystem_type": "bind", "readonly": True},
    ]
    control_visibility = {
        "mount_policy_sha256": _sha256({"namespace_root_kind": "private_tmpfs_root", "mounts": mounts}),
        "namespace_root_kind": "private_tmpfs_root",
        "mounts": mounts,
    }
    environment = {
        "DISPLAY": ":0",
        "HOME": "/home/vst",
        "LANG": "C",
        "PWD": "/home/vst",
        "TZ": "UTC",
        "XAUTHORITY": "/run/m3-v4/Xauthority",
    }
    namespace_expectations: dict[str, object] = {
        "home": "/home/vst",
        "pwd": "/home/vst",
        "cwd": "/home/vst",
        "environment": environment,
        "user_namespace": user_namespace,
        "x11_identity": {
            "display": ":0",
            "display_number": 0,
            "screen": 0,
            "protocol": "MIT-MAGIC-COOKIE-1",
            "authority": {
                "path": "/run/m3-v4/Xauthority",
                "source_device": 11,
                "source_inode": 12,
                "destination_mode": 384,
                "destination_size": 32,
                "sha256": HEX["authority"],
            },
            "socket": {
                "path": "/tmp/.X11-unix/X0",
                "kind": "unix_socket",
                "uid": 1000,
                "gid": 1000,
                "mode": 511,
                "device": 13,
                "inode": 14,
            },
        },
        "measurement_root": {"path": "/run/m3-v4/measurements", "device": 15, "inode": 16},
        "measurement_plan": {
            "resources": ["display"],
            "expected": {"display": {"mode": 292, "size": 0}},
        },
        "private_tree": {
            "home_mount": {"path": "/home/vst", "filesystem_type": "tmpfs", "mode": 448, "writable": True},
            "empty_directories": [".vst", ".vst3"],
        },
        "scan_root": {
            "path": "/home/vst/scan",
            "entries": [
                {"relative_path": "a/plugin.vst3", "input_name": "fixture_input_a", "mode": 292, "size": 1, "sha256": HEX["input_a"]},
                {"relative_path": "b/plugin.vst3", "input_name": "fixture_input_b", "mode": 292, "size": 2, "sha256": HEX["input_b"]},
            ],
            "mount_points": [
                {"relative_path": ".", "readonly": True},
                {"relative_path": "a/plugin.vst3", "readonly": True},
                {"relative_path": "b/plugin.vst3", "readonly": True},
            ],
        },
        "descriptor_policy": descriptor_policy,
        "control_visibility": control_visibility,
    }
    namespace_policy = _sha256(namespace_expectations)
    bwrap = {"path": "/usr/bin/bwrap", "version": "0.10.0", "argv_sha256": HEX["bwrap"]}
    child = {
        "argv": ["/usr/bin/true"],
        "cwd": "/home/vst",
        "environment": dict(environment),
        "timeout_ms": 30000,
    }
    limits = {
        "pre_deadline_ms": 5000,
        "ack_deadline_ms": 5000,
        "post_deadline_ms": 5000,
        "diagnostic_max_bytes": 1024,
        "max_frame_bytes": 2064,
        "child_timeout_ms": 30000,
    }
    certificate_common: dict[str, object] = {
        "schema": 1,
        "certificate_sha256": "0" * 64,
        "fixture_evidence_sha256": HEX["fixture_evidence"],
        "session_source_sha256": HEX["source"],
        "runtime_manifest_sha256": HEX["runtime"],
        "fixture_manifest_sha256": HEX["fixture"],
        "bwrap_path": bwrap["path"],
        "bwrap_version": bwrap["version"],
        "bwrap_argv_sha256": bwrap["argv_sha256"],
        "namespace_policy_sha256": namespace_policy,
        "mount_policy_sha256": control_visibility["mount_policy_sha256"],
        "fd_policy_sha256": descriptor_policy["fd_policy_sha256"],
        "kernel_release": "6.0.0",
        "boot_id": "01234567-89ab-cdef-0123-456789abcdef",
        "uid": 2000,
        "user_namespace_policy_sha256": user_namespace["policy_sha256"],
    }
    certificates: dict[str, object] = {}
    for kind, result in (
        ("proc_ptrace_barrier", {"proc_receipt_blocked": True, "proc_mem_blocked": True}),
        ("control_visibility", {"control_root_absent": True, "mount_mutation_blocked": True}),
    ):
        certificate = dict(certificate_common)
        certificate["kind"] = kind
        certificate["result"] = result
        certificate["certificate_sha256"] = _sha256({key: item for key, item in certificate.items() if key != "certificate_sha256"})
        certificates[kind] = certificate
    value: dict[str, object] = {
        "schema": 1,
        "namespace": NAMESPACE,
        "session_config_sha256": "0" * 64,
        "base_config": {},
        "session_policy_sha256": "0" * 64,
        "direct_input_digests": direct,
        "row": {"sample_rate_hz": 44100, "block_size": 32},
        "runtime_manifest_sha256": HEX["runtime"],
        "run_input_manifest_sha256": HEX["run_input"],
        "fixture_manifest_sha256": HEX["fixture"],
        "namespace_policy_sha256": namespace_policy,
        "fixture_certificates": certificates,
        "bwrap": bwrap,
        "namespace_expectations": namespace_expectations,
        "child": child,
        "limits": limits,
    }
    policy = {
        key: value[key]
        for key in (
            "row", "direct_input_digests", "runtime_manifest_sha256", "run_input_manifest_sha256",
            "fixture_manifest_sha256", "namespace_policy_sha256", "fixture_certificates", "bwrap",
            "namespace_expectations", "child", "limits",
        )
    }
    value["session_policy_sha256"] = _sha256(policy)
    value["base_config"] = _base_config({**direct, "session_policy": value["session_policy_sha256"]})
    value["session_config_sha256"] = _sha256({key: item for key, item in value.items() if key != "session_config_sha256"})
    return value


def _forged_config(session: object, value: dict[str, object]) -> object:
    config = object.__new__(session.SessionConfig)
    object.__setattr__(config, "data", types.MappingProxyType(value))
    return config


def _copy_config(value: dict[str, object]) -> dict[str, object]:
    return json.loads(_canonical(value).decode("ascii"))


def _refresh_policy_identity(value: dict[str, object]) -> None:
    policy = {
        key: value[key]
        for key in (
            "row", "direct_input_digests", "runtime_manifest_sha256", "run_input_manifest_sha256",
            "fixture_manifest_sha256", "namespace_policy_sha256", "fixture_certificates", "bwrap",
            "namespace_expectations", "child", "limits",
        )
    }
    value["session_policy_sha256"] = _sha256(policy)
    value["base_config"] = _base_config({
        **value["direct_input_digests"],
        "session_policy": value["session_policy_sha256"],
    })
    value["session_config_sha256"] = _sha256({
        key: item for key, item in value.items() if key != "session_config_sha256"
    })


def _refresh_certificates_and_policy(value: dict[str, object]) -> None:
    expectations = value["namespace_expectations"]
    user_namespace = expectations["user_namespace"]
    descriptor_policy = expectations["descriptor_policy"]
    control_visibility = expectations["control_visibility"]
    value["namespace_policy_sha256"] = _sha256(expectations)
    for certificate in value["fixture_certificates"].values():
        certificate["namespace_policy_sha256"] = value["namespace_policy_sha256"]
        certificate["mount_policy_sha256"] = control_visibility["mount_policy_sha256"]
        certificate["fd_policy_sha256"] = descriptor_policy["fd_policy_sha256"]
        certificate["user_namespace_policy_sha256"] = user_namespace["policy_sha256"]
        certificate["certificate_sha256"] = _sha256({
            key: item for key, item in certificate.items() if key != "certificate_sha256"
        })
    _refresh_policy_identity(value)


def _refresh_all_identities(value: dict[str, object]) -> None:
    expectations = value["namespace_expectations"]
    user_namespace = expectations["user_namespace"]
    user_namespace["policy_sha256"] = _sha256({
        "effective_uid": user_namespace["effective_uid"],
        "effective_gid": user_namespace["effective_gid"],
        "uid_map": user_namespace["uid_map"],
        "gid_map": user_namespace["gid_map"],
        "setgroups": user_namespace["setgroups"],
    })
    descriptor_policy = expectations["descriptor_policy"]
    descriptor_policy["fd_policy_sha256"] = _sha256({
        "inherited_fds": descriptor_policy["inherited_fds"],
    })
    control_visibility = expectations["control_visibility"]
    control_visibility["mount_policy_sha256"] = _sha256({
        "namespace_root_kind": control_visibility["namespace_root_kind"],
        "mounts": control_visibility["mounts"],
    })
    value["namespace_policy_sha256"] = _sha256(expectations)
    bwrap = value["bwrap"]
    for certificate in value["fixture_certificates"].values():
        certificate["runtime_manifest_sha256"] = value["runtime_manifest_sha256"]
        certificate["fixture_manifest_sha256"] = value["fixture_manifest_sha256"]
        certificate["bwrap_path"] = bwrap["path"]
        certificate["bwrap_version"] = bwrap["version"]
        certificate["bwrap_argv_sha256"] = bwrap["argv_sha256"]
        certificate["namespace_policy_sha256"] = value["namespace_policy_sha256"]
        certificate["mount_policy_sha256"] = control_visibility["mount_policy_sha256"]
        certificate["fd_policy_sha256"] = descriptor_policy["fd_policy_sha256"]
        certificate["user_namespace_policy_sha256"] = user_namespace["policy_sha256"]
        certificate["certificate_sha256"] = _sha256({
            key: item for key, item in certificate.items() if key != "certificate_sha256"
        })
    _refresh_policy_identity(value)


def _session_module() -> object:
    assert_b4b_source_contract()
    return importlib.import_module("tools.reaper_v4_session")


class Task0B4bAdmissionTests(unittest.TestCase):
    def test_admits_a_fresh_unaliased_snapshot(self) -> None:
        session = _session_module()
        backing = _valid_config()
        admitted = session._admit_session_config(_forged_config(session, backing))
        self.assertIs(type(admitted), session.SessionConfig)
        self.assertIs(type(admitted.data), types.MappingProxyType)
        before = _canonical(session._materialize_exact_builtins(admitted.data))
        backing["child"]["cwd"] = "/mutated"
        backing["namespace_expectations"]["environment"]["HOME"] = "/mutated"
        self.assertEqual(_canonical(session._materialize_exact_builtins(admitted.data)), before)
        projection = session._child_spec_projection(admitted.data)
        self.assertEqual(projection, {
            "argv": ("/usr/bin/true",),
            "cwd": "/home/vst",
            "environment": (
                ("DISPLAY", ":0"), ("HOME", "/home/vst"), ("LANG", "C"),
                ("PWD", "/home/vst"), ("TZ", "UTC"), ("XAUTHORITY", "/run/m3-v4/Xauthority"),
            ),
            "timeout_ms": 30000,
        })

    def test_rejects_unfrozen_or_wrong_config_objects(self) -> None:
        session = _session_module()
        backing = _valid_config()
        with self.assertRaises(session.SessionError):
            session._admit_session_config(backing)
        forged = object.__new__(session.SessionConfig)
        object.__setattr__(forged, "data", backing)
        with self.assertRaises(session.SessionError):
            session._admit_session_config(forged)
        missing_data = object.__new__(session.SessionConfig)
        with self.assertRaises(session.SessionError):
            session._admit_session_config(missing_data)

    def test_rejects_named_closed_schema_and_relation_mutations(self) -> None:
        session = _session_module()

        def extra_top_level(value: dict[str, object]) -> None:
            value["unexpected"] = 1
            value["session_config_sha256"] = _sha256({
                key: item for key, item in value.items() if key != "session_config_sha256"
            })

        def base_inputs(value: dict[str, object]) -> None:
            value["base_config"]["inputs"]["unexpected"] = "a" * 64
            value["base_config"]["config_sha256"] = protocol.config_sha256(value["base_config"])
            value["session_config_sha256"] = _sha256({
                key: item for key, item in value.items() if key != "session_config_sha256"
            })

        def fixed_row(value: dict[str, object]) -> None:
            value["row"]["block_size"] = 64
            _refresh_policy_identity(value)

        def session_policy(value: dict[str, object]) -> None:
            value["session_policy_sha256"] = "f" * 64
            value["base_config"] = _base_config({
                **value["direct_input_digests"], "session_policy": value["session_policy_sha256"],
            })
            value["session_config_sha256"] = _sha256({
                key: item for key, item in value.items() if key != "session_config_sha256"
            })

        def namespace_policy(value: dict[str, object]) -> None:
            value["namespace_policy_sha256"] = "e" * 64
            _refresh_policy_identity(value)

        def child_environment(value: dict[str, object]) -> None:
            value["child"]["environment"]["HOME"] = "/other"
            _refresh_policy_identity(value)

        def child_argv(value: dict[str, object]) -> None:
            value["child"]["argv"] = ["relative-program"]
            _refresh_policy_identity(value)

        def fixed_limit(value: dict[str, object]) -> None:
            value["limits"]["ack_deadline_ms"] = True
            _refresh_policy_identity(value)

        def certificate_result(value: dict[str, object]) -> None:
            certificate = value["fixture_certificates"]["proc_ptrace_barrier"]
            certificate["result"]["proc_mem_blocked"] = False
            certificate["certificate_sha256"] = _sha256({
                key: item for key, item in certificate.items() if key != "certificate_sha256"
            })
            _refresh_policy_identity(value)

        def invalid_direct_input(value: dict[str, object]) -> None:
            digest = value["direct_input_digests"].pop("fixture_input_a")
            value["direct_input_digests"]["SessionPolicy"] = digest
            _refresh_policy_identity(value)

        def scan_digest(value: dict[str, object]) -> None:
            value["namespace_expectations"]["scan_root"]["entries"][0]["sha256"] = "d" * 64
            _refresh_certificates_and_policy(value)

        def descriptor_order(value: dict[str, object]) -> None:
            descriptors = value["namespace_expectations"]["descriptor_policy"]
            descriptors["inherited_fds"][0], descriptors["inherited_fds"][1] = (
                descriptors["inherited_fds"][1], descriptors["inherited_fds"][0],
            )
            descriptors["fd_policy_sha256"] = _sha256({"inherited_fds": descriptors["inherited_fds"]})
            _refresh_certificates_and_policy(value)

        def certificate_uid(value: dict[str, object]) -> None:
            certificate = value["fixture_certificates"]["control_visibility"]
            certificate["uid"] = 2001
            certificate["certificate_sha256"] = _sha256({
                key: item for key, item in certificate.items() if key != "certificate_sha256"
            })
            _refresh_policy_identity(value)

        def x11_environment_binding(value: dict[str, object]) -> None:
            value["namespace_expectations"]["x11_identity"]["display"] = ":1"
            value["namespace_expectations"]["x11_identity"]["display_number"] = 1
            value["namespace_expectations"]["x11_identity"]["socket"]["path"] = "/tmp/.X11-unix/X1"
            _refresh_certificates_and_policy(value)

        def extra_scan_mount(value: dict[str, object]) -> None:
            mounts = value["namespace_expectations"]["control_visibility"]["mounts"]
            mounts.append({"path": "/home/vst/scan/c/extra.vst3", "filesystem_type": "bind", "readonly": True})
            control = value["namespace_expectations"]["control_visibility"]
            control["mount_policy_sha256"] = _sha256({
                "namespace_root_kind": control["namespace_root_kind"], "mounts": mounts,
            })
            _refresh_certificates_and_policy(value)

        def child_environment_order(value: dict[str, object]) -> None:
            environment = value["child"]["environment"]
            value["child"]["environment"] = {
                "TZ": environment["TZ"], "DISPLAY": environment["DISPLAY"],
                "HOME": environment["HOME"], "LANG": environment["LANG"],
                "PWD": environment["PWD"], "XAUTHORITY": environment["XAUTHORITY"],
            }
            _refresh_policy_identity(value)

        cases = (
            ("top-level", extra_top_level),
            ("base-input-union", base_inputs),
            ("row", fixed_row),
            ("session-policy", session_policy),
            ("namespace-policy", namespace_policy),
            ("child-environment", child_environment),
            ("child-argv", child_argv),
            ("fixed-limit", fixed_limit),
            ("certificate-result", certificate_result),
            ("direct-input-name", invalid_direct_input),
            ("scan-entry-digest", scan_digest),
            ("descriptor-order", descriptor_order),
            ("certificate-uid", certificate_uid),
            ("x11-environment-binding", x11_environment_binding),
            ("extra-scan-mount", extra_scan_mount),
            ("child-environment-order", child_environment_order),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                value = _copy_config(_valid_config())
                mutate(value)
                with self.assertRaises(session.SessionError):
                    session._admit_session_config(_forged_config(session, value))

    def test_rejects_additional_named_nested_mutations(self) -> None:
        session = _session_module()

        def nested_key(value: dict[str, object]) -> None:
            value["namespace_expectations"]["measurement_root"]["unexpected"] = 1
            _refresh_all_identities(value)

        def boolean_mode(value: dict[str, object]) -> None:
            value["namespace_expectations"]["x11_identity"]["authority"]["destination_mode"] = True
            _refresh_all_identities(value)

        def uid_overlap(value: dict[str, object]) -> None:
            value["namespace_expectations"]["user_namespace"]["uid_map"].append({
                "inside_id": 1000, "outside_id": 4000, "length": 2,
            })
            _refresh_all_identities(value)

        def gid_coverage(value: dict[str, object]) -> None:
            value["namespace_expectations"]["user_namespace"]["effective_gid"] = 4000
            _refresh_all_identities(value)

        def bwrap_path(value: dict[str, object]) -> None:
            value["bwrap"]["path"] = "relative-bwrap"
            _refresh_all_identities(value)

        def measurement_expected(value: dict[str, object]) -> None:
            value["namespace_expectations"]["measurement_plan"]["expected"]["extra"] = {"mode": 292, "size": 0}
            _refresh_all_identities(value)

        def private_tree(value: dict[str, object]) -> None:
            value["namespace_expectations"]["private_tree"]["empty_directories"] = [".vst"]
            _refresh_all_identities(value)

        def authority_bound(value: dict[str, object]) -> None:
            value["namespace_expectations"]["x11_identity"]["authority"]["destination_size"] = 65537
            _refresh_all_identities(value)

        def certificate_digest(value: dict[str, object]) -> None:
            value["fixture_certificates"]["control_visibility"]["certificate_sha256"] = "f" * 64
            _refresh_policy_identity(value)

        def certificate_kind(value: dict[str, object]) -> None:
            certificate = value["fixture_certificates"]["proc_ptrace_barrier"]
            certificate["kind"] = "unknown"
            certificate["certificate_sha256"] = _sha256({
                key: item for key, item in certificate.items() if key != "certificate_sha256"
            })
            _refresh_policy_identity(value)

        def certificate_binding(value: dict[str, object]) -> None:
            certificate = value["fixture_certificates"]["control_visibility"]
            certificate["runtime_manifest_sha256"] = "a" * 64
            certificate["certificate_sha256"] = _sha256({
                key: item for key, item in certificate.items() if key != "certificate_sha256"
            })
            _refresh_policy_identity(value)

        def certificate_boot_id(value: dict[str, object]) -> None:
            certificate = value["fixture_certificates"]["proc_ptrace_barrier"]
            certificate["boot_id"] = "not-a-uuid"
            certificate["certificate_sha256"] = _sha256({
                key: item for key, item in certificate.items() if key != "certificate_sha256"
            })
            _refresh_policy_identity(value)

        def scan_prefix(value: dict[str, object]) -> None:
            entries = value["namespace_expectations"]["scan_root"]["entries"]
            entries[0]["relative_path"] = "a"
            entries[1]["relative_path"] = "a/plugin.vst3"
            _refresh_all_identities(value)

        def scan_size(value: dict[str, object]) -> None:
            value["namespace_expectations"]["scan_root"]["entries"][0]["size"] = 16777217
            _refresh_all_identities(value)

        def mount_order(value: dict[str, object]) -> None:
            mounts = value["namespace_expectations"]["control_visibility"]["mounts"]
            mounts[1], mounts[2] = mounts[2], mounts[1]
            _refresh_all_identities(value)

        def environment_key(value: dict[str, object]) -> None:
            del value["namespace_expectations"]["environment"]["LANG"]
            _refresh_all_identities(value)

        def direct_input_count(value: dict[str, object]) -> None:
            value["direct_input_digests"] = {}
            _refresh_policy_identity(value)

        def direct_input_digest(value: dict[str, object]) -> None:
            value["direct_input_digests"]["fixture_input_a"] = "not-a-digest"
            _refresh_policy_identity(value)

        def top_level_digest(value: dict[str, object]) -> None:
            value["session_config_sha256"] = "f" * 64

        def user_policy_digest(value: dict[str, object]) -> None:
            value["namespace_expectations"]["user_namespace"]["policy_sha256"] = "a" * 64
            _refresh_certificates_and_policy(value)

        def descriptor_policy_digest(value: dict[str, object]) -> None:
            value["namespace_expectations"]["descriptor_policy"]["fd_policy_sha256"] = "b" * 64
            _refresh_certificates_and_policy(value)

        def mount_policy_digest(value: dict[str, object]) -> None:
            value["namespace_expectations"]["control_visibility"]["mount_policy_sha256"] = "c" * 64
            _refresh_certificates_and_policy(value)

        def socket_kind(value: dict[str, object]) -> None:
            value["namespace_expectations"]["x11_identity"]["socket"]["kind"] = "regular_file"
            _refresh_all_identities(value)

        def x11_omitted_screen(value: dict[str, object]) -> None:
            value["namespace_expectations"]["x11_identity"]["screen"] = 1
            _refresh_all_identities(value)

        def measurement_resource(value: dict[str, object]) -> None:
            value["namespace_expectations"]["measurement_plan"]["resources"] = ["nested/resource"]
            value["namespace_expectations"]["measurement_plan"]["expected"] = {
                "nested/resource": {"mode": 292, "size": 0},
            }
            _refresh_all_identities(value)

        def private_home_mode(value: dict[str, object]) -> None:
            value["namespace_expectations"]["private_tree"]["home_mount"]["mode"] = 493
            _refresh_all_identities(value)

        def scan_mount_readonly(value: dict[str, object]) -> None:
            value["namespace_expectations"]["scan_root"]["mount_points"][0]["readonly"] = False
            _refresh_all_identities(value)

        def descriptor_role(value: dict[str, object]) -> None:
            value["namespace_expectations"]["descriptor_policy"]["inherited_fds"][2]["role"] = "wrong"
            _refresh_all_identities(value)

        def control_certificate_result(value: dict[str, object]) -> None:
            certificate = value["fixture_certificates"]["control_visibility"]
            certificate["result"]["control_root_absent"] = False
            certificate["certificate_sha256"] = _sha256({
                key: item for key, item in certificate.items() if key != "certificate_sha256"
            })
            _refresh_policy_identity(value)

        def certificate_fixture_binding(value: dict[str, object]) -> None:
            certificate = value["fixture_certificates"]["proc_ptrace_barrier"]
            certificate["fixture_manifest_sha256"] = "d" * 64
            certificate["certificate_sha256"] = _sha256({
                key: item for key, item in certificate.items() if key != "certificate_sha256"
            })
            _refresh_policy_identity(value)

        def child_timeout(value: dict[str, object]) -> None:
            value["child"]["timeout_ms"] = 1
            _refresh_policy_identity(value)

        cases = (
            ("nested-measurement-root-key", nested_key),
            ("boolean-authority-mode", boolean_mode),
            ("uid-map-overlap", uid_overlap),
            ("gid-map-effective-coverage", gid_coverage),
            ("bwrap-path", bwrap_path),
            ("measurement-expected-members", measurement_expected),
            ("private-tree-empty-directories", private_tree),
            ("authority-size-bound", authority_bound),
            ("certificate-self-digest", certificate_digest),
            ("certificate-kind", certificate_kind),
            ("certificate-runtime-binding", certificate_binding),
            ("certificate-boot-id", certificate_boot_id),
            ("scan-entry-prefix", scan_prefix),
            ("scan-entry-size", scan_size),
            ("mount-order", mount_order),
            ("environment-exact-members", environment_key),
            ("direct-input-minimum", direct_input_count),
            ("direct-input-digest", direct_input_digest),
            ("session-config-digest", top_level_digest),
            ("user-namespace-policy-digest", user_policy_digest),
            ("descriptor-policy-digest", descriptor_policy_digest),
            ("mount-policy-digest", mount_policy_digest),
            ("x11-socket-kind", socket_kind),
            ("x11-omitted-nonzero-screen", x11_omitted_screen),
            ("measurement-resource-path", measurement_resource),
            ("private-home-mode", private_home_mode),
            ("scan-mount-readonly", scan_mount_readonly),
            ("descriptor-role", descriptor_role),
            ("control-certificate-result", control_certificate_result),
            ("certificate-fixture-binding", certificate_fixture_binding),
            ("child-timeout", child_timeout),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                value = _copy_config(_valid_config())
                mutate(value)
                with self.assertRaises(session.SessionError):
                    session._admit_session_config(_forged_config(session, value))

        for key in (
            "pre_deadline_ms", "ack_deadline_ms", "post_deadline_ms",
            "diagnostic_max_bytes", "max_frame_bytes", "child_timeout_ms",
        ):
            with self.subTest(label=f"fixed-limit-{key}"):
                value = _copy_config(_valid_config())
                value["limits"][key] += 1
                _refresh_policy_identity(value)
                with self.assertRaises(session.SessionError):
                    session._admit_session_config(_forged_config(session, value))

    def test_rejects_alias_and_deep_untrusted_snapshots(self) -> None:
        session = _session_module()
        alias = _valid_config()
        alias["child"]["environment"] = alias["namespace_expectations"]["environment"]
        with self.assertRaises(session.SessionError):
            session._admit_session_config(_forged_config(session, alias))
        deeply_nested: object = None
        for _ in range(17):
            deeply_nested = [deeply_nested]
        deep = _valid_config()
        deep["child"]["argv"] = deeply_nested
        with self.assertRaises(session.SessionError):
            session._admit_session_config(_forged_config(session, deep))


if __name__ == "__main__":
    unittest.main()
