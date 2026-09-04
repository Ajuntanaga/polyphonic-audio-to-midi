import pathlib
import tempfile
import unittest


from tools.stage_live_midi_env import (
    DEFAULT_INPUT_DEVICE,
    DEFAULT_OUTPUT_DEVICE,
    LIVE_REAPER_PROFILE,
    stage_live_profile,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]


class StageLiveMidiProfileTests(unittest.TestCase):
    def test_stages_isolated_revelator_profile_with_live_guitar_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "m3-live-midi"

            stage_live_profile(ROOT, output)

            profile = (output / "reaper.ini").read_text(encoding="utf-8")
            self.assertIn("linux_audio_mode=1\n", profile)
            self.assertIn(f"alsa_indev={DEFAULT_INPUT_DEVICE}\n", profile)
            self.assertIn(f"alsa_outdev={DEFAULT_OUTPUT_DEVICE}\n", profile)
            self.assertIn("linux_audio_srate=48000\n", profile)
            self.assertIn("linux_audio_bsize=256\n", profile)
            self.assertIn("linux_audio_nch_in=6\n", profile)
            self.assertIn("linux_audio_nch_out=2\n", profile)
            self.assertNotIn(str(LIVE_REAPER_PROFILE), profile)

            detector = output / "Effects/ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx"
            self.assertTrue(detector.is_file())
            setup = (output / "Scripts/ajuntanaga_M3 Live Guitar to MIDI.lua").read_text(
                encoding="utf-8"
            )
            self.assertIn("M3 8-String Guitar to MIDI (low range)", setup)
            self.assertIn("JS: ajuntanaga_M3 Polyphonic Audio to MIDI", setup)
            self.assertIn("ReaSynth (Cockos)", setup)
            self.assertIn('"I_RECINPUT", 0', setup)
            self.assertIn('"I_RECMON", 1', setup)
            self.assertIn("detector, 7, 48", setup)
            self.assertIn("detector, 8, 1", setup)
            self.assertIn("detector, 9, 12", setup)

    def test_refuses_to_stage_into_live_reaper_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "live REAPER profile"):
            stage_live_profile(ROOT, LIVE_REAPER_PROFILE)

    def test_stages_native_detector_bundle_in_a_separate_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = pathlib.Path(temporary)
            output = temporary_root / "m3-native-live-midi"
            bundle = (
                temporary_root
                / "M3_Polyphonic_Audio_to_MIDI.vst3"
                / "Contents/x86_64-linux"
            )
            bundle.mkdir(parents=True)
            (bundle / "M3_Polyphonic_Audio_to_MIDI.so").write_bytes(b"native")

            stage_live_profile(
                ROOT,
                output,
                detector="native",
                native_bundle=bundle.parents[1],
            )

            profile = (output / "reaper.ini").read_text(encoding="utf-8")
            self.assertIn(f"vstpath={output / 'VST3'}\n", profile)
            copied_bundle = (
                output
                / "VST3/M3_Polyphonic_Audio_to_MIDI.vst3"
                / "Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI.so"
            )
            self.assertEqual(copied_bundle.read_bytes(), b"native")
            setup = (output / "Scripts/ajuntanaga_M3 Live Guitar to MIDI.lua").read_text(
                encoding="utf-8"
            )
            self.assertIn("VST3: M3 Polyphonic Audio to MIDI", setup)
            self.assertIn("TrackFX_SetParamNormalized(track, detector, 0, 0.0)", setup)
            self.assertIn(
                "TrackFX_SetParamNormalized(track, detector, 7, 0.285714285714)",
                setup,
            )
            self.assertIn("TrackFX_SetParamNormalized(track, detector, 8, 0.0)", setup)
            self.assertIn("TrackFX_SetParamNormalized(track, detector, 14, 0.0)", setup)


if __name__ == "__main__":
    unittest.main()
