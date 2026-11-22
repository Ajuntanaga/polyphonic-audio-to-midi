import copy
import json
from pathlib import Path
import unittest

import numpy as np

from tools import mixed_level_analysis as analysis
from tools import mixed_level_probe as probe
from tools.audio_release_levels import window_levels

SPEC = json.loads((Path(__file__).resolve().parents[1] / 'docs/recovery/mixed-level-probe-20261122.json').read_text())
WINDOWS = probe.build_windows(SPEC)
BY_ID = {w['id']: w for w in WINDOWS}


class WindowConstruction(unittest.TestCase):
    def test_grid_counts_and_cap(self):
        self.assertEqual(len(WINDOWS), SPEC['probe']['expected_windows'])
        self.assertEqual(len({w['id'] for w in WINDOWS}), len(WINDOWS))
        for w in WINDOWS:
            self.assertEqual(w['samples'].dtype, np.float32)
            self.assertEqual(len(w['samples']), probe.SAMPLES)
            self.assertTrue(np.isfinite(w['samples']).all())
            self.assertLess(float(np.abs(w['samples']).max()), 0.9)
            if w['kind'] == 'probe' and w['companion'] is not None:
                self.assertLessEqual(w['companion']['level'], SPEC['probe']['companion_cap'])
                self.assertEqual(w['companion']['level'], w['level'] + w['companion']['delta'])
        excluded = [(-30, 35), (-40, 35)]
        for level, delta in excluded:
            self.assertNotIn(probe.window_id('zero', 'sustained', 52, level, ('ended', delta)), BY_ID)
        self.assertIn(probe.window_id('zero', 'sustained', 52, -50, ('ended', 35)), BY_ID)
        self.assertIn(probe.window_id('zero', 'cut', 76, -30, ('through', 20)), BY_ID)

    def test_deterministic_digest(self):
        self.assertEqual(probe.windows_digest(WINDOWS), probe.windows_digest(probe.build_windows(SPEC)))
        self.assertNotEqual(probe.windows_digest(WINDOWS), probe.windows_digest(WINDOWS[:-1]))

    def test_level_matches_the_registered_audio_level_measure(self):
        # The same sinusoids at the 96 kHz corpus rate, measured by the very function the audio-level read used.
        for midi in (43, 52, 64, 76):
            for level in (-80.0, -50.0, -10.0):
                x = probe.tone(midi, level, 0, n=96000, rate=96000)
                measured = window_levels(x, midi, 9600, 1, 1)[0]
                self.assertAlmostEqual(measured, level, delta=0.2, msg=(midi, level))

    def test_silence_cut_and_ended_are_exact_zeros(self):
        self.assertFalse(BY_ID['zero|ref|silence']['samples'].any())
        cut = BY_ID[probe.window_id('zero', 'cut', 52, -30)]['samples']
        self.assertFalse(cut[probe.CUT:].any())
        self.assertTrue(cut[probe.CUT - 2000:probe.CUT].any())
        sustained = BY_ID[probe.window_id('zero', 'sustained', 52, -30)]['samples']
        self.assertTrue(sustained[-2000:].any())
        ended = BY_ID['zero|ref|ended|C-20']['samples']
        self.assertFalse(ended[probe.ENDED:].any())
        self.assertTrue(ended[probe.ENDED - 2000:probe.ENDED - probe.FADE].any())
        through = BY_ID['zero|ref|through|C-20']['samples']
        self.assertTrue(through[-2000:].any())

    def test_tones_start_with_a_ramp_and_the_companion_fade_is_smooth(self):
        window = BY_ID[probe.window_id('zero', 'sustained', 52, -30)]['samples']
        self.assertEqual(float(window[0]), 0.0)
        ended = BY_ID['zero|ref|ended|C-20']['samples']
        fade = np.abs(ended[probe.ENDED - probe.FADE:probe.ENDED])
        self.assertLess(float(fade[-5:].max()), 0.01 * float(np.abs(ended).max()))

    def test_dither_is_one_shared_white_floor(self):
        noise = probe.noise_floor()
        self.assertAlmostEqual(float(np.sqrt(np.mean(noise ** 2))), 10 ** (probe.DITHER_DB / 20.0), delta=0.03 * 10 ** (probe.DITHER_DB / 20.0))
        silent = BY_ID['dither|ref|silence']['samples']
        self.assertTrue(np.allclose(silent, noise.astype(np.float32), atol=1e-12))
        for key in ('sustained', 'cut'):
            a = BY_ID[probe.window_id('zero', key, 64, -50, ('ended', 20))]['samples']
            b = BY_ID[probe.window_id('dither', key, 64, -50, ('ended', 20))]['samples']
            self.assertTrue(np.allclose(b - a, noise, atol=1e-7))

    def test_unknown_options_are_refused(self):
        with self.assertRaises(ValueError):
            probe.make_window('quiet')
        with self.assertRaises(ValueError):
            probe.make_window('zero', probe=(52, -50, 'ramped'))
        with self.assertRaises(ValueError):
            probe.make_window('zero', companion=(-50, 'late'))


