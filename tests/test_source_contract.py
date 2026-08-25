import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
REAPER = pathlib.Path("/home/ajuntanaga/opt/REAPER/reaper")
CONSTANTS = ROOT / "Effects/m3_poly_midi/constants.jsfx-inc"
PROFILE = ROOT / "Effects/m3_poly_midi/m3_profile.jsfx-inc"
LIFECYCLE = ROOT / "Effects/m3_poly_midi/lifecycle.jsfx-inc"
MIDI_EMITTER = ROOT / "Effects/m3_poly_midi/midi_emitter.jsfx-inc"
TELEMETRY_UI = ROOT / "Effects/m3_poly_midi/telemetry_ui.jsfx-inc"
PRODUCTION = ROOT / "Effects/ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx"


def parse_integer_assignments(path: pathlib.Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    assignments = re.findall(
        r"(?m)^\s*(M3_[A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*;",
        text,
    )
    return {name: int(value, 0) for name, value in assignments}


class SourceContractTests(unittest.TestCase):
    def test_all_jsfx_imports_resolve(self):
        missing = []
        sources = sorted((ROOT / "Effects").rglob("*.jsfx"))
        sources += sorted((ROOT / "Effects").rglob("*.jsfx-inc"))
        for source in sources:
            text = source.read_text(encoding="utf-8")
            for imported in re.findall(r"(?m)^import\s+(.+?)\s*$", text):
                imported_path = (source.parent / imported).resolve()
                if not imported_path.is_file():
                    missing.append(f"{source.relative_to(ROOT)} -> {imported}")
        self.assertEqual(missing, [], "missing JSFX imports: " + ", ".join(missing))

    def test_fixed_memory_contract(self):
        self.assertTrue(CONSTANTS.is_file(), f"missing {CONSTANTS.relative_to(ROOT)}")
        constants = parse_integer_assignments(CONSTANTS)

        expected = {
            "M3_MAX_CANDIDATES": 85,
            "M3_MAX_HARMONICS": 8,
            "M3_MAX_VOICES": 8,
            "M3_MAX_EVENTS": 16,
            "M3_M3_OPEN_0": 32,
            "M3_M3_OPEN_1": 36,
            "M3_M3_OPEN_2": 40,
            "M3_M3_OPEN_3": 44,
            "M3_M3_OPEN_4": 48,
            "M3_M3_OPEN_5": 52,
            "M3_M3_OPEN_6": 56,
            "M3_M3_OPEN_7": 60,
        }
        for name, value in expected.items():
            self.assertEqual(constants.get(name), value, name)

        bases = [
            constants.get("M3_CONFIG_BASE"),
            constants.get("M3_CONDITION_BASE"),
            constants.get("M3_RATE_BASE"),
            constants.get("M3_RESONATOR_BASE"),
            constants.get("M3_SALIENCE_BASE"),
            constants.get("M3_SELECTION_BASE"),
            constants.get("M3_M3_SCRATCH_BASE"),
            constants.get("M3_VOICE_BASE"),
            constants.get("M3_EVENT_BASE"),
            constants.get("M3_TELEMETRY_A_BASE"),
            constants.get("M3_TELEMETRY_B_BASE"),
            constants.get("M3_UI_LOCAL_BASE"),
            constants.get("M3_MEMORY_END"),
        ]
        self.assertNotIn(None, bases, "memory map assignment missing")
        self.assertEqual(bases, sorted(set(bases)), "memory bases must be unique and ordered")
        self.assertLess(constants["M3_UI_LOCAL_BASE"], constants["M3_MEMORY_END"])
        self.assertLess(constants["M3_MEMORY_END"], 8_388_608)

    def test_production_jsfx_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/validate_source.py"), str(ROOT)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_profile_scratch_contract(self):
        constants = parse_integer_assignments(CONSTANTS)
        profile = parse_integer_assignments(PROFILE)
        self.assertEqual(profile.get("M3_PROFILE_DP_ROW_SIZE"), 256)
        self.assertEqual(profile.get("M3_PROFILE_DP_WORDS"), 512)
        self.assertEqual(
            profile["M3_PROFILE_DP_WORDS"],
            2 * profile["M3_PROFILE_DP_ROW_SIZE"],
        )
        self.assertLess(
            profile["M3_PROFILE_DP_WORDS"],
            constants["M3_VOICE_BASE"] - constants["M3_M3_SCRATCH_BASE"],
        )

    def test_lifecycle_memory_contract(self):
        constants = parse_integer_assignments(CONSTANTS)
        lifecycle = parse_integer_assignments(LIFECYCLE)
        self.assertEqual(lifecycle.get("M3_VOICE_CELL_SIZE"), 8)
        self.assertEqual(lifecycle.get("M3_EVENT_HEADER_SIZE"), 2)
        self.assertEqual(lifecycle.get("M3_EVENT_CELL_SIZE"), 5)
        self.assertLessEqual(
            128 * lifecycle["M3_VOICE_CELL_SIZE"],
            constants["M3_EVENT_BASE"] - constants["M3_VOICE_BASE"],
        )
        self.assertLessEqual(
            lifecycle["M3_EVENT_HEADER_SIZE"] +
            constants["M3_MAX_EVENTS"] * lifecycle["M3_EVENT_CELL_SIZE"],
            constants["M3_TELEMETRY_A_BASE"] - constants["M3_EVENT_BASE"],
        )

    def test_midi_emitter_contract(self):
        self.assertTrue(
            MIDI_EMITTER.is_file(),
            f"missing {MIDI_EMITTER.relative_to(ROOT)}",
        )
        emitter = MIDI_EMITTER.read_text(encoding="utf-8")
        for interface in (
            "m3_midi_encode_event(",
            "m3_midi_emit_event(",
            "m3_midi_queue_panic(",
            "m3_midi_panic(",
            "m3_host_cleanup_reason(",
            "m3_host_select_input(",
            "m3_host_apply_bounds(",
            "m3_host_reset_detector(",
        ):
            self.assertIn(interface, emitter)

    def test_production_parameter_surface_is_stable(self):
        expected = [
            "slider1:0<0,2,1{Left,Right,Downmix}>Detector input",
            "slider2:0<0,1,1{M3 Eight-String,General Tonal}>Mode",
            "slider3:440<400,480,0.1>A4 reference (Hz)",
            "slider4:0<-24,24,0.1>Input trim (dB)",
            "slider5:50<0,100,1>Sensitivity",
            "slider6:25<0,100,1>Response (Fast to Stable)",
            "slider7:32<24,108,1>Lowest MIDI note",
            "slider8:84<24,108,1>Highest MIDI note",
            "slider9:8<1,8,1>Maximum polyphony",
            "slider10:24<0,36,1>M3 maximum fret",
            "slider11:1<0,1,1{Fixed,Dynamic}>Velocity mode",
            "slider12:100<1,127,1>Fixed velocity",
            "slider13:1<1,16,1>MIDI channel",
            "slider14:0<0,1,1{Ready,Panic}>Panic",
            "slider15:1<0,1,1{Muted,Pass through}>Dry audio",
        ]
        actual = re.findall(r"(?m)^slider\d+:.*$", PRODUCTION.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)

    def test_production_host_lifecycle_is_block_bounded(self):
        text = PRODUCTION.read_text(encoding="utf-8")
        slider = re.search(
            r"(?ms)^@slider[^\n]*\n(.*?)(?=^@|\Z)",
            text,
        ).group(1)
        block = re.search(
            r"(?ms)^@block[^\n]*\n(.*?)(?=^@|\Z)",
            text,
        ).group(1)
        sample = re.search(
            r"(?ms)^@sample[^\n]*\n(.*?)(?=^@|\Z)",
            text,
        ).group(1)

        self.assertIn("ext_noinit = 1;", text)
        self.assertIn("m3_poly_midi/lifecycle.jsfx-inc", text)
        self.assertIn("m3_poly_midi/midi_emitter.jsfx-inc", text)
        self.assertNotIn("m3_bank_init(", slider)
        self.assertNotIn("m3_host_reset_detector(", slider)
        self.assertIn("m3_midi_panic(", block)
        self.assertIn("m3_host_reset_detector(", block)
        self.assertLess(
            block.index("m3_midi_panic("),
            block.index("m3_host_reset_detector("),
        )
        self.assertIn("m3_midi_emit_event(", sample)
        self.assertNotIn("midirecv(", text)

        assignments = re.findall(r"(?m)^\s*(spl[01])\s*=\s*([^;]+);", text)
        self.assertEqual(assignments, [("spl0", "0"), ("spl1", "0")])

    def test_production_telemetry_and_state_are_section_bounded(self):
        text = PRODUCTION.read_text(encoding="utf-8")
        block = re.search(
            r"(?ms)^@block[^\n]*\n(.*?)(?=^@|\Z)",
            text,
        ).group(1)
        sample = re.search(
            r"(?ms)^@sample[^\n]*\n(.*?)(?=^@|\Z)",
            text,
        ).group(1)
        serialize_match = re.search(
            r"(?ms)^@serialize[^\n]*\n(.*?)(?=^@|\Z)",
            text,
        )
        gfx = re.search(
            r"(?ms)^@gfx[^\n]*\n(.*?)(?=^@|\Z)",
            text,
        ).group(1)

        self.assertIn("m3_poly_midi/telemetry_ui.jsfx-inc", text)
        self.assertIsNotNone(serialize_match)
        serialize = serialize_match.group(1)
        self.assertIn("file_var(0, saved_schema_version);", serialize)
        self.assertNotIn("M3_VOICE_BASE", serialize)
        self.assertNotIn("M3_EVENT_BASE", serialize)
        self.assertIn("input_trim_remaining = 64;", block)
        self.assertEqual(sample.count("time_precise("), 2)
        self.assertNotIn("time_precise(", block)
        self.assertIn("m3_telemetry_publish(", sample)
        self.assertIn("m3_telemetry_read(", gfx)
        self.assertIn("m3_ui_draw(", gfx)

    def test_validator_checks_auxiliary_import_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = pathlib.Path(temporary)
            shutil.copytree(ROOT / "Effects", fixture_root / "Effects")
            probe = fixture_root / "Effects/tests/import_probe.jsfx"
            probe.write_text(
                "desc:import probe\nimport ../missing/probe.jsfx-inc\n@init\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/validate_source.py"),
                    str(fixture_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing import", result.stdout + result.stderr)

    def test_validator_rejects_test_reference_call_in_production_effect(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = pathlib.Path(temporary)
            shutil.copytree(ROOT / "Effects", fixture_root / "Effects")
            production = fixture_root / "Effects" / "ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx"
            text = production.read_text(encoding="utf-8")
            production.write_text(
                text.replace(
                    "@sample\n",
                    "@sample\nm3_bank_process_reference(M3_RESONATOR_BASE, 0);\n",
                    1,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/validate_source.py"),
                    str(fixture_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("test-only reference", result.stdout + result.stderr)

    def test_validator_rejects_detector_rebuild_in_slider_section(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = pathlib.Path(temporary)
            shutil.copytree(ROOT / "Effects", fixture_root / "Effects")
            production = fixture_root / "Effects" / PRODUCTION.name
            text = production.read_text(encoding="utf-8")
            production.write_text(
                text.replace(
                    "@slider\n",
                    "@slider\nm3_host_reset_detector(srate, 32, 84, 440);\n",
                    1,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/validate_source.py"),
                    str(fixture_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("slider section rebuilds detector", result.stdout + result.stderr)

    def test_validator_rejects_consuming_incoming_midi(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = pathlib.Path(temporary)
            shutil.copytree(ROOT / "Effects", fixture_root / "Effects")
            production = fixture_root / "Effects" / PRODUCTION.name
            text = production.read_text(encoding="utf-8")
            production.write_text(
                text.replace(
                    "@block\n",
                    "@block\nmidirecv(offset, status, data1, data2);\n",
                    1,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/validate_source.py"),
                    str(fixture_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("production effect consumes incoming MIDI", result.stdout + result.stderr)

    def test_validator_rejects_extra_dry_audio_assignment(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = pathlib.Path(temporary)
            shutil.copytree(ROOT / "Effects", fixture_root / "Effects")
            production = fixture_root / "Effects" / PRODUCTION.name
            text = production.read_text(encoding="utf-8")
            production.write_text(
                text.replace("@sample\n", "@sample\nspl0 = spl0;\n", 1),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/validate_source.py"),
                    str(fixture_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dry audio assignment contract", result.stdout + result.stderr)

    def test_validator_rejects_gfx_write_to_detector_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = pathlib.Path(temporary)
            shutil.copytree(ROOT / "Effects", fixture_root / "Effects")
            production = fixture_root / "Effects" / PRODUCTION.name
            text = production.read_text(encoding="utf-8")
            production.write_text(
                text.replace(
                    "@gfx 520 260\n",
                    "@gfx 520 260\nM3_CONDITION_BASE[0] = 1;\n",
                    1,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/validate_source.py"),
                    str(fixture_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gfx writes protected detector memory", result.stderr)

    def test_validator_rejects_transient_voice_serialization(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = pathlib.Path(temporary)
            shutil.copytree(ROOT / "Effects", fixture_root / "Effects")
            production = fixture_root / "Effects" / PRODUCTION.name
            text = production.read_text(encoding="utf-8")
            production.write_text(
                text.replace(
                    "file_var(0, saved_schema_version);",
                    "file_var(0, saved_schema_version);\n"
                    "file_var(0, active_note_flags);",
                    1,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/validate_source.py"),
                    str(fixture_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("serialization must contain only", result.stderr)

    def test_disposable_staging_never_targets_live_profile(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/stage_reaper_test_env.py"),
                "--reaper",
                str(REAPER),
                "--output",
                str(pathlib.Path.home() / ".config/REAPER"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to stage", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
