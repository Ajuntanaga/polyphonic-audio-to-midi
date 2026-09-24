import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.stage_reaper_test_env import stage


ROOT = pathlib.Path(__file__).resolve().parents[1]
REAPER = pathlib.Path.home() / "opt/REAPER/reaper"
CONSTANTS = ROOT / "Effects/m3_poly_midi/constants.jsfx-inc"
PROFILE = ROOT / "Effects/m3_poly_midi/m3_profile.jsfx-inc"
SELECTOR = ROOT / "Effects/m3_poly_midi/salience_selector.jsfx-inc"
LIFECYCLE = ROOT / "Effects/m3_poly_midi/lifecycle.jsfx-inc"
MIDI_EMITTER = ROOT / "Effects/m3_poly_midi/midi_emitter.jsfx-inc"
TELEMETRY_UI = ROOT / "Effects/m3_poly_midi/telemetry_ui.jsfx-inc"
SIGNAL_SOURCE = (
    ROOT / "Effects/tests/ajuntanaga_M3 Polyphonic MIDI - Signal Source.jsfx"
)
MIDI_CAPTURE = (
    ROOT / "Effects/tests/ajuntanaga_M3 Polyphonic MIDI - MIDI Capture.jsfx"
)
SYNTH_PROBE = (
    ROOT / "Effects/tests/ajuntanaga_M3 Polyphonic MIDI - Synth Output Probe.jsfx"
)
INTEGRATION_RUNNER = (
    ROOT / "Scripts/ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua"
)
SAFE_BYPASS = (
    ROOT / "Scripts/ajuntanaga_M3 Polyphonic MIDI - Safe Bypass.lua"
)
PRODUCTION = ROOT / "Effects/ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx"
HOST_CASES = ROOT / "tests/fixtures/host_cases.tsv"
SYNTHETIC_CASES = ROOT / "tests/fixtures/synthetic_cases.tsv"
CORE_TESTS = ROOT / "Effects/tests/ajuntanaga_M3 Polyphonic MIDI - Core Tests.jsfx"
CORE_OBSERVER = ROOT / "tools/observe_core_harness_case.lua"
NATIVE_CAPABILITY_SOURCE = (
    ROOT / "Effects/tests/ajuntanaga_M3 Native CLAP Capability Source.jsfx"
)
NATIVE_CAPABILITY_RUNNER = (
    ROOT / "Scripts/tests/ajuntanaga_M3 Native CLAP Capability.lua"
)
VST3_BUILD_ROOT = (ROOT / "build/vst3/release/VST3").resolve()
VST3_CAPABILITY_SOURCE = (
    ROOT / "Effects/tests/ajuntanaga_M3 Native VST3 Capability Source.jsfx"
)
VST3_CAPABILITY_RUNNER = (
    ROOT / "Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua"
)