def fake_record(meta, note_value, minimum, range_db):
    note = np.zeros((probe.FRAMES, probe.BINS), dtype=np.float32)
    onset = np.zeros_like(note)
    if meta['kind'] == 'probe':
        p = meta['midi'] - probe.FIRST_MIDI
        note[164:166, p] = note_value
    return probe.extract(meta, note, onset, minimum, range_db)


class Extraction(unittest.TestCase):
    def test_indices_profile_and_exclusions(self):
        meta = next(w for w in WINDOWS if w['id'] == probe.window_id('zero', 'cut', 64, -50, ('through', 20)))
        note = np.zeros((probe.FRAMES, probe.BINS), dtype=np.float32)
        onset = np.zeros_like(note)
        p, q = 64 - 21, 43 - 21
        note[164, p], note[165, p] = 0.2, 0.7
        onset[165, p] = 0.4
        note[165, q] = 0.9                       # the companion's own bin: reported separately, excluded from other_max
        note[164, p + 2] = 0.8                   # within two semitones of the probe: excluded from other_max
        note[164, p + 3] = 0.35                  # the largest stray activation
        note[155, p] = 0.55
        record = probe.extract(meta, note, onset, -100.0, 70.0)
        self.assertEqual(record['note_probe'], [float(np.float32(0.2)), float(np.float32(0.7))])
        self.assertAlmostEqual(record['response'], 0.7, places=6)
        self.assertEqual(record['onset_probe'][0], 0.0)
        self.assertAlmostEqual(record['onset_probe'][1], 0.4, places=6)
        self.assertEqual(len(record['profile']), probe.PROFILE[1] - probe.PROFILE[0])
        self.assertAlmostEqual(record['profile'][155 - probe.PROFILE[0]], 0.55, places=6)
        self.assertAlmostEqual(record['note_companion'][1], 0.9, places=6)
        self.assertAlmostEqual(record['other_max'], 0.35, places=6)
        self.assertEqual(record['active_bins'], 4)       # p, p+2, p+3, companion at >= 0.3
        self.assertEqual((record['min_db'], record['range_db']), (-100.0, 70.0))

    def test_reference_windows_have_no_probe_fields(self):
        record = fake_record(BY_ID['zero|ref|silence'], 0.0, -100.0, 0.0)
        self.assertNotIn('response', record)
        self.assertNotIn('note_companion', record)
        record = fake_record(BY_ID['zero|ref|through|C-20'], 0.0, -100.0, 80.0)
        self.assertIn('note_companion', record)

    def test_wrong_shapes_are_refused(self):
        with self.assertRaises(ValueError):
            probe.extract(WINDOWS[0], np.zeros((172, 87)), np.zeros((172, 88)), -100.0, 1.0)

    def test_run_windows_records_the_difference_to_the_plain_graph(self):
        meta = WINDOWS[:3]

        def stats(samples):
            return np.zeros((172, 88)), np.zeros((172, 88)), -100.0, 5.0

        def plain(samples):
            note = np.zeros((172, 88))
            note[3, 3] = 2e-7
            return note, np.zeros((172, 88))
        records = probe.run_windows(meta, stats, plain)
        self.assertEqual(len(records), 3)
        self.assertAlmostEqual(records[0]['plain_max_abs_note'], 2e-7, places=12)
        self.assertEqual(records[0]['plain_max_abs_onset'], 0.0)
        self.assertTrue(probe.identity(records, 1e-6)['passed'])
        self.assertFalse(probe.identity(records, 1e-8)['passed'])


def fake_report(frontend=lambda meta: (-100.0, None), mask=1.0, unmodified_scale=0.5, adapted_gate=True):
    """A model whose answers are known: response rises with level, a sounding companion masks more than an ended one."""
    def response(meta, scale):
        if meta['kind'] != 'probe':
            return 0.0
        base = float(np.clip((meta['level'] + 90.0) / 60.0, 0.0, 1.0))
        if meta['form'] == 'cut':
            base *= 0.6
        if meta['companion'] is not None:
            weight = 0.5 if meta['companion']['timing'] == 'through' else 0.3
            base = max(0.0, base - mask * weight * meta['companion']['delta'] / 35.0)
        return base * scale

    def records(scale):
        out = []
        for meta in WINDOWS:
            top = meta['level'] if meta['kind'] == 'probe' else -60
            if meta.get('companion') is not None and meta['kind'] == 'probe':
                top = meta['companion']['level']
            minimum, range_db = frontend(meta)
            out.append(fake_record(meta, response(meta, scale), minimum, top + 100.0 + 5.0 if range_db is None else range_db))
        return out
    identity = dict(max_abs_difference=0.0, tolerance=1e-6, passed=True, windows=len(WINDOWS))
    return dict(state='complete', models=dict(
        adapted=dict(windows=records(1.0), identity=dict(identity, passed=adapted_gate)),
        unmodified=dict(windows=records(unmodified_scale), identity=identity)))


