"""Synthetic fail-closed orchestration; no recorded files, audio or model fit."""
from contextlib import ExitStack
import gzip
import hashlib
import json
from itertools import product
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import portable_harmonic_context_learning as runner


class PortableContextTests(unittest.TestCase):
    def test_remote_guard_precedes_dependencies_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_harmonic_context_learning',
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
        configs = [(p, 'none') for p in (runner.MODEL_PARAMS, runner.COMPLETE_SET_PARAMS, runner.SETWISE_PARAMS)]
        configs.extend((runner.SETWISE_PARAMS, mode) for mode in ('shelf', 'partial', 'transpose', 'contrast', 'level'))
        for (params, mode), sequence in product(configs,
                ([False], [True,False,True], [True,True,False], [True,True,True])):
            with self.subTest(gates=sequence, loss=params['loss'], mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                refs = {}
                for name in ('sources', 'baseline', 'source_consistency'):
                    path = root/(name+'.json')
                    path.write_text(json.dumps(dict(datasets=dict(ordinary={}, middle={}))))
                    refs[name] = dict(path=str(path), sha256=runner.digest(path))
                spec = root/'spec.json'
                spec_data = dict(worker_repository='example/worker',
                    mixture_and_clock_settings=runner.SETTINGS, harmonic_parameters=runner.PARAMETERS,
                    model_parameters=params, references=refs, input_releases=[],
                    datasets=dict(ordinary={}, middle={}))
                if params != runner.MODEL_PARAMS:
                    spec_data['training_plan_identity'] = dict(
                        decoded_sha256=hashlib.sha256(b'[]').hexdigest())
                if mode == 'shelf':
                    spec_data['training_source_variation'] = runner.VARIATION
                    spec_data['varied_plan_identity'] = dict(decoded_sha256='synthetic-varied-plan')
                if mode == 'partial':
                    spec_data['training_partial_variation'] = runner.PARTIAL_VARIATION
                    spec_data['partial_plan_identity'] = dict(decoded_sha256='synthetic-partial-plan')
                if mode == 'transpose':
                    spec_data['training_pitch_transposition'] = runner.TRANSPOSITION
                    spec_data['transposed_plan_identity'] = dict(decoded_sha256='synthetic-transposed-plan')
                if mode == 'contrast':
                    spec_data['harmonic_peak_contrast'] = runner.CONTRAST
                if mode == 'level':
                    spec_data['harmonic_level_suppression'] = runner.SUPPRESSION
                spec.write_text(json.dumps(spec_data))
                def synthetic_examples(role, takes, waves, extractor, output):
                    (output/(role+'-mixture-plan.json.gz')).write_bytes(gzip.compress(b'[]'))
                    return (np.zeros((3, runner.NOTE_COUNT*len(extractor.coordinate_names))),
                            np.zeros((3, 53), bool), {})
                def persist(path, model, extractor, model_params=None):
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
                    examples = stack.enter_context(patch.object(runner, 'role_examples', side_effect=synthetic_examples))
                    fit = stack.enter_context(patch.object(runner, 'fit_model', return_value=(Model(), {})))
                    augmentation = stack.enter_context(patch.object(runner, 'variation_examples', return_value=(
                        np.ones((3, runner.NOTE_COUNT*runner.FEATURE_COUNT)), np.zeros((3, 53), bool),
                        dict(decoded_sha256='synthetic-varied-plan'))))
                    partial = stack.enter_context(patch.object(runner, 'partial_examples', return_value=(
                        np.ones((3, runner.NOTE_COUNT*runner.FEATURE_COUNT)), np.zeros((3, 53), bool),
                        dict(decoded_sha256='synthetic-partial-plan'))))
                    transposition = stack.enter_context(patch.object(runner, 'transposition_examples', return_value=(
                        np.ones((3, runner.NOTE_COUNT*runner.FEATURE_COUNT)), np.zeros((3, 53), bool),
                        dict(decoded_sha256='synthetic-transposed-plan'))))
                    activity = stack.enter_context(patch.object(Model, 'activity', autospec=True,
                        side_effect=lambda self, x: np.zeros((len(x), 53))))
                    stack.enter_context(patch.object(runner, 'save_model', side_effect=persist))
                    stack.enter_context(patch.object(runner, 'fit_training_cutoff', return_value=dict(cutoff=.5, feasible=True)))
                    stack.enter_context(patch.object(runner, 'acceptance_gate', side_effect=sequence))
                    replay = stack.enter_context(patch.object(runner, 'continuous_dataset', side_effect=replay_result))
                    result = runner.run(spec, root/'output')
                self.assertEqual(fit.call_count, 1)
                fit_features = fit.call_args.args[0]
                self.assertTrue(np.all(fit_features[:3] == (1 if mode in ('shelf', 'partial') else 0)))
                self.assertEqual(len(fit_features), 6 if mode == 'transpose' else 3)
                if mode == 'transpose':
                    self.assertTrue(np.all(fit_features[3:] == 1))
                self.assertEqual(augmentation.call_count, int(mode == 'shelf'))
                self.assertEqual(partial.call_count, int(mode == 'partial'))
                self.assertEqual(transposition.call_count, int(mode == 'transpose'))
                self.assertTrue(all(np.all(c.args[1] == 0) for c in activity.call_args_list))
                self.assertEqual(fit.call_args.kwargs['model_params'], params)
                self.assertEqual(result['training_objective'], params['loss'])
                if mode == 'partial':
                    self.assertEqual(result['schema'], 'm3_harmonic_partial_variation_v1')
                    self.assertEqual(result['features']['per_candidate'], 62)
                if mode == 'contrast':
                    self.assertEqual(result['features']['per_candidate'], 106)
                    self.assertEqual(set(result['contrast_diagnostics']),
                                     {'train', 'calibration', 'test'} if len(sequence) == 3 else {'train'})
                if mode == 'level':
                    self.assertEqual(result['schema'], 'm3_harmonic_level_suppression_v1')
                    self.assertEqual(result['features']['per_candidate'], 62)
                    self.assertTrue(all(isinstance(c.args[3], runner.HarmonicLevelBlindFeatures)
                                        for c in examples.call_args_list))
                    self.assertTrue(all(isinstance(c.args[4], runner.HarmonicLevelBlindFeatures)
                                        for c in replay.call_args_list))
                if params != runner.MODEL_PARAMS:
                    self.assertTrue(result['training_plan_identity']['verified'])
                self.assertEqual(examples.call_count, len(sequence))
                self.assertEqual(replay.call_count, 2 if all(sequence) else 0)
                self.assertEqual(result['state'], 'completed')
                self.assertTrue(result['final'])
                self.assertEqual(result['research_screen_passed'], all(sequence))
                self.assertEqual(result['held_out_scoring']['executed'], len(sequence) == 3)
                self.assertTrue(result['frozen_model']['persisted_before_held_out_scoring'])


if __name__ == '__main__':
    unittest.main()
