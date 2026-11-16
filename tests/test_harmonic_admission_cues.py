import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_candidate_outcome_analysis import candidate
from tests.test_portable_ordinary_harmonic_prediction import state
from tools.candidate_outcome_analysis import HEADER
from tools.harmonic_admission_cues import (CONFIG, CUE_HEADER, causal_states,
    eligible_notes, evaluate_candidate, generate, independent_pairs,
    numerical_gain_guard, prediction_window)
from tools.portable_ordinary_harmonic_prediction import RATE, design
from tools.harmonic_parent_fit import refine_parents


MODULE = 'tools.harmonic_admission_cues.'


def outcome(samples=8192, annotations=''):
    texts = [candidate(48, selection=4), candidate(73, selection=1,
        fund_ratio=.9, band_score=1., band_fund=1., local=1)]
    return '# m3_candidate_outcome_v2\n' + HEADER + ''.join(
        f'{sample}\t{(sample + 1) // 64}\t0\t{sample + 1}\t{annotations}\t\t\t'
        + ','.join(texts) + '\n' for sample in range(63, samples, 64))


class HarmonicAdmissionCueTests(unittest.TestCase):
    def evaluate(self, signal, base_note=48, note=73, cents=0):
        window, prepared = prediction_window(signal, 4799,
            state(text=candidate(base_note, selection=4, phase_valid=1, phase_cents=cents)))
        return evaluate_candidate(window, prepared, note)

    def test_zero_one_two_independent_pair_geometry(self):
        frequencies = [440., 660., 880., 1100.]
        proposed = design(frequencies, 4800)[:, 1:]
        for count in (0, 1, 2):
            with self.subTest(count=count):
                base = design(frequencies[:4 - count], 4800)
                ratios, passing, selected = independent_pairs(base, proposed, 3840)
                self.assertEqual(len(passing), count)
                self.assertEqual(selected.shape, (4800, count * 2))
                self.assertTrue(all(r < 1e-12 for r in ratios[:4 - count]))

    def test_added_independent_note_predicts_future_and_pure_parent_fails(self):
        clock = np.arange(4800) / RATE
        parent, extra = [440 * 2 ** ((n - 69) / 12) for n in (48, 73)]
        baseline = np.cos(2 * np.pi * parent * clock) + .3 * np.sin(2 * np.pi * parent * 9 * clock)
        pure = self.evaluate(baseline)
        self.assertFalse(pure['admitted'])
        self.assertEqual(pure['status'], 'prediction_rejected')
        added = self.evaluate(baseline + .3 * np.sin(2 * np.pi * extra * clock)
                              + .2 * np.cos(2 * np.pi * 2 * extra * clock))
        self.assertTrue(added['admitted'])
        self.assertGreater(added['prediction_gain_fraction'], .01)
        self.assertGreaterEqual(len(added['independent_harmonics']), 2)
        self.assertEqual(added['supported_harmonics'], [1, 2])
        self.assertLess(added['added_prediction_error_fraction'], 1e-20)

    def test_one_actual_partial_cannot_borrow_support_from_silent_pairs(self):
        clock = np.arange(4800) / RATE
        parent, extra = [440 * 2 ** ((n - 69) / 12) for n in (48, 73)]
        baseline = np.cos(2 * np.pi * parent * clock) + .3 * np.sin(2 * np.pi * parent * 9 * clock)
        for harmonic in (1, 2, 3, 4):
            with self.subTest(harmonic=harmonic):
                row = self.evaluate(baseline + .3 * np.sin(2 * np.pi * extra * harmonic * clock + .4))
                self.assertEqual(row['independent_harmonics'], [1, 2, 3, 4])
                self.assertGreater(row['prediction_gain_fraction'], .01)
                self.assertEqual(row['supported_harmonics'], [harmonic])
                self.assertEqual(row['status'], 'insufficient_supported_pairs')
                self.assertFalse(row['admitted'])

    def test_two_nonadjacent_actual_partials_have_separate_support(self):
        clock = np.arange(4800) / RATE
        parent, extra = [440 * 2 ** ((n - 69) / 12) for n in (48, 73)]
        baseline = np.cos(2 * np.pi * parent * clock)
        row = self.evaluate(baseline + .3 * np.cos(2 * np.pi * extra * 2 * clock)
                            + .2 * np.sin(2 * np.pi * extra * 4 * clock))
        self.assertEqual(row['supported_harmonics'], [2, 4])
        self.assertTrue(row['admitted'])

    def test_exact_and_near_shared_parent_grid_cannot_admit_parent_only_signal(self):
        clock = np.arange(4800) / RATE
        for cents in (0, -1, 1, -5, 5, -10, 10, -25, 25):
            with self.subTest(cents=cents):
                parent = 440 * 2 ** ((58 - 69 + cents / 100) / 12)
                signal = np.cos(2 * np.pi * parent * clock) + .6 * np.sin(2 * np.pi * 2 * parent * clock)
                result = self.evaluate(signal, base_note=58, note=70, cents=cents)
                self.assertFalse(result['admitted'])
                if not cents:
                    self.assertEqual(result['status'], 'insufficient_independent_pairs')

    def test_gain_guard_is_numerical_and_scales_with_error(self):
        guard = numerical_gain_guard(0., 0.)
        self.assertAlmostEqual(guard, 64 * np.finfo(float).eps / 1e-8)
        self.assertEqual(numerical_gain_guard(5., 3.), 5 * guard)

    def detuned_parent(self):
        clock = np.arange(4800) / RATE
        # The sixth harmonic of this slightly flat G2 is exactly D5. Without
        # parent tuning, four D5 columns can absorb its model mismatch.
        frequency = 440 * 2 ** ((74 - 69) / 12) / 6
        signal = sum(np.sin(2 * np.pi * frequency * h * clock + .31 * h) / h
                     for h in range(1, int(3000 // frequency) + 1))
        frame = state(text=candidate(43, selection=4, phase_valid=0))
        return clock, frequency, signal, frame

    def test_missing_phase_detuned_parent_does_not_create_harmonic_note(self):
        _, _, signal, frame = self.detuned_parent()
        result = evaluate_candidate(*prediction_window(signal, 4799, frame), 74)
        self.assertFalse(result['admitted'])
        self.assertEqual(result['status'], 'unavailable_parent_tuning')
        self.assertEqual(result['parent_tuning']['status'], 'unidentifiable_parent_fit')

    def test_missing_phase_fit_retains_a_real_independent_note(self):
        clock, frequency, signal, frame = self.detuned_parent()
        extra = 440 * 2 ** ((75 - 69) / 12)
        signal += .3 * np.sin(2 * np.pi * extra * clock) + .2 * np.cos(2 * np.pi * extra * 3 * clock)
        result = evaluate_candidate(*prediction_window(signal, 4799, frame), 75)
        self.assertTrue(result['admitted'])
        self.assertEqual(result['supported_harmonics'], [1, 3])
        self.assertAlmostEqual(result['base_pitches'][0]['frequency_hz'], frequency, places=6)

    def test_proposed_partial_does_not_pull_unknown_parent_into_false_support(self):
        clock, frequency, signal, frame = self.detuned_parent()
        extra = 440 * 2 ** ((75 - 69) / 12)
        for harmonic in (1, 2, 3, 4):
            with self.subTest(harmonic=harmonic):
                audio = signal + .3 * np.sin(2 * np.pi * extra * harmonic * clock + .4)
                result = evaluate_candidate(*prediction_window(audio, 4799, frame), 75)
                self.assertFalse(result['admitted'])
                self.assertEqual(result['status'], 'insufficient_supported_pairs')
                self.assertEqual(result['supported_harmonics'], [harmonic])
                self.assertAlmostEqual(result['base_pitches'][0]['frequency_hz'], frequency, places=6)

    def test_parent_fit_uses_training_only_and_preserves_valid_phase(self):
        clock, frequency, signal, frame = self.detuned_parent()
        valid = 440 * 2 ** ((40 - 69 - .17) / 12)
        signal += .4 * np.cos(2 * np.pi * valid * clock)
        frame = state(text=','.join((candidate(43, selection=4, phase_valid=0),
            candidate(40, selection=4, phase_valid=1, phase_cents=-17))))
        window, _ = prediction_window(signal, 4799, frame)
        extra = 440 * 2 ** ((75 - 69) / 12)
        proposed = [extra * h for h in range(1, 5)]
        fitted, evidence = refine_parents(signal[:3840], window['base_pitches'], CONFIG, proposed)
        self.assertEqual(evidence['status'], 'fitted')
        self.assertEqual(evidence['notes'], [43])
        by_note = {row['note']: row for row in fitted}
        self.assertEqual(by_note[40]['frequency_hz'], valid)
        self.assertAlmostEqual(by_note[43]['frequency_hz'], frequency, places=6)
        before = evaluate_candidate(*prediction_window(signal, 4799, frame), 75)['parent_tuning']
        signal[3840:] = np.cos(np.arange(960) * .73) * 7
        after = evaluate_candidate(*prediction_window(signal, 4799, frame), 75)['parent_tuning']
        self.assertEqual(before, after)
        with self.assertRaisesRegex(ValueError, 'training prefix'):
            refine_parents(signal, window['base_pitches'], CONFIG, proposed)

    def test_future_samples_annotations_and_unavailable_states(self):
        signal = np.sin(2 * np.pi * 130.8128 * np.arange(4900) / RATE)
        frame = state(text=candidate(48, selection=4))
        result = evaluate_candidate(*prediction_window(signal, 4799, frame), 73)
        signal[4800:] = np.nan
        frame['labels'] = [(123, 73, 128)]
        self.assertEqual(evaluate_candidate(*prediction_window(signal, 4799, frame), 73), result)
        with self.assertRaisesRegex(ValueError, 'prediction-period'):
            prediction_window(signal, 4799, dict(frame, sample=3840))
        for audio, sample, old, status in (
                (np.zeros(4800), 4799, frame, 'zero_energy'),
                (signal, 1023, None, 'insufficient_history'),
                (signal, 4799, state(text=''), 'unavailable_base')):
            row = evaluate_candidate(*prediction_window(audio, sample, old), 73)
            self.assertEqual(row['status'], status)
            self.assertFalse(row['admitted'])
        row = evaluate_candidate(*prediction_window(signal, 4799, frame), 48)
        self.assertEqual(row['status'], 'already_owned')

    def test_candidates_are_all_eligible_pitches_without_label_selection(self):
        good = dict(selection=1, fund_ratio=.9, band_score=1., band_fund=1., local=1)
        frame = state(text=','.join(candidate(note, **good) for note in (32, 73, 84)))
        self.assertEqual(eligible_notes(frame), [32, 73, 84])
        for changes in ({'selection': 4}, {'active': 1}, {'score_ratio': .19},
                        {'fund_ratio': .79}, {'band_score': .89}, {'direct': 0},
                        {'local': 0}, {'note': 85}):
            row = dict(good, note=73)
            row.update(changes)
            self.assertEqual(eligible_notes(state(text=candidate(**row))), [])
        self.assertEqual(eligible_notes(dict(frame, quiet=1)), [])

    def test_shadow_is_complete_causal_and_annotation_blind(self):
        expected = list(causal_states(io.StringIO(outcome()), 8192))
        self.assertEqual(expected, list(causal_states(io.StringIO(outcome(annotations='invalid label text')), 8192)))
        self.assertEqual([row[0] for row in expected], list(range(1023, 8191, 1024)))
        self.assertTrue(all(old['sample'] == sample - 960 for sample, old, _ in expected))
        self.assertTrue(all(not current['labels'] for _, _, current in expected))
        for bad in (outcome()[:-1].rsplit('\n', 1)[0] + '\n',
                    outcome().replace('127\t2\t', '128\t2\t', 1)):
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                list(causal_states(io.StringIO(bad), 8192))

    def test_generated_cues_start_after_evidence_and_have_fixed_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, cues, evidence = [root / name for name in ('shadow.tsv', 'cues.tsv', 'rows.gz')]
            source.write_text(outcome())
            def decision(window, prepared, note):
                return dict(window, candidate_note=note, admitted=prepared is not None)
            with patch(MODULE + 'evaluate_candidate', side_effect=decision):
                result = generate(np.sin(np.arange(8192) * .01), source, cues, evidence, time.monotonic() + 60)
            self.assertEqual(result['cue_spans'], 3)
            self.assertEqual(cues.read_text(), CUE_HEADER + '5120\t6144\t73\n6144\t7168\t73\n7168\t8192\t73\n')
            with self.assertRaises(TimeoutError):
                generate(np.zeros(8192), source, cues, evidence, time.monotonic() - 1)


if __name__ == '__main__':
    unittest.main()
