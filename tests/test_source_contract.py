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
