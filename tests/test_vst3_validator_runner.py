import json
import hashlib
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import run_vst3_validator as RUNNER


class Vst3ValidatorRunnerTests(unittest.TestCase):
    def create_layout(self, root: pathlib.Path, kind: str = "production"):
        contract = RUNNER.KIND_CONTRACTS[kind]
        release = root / "build/vst3/release"
        validator = release / "bin/Release/validator"
        validator.parent.mkdir(parents=True)
        validator.write_bytes(b"official validator\n")
        validator.chmod(0o755)

        bundle = release / "VST3" / contract.bundle_name
        binary = bundle / "Contents/x86_64-linux" / contract.binary_name
        moduleinfo = bundle / "Contents/Resources/moduleinfo.json"
        binary.parent.mkdir(parents=True)
        moduleinfo.parent.mkdir(parents=True)
        binary.write_bytes(b"ELF fixture\n" + contract.fuid.encode("ascii"))
        moduleinfo.write_text(
            json.dumps(
                {
                    "Factory Info": {"Vendor": "ajuntanaga"},
                    "Classes": [
                        {
                            "CID": contract.fuid,
                            "Category": "Audio Module Class",
                            "Name": contract.product_name,
                            "Sub Categories": ["Fx", "Tools"],
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        sdk_manifest = root / "third_party/vst3sdk/SHA256SUMS"
        sdk_manifest.parent.mkdir(parents=True)
        sdk_file = sdk_manifest.parent / "LICENSE.txt"
        sdk_file.write_text("fixture SDK\n", encoding="utf-8")
        sdk_manifest.write_text(
            f"{hashlib.sha256(sdk_file.read_bytes()).hexdigest()}  "
            "third_party/vst3sdk/LICENSE.txt\n",
            encoding="utf-8",
        )
        guard = root / "tools/run_guarded_native_build.py"
        guard.parent.mkdir(parents=True)
        guard.write_text("# fixture\n", encoding="utf-8")
        return release, validator, bundle, binary, moduleinfo, sdk_manifest, guard

    def patch_layout(
        self,
        root,
        release,
        validator,
        sdk_manifest,
        guard,
        results,
    ):
        return mock.patch.multiple(
            RUNNER,
            ROOT=root,
            RELEASE_ROOT=release,
            VALIDATOR=validator,
            SDK_MANIFEST=sdk_manifest,
            GUARD=guard,
            RESULT_ROOT=results,
        )

    def test_exact_kind_bundle_fuid_and_official_validator_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            values = self.create_layout(root)
            release, validator, bundle, _binary, moduleinfo, manifest, guard = values
            results = root / "results"
            with self.patch_layout(
                root, release, validator, manifest, guard, results
            ):
                self.assertEqual(RUNNER.input_errors("production", bundle), [])
                self.assertTrue(
                    any(
                        "exact probe bundle" in error
                        for error in RUNNER.input_errors("probe", bundle)
                    )
                )
                wrong = root / "elsewhere/M3_Polyphonic_Audio_to_MIDI.vst3"
                self.assertTrue(
                    any(
                        "exact production bundle" in error
                        for error in RUNNER.input_errors("production", wrong)
                    )
                )
                document = json.loads(moduleinfo.read_text(encoding="utf-8"))
                document["Classes"][0]["CID"] = RUNNER.KIND_CONTRACTS["probe"].fuid
                moduleinfo.write_text(json.dumps(document), encoding="utf-8")
                self.assertTrue(
                    any(
                        "FUID" in error
                        for error in RUNNER.input_errors("production", bundle)
                    )
                )

                document["Classes"][0]["CID"] = RUNNER.KIND_CONTRACTS[
                    "production"
                ].fuid
                trailing = json.dumps(document, indent=2)
                trailing = trailing.replace("\n  }", ",\n  }").replace(
                    "\n}", ",\n}"
                )
                moduleinfo.write_text(trailing, encoding="utf-8")
                self.assertEqual(RUNNER.input_errors("production", bundle), [])

    def test_classification_separates_plugin_failures_from_infrastructure(self):
        passed = (
            "Factory Info\nClass Info\nBus tests\nParameter tests\n"
            "State tests\nProcess tests\n"
            "Result: 120 tests passed, 0 tests failed\n"
        )
        self.assertEqual(RUNNER.classify_result(0, passed, ""), "pass")
        self.assertEqual(
            RUNNER.classify_result(
                1,
                "Result: 119 tests passed, 1 tests failed\n",
                "State Transition assertion failed\n",
            ),
            "fail",
        )
        self.assertEqual(
            RUNNER.classify_result(255, "Result: 1 tests passed, 1 tests failed\n", ""),
            "fail",
        )
        cases = (
            (-11, "", "segmentation fault"),
            (1, "", "AddressSanitizer: heap-use-after-free"),
            (124, "", "timeout"),
            (1, "", "cannot load module: No such file"),
            (1, "", "unknown validator termination"),
            (0, "Result: 1 tests passed, 0 tests failed\n", ""),
        )
        for returncode, stdout, stderr in cases:
            with self.subTest(returncode=returncode, stderr=stderr):
                self.assertEqual(
                    RUNNER.classify_result(returncode, stdout, stderr),
                    "infrastructure-invalid",
                )

    def test_validator_command_is_guarded_bounded_and_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            release, validator, bundle, _binary, _moduleinfo, manifest, guard = (
                self.create_layout(root)
            )
            with self.patch_layout(
                root, release, validator, manifest, guard, root / "results"
            ):
                command = RUNNER.validator_command(bundle)
            self.assertEqual(command[0], RUNNER.sys.executable)
            self.assertEqual(pathlib.Path(command[1]), guard)
            self.assertIn("--timeout", command)
            self.assertIn("300", command)
            separator = command.index("--")
            self.assertEqual(command[separator + 1 :], [str(validator), str(bundle)])

    def test_one_run_records_atomic_hash_evidence_without_retry(self):
        passed = (
            "Factory Info\nClass Info\nBus tests\nParameter tests\n"
            "State tests\nProcess tests\n"
            "Result: 120 tests passed, 0 tests failed\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            release, validator, bundle, _binary, _moduleinfo, manifest, guard = (
                self.create_layout(root)
            )
            results = root / "results"
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=passed, stderr=""
            )
            with (
                self.patch_layout(
                    root, release, validator, manifest, guard, results
                ),
                mock.patch.object(
                    RUNNER.subprocess, "run", return_value=completed
                ) as run,
            ):
                self.assertEqual(
                    RUNNER.main(
                        ["--kind", "production", "--bundle", str(bundle)]
                    ),
                    0,
                )
            run.assert_called_once()
            record_path = results / "production/result.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["classification"], "pass")
            self.assertEqual(record["validator_returncode"], 0)
            self.assertEqual(
                set(record["hashes"]),
                {
                    "bundle",
                    "bundle_binary",
                    "guard",
                    "moduleinfo",
                    "runner",
                    "sdk_manifest",
                    "validator",
                },
            )
            self.assertEqual(list(record_path.parent.glob("*.pending")), [])

    def test_input_error_never_invokes_validator_or_creates_success_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            release, validator, bundle, _binary, moduleinfo, manifest, guard = (
                self.create_layout(root)
            )
            moduleinfo.unlink()
            results = root / "results"
            with (
                self.patch_layout(
                    root, release, validator, manifest, guard, results
                ),
                mock.patch.object(RUNNER.subprocess, "run") as run,
            ):
                self.assertEqual(
                    RUNNER.main(
                        ["--kind", "production", "--bundle", str(bundle)]
                    ),
                    2,
                )
            run.assert_not_called()
            self.assertFalse((results / "production/result.json").exists())


if __name__ == "__main__":
    unittest.main()
