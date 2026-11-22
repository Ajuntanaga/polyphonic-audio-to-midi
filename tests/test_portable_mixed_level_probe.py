import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

for _name in ('onnx', 'onnxruntime', 'soundfile'):      # the worker has the real packages; no model is run in these tests either way
    try:
        __import__(_name)
    except ImportError:
        sys.modules[_name] = types.ModuleType(_name)

from tools import mixed_level_analysis as analysis
from tools import portable_mixed_level_probe as runner

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'docs/recovery/mixed-level-probe-20261122.json'
SPEC = json.loads(SPEC_PATH.read_text())


class FakeSession:
    """Stands in for an onnxruntime session: the note posterior rises with the window's loudest sample, the scalars follow a pinned floor."""
    def __init__(self, exposed):
        self.exposed = exposed

    def get_inputs(self):
        return [types.SimpleNamespace(name=runner.INPUT, shape=[1, 43844, 1])]

    def get_outputs(self):
        names = [runner.NOTE, runner.ONSET] + ([runner.MINIMUM, runner.RANGE] if self.exposed else [])
        return [types.SimpleNamespace(name=n) for n in names]

    def run(self, names, feed):
        x = feed[runner.INPUT]
        assert x.shape == (1, 43844, 1) and x.dtype == np.float32
        peak = float(np.abs(x).max())
        note = np.zeros((1, 172, 88), dtype=np.float32)
        note[0, 150:, :] = min(1.0, peak)
        onset = np.zeros_like(note)
        values = {runner.NOTE: note, runner.ONSET: onset, runner.MINIMUM: np.array([-100.0], dtype=np.float32),
                  runner.RANGE: np.array([20.0 * np.log10(peak + 1e-9) + 100.0], dtype=np.float32)}
        return [values[n] for n in names]


def fake_collect(spec, folders):
    paths = {}
    for name in spec['reference_members']:
        path = folders['reference'] / name
        path.write_bytes(name.encode())
        paths[name] = path
    return paths


class FrozenSpecification(unittest.TestCase):
    def test_spec_is_accepted(self):
        runner.validate_spec(SPEC)

    def test_any_change_to_the_grid_or_tolerance_is_refused(self):
        for mutate in (lambda s: s['probe']['levels'].append(-20), lambda s: s['probe'].update(companion_cap=-5),
                       lambda s: s.update(identity_tolerance=1e-3), lambda s: s['models'].reverse(),
                       lambda s: s['probe'].update(pitches=[52, 64]), lambda s: s.update(onnxruntime_version='1.21.0')):
            spec = copy.deepcopy(SPEC)
            mutate(spec)
            with self.assertRaises(ValueError):
                runner.validate_spec(spec)

    def test_the_run_requires_github_actions(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(RuntimeError):
                runner.run(SPEC_PATH, Path(folder) / 'out')


class DryRun(unittest.TestCase):
    def test_orchestration_report_and_analysis_on_a_fake_session(self):
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
        environment = dict(SOURCE_SHA=head, GITHUB_REPOSITORY=SPEC['worker_repository'], GITHUB_SHA='f' * 40,
                           GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1')
        fake_onnx = types.SimpleNamespace(__version__='1.17.0', load=lambda path: 'MODEL',
                                          save_model=lambda model, path: Path(path).write_bytes(b'exposed'))
        fake_ort = types.SimpleNamespace(__version__='1.20.1')
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(os.environ, environment), \
                mock.patch.dict(sys.modules, {'onnx': fake_onnx, 'onnxruntime': fake_ort}), \
                mock.patch.object(runner, 'remote_only'), \
                mock.patch.object(runner, 'collect_reference', fake_collect), \
                mock.patch.object(runner, 'rewrite_normalization', lambda model, recent: model), \
                mock.patch.object(runner, 'session', lambda path: FakeSession(str(path).endswith('exposed.onnx'))):
            output = Path(folder) / 'result'
            report = runner.run(SPEC_PATH, output)
            saved = json.loads((output / 'report' / 'report.json').read_text())
            self.assertEqual(report['state'], 'complete')
            self.assertEqual(saved['state'], 'complete')
            self.assertTrue(saved['final'])
            self.assertFalse(saved['promotion_accepted'] or saved['installed_output_changed'])
            self.assertEqual(saved['window_count'], 474)
            self.assertEqual(len(saved['windows_digest']), 64)
            for arm in ('unmodified', 'adapted'):
                model = saved['models'][arm]
                self.assertEqual(len(model['windows']), 474)
                self.assertTrue(model['identity']['passed'])
                self.assertEqual(model['identity']['max_abs_difference'], 0.0)
                self.assertTrue((output / 'bulk' / (arm + '-normalization-exposed.onnx')).exists())
            result = analysis.analyse(saved, SPEC)
            self.assertEqual(result['verdicts']['F1_minimum_pinned_at_power_floor']['verdict'], 'pass')
            self.assertEqual(result['verdicts']['F0_frontend_same_across_models']['verdict'], 'pass')
            self.assertIn('D1_pure_gain_response', result['verdicts'])
            json.dumps(result, allow_nan=False)

    def test_a_mismatch_between_the_graphs_fails_the_identity_gate(self):
        class Drifting(FakeSession):
            def run(self, names, feed):
                out = super().run(names, feed)
                if self.exposed:
                    out[0] = out[0] + np.float32(1e-3)
                return out
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
        environment = dict(SOURCE_SHA=head, GITHUB_REPOSITORY=SPEC['worker_repository'], GITHUB_SHA='f' * 40,
                           GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1')
        fake_onnx = types.SimpleNamespace(__version__='1.17.0', load=lambda path: 'MODEL',
                                          save_model=lambda model, path: Path(path).write_bytes(b'exposed'))
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(os.environ, environment), \
                mock.patch.dict(sys.modules, {'onnx': fake_onnx, 'onnxruntime': types.SimpleNamespace(__version__='1.20.1')}), \
                mock.patch.object(runner, 'remote_only'), \
                mock.patch.object(runner, 'collect_reference', fake_collect), \
                mock.patch.object(runner, 'rewrite_normalization', lambda model, recent: model), \
                mock.patch.object(runner, 'session', lambda path: Drifting(str(path).endswith('exposed.onnx'))):
            report = runner.run(SPEC_PATH, Path(folder) / 'result')
            self.assertFalse(report['models']['adapted']['identity']['passed'])
            result = analysis.analyse(report, SPEC)
            self.assertEqual(result['verdicts']['decisions']['verdict'], 'not_evaluable')

    def test_an_interface_mismatch_is_refused(self):
        class Wrong(FakeSession):
            def get_inputs(self):
                return [types.SimpleNamespace(name='other', shape=[1, 43844, 1])]
        with self.assertRaises(ValueError):
            runner.check_interface(Wrong(False), [runner.NOTE, runner.ONSET])
        with self.assertRaises(ValueError):
            runner.check_interface(FakeSession(False), [runner.NOTE, runner.ONSET, runner.MINIMUM])


if __name__ == '__main__':
    unittest.main()
