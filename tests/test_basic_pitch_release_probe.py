import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from tools import basic_pitch_release_probe as probe
from tools import portable_basic_pitch_release_probe as runner
from tools.basic_pitch_streaming import SETTINGS

ROOT = Path(__file__).resolve().parents[1]


def note_with(midi, release, active=True, dip=None):
    """A (frames, 88) matrix: the played column is high from frame 75 until `release` (None = never released)."""
    note = np.zeros((probe.FRAMES, 88))
    if active:
        column = note[:, midi - probe.FIRST_MIDI]
        column[75:] = 0.9 if release is None else 0.0
        if release is not None:
            column[75:release] = 0.9
        if dip is not None:
            column[dip] = 0.0
    return note


def results(rule):
    """rule(model, case, midi) -> release frame, None (censored) or 'inactive'."""
    out = {model: {} for model in runner.MODELS}
    for model in runner.MODELS:
        for key, kind, tau in probe.all_cases():
            if kind in ('sustained', 'silence'):
                continue
            for midi in probe.PITCHES:
                release = rule(model, key, midi)
                out[model].setdefault(key, {})[midi] = probe.measure(
                    note_with(midi, None if release == 'inactive' else release, active=release != 'inactive'), midi, tau)
    return out


def same(model, case, midi):
    return 90


class Constants(unittest.TestCase):
    def test_settings_and_frame_convention(self):
        self.assertEqual((probe.SAMPLES, probe.FRAMES, probe.HOP, probe.RATE), (43844, 172, 256, 22050))
        self.assertEqual(probe.THRESHOLD, 0.3)
        self.assertEqual(probe.LAST_STEADY_FRAME, 78)
        self.assertEqual(probe.ACTIVE_FRAMES, (75, 78))
        self.assertEqual(probe.HOP * probe.LAST_STEADY_FRAME, 19968)
        self.assertLess(probe.HOP * probe.LAST_STEADY_FRAME, probe.END)
        self.assertGreaterEqual(probe.HOP * (probe.LAST_STEADY_FRAME + 1), probe.END)

    def test_delay_and_level(self):
        self.assertAlmostEqual(probe.delay_ms(79), 224 / 22050 * 1000, places=6)
        self.assertAlmostEqual(probe.delay_ms(171), 1078.3, places=1)
        self.assertAlmostEqual(probe.level_db(0.2, 79), -20 * math.log10(math.exp(224 / (0.2 * 22050))), places=9)
        self.assertLess(probe.level_db(0.2, 90), probe.level_db(0.2, 80))
        self.assertAlmostEqual(probe.level_db(0.1, 100), 2 * probe.level_db(0.2, 100), places=9)


class Rendering(unittest.TestCase):
    def test_shape_dtype_and_silence(self):
        for midi in probe.PITCHES:
            for key, kind, tau in probe.all_cases():
                signal = probe.render(midi, kind, tau)
                self.assertEqual(signal.shape, (probe.SAMPLES,))
                self.assertEqual(signal.dtype, np.float32)
                self.assertTrue(np.all(np.isfinite(signal)))
        self.assertFalse(np.any(probe.render(52, 'silence')))

    def test_before_onset_is_zero_and_onset_is_the_training_taper(self):
        signal = probe.render(52, 'sustained')
        self.assertFalse(np.any(signal[:probe.ONSET]))
        envelope = probe.envelope('sustained')
        self.assertEqual(envelope[probe.ONSET], 0.0)
        self.assertEqual(envelope[probe.ONSET + probe.TAPER - 1], 1.0)
        np.testing.assert_array_equal(envelope[probe.ONSET:probe.ONSET + probe.TAPER], np.linspace(0, 1, probe.TAPER))
        self.assertTrue(np.all(envelope[probe.ONSET + probe.TAPER:] == 1.0))

    def test_steady_level(self):
        for midi in probe.PITCHES:
            steady = probe.render(midi, 'sustained')[probe.ONSET + probe.TAPER:probe.END].astype(np.float64)
            self.assertAlmostEqual(math.sqrt(float(np.mean(steady ** 2))), probe.STEADY_RMS, delta=0.003)

    def test_abrupt_end_is_a_taper_then_exact_zero(self):
        envelope = probe.envelope('abrupt')
        np.testing.assert_allclose(envelope[probe.END - probe.TAPER:probe.END], np.linspace(1, 0, probe.TAPER), rtol=0, atol=1e-12)
        self.assertEqual(envelope[probe.END - probe.TAPER], 1.0)
        self.assertEqual(envelope[probe.END - 1], 0.0)
        self.assertEqual(envelope[probe.END - probe.TAPER - 1], 1.0)
        self.assertFalse(np.any(envelope[probe.END:]))
        self.assertFalse(np.any(probe.render(45, 'abrupt')[probe.END:]))

    def test_decay_has_no_end_taper_and_the_stated_time_constant(self):
        for tau in probe.TAUS:
            envelope = probe.envelope('decay', tau)
            self.assertTrue(np.all(envelope[probe.ONSET + probe.TAPER:probe.END] == 1.0))
            self.assertEqual(envelope[probe.END], 1.0)
            at_tau = probe.END + int(round(tau * probe.RATE))
            self.assertAlmostEqual(envelope[at_tau], math.exp(-1), delta=1e-3)
            self.assertTrue(np.all(np.diff(envelope[probe.END:]) < 0))

    def test_the_decay_matches_the_abrupt_signal_before_the_end_taper(self):
        a, b = probe.render(59, 'abrupt'), probe.render(59, 'decay', 0.2)
        np.testing.assert_array_equal(a[:probe.END - probe.TAPER], b[:probe.END - probe.TAPER])

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            probe.envelope('bogus')

    def test_case_list(self):
        cases = probe.all_cases()
        self.assertEqual(len(cases), 7)
        self.assertEqual(len({key for key, _, _ in cases}), 7)
        self.assertIn(('decay_0.05', 'decay', 0.05), cases)


