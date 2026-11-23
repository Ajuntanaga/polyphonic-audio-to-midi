"""Pure synthetic contracts; no recorded audio, model or native execution."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import period_cancellation as p
from tools import portable_period_cancellation as runner


def tone(note, amplitude=1., phase=0.):
    t = np.arange(p.SETTINGS['context_samples'])/p.SETTINGS['sample_rate']
    return amplitude*np.sin(2*np.pi*440*2**((note-69)/12)*t+phase)


class CancellationTests(unittest.TestCase):
    def test_spec_is_the_frozen_implementation(self):
        spec = json.loads(Path('docs/recovery/period-cancellation-20261123.json').read_text())
        self.assertEqual(spec['settings'], p.SETTINGS)
        self.assertEqual(spec['arms'], list(p.ARMS))

    def test_fft_difference_matches_fixed_past_direct_sum(self):
        past = np.random.default_rng(1).normal(size=16384)
        actual = p.difference_curve(past, 1200)
        for lag in (0, 1, 10, 99, 582, 1200):
            start = len(past)-4096-lag
            expected = np.mean((past[-4096:]-past[start:start+4096])**2)
            self.assertAlmostEqual(actual[lag], expected, places=12)

    def test_period_and_cancellation_on_known_fractional_tone(self):
        for note in (32, 52, 65, 83):
            wave = tone(note)
            true_period = 96000/(440*2**((note-69)/12))
            period = p.estimate_period(wave)['delay_samples']
            self.assertLess(abs(period-true_period), .1)
            self.assertLess(p.power(p.filtered(wave, period))/p.power(wave[-8192:]), 1e-5)

    def test_linear_filter_exact_component_accounting_and_weak_target(self):
        strong, weak = tone(43), tone(64, .1, .4)
        result, error = p.evaluate_wave(strong+weak, [strong, weak], p.PartialReadout())
        self.assertLess(error, 1e-12)
        col = result['component_period_oracle']['components']
        strong_gain = p.gain_db(p.power(col[0]), p.power(strong[-8192:]))
        weak_gain = p.gain_db(p.power(col[1]), p.power(weak[-8192:]))
        self.assertGreater(weak_gain-strong_gain, 30)
        self.assertGreater(weak_gain, -6)

    def test_cancellation_also_removes_shared_harmonics(self):
        strong, octave = tone(48), tone(60, .1)
        delay = 96000/(440*2**((48-69)/12))
        self.assertLess(p.power(p.filtered(strong, delay)), 1e-7)
        self.assertLess(p.power(p.filtered(octave, delay)), 1e-7)

    def test_unison_negative_removes_all_same_pitch_components(self):
        components = [tone(48), tone(64, .1), tone(64, .05, .3)]
        row = dict(example=0, role='test', components=[dict(note=n) for n in (48, 64, 64)])
        queries, checks = p.mixture_queries(row, sum(components), components, p.PartialReadout())
        self.assertEqual([q['note'] for q in queries], [48, 64])
        self.assertEqual(queries[1]['own_components'], 2)
        self.assertTrue(queries[1]['primary'])
        absent = p.PartialReadout()(components[0][-8192:])[64-32]
        self.assertEqual(queries[1]['arms']['raw']['absent_score'], absent)
        self.assertLess(checks['linearity_error'], 1e-12)

    def test_primary_arm_period_does_not_use_oracle_component_choice(self):
        wave = tone(43)+tone(65, .1)
        one, _ = p.evaluate_wave(wave, [wave], p.PartialReadout())
        two, _ = p.evaluate_wave(wave, [tone(43), tone(65, .1)], p.PartialReadout())
        self.assertEqual(one['mixture_period']['metadata'], two['mixture_period']['metadata'])
        np.testing.assert_array_equal(one['mixture_period']['scores'], two['mixture_period']['scores'])

    def test_silence_kept_and_never_detected_with_calibrated_cut(self):
        silence = np.zeros(16384)
        queries, checks = p.mixture_queries(dict(example=0, role='test', components=[]),
                                           silence, [], p.PartialReadout())
        self.assertEqual(queries, [])
        self.assertEqual(checks['silence_maximum_score'], {a: 0. for a in p.ARMS})
        self.assertIsNone(p.estimate_period(silence)['delay_samples'])
        self.assertGreater(p.calibrate_cutoff(np.zeros(100))['cutoff'], 0)

    def test_cutoff_is_calibration_negative_only_and_conservative_on_ties(self):
        scores = [0.]*97+[1., 1., 2.]
        cutoff = p.calibrate_cutoff(scores)
        self.assertEqual(cutoff['allowed_false'], 1)
        self.assertEqual(cutoff['observed_false'], 1)
        self.assertGreater(cutoff['cutoff'], 1.)
        self.assertLess(cutoff['cutoff'], 2.)
        self.assertEqual(cutoff, p.calibrate_cutoff(list(reversed(scores))))

    def test_summary_and_decision_require_every_safety_gate(self):
        rows = []
        for i in range(100):
            row = dict(primary=True, band='60-71', distinct_pitches=2,
                       harmonic_to_strongest=False, arms={})
            for arm in p.ARMS:
                row['arms'][arm] = dict(present_score=1. if i < (10 if arm == 'raw' else 30) else 0.,
                    absent_score=0., target_power_gain_db=0., sir_gain_db=0. if arm == 'raw' else 10.)
            rows.append(row)
        cutoffs = {arm: dict(cutoff=.5) for arm in p.ARMS}
        summary = p.summarize_queries(rows, cutoffs)
        self.assertEqual(summary['primary']['arms']['raw']['found'], 10)
        silence = {arm: 0. for arm in p.ARMS}
        self.assertTrue(p.decision(summary, True, silence, cutoffs)['pass_all'])
        changed = copy.deepcopy(summary)
        changed['all']['arms']['mixture_period']['false_responses'] = 1
        self.assertFalse(p.decision(changed, True, silence, cutoffs)['pass_all'])
        self.assertFalse(p.decision(summary, False, silence, cutoffs)['pass_all'])
        silence['mixture_period'] = .5
        self.assertFalse(p.decision(summary, True, silence, cutoffs)['pass_all'])

    def test_invalid_shapes_nonfinite_and_out_of_past_delays_fail(self):
        for wave in (np.zeros(16385), np.full(16384, np.nan)):
            with self.assertRaises(ValueError):
                p.estimate_period(wave)
        for delay in (0, 8192, np.inf, np.nan):
            with self.assertRaises(ValueError):
                p.filtered(np.zeros(16384), delay)
        for scores in ([], [np.nan], [-1]):
            with self.assertRaises(ValueError):
                p.calibrate_cutoff(scores)

    def test_role_source_coverage_and_query_accounting(self):
        wave = tone(60)
        plan = [dict(example=0, role='train', components=[]),
                dict(example=1, role='train', components=[dict(note=60, source_key='a')])]
        truth = np.zeros(53, bool)
        truth[60-32] = True
        pairs = [(np.zeros(16384), np.zeros(53, bool), [], 0.), (wave, truth, [wave], 0.)]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner, 'remote_only'), patch.object(runner, 'mixture_plan', return_value=plan), \
                 patch.object(runner, 'paired_audio', side_effect=pairs):
                queries, info = runner.measure_role('train', [dict(key='a', role='train')], {},
                                                    p.PartialReadout(), Path(directory))
            self.assertEqual(len(queries), 1)
            self.assertEqual(info['silence_rows'], 1)
            self.assertTrue(all(info['integrity'].values()))
            with patch.object(runner, 'remote_only'), patch.object(runner, 'mixture_plan', return_value=plan):
                with self.assertRaisesRegex(ValueError, 'Source role omitted'):
                    runner.measure_role('train', [dict(key='b', role='train')], {}, p.PartialReadout(), Path(directory))

    def test_remote_guard_precedes_recorded_data_and_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_period_cancellation',
                '--spec', 'absent', '--output', str(output)], capture_output=True, text=True,
                env={k: v for k, v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
