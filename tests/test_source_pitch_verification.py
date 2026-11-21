import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.source_pitch_verification import (PARAMETERS, context_bounds, harmonic_evidence,
    measure_take, select_sources, spectrum, window_starts)


def tone(note, length, harmonics=(1,)):
    time = np.arange(length)/96000.
    frequency = 440*2**((note-69)/12)
    return sum(.05*np.sin(2*np.pi*frequency*h*time) for h in harmonics)


def take(length, note=60):
    return dict(key='synthetic:0', role='test', start_sample=0, end_sample=length,
                midi_note=note, string_mask=1, expected_cents=0.)


CONTEXT = dict(previous_note=72, next_note=64, open_note=48)


class SourceVerificationTests(unittest.TestCase):
    def test_grid_covers_endpoints_and_contexts_stay_inside_take(self):
        for length in (16384, 27600, 65536, 220800):
            starts = window_starts(length)
            self.assertEqual(starts[0], 0)
            self.assertEqual(starts[-1]+16384, length)
            self.assertTrue(all(0 < b-a <= 8192 for a,b in zip(starts, starts[1:])))
            for start in starts:
                left, right = context_bounds(start, length)
                self.assertTrue(0 <= left <= start < start+16384 <= right <= length)
                self.assertEqual(right-left, min(65536, length))

    def test_sustained_wrong_non_octave_and_control(self):
        for actual in (60, 64):
            summary, rows = measure_take(tone(actual, 100000), take(100000), CONTEXT)
            self.assertEqual(summary['periodic_nearest_midi_histogram'], {actual: len(rows)})
            self.assertEqual(summary['dominant_spectral_peak_midi_histogram'], {actual: len(rows)})
            self.assertEqual(sum(summary['classifications'].values()), len(rows))
            if actual == 64:
                self.assertLess(summary['hypothesis_medians']['label']['union_fraction'], .001)
                self.assertGreater(summary['hypothesis_medians']['next_note']['union_fraction'], .99)

    def test_even_only_octave_is_not_independent_fundamental_evidence(self):
        spec = spectrum(tone(48, 65536, (2,4,6)))
        lower = harmonic_evidence(spec, 48)
        upper = harmonic_evidence(spec, 60)
        self.assertGreater(lower['union_fraction'], .99)
        self.assertGreater(upper['union_fraction'], .99)
        self.assertLess(lower['odd_union_fraction'], .001)
        self.assertGreater(lower['even_union_fraction'], .99)

    def test_missing_fundamental_keeps_odd_harmonic_evidence(self):
        spec = spectrum(tone(48, 65536, (2,3,4)))
        result = harmonic_evidence(spec, 48)
        self.assertGreater(result['odd_union_fraction'], .30)
        self.assertLess(result['harmonic_fractions'][0], .001)

    def test_short_control_and_silence_are_retained(self):
        summary, rows = measure_take(np.zeros(27600), take(27600), CONTEXT)
        self.assertEqual(summary['classifications'], {'silent':len(rows)})
        self.assertEqual(summary['unique_spectral_windows'], 1)
        self.assertFalse(summary['dominant_spectral_peak_midi_histogram'])
        self.assertTrue(all(r['spectral_native_bin_hz'] == 96000/27600 for r in rows))

    def test_selection_preserves_missing_control_and_deduplicates(self):
        def row(key, role, category, note=60):
            return dict(source_key=key, role=role, note=note, string_mask=1,
                unique_crops=dict(count=3, classes={k:3 if k==category else 0 for k in
                    ('periodic_target','periodic_other','unresolved_periodicity','silent')}))
        rows = [row('s:51','test','periodic_other'),row('s:54','test','periodic_other'),
            row('s:12','train','periodic_target'),row('s:2','train','periodic_target'),
            row('s:50','calibration','periodic_other')]
        result = select_sources(rows)
        self.assertEqual(result['flagged_count'], 2)
        self.assertEqual(result['unique_control_count'], 1)
        self.assertEqual(result['pairs'][0]['controls'], dict(train='s:2', calibration=None))
        with self.assertRaises(ValueError):
            select_sources(rows+rows[:1])

    def test_remote_guard_precedes_output_and_file_access(self):
        from tools.portable_source_pitch_verification import run
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'GITHUB_ACTIONS':'false'}):
            output = Path(folder)/'output'
            with self.assertRaises(RuntimeError):
                run(Path(folder)/'nonexistent.json', output)
            self.assertFalse(output.exists())

    def test_invalid_waveforms_fail(self):
        with self.assertRaises(ValueError):
            measure_take(np.zeros(17000), take(16384), CONTEXT)
        with self.assertRaises(ValueError):
            spectrum(np.full(16384, np.nan))


if __name__ == '__main__':
    unittest.main()