class Measuring(unittest.TestCase):
    def test_release_frame_delay_and_level(self):
        row = probe.measure(note_with(52, 90), 52, 0.2)
        self.assertTrue(row['active'])
        self.assertFalse(row['censored'])
        self.assertEqual(row['release_frame'], 90)
        self.assertAlmostEqual(row['delay_ms'], (256 * 90 - 20000) / 22050 * 1000, places=2)
        self.assertAlmostEqual(row['level_db'], probe.level_db(0.2, 90), places=2)
        self.assertEqual(row['decoder_off_frame'], 92)
        self.assertFalse(row['edge_affected'])

    def test_abrupt_rows_have_no_level(self):
        self.assertNotIn('level_db', probe.measure(note_with(52, 90), 52, None))

    def test_not_active_is_undetected(self):
        row = probe.measure(note_with(52, 90, active=False), 52, 0.2)
        self.assertEqual(row, dict(midi=52, active=False))
        low = note_with(52, 90)
        low[76, 52 - probe.FIRST_MIDI] = 0.29
        self.assertFalse(probe.measure(low, 52, 0.2)['active'])
        edge = note_with(52, 90)
        edge[78, 52 - probe.FIRST_MIDI] = 0.3
        self.assertTrue(probe.measure(edge, 52, 0.2)['active'])

    def test_censored_is_a_bound(self):
        row = probe.measure(note_with(52, None), 52, 0.4)
        self.assertTrue(row['censored'])
        self.assertIsNone(row['release_frame'])
        self.assertAlmostEqual(row['delay_ms'], 1078.31, places=1)
        self.assertAlmostEqual(row['level_db'], probe.level_db(0.4, 171), places=2)
        self.assertIsNone(row['decoder_off_frame'])
        self.assertFalse(row['edge_affected'])

    def test_a_dip_is_the_release_frame_but_not_the_decoder_off_frame(self):
        row = probe.measure(note_with(66, 100, dip=85), 66, None)
        self.assertEqual(row['release_frame'], 85)
        self.assertEqual(row['decoder_off_frame'], 102)

    def test_the_first_frame_after_the_steady_segment_counts(self):
        self.assertEqual(probe.measure(note_with(45, 79), 45, None)['release_frame'], 79)
        self.assertAlmostEqual(probe.measure(note_with(45, 79), 45, None)['delay_ms'], 10.16, places=2)

    def test_edge_flag(self):
        self.assertFalse(probe.measure(note_with(45, 164), 45, None)['edge_affected'])
        self.assertTrue(probe.measure(note_with(45, 165), 45, None)['edge_affected'])
        self.assertTrue(probe.measure(note_with(45, 171), 45, None)['edge_affected'])

    def test_only_the_played_column_is_read(self):
        note = note_with(52, 90)
        note[:, 59 - probe.FIRST_MIDI] = 0.9
        self.assertEqual(probe.measure(note, 52, None)['release_frame'], 90)


