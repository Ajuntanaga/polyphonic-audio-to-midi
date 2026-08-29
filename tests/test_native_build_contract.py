import hashlib
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/native/jsfx-48k128"
CLAP = ROOT / "third_party/clap"
JSFX_PATHS = (
    "Effects/ajuntanaga_M3 Polyphonic Audio to MIDI.jsfx",
    "Effects/m3_poly_midi",
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NativeBuildContractTests(unittest.TestCase):
    def test_frozen_jsfx_oracle_is_complete_and_identified(self):
        required = (
            "ORIGIN.md",
            "SHA256SUMS",
            "cases.tsv",
            "events.tsv",
            "safety.tsv",
            "summary.tsv",
        )
        self.assertEqual(
            sorted(path.name for path in FIXTURE.iterdir()),
            sorted(required),
        )
        self.assertEqual(
            sha256(FIXTURE / "cases.tsv"),
            "5a2d0b4c9ced2f8f97248bdf164118ed3882307adcc41c976f429b363ff88dd3",
        )
        self.assertEqual(
            sha256(FIXTURE / "events.tsv"),
            "a695ebdc5ac641bf3f51b16cfd0f48dca08f3723f717e296bde003bb437c2f2a",
        )

    def test_production_jsfx_matches_the_frozen_checkpoint(self):
        result = subprocess.run(
            ["git", "diff", "--exit-code", "0be04d3", "--", *JSFX_PATHS],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_sources_exclude_unapproved_dependencies(self):
        forbidden = (
            "NeuralNote",
            "Basic Pitch",
            "ReaTune",
            "ONNX",
            "Torch",
            "TensorFlow",
            "curl/",
            "sys/socket",
            ".onnx",
            ".pt",
            ".tflite",
        )
        roots = (ROOT / "native", ROOT / "third_party")
        for source_root in roots:
            if not source_root.exists():
                continue
            for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
                text = path.read_text(encoding="utf-8", errors="ignore")
                for token in forbidden:
                    self.assertNotIn(token, text, f"{token!r} found in {path}")

    def test_native_build_rules_use_only_the_approved_toolchain(self):
        forbidden = ("-march=native", "cmake", "ninja", "juce", "iplug2")
        for path in sorted((ROOT / "native").glob("*Makefile")) if (ROOT / "native").exists() else ():
            text = path.read_text(encoding="utf-8").lower()
            for token in forbidden:
                self.assertNotIn(token, text, f"{token!r} found in {path}")

    def test_vendored_clap_headers_have_exact_upstream_and_hashes(self):
        upstream = (CLAP / "UPSTREAM.md").read_text(encoding="utf-8")
        for required in (
            "https://github.com/free-audio/clap",
            "1.2.10",
            "195b42a004144fab0b3cf95e9c067187d15365b7",
            "include/clap",
            "LICENSE",
        ):
            self.assertIn(required, upstream)

        copied = {
            path.relative_to(CLAP).as_posix()
            for path in CLAP.rglob("*")
            if path.is_file()
            and path.name not in {"UPSTREAM.md", "SHA256SUMS"}
        }
        self.assertIn("LICENSE", copied)
        self.assertTrue(any(name.startswith("include/clap/") for name in copied))
        self.assertTrue(
            all(name == "LICENSE" or name.startswith("include/clap/") for name in copied)
        )

        recorded = {}
        for line in (CLAP / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            recorded[name] = digest
        self.assertEqual(set(recorded), copied)
        for name, expected in recorded.items():
            self.assertEqual(sha256(CLAP / name), expected, name)

        license_text = (CLAP / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)


if __name__ == "__main__":
    unittest.main()
