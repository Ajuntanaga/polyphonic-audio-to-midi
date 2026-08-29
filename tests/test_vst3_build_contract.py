import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from tools import validate_native_source


ROOT = pathlib.Path(__file__).resolve().parents[1]
IDENTITY_HEADER = ROOT / "native/vst3/vst3_ids.hpp"
VST3_SDK_ROOT = ROOT / "third_party/vst3sdk"
VST3_SDK_REVISIONS = {
    ".": (
        "https://github.com/steinbergmedia/vst3sdk.git",
        "3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96",
    ),
    "base": (
        "https://github.com/steinbergmedia/vst3_base",
        "fcf9da0bd27a16f7f03773a3a39822f28f5c8477",
    ),
    "cmake": (
        "https://github.com/steinbergmedia/vst3_cmake",
        "054c9143cbb8d47fc4694e473f2ee3b4d951a8f5",
    ),
    "pluginterfaces": (
        "https://github.com/steinbergmedia/vst3_pluginterfaces",
        "4f547e8e102b47de4a8b8aaf343c73b700786372",
    ),
    "public.sdk": (
        "https://github.com/steinbergmedia/vst3_public_sdk",
        "586dc5e6c8012c3e4b01c79389375cbe96bdb1da",
    ),
}


class Vst3BuildContractTests(unittest.TestCase):
    def validation_errors(self, entries, *, sdk_present=False):
        validator = getattr(validate_native_source, "validate_entries", None)
        self.assertIsNotNone(validator, "validate_entries() is absent")
        return validator(entries, sdk_present=sdk_present)

    def test_installed_cmake_meets_the_offline_build_prerequisite(self):
        cmake = shutil.which("cmake")
        self.assertIsNotNone(cmake, "CMake executable is required after Gate T1")
        result = subprocess.run(
            [cmake, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        match = re.fullmatch(r"cmake version (\d+)\.(\d+)\.(\d+)", first_line)
        self.assertIsNotNone(match, first_line)
        version = tuple(int(part) for part in match.groups())
        self.assertGreaterEqual(version, (3, 25, 0))

    def test_cmake_build_graph_is_explicit_offline_and_hardened(self):
        root_cmake = ROOT / "CMakeLists.txt"
        compiler_options = ROOT / "cmake/M3CompilerOptions.cmake"
        sdk_setup = ROOT / "cmake/M3Vst3Sdk.cmake"
        for path in (root_cmake, compiler_options, sdk_setup):
            self.assertTrue(path.is_file(), f"required CMake source is absent: {path}")

        build_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root_cmake, compiler_options, sdk_setup)
        )
        for forbidden in (
            r"\bfile\s*\(\s*GLOB",
            r"\baux_source_directory\s*\(",
            r"\bFetchContent\b",
            r"\bExternalProject_Add\b",
            r"\bfile\s*\(\s*DOWNLOAD",
            r"\b-march=native\b",
        ):
            self.assertIsNone(re.search(forbidden, build_text, re.IGNORECASE), forbidden)
        for required in (
            "CMAKE_CXX_STANDARD 17",
            "SMTG_ENABLE_VSTGUI_SUPPORT OFF",
            "SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF",
            "SMTG_ENABLE_VST3_HOSTING_EXAMPLES OFF",
            "SMTG_CREATE_PLUGIN_LINK OFF",
            "SMTG_CREATE_MODULE_INFO OFF",
            "m3_native_tests",
            "m3_clap_history",
            "m3_vst3_probe",
            "m3_vst3_production",
            "m3_vst3_benchmark",
            "m3_validate_production",
        ):
            self.assertIn(required, build_text)

        authored_cpp = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "native").rglob("*.cpp")
        }
        for relative in authored_cpp:
            self.assertIn(relative, build_text, f"source is not explicit: {relative}")

        cmake = shutil.which("cmake")
        self.assertIsNotNone(cmake)
        (ROOT / "build/vst3").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="contract-", dir=ROOT / "build/vst3"
        ) as temporary:
            build_dir = pathlib.Path(temporary)
            configure = subprocess.run(
                [
                    cmake,
                    "-S",
                    str(ROOT),
                    "-B",
                    str(build_dir),
                    "-DCMAKE_BUILD_TYPE=Debug",
                    "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                configure.returncode,
                0,
                configure.stdout + configure.stderr,
            )
            cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
            for setting in (
                "SMTG_ENABLE_VSTGUI_SUPPORT:BOOL=OFF",
                "SMTG_ENABLE_VST3_PLUGIN_EXAMPLES:BOOL=OFF",
                "SMTG_ENABLE_VST3_HOSTING_EXAMPLES:BOOL=OFF",
                "SMTG_CREATE_PLUGIN_LINK:BOOL=OFF",
                "SMTG_CREATE_MODULE_INFO:BOOL=OFF",
            ):
                self.assertIn(setting, cache)

            target_help = subprocess.run(
                [cmake, "--build", str(build_dir), "--target", "help", "-j1"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                target_help.returncode,
                0,
                target_help.stdout + target_help.stderr,
            )
            for target in (
                "m3_native_tests",
                "m3_clap_history",
                "m3_vst3_probe",
                "m3_vst3_production",
                "m3_vst3_benchmark",
                "m3_validate_production",
            ):
                self.assertIn(target, target_help.stdout)

            commands = json.loads(
                (build_dir / "compile_commands.json").read_text(encoding="utf-8")
            )
            project_commands = [
                row["command"]
                for row in commands
                if "/native/" in row["file"]
                and "/third_party/" not in row["file"]
            ]
            self.assertTrue(project_commands)
            for command in project_commands:
                for flag in (
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Wpedantic",
                    "-Wconversion",
                    "-Wshadow",
                    "-Werror",
                    "-fno-exceptions",
                    "-fno-rtti",
                    "-fstack-protector-strong",
                    "-fvisibility=hidden",
                ):
                    self.assertIn(flag, command)
                self.assertNotIn("-march=native", command)

            probe_commands = [
                row
                for row in commands
                if "-DM3_VST3_PROBE_BUILD" in row["command"]
            ]
            self.assertEqual(
                {
                    pathlib.Path(row["file"]).relative_to(ROOT).as_posix()
                    for row in probe_commands
                },
                {
                    "native/src/generated_note_ledger.cpp",
                    "native/src/parameter_contract.cpp",
                    "native/src/state_image.cpp",
                    "native/vst3/vst3_component.cpp",
                    "native/vst3/vst3_factory.cpp",
                    (
                        "third_party/vst3sdk/public.sdk/source/main/"
                        "linuxmain.cpp"
                    ),
                    (
                        "third_party/vst3sdk/public.sdk/source/vst/"
                        "vstsinglecomponenteffect.cpp"
                    ),
                },
            )
            for row in probe_commands:
                self.assertNotIn("third_party/clap/include", row["command"])
                self.assertNotIn("-DM3_TESTING", row["command"])

            self.assertNotIn("add_custom_target(m3_vst3_probe", build_text)
            self.assertIn("smtg_add_vst3plugin(m3_vst3_probe", build_text)

            for target in (
                "m3_native_tests",
                "m3_clap_history",
                "m3_vst3_probe",
            ):
                link_command = (
                    build_dir / f"CMakeFiles/{target}.dir/link.txt"
                ).read_text(encoding="utf-8")
                for flag in (
                    "-Wl,-z,relro",
                    "-Wl,-z,now",
                    "-Wl,--no-undefined",
                    "-Wl,--build-id=none",
                ):
                    self.assertIn(flag, link_command)

    def test_identity_header_exposes_the_locked_sdk_independent_contract(self):
        self.assertTrue(IDENTITY_HEADER.is_file(), "vst3_ids.hpp is absent")

        text = IDENTITY_HEADER.read_text(encoding="utf-8")
        tuples = (
            (
                r"0x4A1BA42FU\s*,\s*0x6D704609U\s*,\s*"
                r"0x8B52450CU\s*,\s*0x3842F11FU"
            ),
            (
                r"0x6F62F8B1U\s*,\s*0xB8A14872U\s*,\s*"
                r"0xA0D92C3CU\s*,\s*0x274421D8U"
            ),
            (
                r"0x28713895U\s*,\s*0x1CCA47ECU\s*,\s*"
                r"0x919F6CC1U\s*,\s*0xBCB88A8FU"
            ),
        )
        for tuple_pattern in tuples:
            self.assertEqual(len(re.findall(tuple_pattern, text)), 1)

        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler, "GNU C++ compiler is required")
        source = textwrap.dedent(
            r'''
            #include "native/vst3/vst3_ids.hpp"

            #include <array>
            #include <cstdint>
            #include <string_view>

            namespace ids = m3::vst3;

            static_assert(ids::kProductionClassIdWords[0] == 0x4A1BA42FU &&
                          ids::kProductionClassIdWords[1] == 0x6D704609U &&
                          ids::kProductionClassIdWords[2] == 0x8B52450CU &&
                          ids::kProductionClassIdWords[3] == 0x3842F11FU);
            static_assert(ids::kProbeClassIdWords[0] == 0x6F62F8B1U &&
                          ids::kProbeClassIdWords[1] == 0xB8A14872U &&
                          ids::kProbeClassIdWords[2] == 0xA0D92C3CU &&
                          ids::kProbeClassIdWords[3] == 0x274421D8U);
            static_assert(ids::kBenchmarkClassIdWords[0] == 0x28713895U &&
                          ids::kBenchmarkClassIdWords[1] == 0x1CCA47ECU &&
                          ids::kBenchmarkClassIdWords[2] == 0x919F6CC1U &&
                          ids::kBenchmarkClassIdWords[3] == 0xBCB88A8FU);
            static_assert(ids::kProductionClassIdWords[0] != 0U &&
                          ids::kProductionClassIdWords[1] != 0U &&
                          ids::kProductionClassIdWords[2] != 0U &&
                          ids::kProductionClassIdWords[3] != 0U);
            static_assert(ids::kProbeClassIdWords[0] != 0U &&
                          ids::kProbeClassIdWords[1] != 0U &&
                          ids::kProbeClassIdWords[2] != 0U &&
                          ids::kProbeClassIdWords[3] != 0U);
            static_assert(ids::kBenchmarkClassIdWords[0] != 0U &&
                          ids::kBenchmarkClassIdWords[1] != 0U &&
                          ids::kBenchmarkClassIdWords[2] != 0U &&
                          ids::kBenchmarkClassIdWords[3] != 0U);
            static_assert(std::string_view(ids::kDescriptiveId) ==
                          "com.ajuntanaga.m3-polyphonic-audio-to-midi");
            static_assert(std::string_view(ids::kVendorName) == "ajuntanaga");
            static_assert(std::string_view(ids::kProductName) ==
                          "M3 Polyphonic Audio to MIDI");
            static_assert(std::string_view(ids::kProbeProductName) ==
                          "M3 Polyphonic Audio to MIDI Probe");
            static_assert(std::string_view(ids::kBenchmarkProductName) ==
                          "M3 Polyphonic Audio to MIDI Benchmark");
            static_assert(std::string_view(ids::kVersionString) == "0.1.0");
            static_assert(std::string_view(ids::kProductionSubcategories) ==
                          "Fx|Tools");

            int main() { return 0; }
            '''
        )
        with tempfile.TemporaryDirectory() as temporary:
            source_path = pathlib.Path(temporary) / "identity_contract.cpp"
            source_path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Wpedantic",
                    "-Werror",
                    "-fsyntax-only",
                    "-I",
                    str(ROOT),
                    str(source_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_vendored_vst3_sdk_matches_the_exact_official_contract(self):
        upstream_path = VST3_SDK_ROOT / "UPSTREAM.md"
        self.assertTrue(upstream_path.is_file(), "third_party/vst3sdk/UPSTREAM.md is absent")

        expected_children = {
            "CMakeLists.txt",
            "LICENSE.txt",
            "README.md",
            "SHA256SUMS",
            "UPSTREAM.md",
            "base",
            "cmake",
            "pluginterfaces",
            "public.sdk",
        }
        self.assertEqual(
            {path.name for path in VST3_SDK_ROOT.iterdir()},
            expected_children,
        )
        for retained_root in ("base", "cmake", "pluginterfaces", "public.sdk"):
            self.assertTrue((VST3_SDK_ROOT / retained_root).is_dir())
        for excluded_root in ("doc", "tutorials", "vstgui4"):
            self.assertFalse((VST3_SDK_ROOT / excluded_root).exists())
        self.assertEqual(
            [path for path in VST3_SDK_ROOT.rglob(".git")],
            [],
            "vendored SDK contains Git metadata",
        )

        license_text = (VST3_SDK_ROOT / "LICENSE.txt").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted, free of charge", license_text)

        upstream = upstream_path.read_text(encoding="utf-8")
        self.assertRegex(
            upstream,
            r"(?m)^Retrieved UTC: `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z`$",
        )
        self.assertIn("Tag: `v3.8.1_build_84`", upstream)
        revision_rows = {
            match.groups()
            for match in re.finditer(
                r"(?m)^\| `([^`]+)` \| `([^`]+)` \| `([0-9a-f]{40})` \|$",
                upstream,
            )
        }
        self.assertEqual(
            revision_rows,
            {
                (path, repository, revision)
                for path, (repository, revision) in VST3_SDK_REVISIONS.items()
            },
        )
        self.assertIn(
            "git clone --filter=blob:none --no-checkout "
            "https://github.com/steinbergmedia/vst3sdk.git "
            "build/vendor/vst3sdk-src",
            upstream,
        )
        self.assertIn(
            "git -C build/vendor/vst3sdk-src checkout --detach "
            "3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96",
            upstream,
        )
        self.assertIn(
            "git -C build/vendor/vst3sdk-src submodule update --init --depth 1 "
            "base cmake pluginterfaces public.sdk",
            upstream,
        )

        manifest_path = VST3_SDK_ROOT / "SHA256SUMS"
        self.assertTrue(manifest_path.is_file())
        manifest_rows = []
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  (third_party/vst3sdk/.+)", line)
            self.assertIsNotNone(match, line)
            manifest_rows.append(match.groups())
        manifest_names = [name for _digest, name in manifest_rows]
        self.assertEqual(manifest_names, sorted(manifest_names))
        self.assertEqual(len(manifest_names), len(set(manifest_names)))

        actual_names = sorted(
            path.relative_to(ROOT).as_posix()
            for path in VST3_SDK_ROOT.rglob("*")
            if path.is_file() and path != manifest_path
        )
        self.assertEqual(manifest_names, actual_names)
        for expected_digest, relative in manifest_rows:
            actual_digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual_digest, expected_digest, relative)

        persistent_bundles = [
            path
            for path in ROOT.rglob("*.vst3")
            if not path.relative_to(ROOT).as_posix().startswith("build/")
        ]
        self.assertEqual(persistent_bundles, [])

        vst3_root = ROOT / "native/vst3"
        cpp_sources = {
            path.name for path in vst3_root.glob("*.cpp")
        } if vst3_root.exists() else set()
        self.assertEqual(
            cpp_sources,
            {"vst3_component.cpp", "vst3_factory.cpp"},
        )

    def test_source_validator_accepts_the_sdk_independent_identity_header(self):
        errors = self.validation_errors(
            [
                (
                    "native/vst3/vst3_ids.hpp",
                    "#include <array>\nnamespace m3::vst3 {}\n",
                )
            ]
        )
        self.assertEqual(errors, [])

    def test_source_validator_rejects_unapproved_dependencies_and_abi_copies(self):
        cases = (
            ("#include <vstgui/lib/vstguiinit.h>\n", "vstgui"),
            ("#include <juce_audio_processors/juce_audio_processors.h>\n", "juce"),
            ("#include <IPlug_include_in_plug_src.h>\n", "iplug"),
            ("#include <onnxruntime_cxx_api.h>\n", "onnx"),
            ("namespace Steinberg { class FUnknown; }\n", "handwritten VST3 ABI"),
        )
        for source, label in cases:
            with self.subTest(label=label):
                errors = self.validation_errors(
                    [("native/vst3/bad_boundary.cpp", source)]
                )
                self.assertTrue(any(label in error for error in errors), errors)

    def test_source_validator_allows_the_official_vst3_view_interface(self):
        errors = self.validation_errors(
            [
                (
                    "native/vst3/vst3_component.hpp",
                    "#include <pluginterfaces/gui/iplugview.h>\n"
                    "Steinberg::IPlugView* create_view();\n",
                )
            ],
            sdk_present=True,
        )
        self.assertEqual(errors, [])

    def test_source_validator_rejects_networked_build_rules(self):
        cases = (
            "include(FetchContent)\nFetchContent_Declare(sdk URL https://example.test/sdk)\n",
            "file(DOWNLOAD https://example.test/sdk archive.zip)\n",
            "execute_process(COMMAND git clone https://example.test/sdk)\n",
        )
        for source in cases:
            with self.subTest(source=source.splitlines()[0]):
                errors = self.validation_errors([("CMakeLists.txt", source)])
                self.assertTrue(
                    any("network build token" in error for error in errors),
                    errors,
                )

    def test_source_validator_accepts_the_offline_cmake_wrapper(self):
        errors = self.validation_errors(
            [
                (
                    "native/Makefile",
                    "cmake -S /repo -B /repo/build/vst3/debug\n"
                    "cmake --build /repo/build/vst3/debug -j1\n",
                )
            ],
            sdk_present=True,
        )
        self.assertEqual(errors, [])

    def test_source_validator_keeps_vst3_code_out_of_the_clap_adapter_directory(self):
        errors = self.validation_errors(
            [("native/plugin/vst3_adapter.cpp", "namespace m3 {}\n")]
        )
        self.assertTrue(
            any("VST3 source under native/plugin" in error for error in errors),
            errors,
        )

    def test_source_validator_rejects_sdk_includes_before_gate_d2(self):
        includes = (
            "pluginterfaces/vst/ivstaudioprocessor.h",
            "public.sdk/source/vst/vstaudioeffect.h",
            "base/source/fstring.h",
        )
        for include in includes:
            with self.subTest(include=include):
                entry = (
                    "native/vst3/vst3_component.cpp",
                    f"#include <{include}>\n",
                )
                errors = self.validation_errors([entry], sdk_present=False)
                self.assertTrue(
                    any("SDK include before Gate D2" in error for error in errors),
                    errors,
                )
                self.assertEqual(
                    self.validation_errors([entry], sdk_present=True), []
                )

    def test_source_validator_rejects_raw_fuid_words_outside_the_identity_header(self):
        production_tuple = (
            "0x4A1BA42FU, 0x6D704609U, 0x8B52450CU, 0x3842F11FU"
        )
        errors = self.validation_errors(
            [("native/vst3/vst3_component.cpp", production_tuple)]
        )
        self.assertTrue(
            any("FUID tuple outside identity header" in error for error in errors),
            errors,
        )

    def test_source_validator_rejects_duplicate_raw_fuid_words(self):
        probe_tuple = (
            "0x6F62F8B1U, 0xB8A14872U, 0xA0D92C3CU, 0x274421D8U"
        )
        lowercase_probe_tuple = (
            "0x6f62f8b1, 0xb8a14872, 0xa0d92c3c, 0x274421d8"
        )
        errors = self.validation_errors(
            [
                ("native/vst3/vst3_ids.hpp", probe_tuple),
                ("native/vst3/duplicate.hpp", lowercase_probe_tuple),
            ]
        )
        self.assertTrue(
            any("duplicate FUID tuple" in error for error in errors),
            errors,
        )

    def test_source_validator_rejects_test_only_fuid_from_production_source(self):
        for symbol in ("kProbeClassIdWords", "kBenchmarkClassIdWords"):
            with self.subTest(symbol=symbol):
                errors = self.validation_errors(
                    [
                        ("native/vst3/vst3_ids.hpp", f"constexpr int {symbol} = 0;\n"),
                        (
                            "native/vst3/vst3_component.cpp",
                            f"auto class_id = m3::vst3::{symbol};\n",
                        ),
                    ]
                )
                self.assertTrue(
                    any("production reference to test-only FUID" in error for error in errors),
                    errors,
                )


if __name__ == "__main__":
    unittest.main()