def parse_integer_assignments(path: pathlib.Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    assignments = re.findall(
        r"(?m)^\s*(M3_[A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*;",
        text,
    )
    return {name: int(value, 0) for name, value in assignments}


class SourceContractTests(unittest.TestCase):
    def test_tracked_public_files_do_not_embed_a_contributor_home_path(self):
        frozen_observation = (
            b"tests/fixtures/reaper_v4_closure/observed-runtime-catalog.json"
        )
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        contributor_home = b"/home/" + b"ajuntanaga"
        offenders = []
        for relative in tracked:
            if not relative:
                continue
            if relative == frozen_observation:
                continue
            path = ROOT / relative.decode("utf-8")
            if not path.is_file():
                continue
            if contributor_home in path.read_bytes():
                offenders.append(relative.decode("utf-8"))

        self.assertEqual(offenders, [])

    def test_native_capability_probe_sources_are_bounded_and_exact(self):
        source = NATIVE_CAPABILITY_SOURCE.read_text(encoding="utf-8")
        runner = NATIVE_CAPABILITY_RUNNER.read_text(encoding="utf-8")
        capture = MIDI_CAPTURE.read_text(encoding="utf-8")

        self.assertIn("options:gmem=m3_poly_midi_tests_v1", source)
        self.assertIn("samplesblock < 32", source)
        self.assertIn("midisend(4, 0x90, 67 | (101 << 8))", source)
        self.assertIn("midisend(8, 0xB0, 119 | (1 << 8))", source)
        self.assertIn("midisend(9, 0x90, 65 | (99 << 8))", source)
        self.assertIn("midisend(11, 0xB0, 1 | (64 << 8))", source)
        self.assertIn("midisend(20, 0x80, 67)", source)
        self.assertIn("midisend(21, 0x80, 65)", source)
        self.assertIn("spl0 = m3_capability_left", source)
        self.assertIn("spl1 = m3_capability_right", source)
        self.assertIn("M3_CAPABILITY_REFERENCE_LEFT = 8192", source)
        self.assertIn("M3_CAPABILITY_REFERENCE_RIGHT = 8704", source)
        self.assertNotIn("rand(", source)

        self.assertIn("gmem[M3_CAPABILITY_ACTIVE] ?", capture)
        self.assertIn("abs(spl0 - m3_capture_reference_left)", capture)
        self.assertIn("abs(spl1 - m3_capture_reference_right)", capture)

        for contract in (
            'TrackFX_AddByName(track, "CLAP: M3 Polyphonic Audio to MIDI Probe"',
            'TrackFX_GetNamedConfigParm(track, probe_fx, "pdc")',
            "local EXPECTED_PARAMETER_COUNT = 16",
            "local PERSISTENT_PARAMETER_COUNT = 14",
            "reaper.GetTrackStateChunk",
            "reaper.SetTrackStateChunk",
            "reaper.TrackFX_Delete(track, probe_fx)",
            'write_phase("suite-finish")',
            'atomic_write(result_directory .. "/capability.tsv"',
            'atomic_write(result_directory .. "/events.tsv"',
            'atomic_write(result_directory .. "/state.tsv"',
        ):
            self.assertIn(contract, runner)
        finish = runner.index("local function finish_after_report()")
        report_read = runner.index("local report = io.open(probe_report_path", finish)
        suite_finish = runner.index('write_phase("suite-finish")', report_read)
        self.assertLess(report_read, suite_finish)
        self.assertIn("reaper.defer(poll_report)", runner)
        self.assertNotIn(".config/REAPER", runner)

    def test_native_vst3_capability_is_audio_triggered_bounded_and_exact(self):
        source = VST3_CAPABILITY_SOURCE.read_text(encoding="utf-8")
        runner = VST3_CAPABILITY_RUNNER.read_text(encoding="utf-8")
        capture = MIDI_CAPTURE.read_text(encoding="utf-8")

        for contract in (
            "desc:ajuntanaga/M3 Native VST3 Capability Source",
            "options:gmem=m3_poly_midi_tests_v1",
            "slider1:0<0,5,1>-Phase",
            "slider2:0<0,1048576,1>-Phase sample",
            "slider3:0<0,384000,1>-Host sample rate",
            "slider4:0<0,16384,1>-Host block size",
            "M3_VST3_COMMAND = 2210",
            "M3_VST3_PHASE_SAMPLE = 2212",
            "M3_VST3_MAGIC = 2205",
            "M3_VST3_GENERATION = 2206",
            "M3_VST3_READY = 2207",
            "M3_VST3_HEARTBEAT = 2208",
            "M3_VST3_ACK = 2209",
            "M3_VST3_MAGIC_VALUE = 0x4D335633",
            "gmem[M3_VST3_MAGIC] = M3_VST3_MAGIC_VALUE",
            "gmem[M3_VST3_HEARTBEAT] += 1",
            "gmem[M3_VST3_READY] = m3_vst3_generation",
            "gmem[M3_VST3_ACK] = m3_vst3_reset",
            "m3_vst3_left = 0.25",
            "m3_vst3_right = -0.25",
            "m3_vst3_left = -0.75",
            "m3_vst3_right = -0.75",
            "spl0 = m3_vst3_left",
            "spl1 = m3_vst3_right",
        ):
            self.assertIn(contract, source)
        for forbidden in (
            "midisend",
            "midirecv",
            "file_",
            "http_",
            "tcp_",
            "while(",
            "loop(",
            ".config/REAPER",
        ):
            self.assertNotIn(forbidden, source.lower())

        for contract in (
            "M3_CAPTURE_OUTPUT_PEAK = 2050",
            "M3_CAPTURE_NONFINITE = 2051",
            "gmem[M3_CAPTURE_OUTPUT_PEAK] = max",
            "gmem[M3_CAPTURE_NONFINITE] = 1",
        ):
            self.assertIn(contract, capture)

        for contract in (
            'TrackFX_AddByName(track, "VST3: M3 Polyphonic Audio to MIDI Probe"',
            'reporter_fx = reaper.TrackFX_AddByName(track, "VST3: M3 Polyphonic Audio to MIDI Probe", false, -1)',
            'TrackFX_GetNamedConfigParm(track, probe_fx, "fx_type")',
            'TrackFX_GetNamedConfigParm(track, probe_fx, "is_instrument")',
            "reaper.TrackFX_GetParamIdent",
            "reaper.TrackFX_GetParamFromIdent",
            "local OBSERVER_MAGIC_VALUE = 0x4D335633",
            "reaper.TrackFX_GetParamNormalized",
            "reaper.TrackFX_SetParamNormalized",
            "reaper.TrackFX_FormatParamValueNormalized",
            "reaper.TrackFX_GetParameterStepSizes",
            "reaper.TrackFX_GetFormattedParamValue",
            "local PERSISTENT_PARAMETER_COUNT = 14",
            "reaper.GetTrackStateChunk",
            "reaper.SetTrackStateChunk",
            "reaper.TrackFX_SetEnabled(track, probe_fx, false)",
            "reaper.TrackFX_SetEnabled(track, probe_fx, true)",
            "reaper.TrackFX_SetEnabled(track, reporter_fx, false)",
            "reaper.TrackFX_Delete(track, probe_fx)",
            'atomic_write(result_directory .. "/capability.tsv"',
            'atomic_write(result_directory .. "/events.tsv"',
            'atomic_write(result_directory .. "/state.tsv"',
            'atomic_write(result_directory .. "/probe-vst3.tsv"',
            'write_phase(#failures == 0 and "suite-finish" or "suite-fail")',
            "reaper.Main_OnCommand(40004, 0)",
        ):
            self.assertIn(contract, runner)
        self.assertNotIn("EXPECTED_PARAMETER_COUNT", runner)
        self.assertNotIn("CLAP:", runner)
        self.assertNotIn("MIDI trigger", runner)
        self.assertNotIn(".config/REAPER", runner)
        self.assertIn(
            '"phase\\tindex\\tabsolute_sample\\toffset\\ttype\\tchannel\\tpitch\\tvelocity\\tnote_id"',
            runner,
        )
        self.assertIn(
            '"index\\tstable_id\\tname\\tdefault\\tmutated\\trestored"',
            runner,
        )
        terminal_phase = runner.index(
            'write_phase(#failures == 0 and "suite-finish" or "suite-fail")'
        )
        close_process = runner.index("reaper.Main_OnCommand(40004, 0)")
        self.assertLess(terminal_phase, close_process)

        with tempfile.TemporaryDirectory() as temporary:
            staged = pathlib.Path(temporary) / "reaper-test"
            stage(
                ROOT,
                staged,
                sample_rate=44100,
                block_size=32,
                vst3_path=VST3_BUILD_ROOT,
            )
            self.assertEqual(
                (
                    staged
                    / "Effects/tests/ajuntanaga_M3 Native VST3 Capability Source.jsfx"
                ).read_bytes(),
                VST3_CAPABILITY_SOURCE.read_bytes(),
            )
            self.assertEqual(
                (
                    staged
                    / "Scripts/tests/ajuntanaga_M3 Native VST3 Capability.lua"
                ).read_bytes(),
                VST3_CAPABILITY_RUNNER.read_bytes(),
            )

    def test_disposable_staging_contains_only_approved_runtime_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = pathlib.Path(temporary) / "reaper-test"
            staged.mkdir()
            (staged / "reaper-kb.ini").write_text("stale", encoding="utf-8")
            (staged / "reaper-jsfx.ini").write_text("stale", encoding="utf-8")
            stage(ROOT, staged)

            self.assertTrue((staged / "reaper.ini").is_file())
            self.assertTrue(
                (
                    staged /
                    "Effects/ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx"
                ).is_file()
            )
            self.assertTrue(
                (staged / "Effects/m3_poly_midi/constants.jsfx-inc").is_file()
            )
            self.assertTrue(
                (
                    staged /
                    "Scripts/ajuntanaga_M3 Polyphonic MIDI - Run Tests.lua"
                ).is_file()
            )
            self.assertTrue(
                (
                    staged /
                    "Effects/tests/ajuntanaga_M3 Polyphonic MIDI - Synth Output Probe.jsfx"
                ).is_file()
            )
            self.assertTrue(
                (
                    staged /
                    "Scripts/ajuntanaga_M3 Polyphonic MIDI - Safe Bypass.lua"
                ).is_file()
            )
            self.assertFalse((staged / "reaper-kb.ini").exists())
            self.assertFalse((staged / "reaper-jsfx.ini").exists())
            self.assertEqual(
                (staged / "reaper.ini").read_text(encoding="utf-8"),
                "[reaper]\n"
                "linux_audio_bsize=128\n"
                "linux_audio_bufs=2\n"
                "linux_audio_mode=3\n"
                "linux_audio_nch_in=0\n"
                "linux_audio_nch_out=2\n"
                "linux_audio_srate=48000\n"
                "newprojdo=0\n"
                "saveFlags=0\n"
                "warnmaxram64=0\n",
            )
            self.assertEqual(
                (
                    staged / "Data/m3_poly_midi/synthetic_cases.tsv"
                ).read_bytes(),
                HOST_CASES.read_bytes(),
            )
            self.assertTrue((staged / "test-results").is_dir())

    def test_disposable_staging_rejects_every_source_tree_overlap_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = pathlib.Path(temporary)
            source = temporary_root / "source"
            source.mkdir()
            sentinel = source / "must-survive.txt"
            sentinel.write_text("source-owned\n", encoding="utf-8")

            for output in (temporary_root, source, source / "nested-output"):
                with self.subTest(output=output):
                    with self.assertRaisesRegex(ValueError, "source tree"):
                        stage(source, output)
                    self.assertEqual(
                        sentinel.read_text(encoding="utf-8"), "source-owned\n"
                    )
                    self.assertFalse((source / "nested-output").exists())

    def test_vst3_staging_puts_only_the_exact_scan_root_in_disposable_ini(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = pathlib.Path(temporary) / "reaper-test"
            staged.mkdir()
            for name in (
                "reaper-vstplugins.ini",
                "reaper-vstplugins64.ini",
                "reaper-clapplugins64.ini",
            ):
                (staged / name).write_text("stale\n", encoding="utf-8")

            stage(
                ROOT,
                staged,
                sample_rate=88200,
                block_size=512,
                vst3_path=VST3_BUILD_ROOT,
            )

            profile = (staged / "reaper.ini").read_text(encoding="utf-8")
            self.assertEqual(
                [line for line in profile.splitlines() if line.startswith("vstpath=")],
                [f"vstpath={VST3_BUILD_ROOT}"],
            )
            self.assertNotIn("CLAP_PATH", profile)
            self.assertNotIn(str(pathlib.Path.home() / ".config/REAPER"), profile)
            for name in (
                "reaper-vstplugins.ini",
                "reaper-vstplugins64.ini",
                "reaper-clapplugins64.ini",
            ):
                self.assertFalse((staged / name).exists())
            path_mentions = []
            for path in staged.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeError:
                    continue
                if str(VST3_BUILD_ROOT) in text:
                    path_mentions.append(path.relative_to(staged).as_posix())
            self.assertEqual(path_mentions, ["reaper.ini"])

    def test_disposable_staging_selects_only_a_bounded_synthetic_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = pathlib.Path(temporary) / "reaper-test"

            stage(
                ROOT,
                staged,
                case_set="synthetic",
                sample_rate=48000,
                block_size=128,
                case_offset=0,
                case_limit=2,
            )

            self.assertEqual(
                (
                    staged / "Data/m3_poly_midi/synthetic_cases.tsv"
                ).read_text(encoding="utf-8").splitlines(),
                [
                    "case_id\tsample_rate\tblock_size\tmode\tnotes\t"
                    "detune_cents\tmissing_fundamental\tgains_db\t"
                    "noise_db\thum_db\tclip\tstagger_ms\texpected",
                    "7\t48000\t128\tgeneral\t24\t0\t0\t0\t-120\t"
                    "-120\t0\t0\t24",
                    "19\t48000\t128\tgeneral\t25\t0\t0\t0\t-120\t"
                    "-120\t0\t0\t25",
                ],
            )

    def test_synthetic_batch_controls_profile_rate_block_and_offset(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = pathlib.Path(temporary) / "reaper-test"

            stage(
                ROOT,
                staged,
                case_set="synthetic",
                sample_rate=44100,
                block_size=32,
                case_offset=1,
                case_limit=2,
            )

            profile = (staged / "reaper.ini").read_text(encoding="utf-8")
            rows = (
                staged / "Data/m3_poly_midi/synthetic_cases.tsv"
            ).read_text(encoding="utf-8").splitlines()
            self.assertIn("linux_audio_bsize=32\n", profile)
            self.assertIn("linux_audio_srate=44100\n", profile)
            self.assertEqual([row.split("\t", 1)[0] for row in rows[1:]], ["13", "25"])

    def test_synthetic_batch_refuses_more_than_thirty_two_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = pathlib.Path(temporary) / "reaper-test"

            with self.assertRaisesRegex(ValueError, "case limit"):
                stage(
                    ROOT,
                    staged,
                    case_set="synthetic",
                    case_limit=33,
                )

    def test_disposable_staging_refuses_an_unknown_case_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = pathlib.Path(temporary) / "reaper-test"

            with self.assertRaisesRegex(ValueError, "case set"):
                stage(ROOT, staged, case_set="recorded")

    def test_integration_effects_and_runner_use_the_bounded_protocol(self):
        source = SIGNAL_SOURCE.read_text(encoding="utf-8")
        capture = MIDI_CAPTURE.read_text(encoding="utf-8")
        synth_probe = SYNTH_PROBE.read_text(encoding="utf-8")
        runner = INTEGRATION_RUNNER.read_text(encoding="utf-8")

        self.assertIn("options:gmem=m3_poly_midi_tests_v1", source)
        self.assertIn("M3_INTEGRATION_REFERENCE_CAPACITY = 2048;", source)
        self.assertIn("M3_INTEGRATION_WARMUP_SECONDS = 0.500;", source)
        self.assertIn("M3_INTEGRATION_BLOCK_SIZE = 127;", source)
        self.assertIn(
            "gmem[M3_INTEGRATION_BLOCK_SIZE] = samplesblock;",
            source,
        )
        self.assertIn("m3_source_harmonic * m3_source_frequency < 0.45 * srate", source)
        self.assertIn("spl0 = m3_source_generated;", source)
        self.assertIn("spl1 = m3_source_generated;", source)
        self.assertIn("options:gmem=m3_poly_midi_tests_v1", capture)
        self.assertIn("M3_CAPTURE_MAX_EVENTS = 256;", capture)
        self.assertIn("while(midirecv(", capture)
        self.assertIn("gmem[M3_CAPTURE_DRY_ERROR]", capture)
        self.assertIn("options:gmem=m3_poly_midi_tests_v1", synth_probe)
        self.assertIn("M3_SYNTH_OUTPUT_PEAK = 2100;", synth_probe)
        self.assertIn("gmem[M3_SYNTH_OUTPUT_PEAK]", synth_probe)
        self.assertIn("local index = reaper.CountTracks(0)", runner)
        self.assertIn("Signal Source", runner)
        self.assertIn("Audio to MIDI", runner)
        self.assertIn("MIDI Capture", runner)
        self.assertIn("ReaSynth (Cockos)", runner)
        self.assertIn("Synth Output Probe", runner)
        self.assertIn('result_directory .. "/events.tsv"', runner)
        self.assertIn('result_directory .. "/summary.tsv"', runner)
        self.assertIn('result_directory .. "/safety.tsv"', runner)
        self.assertIn("local CASE_TIMEOUT_SECONDS = 10", runner)
        self.assertIn("local MATRIX_CASE_TIMEOUT_SECONDS = 20", runner)
        self.assertIn("local PANIC_TRIALS_REQUIRED = 10", runner)
        self.assertIn("local PANIC_OFF_TIMEOUT_SECONDS = 0.500", runner)
        self.assertIn("local SAFE_BYPASS_TIMEOUT_SECONDS = 0.500", runner)
        self.assertIn("local ACTUAL_BLOCK = 127", runner)
        self.assertIn("local cases, host_mode = read_cases(manifest_path)", runner)
        self.assertIn("if host_mode then\n  append_panic_trials(cases)", runner)
        self.assertIn("reaper.OnPlayButton()", runner)
        self.assertIn("reaper.defer(poll_case)", runner)
        self.assertIn("reaper.TrackFX_SetParam(track, detector_fx, 5, 0)", runner)
        self.assertIn("reaper.TrackFX_SetParam(track, detector_fx, 13, 1)", runner)
        self.assertIn("local function prime_detector_for_case()", runner)
        self.assertIn("local function capture_request_sample(case)", runner)
        self.assertIn("panic_sample = capture_request_sample(case)", runner)
        self.assertIn("panic_event_index = snapshot.count", runner)
        self.assertIn("index >= panic_event_index", runner)
        self.assertIn(
            "if state == STATE_COMPLETE and not panic_started_at then",
            runner,
        )
        self.assertIn(
            "prime_detector_for_case()\n  reaper.OnPlayButton()",
            runner,
        )
        self.assertIn("pcall(dofile, safe_bypass_path)", runner)
        self.assertIn(
            "not reaper.TrackFX_GetEnabled(track, detector_fx)",
            runner,
        )
        self.assertNotIn(
            "reaper.TrackFX_SetEnabled(track, detector_fx, false)",
            runner,
        )
        self.assertIn("reaper.TrackFX_Delete(track, detector_fx)", runner)
        self.assertIn("panic_trials_passed == PANIC_TRIALS_REQUIRED", runner)
        self.assertIn(
            'if status == "pass" then\n    case_forced_reason = nil',
            runner,
        )
        self.assertNotIn('status == "pass" and nil or reason', runner)
        self.assertIn('reaper.GetSetProjectInfo(0, "DIRTY", 0, true)', runner)
        self.assertNotIn("reaper.Main_SaveProject", runner)
        self.assertNotIn('"RENDER_STATS"', runner)
        self.assertIn("local function setup_suite()", runner)
        self.assertIn(
            "local setup_ok, setup_error = xpcall(\n"
            "  setup_suite,\n"
            "  debug.traceback\n"
            ")",
            runner,
        )
        self.assertIn(
            'failures[#failures + 1] = "setup: " .. tostring(setup_error)',
            runner,
        )
        setup = runner.index("local function setup_suite()")
        undo_begin = runner.index("reaper.Undo_BeginBlock2(0)", setup)
        setup_guard = runner.index("local setup_ok, setup_error = xpcall", setup)
        self.assertLess(undo_begin, setup_guard)
        self.assertLess(
            runner.index("atomic_write(summary_path, summary_lines)"),
            runner.index('write_phase("suite-finish")'),
        )

    def test_host_manifest_includes_real_polyphonic_cases(self):
        manifest = HOST_CASES.read_text(encoding="utf-8")
        rows = manifest.splitlines()
        expected = (
            "2\t48000\t128\tm3\t40,47\t0\t0\t0,-3\t-120\t-120\t0\t0\t"
            "50\t40,47",
            "3\t48000\t128\tm3\t32,36,40,44,48,52,56,60\t0\t0\t"
            "0,0,0,0,0,0,0,0\t-120\t-120\t0\t0\t"
            "80\t32,36,40,44,48,52,56,60",
        )
        for row in expected:
            self.assertIn(row, rows)

    def test_safe_bypass_panics_before_delayed_disable_without_delete(self):
        script = SAFE_BYPASS.read_text(encoding="utf-8")
        self.assertIn("local SAFE_BYPASS_MIN_DELAY_SECONDS = 0.100", script)
        self.assertIn("local SAFE_BYPASS_PROCESS_BLOCKS = 4", script)
        self.assertIn('audio_number("SRATE", 48000)', script)
        self.assertIn('audio_number("BSIZE", 512)', script)
        self.assertIn("math.max(", script)
        self.assertNotIn("SAFE_BYPASS_DELAY_SECONDS = 0.050", script)
        self.assertIn("reaper.TrackFX_GetFXGUID(track, detector_fx)", script)
        self.assertIn(
            "reaper.TrackFX_SetParam(track, detector_fx, 4, 0)",
            script,
        )
        self.assertIn(
            "reaper.TrackFX_SetParam(track, detector_fx, 13, 1)",
            script,
        )
        self.assertIn("reaper.defer(disable_detector)", script)
        self.assertIn(
            "reaper.TrackFX_SetEnabled(track, current_fx, false)",
            script,
        )
        self.assertIn(
            "reaper.TrackFX_SetParam(\n"
            "    track, current_fx, 4, original_sensitivity\n"
            "  )",
            script,
        )
        disable = script.index(
            "reaper.TrackFX_SetEnabled(track, current_fx, false)"
        )
        restore = script.index(
            "reaper.TrackFX_SetParam(\n"
            "    track, current_fx, 4, original_sensitivity\n"
            "  )",
            disable,
        )
        verify = script.index(
            "reaper.TrackFX_GetEnabled(track, current_fx)", disable
        )
        self.assertLess(disable, restore)
        self.assertLess(restore, verify)
        self.assertNotIn("TrackFX_Delete", script)

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
            "M3_MAX_CANDIDATES": 87,
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
        self.assertEqual(profile.get("M3_PROFILE_DP_WORDS"), 768)
        self.assertEqual(
            profile["M3_PROFILE_DP_WORDS"],
            3 * profile["M3_PROFILE_DP_ROW_SIZE"],
        )
        self.assertLessEqual(
            profile["M3_PROFILE_DP_WORDS"],
            constants["M3_VOICE_BASE"] - constants["M3_M3_SCRATCH_BASE"],
        )

    def test_m3_selection_shortlist_stays_inside_fixed_workspace(self):
        constants = parse_integer_assignments(CONSTANTS)
        selector = parse_integer_assignments(SELECTOR)
        self.assertEqual(selector.get("M3_SELECTION_INTERNAL_CANDIDATES"), 16)
        self.assertEqual(selector.get("M3_SELECTION_RESULT_WORDS"), 64)
        self.assertEqual(selector.get("M3_SELECTION_RESIDUAL_OFFSET"), 64)
        self.assertEqual(
            selector.get("M3_SELECTION_PROFILE_RESIDUAL_OFFSET"),
            149,
        )
        self.assertEqual(selector.get("M3_SELECTION_WORK_WORDS"), 234)
        self.assertEqual(selector.get("M3_SELECTION_SMOOTHED_ENERGY_OFFSET"), 256)
        self.assertEqual(selector.get("M3_SELECTION_RAW_ENERGY_OFFSET"), 343)
        self.assertLessEqual(
            selector["M3_SELECTION_RAW_ENERGY_OFFSET"] +
            constants["M3_MAX_CANDIDATES"],
            constants["M3_SELECTION_BASE"] - constants["M3_SALIENCE_BASE"],
        )
        self.assertLessEqual(
            selector["M3_SELECTION_WORK_WORDS"],
            constants["M3_M3_SCRATCH_BASE"] - constants["M3_SELECTION_BASE"],
        )

    def test_general_selector_has_bounded_shared_partial_regressions(self):
        selector = SELECTOR.read_text(encoding="utf-8")
        profile = PROFILE.read_text(encoding="utf-8")
        core_tests = CORE_TESTS.read_text(encoding="utf-8")
        observer = CORE_OBSERVER.read_text(encoding="utf-8")
        self.assertIn("M3_SELECTION_GENERAL_LOCAL_ENERGY_RATIO = 1.05;", selector)
        self.assertIn("M3_SELECTION_M3_LOCAL_ENERGY_RATIO = 1.05;", selector)
        self.assertIn(
            "M3_SELECTION_GENERAL_PLATEAU_ENERGY_RATIO = 1.00;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_LOW_OPEN_NOTE = 32;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_LOW_OPEN_ENERGY_RATIO = 0.90;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_PLATEAU_FUNDAMENTAL_RATIO = 0.98;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_PLATEAU_CONFIDENCE_FLOOR = 0.30;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_PLATEAU_MIN_NOTE = 32;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_PLATEAU_MAX_NOTE = 35;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_M3_FUNDAMENTAL_PLATEAU_RATIO = 0.85;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_M3_MISSING_FUNDAMENTAL_RATIO = 0.15;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_MISSING_FUNDAMENTAL_RATIO = 0.10;",
            selector,
        )
        self.assertIn("M3_PROFILE_OPEN_CHORD_MIN_OPENS = 2;", profile)
        self.assertIn("M3_PROFILE_FRETTED_NOTE_PENALTY = 0.60;", profile)
        self.assertIn("M3_PROFILE_FRET_PENALTY = 0.005;", profile)
        self.assertIn("function m3_profile_open_note(note)", profile)
        self.assertIn(
            "next_score = state_score + confidence - assignment_penalty;",
            profile,
        )
        self.assertIn("note > M3_M3_OPEN_7", profile)
        self.assertIn(
            "M3_SELECTION_MISSING_FUNDAMENTAL_ALIAS_SCORE_RATIO = 0.90;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_MISSING_FUNDAMENTAL_ALIAS_ROOT_RATIO = 0.15;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_MISSING_ROOT_PROBE_COUNT = 9;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_MISSING_MIN_GLOBAL_ENERGY_RATIO = 0.65;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_MISSING_FUNDAMENTAL_PARENT_ENERGY_RATIO = 0.80;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_MISSING_MIN_NOTE = 32;",
            selector,
        )
        self.assertIn("M3_SELECTION_SHARED_FUNDAMENTAL_RATIO = 0.40;", selector)
        self.assertIn(
            "M3_SELECTION_SHARED_FIFTH_FUNDAMENTAL_RATIO = 0.30;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_SHARED_FUNDAMENTAL_RATIO = 0.60;",
            selector,
        )
        self.assertIn(
            "M3_SELECTION_GENERAL_OCTAVE_WEIGHTED_RATIO = 0.40;",
            selector,
        )
        self.assertIn(
            "function m3_selection_downweight_general_octave_aliases(",
            selector,
        )
        self.assertIn("function m3_selection_contains_note(", selector)
        self.assertIn("dense_context_count >= 2", selector)
        self.assertIn(
            "function m3_selection_downweight_missing_fundamental_aliases(",
            selector,
        )
        self.assertIn(
            "function m3_selection_downweight_missing_fundamental_lower_aliases(",
            selector,
        )
        self.assertIn("M3_SELECTION_FUNDAMENTAL_DOMINANCE_RATIO = 0.80;", selector)
        self.assertIn("M3_SELECTION_SHARED_PARTIAL_RESIDUAL_FACTOR = 0.10;", selector)
        self.assertIn("M3_SELECTION_ENERGY_SMOOTH_SECONDS = 0.008;", selector)
        self.assertIn("M3_SELECTION_GENERAL_ACQUISITION_SECONDS = 0.002;", selector)
        self.assertIn("M3_SELECTION_M3_ACQUISITION_SECONDS = 0.002;", selector)
        self.assertIn("fundamental_local_peak", selector)
        self.assertIn("function m3_selection_shared_partial_interval(", selector)
        self.assertIn(
            "function m3_selection_general_quiet_interval(interval)",
            selector,
        )
        self.assertIn(
            "shared_partial && !general_quiet_interval ? (",
            selector,
        )
        self.assertIn(
            "general_quiet_interval = allow_fundamental_dominance &&\n"
            "              (general_quiet_context ||",
            selector,
        )
        production = PRODUCTION.read_text(encoding="utf-8")
        self.assertIn(
            "profile_mode == M3_PROFILE_MODE_M3\n"
            "      ? M3_SELECTION_M3_ACQUISITION_SECONDS\n"
            "      : M3_SELECTION_GENERAL_ACQUISITION_SECONDS",
            production,
        )
        self.assertIn(
            "profile_mode == M3_PROFILE_MODE_M3\n"
            "      ? M3_SELECTION_M3_LOCAL_ENERGY_RATIO\n"
            "      : M3_SELECTION_GENERAL_LOCAL_ENERGY_RATIO",
            production,
        )
        self.assertIn(
            "selected_voice_allow_fundamental_dominance =\n"
            "      profile_mode == M3_PROFILE_MODE_M3 ? 0 : 1;",
            production,
        )
        self.assertIn(
            "selected_voice_local_energy_ratio,\n"
            "      selected_voice_allow_fundamental_dominance,\n"
            "      samplesblock,\n"
            "      srate,",
            production,
        )
        self.assertIn("case_id == 12101", core_tests)
        self.assertIn("case_id == 12102", core_tests)
        self.assertIn("case_id == 12103", core_tests)
        self.assertIn("case_id == 12104", core_tests)
        self.assertIn("case_id == 12105", core_tests)
        self.assertIn("case_id == 12106", core_tests)
        self.assertIn("case_id == 12107", core_tests)
        self.assertIn("case_id == 12108", core_tests)
        self.assertIn("case_id == 12109", core_tests)
        self.assertIn("case_id == 12110", core_tests)
        self.assertIn("case_id == 12111", core_tests)
        self.assertIn("case_id == 12112", core_tests)
        self.assertIn("case_id == 12113", core_tests)
        self.assertIn("case_id == 12114", core_tests)
        self.assertIn("case_id == 12115", core_tests)
        self.assertIn("case_id == 12116", core_tests)
        self.assertIn("case_id == 12117", core_tests)
        self.assertIn("case_id == 12118", core_tests)
        self.assertIn(
            "(test_bank_case_id >= 12101 && test_bank_case_id <= 12103)",
            core_tests,
        )
        self.assertIn(
            "(test_bank_case_id >= 12107 && test_bank_case_id <= 12108)",
            core_tests,
        )
        self.assertIn("function m3_test_realtime_select_m3(", core_tests)
        self.assertIn(
            "m3_test_realtime_single_on_error(test_sr, 32, 1)",
            core_tests,
        )
        self.assertIn(
            "m3_test_realtime_single_on_error(test_sr, 48, 1)",
            core_tests,
        )
        lifecycle = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn(
            "M3_LIFECYCLE_GENERAL_OCTAVE_ENERGY_RATIO = 0.70;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_GENERAL_OCTAVE_GUARD_MAX_PARENT_NOTE = 84;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_GENERAL_HARMONIC_ENERGY_RATIO = 0.55;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_GENERAL_HARMONIC_PARENT_COUNT = 5;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_STALE_ATTACK_DROPOUT_MULTIPLIER = 11;",
            lifecycle,
        )
        self.assertEqual(
            lifecycle.count(
                "energy_decay = exp(-elapsed / max(1, stale_attack_limit));"
            ),
            2,
        )
        self.assertGreaterEqual(
            lifecycle.count(
                "energy_decay * cell[M3_VOICE_ENERGY_OFFSET]"
            ),
            2,
        )
        self.assertIn(
            "M3_LIFECYCLE_ATTACK_ADMISSION_SLOW_RATIO = 0.10;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_GENERAL_STACK_SPAN_SEMITONES = 28;",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_attack_admission_allowed(",
            lifecycle,
        )
        self.assertIn("function m3_lifecycle_snapshot_active(", lifecycle)
        self.assertIn(
            "m3_lifecycle_attack_admission = analysis_signal_present &&",
            production,
        )
        self.assertIn("function m3_lifecycle_octave_alias_blocked(", lifecycle)
        self.assertIn("stacked_octave_context", lifecycle)
        self.assertIn(
            "function m3_lifecycle_general_stacked_context(",
            lifecycle,
        )
        self.assertIn(
            "note - m3_lifecycle_context_anchor_lowest_note <=",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_context_anchor_lowest_note = 128;",
            lifecycle,
        )
        self.assertIn(
            "max(attack_bridge_limit, attack_dropout_limit)",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_general_harmonic_alias_blocked(",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_general_shared_octave_blocked(",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_general_octave_guard =\n"
            "    profile_mode == M3_PROFILE_MODE_GENERAL;",
            production,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_LOW_STRING_MIN_NOTE = 24;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_LOW_STRING_MAX_NOTE = 35;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_LOW_OPEN_NOTE = 32;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_FAST_OPEN_ATTACK_SECONDS = 0.002;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_GUARDED_OPEN_ATTACK_SECONDS = 0.005;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_FAST_OPEN_CONFIDENCE_FLOOR = 0.52;",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_m3_open_attack_samples(note, confidence)",
            lifecycle,
        )
        self.assertIn("note == M3_M3_OPEN_4 &&", lifecycle)
        self.assertIn(
            "M3_LIFECYCLE_M3_LOW_CHORD_ATTACK_SECONDS = 0.040;",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_m3_low_chord_context(",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_m3_low_chord_attack_samples = max(",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_OPEN_CONFIDENCE_FLOOR = 0.50;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_OPEN_52_CONFIDENCE_FLOOR = 0.48;",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_m3_open_confidence_allowed(",
            lifecycle,
        )
        self.assertIn("note == M3_M3_OPEN_2 ||", lifecycle)
        self.assertIn(
            "M3_LIFECYCLE_M3_MIN_DROPOUT_SECONDS = 0.024;",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_m3_low_string_conflict(",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_m3_low_string_guard =\n"
            "    profile_mode == M3_PROFILE_MODE_M3;",
            production,
        )
        self.assertIn(
            "m3_lifecycle_m3_low_open_fast_attack =\n"
            "    profile_mode == M3_PROFILE_MODE_M3;",
            production,
        )
        self.assertIn("m3_lifecycle_attack_hysteresis = 1;", production)
        self.assertIn(
            "m3_lifecycle_attack_bridge_samples = 2 * samplesblock;",
            production,
        )
        self.assertIn(
            "m3_lifecycle_attack_evidence_step_samples = samplesblock;",
            production,
        )
        self.assertIn(
            "? min(max(0, elapsed), attack_evidence_step_limit)",
            lifecycle,
        )
        self.assertIn(
            "? min(attack_limit, attack_evidence_step_limit)",
            lifecycle,
        )
        self.assertIn(
            "evidence_energy >= 2 * m3_lifecycle_min_attack_energy",
            lifecycle,
        )
        self.assertIn(
            "note_attack_limit = max(note_attack_limit, dropout_limit);",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_reserve_lower_attacks =\n"
            "    profile_mode == M3_PROFILE_MODE_GENERAL &&\n"
            "    max_polyphony < M3_MAX_VOICES;",
            production,
        )
        self.assertIn(
            "active_count + lower_attack_count < active_limit",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_GENERAL_CAPPED_ATTACK_SECONDS = 0.060;",
            lifecycle,
        )
        self.assertIn(
            "note_attack_limit = max(\n"
            "          note_attack_limit,\n"
            "          m3_lifecycle_general_capped_attack_samples",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_m3_low_chord_context(note, m3_high_open_context) ? (",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_m3_low_chord_attack_samples",
            lifecycle,
        )
        self.assertIn("highest_active_note > note &&", lifecycle)
        self.assertIn(
            "attack_dropout_limit = m3_lifecycle_reserve_lower_attacks",
            lifecycle,
        )
        self.assertIn("elapsed > attack_dropout_limit ? (", lifecycle)
        self.assertGreaterEqual(
            lifecycle.count("now - cell[M3_VOICE_LAST_EVIDENCE_OFFSET] <="),
            2,
        )
        self.assertIn("replacement_note = highest_active_note;", lifecycle)
        self.assertIn(
            "event_base[M3_EVENT_COUNT_OFFSET] <= M3_MAX_EVENTS - 2",
            lifecycle,
        )
        self.assertIn("general_quiet_context =", selector)
        self.assertIn(
            "M3_SELECTION_GENERAL_QUIET_CONFIDENCE_FLOOR = 0.30;",
            selector,
        )
        self.assertIn(
            "residual_base[candidate] = max(\n"
            "                residual_base[candidate],\n"
            "                M3_SELECTION_GENERAL_QUIET_CONFIDENCE_FLOOR",
            selector,
        )
        self.assertIn("octave_chord_context =", selector)
        self.assertIn(
            "!m3_lifecycle_attack_hysteresis ? (\n"
            "            cell[M3_VOICE_CONFIDENCE_OFFSET] = 0;",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_m3_low_open_fast_attack &&\n"
            "      m3_lifecycle_m3_open_note(note)",
            lifecycle,
        )
        self.assertGreaterEqual(
            lifecycle.count("m3_lifecycle_m3_open_note(note)"),
            2,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_MIN_ATTACK_SECONDS = 0.009;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_LOW_OPEN_CONFIDENCE_FLOOR = 0.44;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_HIGH_OPEN_ATTACK_SECONDS = 0.009;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_GENERAL_MIN_ATTACK_SECONDS = 0.008;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_PARENT_CONFIRMATION_BLOCKS = 6;",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_MATURE_PARENT_ENERGY_RATIO = 0.80;",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_m3_mature_parent_alias_blocked(",
            lifecycle,
        )
        self.assertIn(
            "!m3_lifecycle_m3_mature_parent_alias_blocked(",
            lifecycle,
        )
        self.assertIn(
            "M3_LIFECYCLE_M3_MULTI_PARENT_ENERGY_RATIO = 0.80;",
            lifecycle,
        )
        self.assertIn("function m3_lifecycle_m3_open_note(note)", lifecycle)
        self.assertIn(
            "function m3_lifecycle_m3_adjacent_shadow_blocked(",
            lifecycle,
        )
        self.assertIn(
            "m3_lifecycle_m3_open_note(neighbor_note) &&",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_m3_parent_unconfirmed(",
            lifecycle,
        )
        self.assertIn(
            "function m3_lifecycle_m3_multi_parent_alias_blocked(",
            lifecycle,
        )
        self.assertIn(
            "M3_SELECTION_SHARED_PARTIAL_FACTOR = 0.25;",
            selector,
        )
        self.assertIn(
            "m3_lifecycle_max_active_voices = max_polyphony;",
            production,
        )
        self.assertIn(
            "profile_mode == M3_PROFILE_MODE_GENERAL ? candidate_count : (",
            profile,
        )
        self.assertIn(
            "selected_voice_candidate_limit =\n"
            "      profile_mode == M3_PROFILE_MODE_M3\n"
            "      ? M3_SELECTION_INTERNAL_CANDIDATES\n"
            "      : M3_MAX_VOICES;",
            production,
        )
        self.assertIn(
            "candidate_count = min(\n"
            "    M3_MAX_VOICES,\n"
            "    max(0, floor(selected_count))\n"
            "  );",
            lifecycle,
        )
        self.assertIn(
            "iteration_count = floor(m3_clamp(\n"
            "    max_voices,\n"
            "    0,\n"
            "    M3_SELECTION_INTERNAL_CANDIDATES\n"
            "  ));",
            selector,
        )
        self.assertIn(
            "M3_SALIENCE_BASE[M3_SALIENCE_EFFECTIVE_THRESHOLD_OFFSET],\n"
            "      selected_voice_candidate_limit,",
            production,
        )
        self.assertIn(
            "expected_case >= 12101 and expected_case <= 12118",
            observer,
        )
        self.assertIn("expected_case == 5102 and 4 or", observer)
        self.assertIn("expected_case == 12108 and 6 or", observer)
        self.assertIn("expected_case == 12110 and 8 or", observer)
        self.assertIn("expected_case == 12114 and 12 or", observer)
        self.assertIn("expected_case == 12113 and 5 or", observer)
        self.assertIn("expected_case == 12115 and 7 or", observer)
        self.assertIn("expected_case == 12117 and 6 or", observer)
        self.assertIn("expected_case == 12118 and 4 or 3", observer)

    def test_lifecycle_memory_contract(self):
        constants = parse_integer_assignments(CONSTANTS)
        lifecycle = parse_integer_assignments(LIFECYCLE)
        self.assertEqual(lifecycle.get("M3_VOICE_CELL_SIZE"), 8)
        self.assertEqual(lifecycle.get("M3_EVENT_HEADER_SIZE"), 2)
        self.assertEqual(lifecycle.get("M3_EVENT_CELL_SIZE"), 5)
        self.assertEqual(lifecycle.get("M3_LIFECYCLE_SUB_GSHARP_MAX_NOTE"), 31)
        self.assertIn(
            "M3_LIFECYCLE_M3_MIN_RELEASE_SECONDS = 0.048;",
            LIFECYCLE.read_text(encoding="utf-8"),
        )
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
            "m3_host_signal_present(",
            "m3_host_panic_hold_next(",
            "m3_host_apply_bounds(",
            "m3_host_reset_detector(",
        ):
            self.assertIn(interface, emitter)
        self.assertIn("M3_HOST_MIN_SIGNAL_ENERGY = 0.00000001;", emitter)
        self.assertIn("M3_HOST_PANIC_RELEASE_PEAK = 0.0001;", emitter)

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
        self.assertIn(
            "panic_hold = m3_host_panic_hold_next(\n"
            "  panic_hold, panic_requested, block_input_peak\n"
            ");",
            block,
        )
        self.assertIn("!panic_hold", block)
        self.assertIn(
            "analysis_signal_present = m3_host_signal_present(\n"
            "    M3_CONDITION_BASE[10]\n"
            "  );",
            block,
        )
        self.assertIn("analysis_signal_present ? (", block)
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
