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


class Vst3BuildContractTests(unittest.TestCase):
    def validation_errors(self, entries, *, sdk_present=False):
        validator = getattr(validate_native_source, "validate_entries", None)
        self.assertIsNotNone(validator, "validate_entries() is absent")
        return validator(entries, sdk_present=sdk_present)

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

    def test_dependency_gate_has_not_been_crossed(self):
        self.assertFalse((ROOT / "third_party/vst3sdk").exists())
        self.assertEqual(list(ROOT.rglob("*.vst3")), [])

        vst3_root = ROOT / "native/vst3"
        cpp_sources = list(vst3_root.glob("*.cpp")) if vst3_root.exists() else []
        self.assertEqual(cpp_sources, [])

        sdk_include = re.compile(
            r"(?m)^\s*#\s*include\s*[<\"](?:pluginterfaces|public\.sdk)/"
        )
        for path in sorted(vst3_root.glob("*")) if vst3_root.exists() else ():
            if path.is_file():
                self.assertIsNone(
                    sdk_include.search(path.read_text(encoding="utf-8")),
                    f"SDK include crossed Gate D2 in {path}",
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
