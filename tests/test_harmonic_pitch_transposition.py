"""Synthetic-only checks of pitch, chord identity, boundaries and role isolation."""
from copy import deepcopy
import importlib.util
import unittest

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, render_mixture
from tools.harmonic_pitch_transposition import (TRANSPOSITION, transpose_training_plan,
    resampling_ratio, transposed_component, render_transposed_mixture)
from tools.harmonic_source_variation import encoded_plan


def fixture(notes=(52, 59, 64), count=100):
    takes = [dict(key=str(i), stem=str(i), role='train', start_sample=100,
                  end_sample=52000, midi_note=note, string_mask=1 << i)
             for i, note in enumerate(notes)]
    rows = [dict(example=j, role='train', gain_db=-6, components=[dict(
        source_key=t['key'], stem=t['stem'], string_mask=t['string_mask'],
        note=t['midi_note'], crop_begin=100 if j % 2 else 52000-16384,
        crop_end=100+16384 if j % 2 else 52000, gain_db=-12) for t in takes])
        for j in range(count)]
    return rows, takes


class PitchTranspositionTests(unittest.TestCase):
    def test_plan_repeatable_preserves_intervals_sources_and_original(self):
        rows, takes = fixture()
        original = deepcopy(rows)
        plan = transpose_training_plan(rows, takes)
        self.assertEqual(rows, original)
        self.assertEqual(encoded_plan(plan), encoded_plan(transpose_training_plan(rows, takes)))
        self.assertEqual({r['transpose_semitones'] for r in plan}, set(range(-6, 7))-{0})
        for base, row in zip(rows, plan):
            k = row['transpose_semitones']
            self.assertEqual(np.diff([c['note'] for c in row['components']]).tolist(), [7, 5])
            for before, after in zip(base['components'], row['components']):
                self.assertEqual(after['note'], before['note']+k)
                self.assertEqual(after['source_note'], before['note'])
                self.assertEqual({key: after[key] for key in before if key != 'note'},
                                 {key: before[key] for key in before if key != 'note'})
                self.assertGreaterEqual(after['support_begin'], 100)
                self.assertLessEqual(after['support_end'], 52000)

    def test_held_out_cross_role_wrong_provenance_and_repeated_use_fail(self):
        rows, takes = fixture(count=1)
        for role in ('calibration', 'test'):
            bad_rows = deepcopy(rows)
            bad_rows[0]['role'] = role
            with self.assertRaises(ValueError):
                transpose_training_plan(bad_rows, takes)
            bad_takes = deepcopy(takes)
            bad_takes[0]['role'] = role
            with self.assertRaises(ValueError):
                transpose_training_plan(rows, bad_takes)
        bad = deepcopy(rows)
        bad[0]['components'][0]['note'] += 1
        with self.assertRaises(ValueError):
            transpose_training_plan(bad, takes)
        with self.assertRaisesRegex(ValueError, 'already transposed'):
            transpose_training_plan(transpose_training_plan(rows, takes), takes)
        bad = deepcopy(takes)
        bad[0]['end_sample'] = 12000
        with self.assertRaises(ValueError):
            transpose_training_plan(rows, bad)

    def test_boundary_chord_and_silence_are_exact_identity(self):
        rows, takes = fixture(notes=(32, 84), count=1)
        rows.append(dict(example=1, role='train', gain_db=0, components=[]))
        waves = {str(i): np.random.default_rng(i).normal(size=53000) for i in range(2)}
        for base, shifted in zip(rows, transpose_training_plan(rows, takes)):
            self.assertEqual(shifted['transpose_semitones'], 0)
            expected, truth = render_mixture(base, waves)
            actual, target = render_transposed_mixture(shifted, waves)
            np.testing.assert_array_equal(actual, expected)
            np.testing.assert_array_equal(target, truth)

    def test_rational_pitch_tolerance_and_bounds(self):
        for shift in range(-6, 7):
            up, down = resampling_ratio(shift)
            self.assertLessEqual(abs(1200*np.log2(down/up)-100*shift), 0.01)
        for shift in (-7, 7, 0.5):
            with self.assertRaises(ValueError):
                resampling_ratio(shift)

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy pinned on GitHub')
    def test_tone_frequency_rms_target_and_boundary_independence(self):
        rows, takes = fixture(notes=(60,), count=100)
        plans = {r['transpose_semitones']: r for r in transpose_training_plan(rows, takes)}
        t = np.arange(53000)/SETTINGS['sample_rate']
        wave = np.sin(2*np.pi*500*t)
        for shift, row in plans.items():
            audio, target = render_transposed_mixture(row, {'0': wave})
            spectrum = abs(np.fft.rfft(audio*np.hanning(len(audio))))
            peak = np.argmax(spectrum)*SETTINGS['sample_rate']/len(audio)
            up, down = resampling_ratio(shift)
            self.assertLess(abs(peak-500*down/up), SETTINGS['sample_rate']/len(audio))
            self.assertEqual(np.flatnonzero(target).tolist(), [60+shift-SETTINGS['note_low']])
            self.assertAlmostEqual(float(np.sqrt(np.mean(audio**2))),
                SETTINGS['component_rms']*10**((-12-6)/20), places=13)
            c = row['components'][0]
            altered = wave.copy()
            altered[:c['support_begin']+16] = 10000
            altered[c['support_end']-16:] = -10000
            np.testing.assert_array_equal(transposed_component(wave, c, shift),
                                          transposed_component(altered, c, shift))
            bad = dict(c, output_begin=0)
            with self.assertRaisesRegex(ValueError, 'boundary'):
                transposed_component(wave, bad, shift)

    @unittest.skipUnless(importlib.util.find_spec('scipy'), 'SciPy pinned on GitHub')
    def test_antialias_and_unison_cardinality(self):
        rows, takes = fixture(notes=(60, 60), count=100)
        plan = transpose_training_plan(rows, takes)
        row = next(r for r in plan if r['transpose_semitones'] == 6)
        t = np.arange(53000)/SETTINGS['sample_rate']
        low = np.sin(2*np.pi*500*t)
        high = np.sin(2*np.pi*45000*t)
        c = row['components'][0]
        low_out = transposed_component(low, c, 6)
        high_out = transposed_component(high, c, 6)
        self.assertLess(np.mean(high_out**2)/np.mean(low_out**2), 1e-5)
        _, target = render_transposed_mixture(row, {'0': low, '1': low})
        self.assertEqual(int(target.sum()), 1)
        silent, _ = render_transposed_mixture(row, {'0': low*0, '1': low*0})
        np.testing.assert_array_equal(silent, 0)


if __name__ == '__main__':
    unittest.main()
