"""Synthetic fail-closed orchestration; no recorded files, audio or model fit."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import portable_shared_harmonic_learning as runner


class PortableSharedTests(unittest.TestCase):
    def test_remote_guard_precedes_dependencies_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_shared_harmonic_learning',
                '--spec', 'absent', '--output', str(output)], capture_output=True, text=True,
                env={k: v for k, v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())

    def test_training_and_both_held_out_roles_control_continuous(self):
        class Model:
            cutoff = None
            def activity(self, features):
                return np.zeros((len(features), 53))
        for sequence in ([False], [True,False,True], [True,True,False], [True,True,True]):
            with self.subTest(gates=sequence), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                refs = {}
                for name in ('sources', 'baseline', 'source_consistency'):
                    path = root/(name+'.json')
                    path.write_text(json.dumps(dict(datasets=dict(ordinary={}, middle={}))))
                    refs[name] = dict(path=str(path), sha256=runner.digest(path))
                spec = root/'spec.json'
                spec.write_text(json.dumps(dict(worker_repository='example/worker',
                    mixture_and_clock_settings=runner.SETTINGS, harmonic_parameters=runner.PARAMETERS,
                    model_parameters=runner.MODEL_PARAMS, references=refs, input_releases=[],
                    datasets=dict(ordinary={}, middle={}))))
                def persist(path, model, extractor):
                    path.write_text(str(model.cutoff))
                def replay_result(*args):
                    return dict(timing={}, arms=dict(primary_fifo=dict(comparison=dict(
                        no_pitch_safety_regression=True, pitch_coverage_gain_pp=5.1))))
                with ExitStack() as stack:
                    stack.enter_context(patch.object(runner, 'remote_only'))
                    stack.enter_context(patch.object(runner, 'captured_text', return_value='a'*40))
                    stack.enter_context(patch.dict(runner.os.environ, dict(SOURCE_SHA='a'*40,
                        GITHUB_REPOSITORY='example/worker', GITHUB_SHA='b'*40,
                        GITHUB_RUN_ID='synthetic', GITHUB_RUN_ATTEMPT='1')))
                    stack.enter_context(patch.object(runner, 'dependency_versions', return_value=runner.DEPENDENCIES))
                    stack.enter_context(patch.object(runner, 'validate_manifest', return_value=([], dict(train=200, calibration=200, test=155))))
                    stack.enter_context(patch.object(runner, 'source_waves', return_value={}))
                    examples = stack.enter_context(patch.object(runner, 'role_examples', return_value=(
                        np.zeros((3, runner.NOTE_COUNT*runner.FEATURE_COUNT)), np.zeros((3,53), bool), {})))
                    fit = stack.enter_context(patch.object(runner, 'fit_model', return_value=(Model(), {})))
                    stack.enter_context(patch.object(runner, 'save_model', side_effect=persist))
                    stack.enter_context(patch.object(runner, 'fit_training_cutoff', return_value=dict(cutoff=.5, feasible=True)))
                    stack.enter_context(patch.object(runner, 'acceptance_gate', side_effect=sequence))
                    replay = stack.enter_context(patch.object(runner, 'continuous_dataset', side_effect=replay_result))
                    result = runner.run(spec, root/'output')
                self.assertEqual(fit.call_count, 1)
                self.assertEqual(examples.call_count, len(sequence))
                self.assertEqual(replay.call_count, 2 if all(sequence) else 0)
                self.assertEqual(result['state'], 'completed')
                self.assertTrue(result['final'])
                self.assertEqual(result['research_screen_passed'], all(sequence))
                self.assertEqual(result['held_out_scoring']['executed'], len(sequence) == 3)
                self.assertTrue(result['frozen_model']['persisted_before_held_out_scoring'])


if __name__ == '__main__':
    unittest.main()