class Analysis(unittest.TestCase):
    def test_a_model_with_the_predicted_behaviour_passes_everything(self):
        result = analysis.analyse(fake_report(), SPEC)
        verdicts = {k: v['verdict'] for k, v in result['verdicts'].items()}
        self.assertEqual(set(verdicts.values()), {'pass'}, verdicts)
        self.assertEqual(len(verdicts), 10)
        f3 = result['verdicts']['F3_ended_companion_raises_range']
        self.assertEqual(f3['median_range_raise_db_by_delta']['35'], 35.0)

    def test_ended_pair_count_is_the_registered_grid(self):
        # 2 floors x 2 forms x 3 pitches x 16 (level, delta) pairs of the grid, for the ended timing
        result = analysis.analyse(fake_report(), SPEC)
        self.assertEqual(result['verdicts']['F3_ended_companion_raises_range']['pairs'], 2 * 2 * 3 * 16)

    def test_unpinned_minimum_is_a_miss_for_the_frontend_claims_only(self):
        report = fake_report(frontend=lambda meta: (-100.0 + 0.1 * (meta.get('level') or 0) + 8.0, None))
        result = analysis.analyse(report, SPEC)
        self.assertEqual(result['verdicts']['F1_minimum_pinned_at_power_floor']['verdict'], 'miss')
        self.assertEqual(result['verdicts']['D1_pure_gain_response']['verdict'], 'pass')

    def test_flat_range_is_a_miss_for_the_slope_claim(self):
        report = fake_report(frontend=lambda meta: (-100.0, 60.0))
        result = analysis.analyse(report, SPEC)
        self.assertEqual(result['verdicts']['F2_range_slope_one_in_level']['verdict'], 'miss')
        self.assertEqual(result['verdicts']['F3_ended_companion_raises_range']['verdict'], 'miss')

    def test_no_masking_gives_not_evaluable_not_a_pass(self):
        result = analysis.analyse(fake_report(mask=0.0), SPEC)
        self.assertEqual(result['verdicts']['D2_ended_companion_masks']['verdict'], 'miss')
        self.assertEqual(result['verdicts']['D3_normalization_share_of_masking']['verdict'], 'not_evaluable')

    def test_a_silent_model_has_no_eligible_cells(self):
        report = fake_report()
        for arm in report['models'].values():
            for record in arm['windows']:
                if 'response' in record:
                    record['response'] = 0.0
        result = analysis.analyse(report, SPEC)
        self.assertEqual(result['verdicts']['D2_ended_companion_masks']['verdict'], 'not_evaluable')
        self.assertEqual(result['verdicts']['D1_pure_gain_response']['verdict'], 'miss')

    def test_a_failed_identity_gate_withholds_the_decision_verdicts(self):
        result = analysis.analyse(fake_report(adapted_gate=False), SPEC)
        self.assertEqual(result['verdicts']['decisions']['verdict'], 'not_evaluable')
        self.assertNotIn('D1_pure_gain_response', result['verdicts'])
        self.assertIn('F1_minimum_pinned_at_power_floor', result['verdicts'])

    def test_incomplete_or_short_reports_are_refused(self):
        report = fake_report()
        report['state'] = 'failed'
        with self.assertRaises(ValueError):
            analysis.analyse(report, SPEC)
        report = fake_report()
        report['models']['adapted']['windows'].pop()
        with self.assertRaises(ValueError):
            analysis.analyse(report, SPEC)

    def test_dither_difference_is_detected(self):
        report = fake_report()
        for record in report['models']['adapted']['windows']:
            if record['id'].startswith('dither|') and 'response' in record:
                record['response'] = min(1.0, record['response'] + 0.3)
        result = analysis.analyse(report, SPEC)
        self.assertEqual(result['verdicts']['D5_dither_irrelevant']['verdict'], 'miss')

    def test_models_with_a_different_frontend_fail_f0(self):
        report = fake_report()
        report['models']['unmodified']['windows'][5]['range_db'] += 0.5
        result = analysis.analyse(report, SPEC)
        self.assertEqual(result['verdicts']['F0_frontend_same_across_models']['verdict'], 'miss')

    def test_spec_is_frozen_by_these_checks(self):
        p = SPEC['probe']
        self.assertEqual((p['levels'], p['deltas'], p['pitches'], p['companion_cap'], p['readout_frames']),
                         ([-80, -70, -60, -50, -40, -30], [10, 20, 35], [52, 64, 76], -10, [164, 165]))
        self.assertEqual((p['cut_sample'], p['ended_sample'], p['window_samples'], p['sample_rate']),
                         (probe.CUT, probe.ENDED, probe.SAMPLES, probe.RATE))
        self.assertEqual((p['dither_db'], p['noise_seed'], p['companion_midi']), (probe.DITHER_DB, probe.NOISE_SEED, probe.COMPANION_MIDI))


if __name__ == '__main__':
    unittest.main()