class Verdicts(unittest.TestCase):
    def test_identical_models_pass_p0_and_p3_and_miss_p1(self):
        out = probe.verdicts(results(same))
        self.assertEqual(out['P0']['verdict'], 'pass')
        self.assertEqual(out['P1']['verdict'], 'miss')
        self.assertEqual(out['P1']['pitches_counted'], 0)
        self.assertEqual(out['P2']['verdict'], 'not_evaluated')
        self.assertEqual(out['P3']['verdict'], 'pass')

    def test_a_longer_decay_hold_passes_p1_and_p2(self):
        def rule(model, case, midi):
            return 120 if model == 'adapted' and case.startswith('decay') else 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P0']['verdict'], 'pass')
        self.assertEqual(out['P1']['verdict'], 'pass')
        self.assertEqual(out['P1']['pitches_counted'], 4)
        self.assertEqual(out['P2']['verdict'], 'pass')
        self.assertEqual(sorted(out['P2']['pitches_proven']), [45, 52, 59, 66])
        self.assertEqual(out['P3']['verdict'], 'pass')

    def test_p0_miss_when_an_abrupt_delay_differs_by_more_than_25_ms(self):
        def rule(model, case, midi):
            return 93 if model == 'adapted' and case == 'abrupt' and midi == 59 else 90
        out = probe.verdicts(results(rule))
        self.assertAlmostEqual(out['P0']['by_pitch'][59]['difference_ms'], 3 * 256 / 22050 * 1000, places=2)
        self.assertEqual(out['P0']['verdict'], 'miss')

    def test_p0_allows_a_difference_of_two_frames(self):
        def rule(model, case, midi):
            return 92 if model == 'adapted' and case == 'abrupt' else 90
        self.assertEqual(probe.verdicts(results(rule))['P0']['verdict'], 'pass')

    def test_p0_censored_abrupt_is_a_miss_not_a_pass(self):
        def rule(model, case, midi):
            return None if model == 'adapted' and case == 'abrupt' and midi == 45 else 90
        self.assertEqual(probe.verdicts(results(rule))['P0']['verdict'], 'miss')

    def test_p0_unevaluable_with_fewer_than_three_pitches(self):
        def rule(model, case, midi):
            return 'inactive' if model == 'adapted' and case == 'abrupt' and midi in (45, 66) else 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P0']['verdict'], 'unevaluable')
        self.assertEqual(out['P0']['evaluable_pitches'], [52, 59])

    def test_p0_with_three_evaluable_pitches_ignores_the_undetected_one(self):
        def rule(model, case, midi):
            return 'inactive' if model == 'adapted' and case == 'abrupt' and midi == 45 else 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P0']['verdict'], 'pass')
        self.assertEqual(out['P0']['evaluable_pitches'], [52, 59, 66])

    def test_p1_censored_adapted_counts_when_the_bound_proves_it(self):
        def rule(model, case, midi):
            return None if model == 'adapted' and case.startswith('decay') else 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P1']['verdict'], 'pass')
        self.assertEqual(out['P2']['verdict'], 'pass')

    def test_p1_censored_original_never_proves_a_difference(self):
        def rule(model, case, midi):
            return None if model == 'unmodified' and case.startswith('decay') else 120
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P1']['verdict'], 'miss')
        self.assertEqual(out['P1']['pitches_counted'], 0)

    def test_p1_needs_three_db_and_two_taus(self):
        # 3 frames is 3.0 dB at tau 0.1 (1.008 dB/frame) and 1.5 dB at tau 0.2: only tau 0.1 is proven at each pitch.
        def rule(model, case, midi):
            return 93 if model == 'adapted' and case.startswith('decay') else 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P1']['verdict'], 'miss')
        self.assertEqual(out['P1']['by_pitch'][52]['taus_proven'], [0.1])
        # 7 frames: 7.1 dB at tau 0.1, 3.5 dB at 0.2, 1.8 dB at 0.4: two taus are proven.
        def rule7(model, case, midi):
            return 97 if model == 'adapted' and case.startswith('decay') else 90
        out7 = probe.verdicts(results(rule7))
        self.assertEqual(out7['P1']['by_pitch'][52]['taus_proven'], [0.1, 0.2])
        self.assertEqual(out7['P1']['verdict'], 'pass')

    def test_p1_unevaluable_when_pitches_are_undetected(self):
        def rule(model, case, midi):
            return 'inactive' if model == 'adapted' and midi in (45, 66) and case.startswith('decay') else 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P1']['verdict'], 'unevaluable')
        self.assertEqual(out['P2']['verdict'], 'not_evaluated')

    def test_p2_miss_when_the_gap_is_under_30_ms(self):
        # 8 frames passes P1 (8.1 dB at tau 0.1) but the delay difference is 8 frames = 92.9 ms: choose 1 frame at tau 0.2 only.
        def rule(model, case, midi):
            if model == 'adapted' and case in ('decay_0.1', 'decay_0.4'):
                return 160
            if model == 'adapted' and case == 'decay_0.2':
                return 91
            return 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P1']['verdict'], 'pass')
        self.assertEqual(out['P2']['verdict'], 'miss')
        self.assertEqual(out['P2']['pitches_proven'], [])

    def test_p3_miss_when_two_pitches_differ_by_more_than_3_db(self):
        def rule(model, case, midi):
            return 110 if model == 'adapted' and midi == 52 and case.startswith('decay') else 90
        out = probe.verdicts(results(rule))
        self.assertEqual(out['P3']['verdict'], 'miss')
        self.assertGreater(abs(out['P3']['level_difference_db_52_minus_59']['adapted'][0.2]), 3)
        self.assertEqual(out['P3']['level_difference_db_52_minus_59']['unmodified'][0.2], 0.0)

    def test_p3_unevaluable_with_fewer_than_two_taus_for_a_model(self):
        def rule(model, case, midi):
            return 'inactive' if model == 'unmodified' and midi == 52 and case in ('decay_0.05', 'decay_0.1', 'decay_0.2') else 90
        self.assertEqual(probe.verdicts(results(rule))['P3']['verdict'], 'unevaluable')


