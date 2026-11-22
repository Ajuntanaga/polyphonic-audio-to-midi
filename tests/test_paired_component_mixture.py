"""Synthetic matched-crop attribution and frozen-output integrity checks."""
from contextlib import ExitStack
import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_direct_spectrum_learning import manifest
from tools.direct_spectrum_learning import SETTINGS, mixture_plan, validate_manifest
from tools.paired_component_mixture import (PairedCensus, paired_audio,
    probabilities, relative_level, require_reproduction)
from tools import portable_paired_component_mixture as runner


def predictions(*notes):
    value = np.zeros(53)
    value[np.asarray(notes, dtype=int) - 32] = .9
    return value


class PairedComponentTests(unittest.TestCase):
    def test_crops_component_and_global_gains_preserved(self):
        waves = dict(a=np.sin(np.arange(20000)*.13),
                     b=np.cos(np.arange(20000)*.23))
        components = [dict(stem=name, crop_begin=123, crop_end=16507,
                           gain_db=gain, note=note)
                      for name, gain, note in [('a', 0, 48), ('b', -18, 72)]]
        mixed, targets, solos, error = paired_audio(dict(components=components, gain_db=-6), waves)
        for audio, component in zip(solos, components):
            clip = waves[component['stem']][123:16507]
            expected = clip / np.sqrt(np.mean(clip**2)) * .05 * 10**((component['gain_db']-6)/20)
            np.testing.assert_allclose(audio, expected, rtol=1e-14, atol=1e-16)
        np.testing.assert_allclose(mixed, np.sum(solos, axis=0), rtol=0, atol=1e-14)
        self.assertLess(error, 1e-14)
        self.assertEqual(np.flatnonzero(targets).tolist(), [16, 40])

    def test_cancellation_and_silence_keep_intended_targets(self):
        tone = np.sin(np.arange(16384)*.13)
        row = dict(gain_db=6, components=[dict(stem=name, note=60, gain_db=0,
            crop_begin=0, crop_end=16384) for name in ('a', 'b')])
        mixed, targets, solos, _ = paired_audio(row, dict(a=tone, b=-tone))
        self.assertFalse(mixed.any())
        self.assertEqual(int(targets.sum()), 1)
        self.assertTrue(all(np.any(solo) for solo in solos))
        mixed, targets, solos, _ = paired_audio(dict(gain_db=0, components=[]), {})
        self.assertFalse(mixed.any())
        self.assertFalse(targets.any())
        self.assertEqual(solos, [])

    def test_all_four_states_extras_and_strata_reconcile(self):
        row = dict(components=[dict(note=n) for n in (40, 50, 60, 72)])
        solo = np.array([predictions(40, 80), predictions(), predictions(60), predictions()])
        census = PairedCensus(.5)
        census.add(row, predictions(40, 50, 80, 81), solo, [1, .5, .1, .01])
        result = census.finish()
        overall = result['overall']
        for key in ('retained', 'emerged_after_sum', 'lost_after_sum', 'already_missing_alone',
                    'extra_in_any_solo', 'extra_new_after_sum'):
            self.assertEqual(overall[key], 1)
        self.assertEqual(overall['mixture_missing'], 2)
        self.assertEqual(overall['mixture_extras'], 2)
        self.assertEqual(overall['complete_sets'], 0)
        for strata in ('by_pitch_band', 'by_relative_component_level'):
            self.assertEqual(sum(v.get('expected', 0) for v in result[strata].values()), 4)
        self.assertEqual(result['by_component_count']['4'], overall)

    def test_unison_counts_once_and_other_source_ghost_is_not_own_detection(self):
        census = PairedCensus(.5)
        row = dict(components=[dict(note=n) for n in (60, 60, 48)])
        solo = np.array([predictions(), predictions(), predictions(48, 60)])
        counts = census.add(row, predictions(48), solo, [1, .1, 1])
        self.assertEqual(counts['expected'], 2)
        self.assertEqual(counts['already_missing_alone'], 1)
        self.assertEqual(counts['lost_after_sum'], 0)
        solo[1] = predictions(60)
        counts = census.add(row, predictions(48, 60), solo, [1, .1, 1])
        self.assertEqual(counts['retained'], 2)
        self.assertEqual(counts['all_own_pitches_found_alone'], 1)
        counts = census.add(dict(components=[]), predictions(72), np.zeros((0, 53)), [])
        self.assertEqual(counts['all_own_pitches_found_alone'], 0)
        self.assertEqual(counts['extra_new_after_sum'], 1)
        self.assertEqual(census.finish()['overall']['examples'], 3)

    def test_reproduction_requires_probabilities_and_exact_decisions(self):
        value = np.full((2, 53), .2)
        self.assertEqual(require_reproduction(value+5e-7, value, .5)['changed_decisions'], 0)
        with self.assertRaisesRegex(ValueError, 'reproduction failed'):
            require_reproduction(value+2e-6, value, .5)
        with self.assertRaisesRegex(ValueError, 'changed='):
            require_reproduction(np.full((1, 53), .50000001), np.full((1, 53), .49999999), .5)
        for invalid in (np.zeros((1, 52)), np.full((1, 53), np.nan), np.full((1, 53), 1.01)):
            with self.assertRaises(ValueError):
                probabilities(invalid, 1)
        self.assertEqual(relative_level(10**(-6/20), 1), '0_to_-6dB')
        self.assertEqual(relative_level(10**(-12/20), 1), '-6_to_-12dB')
        self.assertEqual(relative_level(0, 1), 'silent_component')


class PairedRunnerTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'Model execution stays on GitHub')
    def test_synthetic_model_save_load_preserves_outputs_and_rejects_metadata_change(self):
        import torch
        from tools.portable_harmonic_context_learning import save_model
        torch.manual_seed(1729)
        extractor = runner.HarmonicFeatures()
        original = runner.HarmonicContextModel(np.zeros(62), np.ones(62),
                                              runner.make_network(), cutoff=.6)
        features = np.random.default_rng(42).normal(size=(3, 53*62))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'synthetic.pt'
            save_model(path, original, extractor, model_params=runner.SETWISE_PARAMS)
            loaded = runner.load_model(path, .6, extractor)
            require_reproduction(loaded.activity(features), original.activity(features), .6)
            with self.assertRaisesRegex(ValueError, 'metadata differs: cutoff'):
                runner.load_model(path, .5, extractor)

    def test_reference_plan_regeneration_and_cutoff_fail_closed(self):
        takes, _ = validate_manifest(manifest())
        plan = mixture_plan(takes, role='test', count=30, seed=SETTINGS['test_seed'])
        with tempfile.TemporaryDirectory() as directory, patch.dict(SETTINGS, test_examples=30):
            root = Path(directory)
            path = root/'test-mixture-plan.json.gz'
            path.write_bytes(gzip.compress(json.dumps(plan).encode()))
            np.savez(root/'test-predictions.npz', probability=np.zeros((30, 53)),
                     targets=np.zeros((30, 53), bool), cutoff=.6)
            result = runner.load_reference('test', root, takes, .6)
            self.assertEqual(result['plan'], plan)
            with self.assertRaisesRegex(ValueError, 'cutoff'):
                runner.load_reference('test', root, takes, .5)
            plan[1]['components'][0]['crop_begin'] += 1
            path.write_bytes(gzip.compress(json.dumps(plan).encode()))
            with self.assertRaisesRegex(ValueError, 'plan/source'):
                runner.load_reference('test', root, takes, .6)

    def test_remote_guard_precedes_input_model_and_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            output = Path(directory)/'absent'
            with self.assertRaisesRegex(RuntimeError, 'requires GitHub Actions'):
                runner.run(Path('absent-spec'), output)
            with self.assertRaisesRegex(RuntimeError, 'requires GitHub Actions'):
                runner.load_model(Path('absent-model'), .5, None)
            self.assertFalse(output.exists())

    def test_every_mixture_role_must_reproduce_before_any_component_measurement(self):
        for failure in (None, 'calibration'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                sources = root/'sources.json'; sources.write_text('{}')
                spec = root/'spec.json'
                spec.write_text(json.dumps(dict(worker_repository='example/worker',
                    probability_absolute_tolerance=1e-6, recomposition_absolute_tolerance=1e-14,
                    frozen_reference=dict(run_id='synthetic'),
                    sources=dict(path=str(sources), sha256=runner.digest(sources)),
                    artifact={}, cutoff=.5, input_releases=[], limits=['synthetic'])))
                events = []
                def reproduce(reference, *args):
                    role = reference['role']; events.append('reproduce:'+role)
                    if role == failure:
                        raise ValueError('synthetic identity failure')
                    return np.zeros((1, 53)), {}
                def measure(role, *args):
                    self.assertEqual(events[:3], ['reproduce:'+r for r in runner.ROLES])
                    events.append('measure:'+role)
                    return {}
                with ExitStack() as stack:
                    for name, value in [('remote_only', None), ('captured_text', 'a'*40),
                        ('dependency_versions', runner.DEPENDENCIES), ('validate_manifest', ([], {})),
                        ('fetch_artifact', {}), ('source_waves', {}), ('load_model', object())]:
                        stack.enter_context(patch.object(runner, name, return_value=value))
                    stack.enter_context(patch.dict(os.environ, SOURCE_SHA='a'*40,
                        GITHUB_REPOSITORY='example/worker', GITHUB_SHA='b'*40))
                    stack.enter_context(patch.object(runner, 'load_reference',
                        side_effect=lambda role, *args: dict(role=role)))
                    stack.enter_context(patch.object(runner, 'reproduce', side_effect=reproduce))
                    measured = stack.enter_context(patch.object(runner, 'measure_components', side_effect=measure))
                    if failure:
                        with self.assertRaisesRegex(ValueError, 'identity failure'):
                            runner.run(spec, root/'output')
                        self.assertEqual(measured.call_count, 0)
                        result = json.loads((root/'output/report/report.json').read_text())
                        self.assertEqual(result['state'], 'failed')
                    else:
                        result = runner.run(spec, root/'output')
                        self.assertEqual(measured.call_count, 3)
                        self.assertTrue(result['all_original_mixtures_reproduced'])
                        self.assertEqual(result['fits'], 0)


if __name__ == '__main__':
    unittest.main()
