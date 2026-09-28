import binascii
import hashlib
import json
import pathlib
import struct
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/m3_physical_a440"


class PhysicalCalibrationFixtureTests(unittest.TestCase):
    def test_complete_a440_bank_is_sealed_and_structurally_valid(self):
        manifest = json.loads((FIXTURE / "manifest-v1.json").read_text())
        calibration = (FIXTURE / manifest["calibration_file"]).read_bytes()

        self.assertEqual(manifest["schema"], 1)
        self.assertEqual(manifest["format"], "M3CB-v1")
        self.assertEqual(manifest["calibration_method"], "pass-balanced-v1")
        self.assertEqual(
            manifest["calibration_pass_roles"],
            [
                "ascending_walk_timbre_and_pitch",
                "descending_walk_timbre_and_pitch",
                "isolated_notes_pitch_only",
            ],
        )
        self.assertEqual(manifest["a4_hz"], 440)
        self.assertEqual(manifest["sample_rate_hz"], 96000)
        self.assertEqual(manifest["string_count"], 8)
        self.assertEqual(manifest["fret_range"], [0, 24])
        self.assertEqual(len(manifest["recording_sha256_thick_to_thin"]), 8)
        self.assertTrue(
            all(
                len(value) == 64 and set(value) <= set("0123456789abcdef")
                for value in manifest["recording_sha256_thick_to_thin"]
            )
        )
        self.assertEqual(hashlib.sha256(calibration).hexdigest(),
                         manifest["calibration_sha256"])

        self.assertEqual(len(calibration), 3825)
        self.assertEqual(calibration[:4], b"M3CB")
        version, strings, frets, harmonics, payload_size, payload_crc, reserved = (
            struct.unpack_from("<HHHHIII", calibration, 4)
        )
        self.assertEqual((version, strings, frets, harmonics), (1, 8, 25, 6))
        self.assertEqual(payload_size, len(calibration) - 24)
        self.assertEqual(payload_crc,
                         binascii.crc32(calibration[24:]) & 0xFFFFFFFF)
        self.assertEqual(reserved, 0)
        self.assertEqual(calibration[24], 0xFF)


if __name__ == "__main__":
    unittest.main()