class Runner(unittest.TestCase):
    def test_the_spec_pins_the_same_signal_as_the_code(self):
        spec = json.loads((ROOT / 'docs/recovery/basic-pitch-release-probe-20261122.json').read_text())
        self.assertEqual(spec['signal'], runner.probe_description())
        self.assertEqual(spec['worker_repository'], 'Ajuntanaga/m3-offload')
        self.assertEqual(spec['evidence']['run_id'], 45029161409)
        for name in runner.MODELS:
            self.assertRegex(spec['models'][name]['sha256'], '^[0-9a-f]{64}$')
            self.assertEqual(spec['models'][name]['file'], name + '.onnx')

    def test_the_interface_is_the_pinned_one(self):
        from tools.basic_pitch_onnx_export import INPUT, OUTPUTS
        self.assertEqual(runner.INPUT, INPUT)
        self.assertEqual(runner.OUTPUTS, (OUTPUTS['note'], OUTPUTS['onset']))

    def test_signals_cover_every_case_once_in_a_fixed_order(self):
        rows = list(runner.signals())
        labels = [row[0] for row in rows]
        self.assertEqual(len(rows), 4 * 6 + 1)
        self.assertEqual(len(set(labels)), len(labels))
        self.assertEqual(labels[0], '45_abrupt')
        self.assertEqual(labels[-1], 'silence')
        for _, midi, case, tau, signal in rows:
            self.assertEqual((signal.shape, signal.dtype), ((probe.SAMPLES,), np.float32))
        self.assertEqual({row[2] for row in rows}, {key for key, _, _ in probe.all_cases()})

    def test_model_execution_is_remote_only(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GITHUB_ACTIONS', None)
            with self.assertRaises(RuntimeError):
                runner.remote_only()
            with self.assertRaises(RuntimeError):
                runner.Backend(Path('missing.onnx'))
            with self.assertRaises(RuntimeError):
                runner.run(Path('missing.json'), Path('missing'), Path('missing-output'))

    def test_find_model_needs_exactly_one(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                runner.find_model(root, 'adapted')
            (root / 'a').mkdir()
            (root / 'a' / 'adapted.onnx').write_bytes(b'x')
            self.assertEqual(runner.find_model(root, 'adapted'), root / 'a' / 'adapted.onnx')
            (root / 'adapted.onnx').write_bytes(b'y')
            with self.assertRaises(ValueError):
                runner.find_model(root, 'adapted')

    def test_end_to_end_with_stand_in_models(self):
        """The whole run path with fake graphs: energy-following stand-ins, the 'adapted' one holds a quieter tail."""
        class Fake:
            def __init__(self, path):
                self.version = 'fake'
                self.scale = 0.02 if 'unmodified' in str(path) else 0.002

            def predict(self, window):
                # Backward-looking energy: frame f summarises the 256 samples that end at sample 256 f.
                frames = np.arange(probe.FRAMES) * probe.HOP
                energy = np.array([float(np.sqrt(np.mean(window[max(0, f - probe.HOP):max(f, 1)].astype(np.float64) ** 2)))
                                   for f in frames])
                note = np.repeat(np.minimum(1.0, energy / self.scale)[:, None], 88, axis=1).astype(np.float32)
                return note, note * 0.5

        spec = json.loads((ROOT / 'docs/recovery/basic-pitch-release-probe-20261122.json').read_text())
        env = dict(GITHUB_ACTIONS='true', SOURCE_SHA='a' * 40, GITHUB_REPOSITORY='Ajuntanaga/m3-offload', GITHUB_SHA='b' * 40,
                   GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1')
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, env), \
                mock.patch.object(runner, 'Backend', Fake), \
                mock.patch.object(runner.subprocess, 'run', return_value=mock.Mock(stdout='a' * 40)):
            root = Path(folder)
            (root / 'evidence' / 'nested').mkdir(parents=True)
            for name in runner.MODELS:
                (root / 'evidence' / 'nested' / (name + '.onnx')).write_bytes(name.encode())
                spec['models'][name]['sha256'] = runner.digest(root / 'evidence' / 'nested' / (name + '.onnx'))
            spec_path = root / 'spec.json'
            spec_path.write_text(json.dumps(spec))
            report = runner.run(spec_path, root / 'evidence', root / 'out')
            saved = json.loads((root / 'out' / 'report' / 'report.json').read_text())
            self.assertEqual(saved['state'], 'complete')
            self.assertTrue(saved['final'])
            self.assertFalse(saved['promotion_accepted'])
            self.assertEqual(report['verdicts']['P0']['verdict'], 'pass')
            self.assertEqual(saved['verdicts']['P1']['verdict'], 'pass')
            self.assertEqual(saved['verdicts']['P2']['verdict'], 'pass')
            self.assertEqual(saved['verdicts']['P3']['verdict'], 'pass')
            self.assertEqual(saved['controls']['unmodified']['silence_note_max'], 0.0)
            self.assertTrue(saved['controls']['adapted']['sustained']['52']['active_at_end'])
            self.assertEqual(set(saved['measurements']['adapted']), {key for key, kind, _ in probe.all_cases()
                                                                  if kind not in ('sustained', 'silence')})
            with np.load(root / 'out' / 'bulk' / 'adapted-outputs.npz') as arrays:
                self.assertEqual(len(arrays.files), 2 * 25)
                self.assertEqual(arrays['52_abrupt_note'].shape, (172, 88))
            with self.assertRaises(FileExistsError):
                runner.run(spec_path, root / 'evidence', root / 'out')

    def test_a_model_hash_mismatch_stops_before_inference(self):
        spec = json.loads((ROOT / 'docs/recovery/basic-pitch-release-probe-20261122.json').read_text())
        env = dict(GITHUB_ACTIONS='true', SOURCE_SHA='a' * 40, GITHUB_REPOSITORY='Ajuntanaga/m3-offload', GITHUB_SHA='b' * 40,
                   GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='1')
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, env), \
                mock.patch.object(runner, 'Backend', side_effect=AssertionError('inference must not start')), \
                mock.patch.object(runner.subprocess, 'run', return_value=mock.Mock(stdout='a' * 40)):
            root = Path(folder)
            for name in runner.MODELS:
                (root / (name + '.onnx')).write_bytes(b'not the pinned model')
            spec_path = root / 'spec.json'
            spec_path.write_text(json.dumps(spec))
            with self.assertRaises(ValueError):
                runner.run(spec_path, root, root / 'out')
            saved = json.loads((root / 'out' / 'report' / 'report.json').read_text())
            self.assertEqual(saved['state'], 'failed')
            self.assertEqual(saved['error']['type'], 'ValueError')

    def test_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'f'
            path.write_bytes(b'abc')
            self.assertEqual(runner.digest(path), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')


if __name__ == '__main__':
    unittest.main()
