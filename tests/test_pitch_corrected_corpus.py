import math
import binascii
import pathlib
import sys
import tempfile
import unittest
import wave

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_pitch_corrected_corpus as corpus
import render_pitch_corrected_corpus_reaper as reaper_corpus


class PitchCorrectedCorpusTests(unittest.TestCase):
    def test_reaper_finalization_restores_silence_outside_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            rendered = root / "rendered.wav"
            labels = root / "labels.tsv"
            sample_values = [
                0x010203,
                -0x010203,
                0x111213,
                -0x111213,
                0x212223,
                -0x212223,
                0x313233,
                -0x313233,
                0x414243,
                -0x414243,
            ]
            with wave.open(str(rendered), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(3)
                stream.setframerate(96_000)
                stream.writeframes(
                    b"".join(
                        (value & 0xFFFFFF).to_bytes(3, "little")
                        for value in sample_values
                    )
                )
            labels.write_text(
                "start_sample\tend_sample\tmidi_note\tstring_mask\t"
                "calibration_pass\n"
                "2\t5\t40\t128\t1\n"
                "7\t9\t41\t128\t1\n",
                encoding="ascii",
            )

            reaper_corpus.silence_unlabeled_regions(rendered, labels)

            with wave.open(str(rendered), "rb") as stream:
                frames = stream.readframes(stream.getnframes())
            actual = [
                int.from_bytes(frames[index : index + 3], "little", signed=True)
                for index in range(0, len(frames), 3)
            ]
            self.assertEqual(
                actual,
                [0, 0, *sample_values[2:5], 0, 0, *sample_values[7:9], 0],
            )

    def test_zero_centered_bank_retains_every_non_pitch_calibration_field(self):
        source = ROOT / "tests/fixtures/m3_physical_a440/calibration-v1.m3cb"
        original = source.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "zero.m3cb"
            corpus.write_zero_centered_calibration(source, output)
            centered = output.read_bytes()

        self.assertEqual(len(centered), len(original))
        self.assertEqual(centered[:16], original[:16])
        self.assertEqual(centered[20:25], original[20:25])
        self.assertEqual(
            int.from_bytes(centered[16:20], "little"),
            binascii.crc32(centered[24:]) & 0xFFFFFFFF,
        )
        for point in range(8 * 25):
            offset = 25 + point * 19
            self.assertEqual(centered[offset : offset + 2], b"\0\0")
            self.assertEqual(centered[offset + 2 : offset + 19],
                             original[offset + 2 : offset + 19])

    def test_midpoint_bank_halves_pitch_centers_only(self):
        source = ROOT / "tests/fixtures/m3_physical_a440/calibration-v1.m3cb"
        original = source.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "midpoint.m3cb"
            corpus.write_scaled_center_calibration(source, output, 0.5)
            midpoint = output.read_bytes()

        for point in range(8 * 25):
            offset = 25 + point * 19
            original_cents = int.from_bytes(
                original[offset : offset + 2], "little", signed=True
            )
            midpoint_cents = int.from_bytes(
                midpoint[offset : offset + 2], "little", signed=True
            )
            self.assertEqual(midpoint_cents, round(original_cents * 0.5))
            self.assertEqual(midpoint[offset + 2 : offset + 19],
                             original[offset + 2 : offset + 19])

    def test_reaper_project_uses_elastique_pro_and_exact_segment_geometry(self):
        manifest = {
            "sample_rate_hz": 96_000,
            "source_wave": "/recordings/string.wav",
            "silence_frames_between_holds": 24_000,
            "output_sample_count": 120_000,
            "physical_string_number": 8,
            "observations": [
                {
                    "label_index": 0,
                    "source_start_sample": 48_000,
                    "source_end_sample": 96_000,
                    "target_hz": 110.0,
                    "measured_hz": 108.0,
                }
            ],
        }
        project = reaper_corpus.build_reaper_project(
            manifest,
            pathlib.Path("/renders/string-08-midpoint.wav"),
            correction_fraction=0.5,
        )

        expected_pitch = 0.5 * 12.0 * math.log2(110.0 / 108.0)
        self.assertIn("DEFPITCHMODE 589825 0", project)
        self.assertIn(
            f"PLAYRATE 1 1 {expected_pitch:.12f} 589825 0 0.0025", project
        )
        self.assertIn("POSITION 0.050000000000", project)
        self.assertIn("LENGTH 0.700000000000", project)
        self.assertIn("SOFFS 0.300000000000 0", project)
        self.assertIn('FILE "/recordings/string.wav"', project)
        self.assertIn('RENDER_FILE "/renders/string-08-midpoint.wav"', project)

    def test_generation_preserves_label_spans_and_measures_correction(self):
        sample_rate = 48_000
        midi_note = 57
        target_hz = 440.0 * math.pow(2.0, (midi_note - 69) / 12.0)
        source_hz = target_hz * math.pow(2.0, -24.0 / 1200.0)
        total = sample_rate * 2
        time = np.arange(total, dtype=np.float64) / sample_rate
        samples = (0.25 * np.sin(2.0 * math.pi * source_hz * time)).astype(
            np.float32
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source = root / "source.wav"
            labels = root / "labels.tsv"
            output = root / "out"
            corpus.write_float_wave(source, samples, sample_rate)
            labels.write_text(
                "start_sample\tend_sample\tmidi_note\tstring_mask\t"
                "calibration_pass\n"
                f"12000\t60000\t{midi_note}\t128\t1\n",
                encoding="ascii",
            )

            manifest = corpus.generate_string_corpus(
                source, labels, output, string_index=7, silence_seconds=0.1
            )
            raw, raw_rate = corpus.read_float_wave(output / "string-01-raw.wav")
            output_labels = corpus.read_labels(output / "string-01.tsv")

            self.assertEqual(raw_rate, sample_rate)
            self.assertEqual(len(output_labels), 1)
            label = output_labels[0]
            self.assertEqual(label.end_sample - label.start_sample, 48_000)
            self.assertEqual(label.calibration_pass, 1)
            self.assertTrue(np.array_equal(
                raw[label.start_sample:label.end_sample], samples[12000:60000]
            ))
            self.assertEqual(manifest["label_count"], 1)
            self.assertEqual(manifest["sample_rate_hz"], sample_rate)
            self.assertEqual(
                manifest["correction_plan"], "reaper-elastique-3-pro-v1"
            )
            correction = manifest["observations"][0][
                "pitch_correction_semitones"
            ]
            self.assertAlmostEqual(correction, 0.24, delta=0.02)


if __name__ == "__main__":
    unittest.main()
