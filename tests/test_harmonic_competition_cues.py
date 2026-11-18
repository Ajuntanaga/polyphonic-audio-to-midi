import copy
import gzip
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_candidate_outcome_analysis import candidate
from tests.test_harmonic_admission_cues import outcome
from tests.test_portable_ordinary_harmonic_prediction import state
from tools import harmonic_admission_cues as admission
from tools import harmonic_competition_cues as competition
from tools.portable_ordinary_harmonic_prediction import RATE


def lower(note=62, **changes):
    features = dict(selection=1, score_ratio=.4, fund_ratio=.38,
                    band_score=1., band_fund=1., local=1, phase_valid=0)
    features.update(changes)
    return candidate(note, **features)


class HarmonicCompetitionTests(unittest.TestCase):
    def setUp(self):
        self.clock = np.arange(4800) / RATE
        self.base = np.cos(2 * np.pi * self.hz(40) * self.clock)
        self.frame = state(text=','.join((candidate(40, selection=4, phase_valid=1), lower())))

    @staticmethod
    def hz(note, cents=0.):
        return 440 * 2 ** ((note - 69 + cents / 100) / 12)

    def signal(self, note, harmonics, cents=0.):
        return sum(amplitude * np.sin(2 * np.pi * self.hz(note, cents) * h * self.clock + .31 * h)
                   for h, amplitude in harmonics)

    def evaluate(self, signal, note=74, frame=None):
        frame = self.frame if frame is None else frame
        return competition.evaluate_candidate(*admission.prediction_window(signal, 4799, frame), note, frame)

    def test_fundamental_veto_check_requires_independent_predictive_energy(self):
        from tools.portable_ordinary_harmonic_prediction import design
        # A real upper fundamental can survive a lower non-octave background.
        background = design([self.hz(63), 2*self.hz(63)], 4800)
        for present in (True, False):
            signal = background[:, 1] + (self.signal(65, [(1, .8)]) if present else 0)
            prepared = dict(signal=signal, energy=float(signal[3840:] @ signal[3840:]))
            prepared = competition.prepared_with_base(prepared, background)
            result = competition.fundamental_comparison(prepared, self.hz(65))
            self.assertEqual(result['admitted'], present)
        # An octave is already represented by the lower second harmonic.
        result = competition.fundamental_comparison(prepared, 2*self.hz(63))
        self.assertFalse(result['admitted'])
        self.assertEqual(result['status'], 'shared_or_unidentifiable_fundamental')

    def test_observed_omitted_parent_removes_false_octave(self):
        signal = self.base + self.signal(62, [(h, .6 / h) for h in range(1, int(3000 // self.hz(62)) + 1)])
        original = admission.evaluate_candidate(*admission.prediction_window(signal, 4799, self.frame), 74)
        self.assertTrue(original['admitted'])
        result = self.evaluate(signal)
        self.assertFalse(result['admitted'])
        self.assertEqual(result['status'], 'lower_competition_withheld')
        self.assertEqual(result['withholding_lower_note'], 62)
        check = result['lower_comparisons'][0]
        self.assertEqual(check['independent_lower_support']['supported_harmonics'], [1, 3])
        # Shared partials make this model unable to distinguish the octave.
        # Withholding is not a declaration that the upper note cannot be real.
        self.assertFalse(check['upper_comparison']['admitted'])
        self.assertEqual(check['upper_comparison']['status'], 'insufficient_independent_pairs')

    def test_real_65_survives_lower_63_with_unresolved_owned_51(self):
        frame = state(text=','.join((candidate(51, selection=4, phase_valid=0), lower(63))))
        signal = self.signal(51, [(h, 1. / h) for h in range(1, int(3000 // self.hz(51, -25)) + 1)], -25)
        signal += self.signal(63, [(h, .4 / h) for h in range(1, 5)])
        signal += self.signal(65, [(1, .6), (2, .3)])
        result = self.evaluate(signal, note=65, frame=frame)
        self.assertEqual(result['parent_tuning']['status'], 'fitted')
        self.assertTrue(result['admitted'])
        check = result['lower_comparisons'][0]
        self.assertTrue(check['independent_lower_support']['admitted'])
        self.assertTrue(check['upper_comparison']['admitted'])

    def test_unavailable_comparison_retains_original_admission(self):
        signal = self.base + self.signal(62, [(h, .6 / h) for h in range(1, int(3000 // self.hz(62)) + 1)])
        signal += self.signal(75, [(1, .6), (3, .4)])
        evaluate_support = admission.evaluate_partial_support
        calls = []
        def unavailable_comparison(prepared, frequencies):
            calls.append(frequencies)
            if len(calls) == 3:  # Original upper and lower support were measured normally.
                return dict(admitted=False, status='ill_conditioned_augmented_design')
            return evaluate_support(prepared, frequencies)
        with patch.object(admission, 'evaluate_partial_support', side_effect=unavailable_comparison):
            result = self.evaluate(signal, note=75)
        self.assertTrue(result['admitted'])
        self.assertEqual(result['status'], 'competition_incomplete')
        self.assertEqual(result['unavailable_comparisons'], 1)
        self.assertEqual(result['lower_comparisons'][0]['comparison_outcome'], 'unavailable')

    def test_real_independent_upper_survives_supported_lower(self):
        signal = self.base + self.signal(62, [(h, .6 / h) for h in range(1, int(3000 // self.hz(62)) + 1)])
        signal += self.signal(75, [(1, .6), (3, .4)])
        original = admission.evaluate_candidate(*admission.prediction_window(signal, 4799, self.frame), 75)
        self.assertTrue(original['admitted'])
        result = self.evaluate(signal, note=75)
        self.assertTrue(result['admitted'])
        check = result['lower_comparisons'][0]
        self.assertTrue(check['independent_lower_support']['admitted'])
        self.assertTrue(check['upper_comparison']['admitted'])

    def test_lower_presence_cannot_veto_true_upper_without_own_support(self):
        signal = self.base + self.signal(74, [(1, .3), (2, .2)])
        result = self.evaluate(signal)
        self.assertTrue(result['admitted'])
        check = result['lower_comparisons'][0]
        self.assertFalse(check['independent_lower_support']['admitted'])
        self.assertNotIn('upper_comparison', check)

    def test_spurious_parent_harmonic_has_no_independent_support(self):
        signal = self.base + self.signal(74, [(1, .3), (2, .2)])
        frame = state(text=','.join((candidate(40, selection=4, phase_valid=1), lower(52, selection=2))))
        result = self.evaluate(signal, frame=frame)
        self.assertTrue(result['admitted'])
        self.assertFalse(result['lower_comparisons'][0]['independent_lower_support']['admitted'])

    def test_candidates_use_native_lower_floor_and_frozen_state_not_annotations(self):
        candidates = competition.lower_candidates(self.frame, 74, {40})
        self.assertEqual([row['note'] for row in candidates], [62])
        self.assertNotIn(62, admission.eligible_notes(self.frame))
        for changes in ({'fund_ratio': .19}, {'score_ratio': .19}, {'band_score': .89},
                        {'band_fund': .79}, {'direct': 0}, {'local': 0},
                        {'selection': 4}, {'active': 1}):
            with self.subTest(changes=changes):
                self.assertEqual(competition.lower_candidates(state(text=lower(**changes)), 74, {40}), [])
        signal = self.base + self.signal(74, [(1, .3), (2, .2)])
        before = self.evaluate(signal)
        annotated = copy.deepcopy(self.frame)
        annotated['labels'] = [(123, 62, 64), (124, 74, 128)]
        self.assertEqual(self.evaluate(np.concatenate((signal, [np.nan])), frame=annotated), before)
        window, prepared = admission.prediction_window(signal, 4799, self.frame)
        with self.assertRaisesRegex(ValueError, 'causal baseline'):
            competition.evaluate_candidate(window, prepared, 74, dict(self.frame, sample=3840))
        self.assertFalse(self.evaluate(signal, frame=state(text=''))['admitted'])

    def test_overflow_withholds_without_arbitrary_competitor_truncation(self):
        frame = state(text=','.join([candidate(40, selection=4, phase_valid=1)]
                                    + [lower(n) for n in range(50, 59)]))
        signal = self.base + self.signal(74, [(1, .3), (2, .2)])
        result = self.evaluate(signal, frame=frame)
        self.assertFalse(result['admitted'])
        self.assertEqual(result['status'], 'too_many_lower_candidates')
        self.assertEqual(len(result['lower_candidates']), 9)

    def test_generation_experiment_is_explicit_and_default_is_preserved(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                with patch.object(admission, 'generate') as generate, patch.object(
                        competition, 'evaluate_candidate', return_value={'admitted': True}) as evaluate:
                    competition.generate(None, None, None, None, 100,
                                         fundamental_veto_check=enabled)
                    decision = generate.call_args.kwargs['decision']
                    decision('window', 'prepared', 65, 'state')
                    expected = {'fundamental_veto_check': True} if enabled else {}
                    evaluate.assert_called_once_with('window', 'prepared', 65, 'state', **expected)

    def test_generation_passes_old_state_and_fixed_cue_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, cues, evidence = [root / name for name in ('shadow.tsv', 'cues.tsv', 'rows.gz')]
            source.write_text(outcome())
            seen = []
            def decision(window, prepared, note, old):
                if prepared is not None:
                    seen.append(old['sample'])
                    self.assertEqual(old['sample'], window['available_sample'] - 960)
                return dict(window, candidate_note=note, admitted=prepared is not None)
            with patch.object(competition, 'evaluate_candidate', side_effect=decision):
                result = competition.generate(np.sin(np.arange(8192) * .01), source, cues, evidence,
                                               time.monotonic() + 60)
            self.assertEqual(seen, [4159, 5183, 6207])
            self.assertEqual(result['cue_spans'], 3)
            self.assertEqual(cues.read_text(), admission.CUE_HEADER +
                             '5120\t6144\t73\n6144\t7168\t73\n7168\t8192\t73\n')
            with gzip.open(evidence, 'rt') as stream:
                self.assertTrue(all(json.loads(line)['candidate_note'] == 73 for line in stream))


if __name__ == '__main__':
    unittest.main()
