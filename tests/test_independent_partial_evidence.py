import unittest

import numpy as np

from tools.independent_partial_evidence import (
    CONFIG, _local_reference, compare_local_reference, measure, summarize,
)


RATE = 12000
SETTINGS = {**CONFIG, 'window_samples': 2048, 'fft_samples': 8192, 'hop_samples': 512}


def signal(note=36, cents=-30, partials=(1, 2, 3, 4, 5, 6), count=6000):
    t = np.arange(count) / RATE
    frequency = 440 * 2 ** ((note - 69) / 12 + cents / 1200)
    return sum(np.cos(2 * np.pi * frequency * h * t + 0.31 * h) / h for h in partials)


def observe(wave, **kwargs):
    return list(measure(wave, RATE, config=SETTINGS, **kwargs))


class IndependentPartialTests(unittest.TestCase):
    def test_known_note_has_odd_support_but_octave_shadow_does_not(self):
        true = observe(signal())[-1]['notes']
        self.assertTrue(true['36']['odd_pair_cue'])
        self.assertFalse(true['37']['odd_pair_cue'])
        for h in (2, 4):
            self.assertAlmostEqual(true['36']['partials'][h]['cents'], -30, delta=1.5)
        other = observe(signal(49, cents=5))[-1]['notes']['37']
        self.assertIsNotNone(other['partials'][1])  # Its H2 is the real upper fundamental.
        self.assertFalse(other['odd_pair_cue'])

    def test_silence_missing_harmonics_and_history_abstain(self):
        rows = observe(np.zeros(6000))
        self.assertFalse(rows[0]['history_available'])
        self.assertFalse(rows[0]['notes'])
        self.assertTrue(rows[-1]['history_available'])
        self.assertEqual(rows[-1]['notes']['36']['partials'], [None] * 6)
        for partials in ((1, 2), (2, 4, 6), (3,)):
            self.assertFalse(observe(signal(partials=partials))[-1]['notes']['36']['odd_pair_cue'])

    def test_future_samples_cannot_change_earlier_observations(self):
        before = signal()
        after = before.copy()
        after[4096:] = signal(49, count=len(after) - 4096)
        a, b = observe(before), observe(after)
        self.assertEqual([r for r in a if r['sample'] < 4096],
                         [r for r in b if r['sample'] < 4096])

    def test_component_evaluation_does_not_change_signal_features(self):
        target, other = signal(), signal(49, cents=5)
        mixed = target + other
        plain = observe(mixed)[-1]
        oracle = observe(mixed, components={'target': target, 'interferer': other})[-1]
        for note in ('36', '37'):
            value = oracle['notes'][note]
            for peak in value['partials']:
                if peak:
                    shares = peak.pop('oracle_component_power_share')
                    self.assertAlmostEqual(sum(shares.values()), 1.0)
                    peak.pop('oracle_component_power')
            self.assertEqual(value, plain['notes'][note])
        self.assertTrue(plain['notes']['36']['odd_pair_cue'])
        self.assertFalse(plain['notes']['37']['odd_pair_cue'])

    def test_gain_changes_do_not_create_different_support(self):
        original = observe(signal())[-1]['notes']['36']
        for gain in (0.0001, 100):
            scaled = observe(signal() * gain)[-1]['notes']['36']
            self.assertEqual(original['odd_pair_cue'], scaled['odd_pair_cue'])
            for left, right in zip(original['partials'], scaled['partials']):
                self.assertEqual(left is None, right is None)
                if left:
                    self.assertAlmostEqual(left['cents'], right['cents'], places=7)
                    self.assertAlmostEqual(left['relative_power'], right['relative_power'], places=7)
                    self.assertAlmostEqual(left['local_prominence_db'], right['local_prominence_db'], places=7)

    def test_weak_fifth_is_measured_even_when_global_floor_rejects_it(self):
        wave = signal(partials=(1, 3)) + 0.03 * signal(partials=(5,))
        rows = observe(wave)
        value = rows[-1]['notes']['36']
        self.assertFalse(value['odd_pair_cue'])
        self.assertFalse(value['odd_support'][1])
        self.assertLess(value['odd_raw_agreement_cents'], 2)
        self.assertGreater(value['partials'][4]['local_prominence_db'], 6)
        summary = summarize(rows, start_sample=0, end_sample=len(wave), sample_rate=RATE)
        settled = summary['sustain_350ms_plus']['notes']['36']
        self.assertEqual(settled['fifth_supported_frames'], 0)
        self.assertEqual(settled['odd_both_peak_frames'], settled['observed_frames'])

    def test_fixed_sidebands_use_stronger_side_and_refuse_missing_reference(self):
        frequencies = np.arange(100, dtype=float)
        power = np.ones(100)
        power[45:47] = 4
        power[54:56] = 16
        self.assertEqual(_local_reference(power, frequencies, 50, 1, CONFIG), 16)
        self.assertIsNone(_local_reference(np.zeros(100), frequencies, 50, 1, CONFIG))
        self.assertIsNone(_local_reference(power, frequencies, 3, 1, CONFIG))

    def test_local_comparison_includes_source_only_and_absent_alternate_controls(self):
        def note(third, fifth, share=1):
            def peak(db):
                return dict(local_prominence_db=db, oracle_component_power_share={'target': share})
            return dict(partials=[None, None, peak(third), None, peak(fifth), None])

        def row(sample, target, alternate):
            return dict(sample=sample, history_available=True, notes={'36': target, '37': alternate})

        cases = {
            'mixture': dict(source_only=False, start_sample=0, end_sample=3, rows=[
                row(0, note(25, 30), note(1, 35, 0)),
                row(1, note(35, 40, 0.5), note(1, 22, 0)),
                row(3, note(99, 99), note(99, 99, 0))]),
            'source': dict(source_only=True, start_sample=0, end_sample=3, rows=[
                row(0, note(12, 15, 0), note(8, 18, 0))])}
        report = compare_local_reference(cases)
        result = report['target_present_cases']['mixture:note36']
        self.assertEqual(report['control_envelopes']['h5']['maximum'], 35)
        self.assertEqual(report['control_envelopes']['odd_pair']['maximum'], 12)
        self.assertEqual(result['observed_frames'], 2)
        self.assertEqual(result['h5_above_negative_max_frames'], 1)
        self.assertEqual(result['h5_above_negative_max_target_dominated_frames'], 0)
        self.assertEqual(result['odd_pair_above_negative_max_frames'], 2)
        self.assertEqual(result['odd_pair_above_negative_max_target_dominated_frames'], 1)
        with self.assertRaises(ValueError):
            compare_local_reference({'mixture': cases['mixture']})

    def test_local_comparison_does_not_turn_unmeasured_controls_into_zero(self):
        value = dict(partials=[None] * 6)
        case = dict(start_sample=0, end_sample=2, rows=[dict(sample=1,
            history_available=True, notes={'36': value, '37': value})])
        report = compare_local_reference({'mixture': dict(case, source_only=False),
                                          'source': dict(case, source_only=True)})
        self.assertIsNone(report['control_envelopes']['h5'])
        self.assertIsNone(report['target_present_cases']['mixture:note36']['h5_above_negative_max_frames'])

    def test_scoring_only_partitions_fixed_measurements(self):
        rows = observe(signal())
        summary = summarize(rows, start_sample=1000, end_sample=5000, sample_rate=RATE)
        self.assertEqual(sum(group['frames'] for group in summary.values()), len(rows))
        self.assertGreater(summary['before_note']['unavailable_history'], 0)
        with self.assertRaisesRegex(ValueError, 'clock'):
            summarize(rows + [rows[0]], start_sample=1000, end_sample=5000, sample_rate=RATE)

    def test_invalid_audio_and_component_alignment_fail(self):
        for wave in ([], [np.nan], [[0, 1]]):
            with self.assertRaises(ValueError):
                observe(wave)
        with self.assertRaises(ValueError):
            observe(signal(), components={'target': [1]})
        with self.assertRaises(ValueError):
            list(measure(signal(), RATE, config={**SETTINGS, 'fft_samples': 1000}))


if __name__ == '__main__':
    unittest.main()
