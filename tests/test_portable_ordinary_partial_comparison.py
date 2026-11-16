import copy
from contextlib import ExitStack
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tests.test_candidate_outcome_analysis import candidate
from tools.partial_motion_evidence import phase_window_trajectories, trajectories
from tools.portable_assignment_trace import digest
from tools.portable_ordinary_partial_comparison import (
    CASES, END, FLAGS, RATE, SAMPLES, analyze, pair_observations, read_motion,
    run, summarize_pair, validate_reference, verify_capture)


REFERENCE = Path(__file__).resolve().parents[1] / 'docs/recovery/ordinary-partial-references-20261116.json'
MODULE = 'tools.portable_ordinary_partial_comparison.'


def motion_fixture(note=42):
    centers = 120. * np.arange(1, 7)
    header = dict(kind='header', schema='m3_partial_motion_v1', sample_rate=RATE,
                  sample_origin=0, sample_clock='zero_based_input_sample', note=note,
                  harmonics=6, tracks='measured_demodulated_mixture')
    frames = [dict(kind='frame', note=note, sample=63 + 64 * i, tick=i + 1,
                   frequency_hz=centers.tolist(), tracks_available=True,
                   real=[1.] * 6, imaginary=[0.] * 6) for i in range(END // 64)]
    return header, frames, np.ones((6, len(frames)), dtype=complex), centers


def outcomes_fixture(frames):
    rows = []
    for frame in frames:
        sample = frame['sample']
        case = next((case for case in CASES if case['start_sample'] <= sample < case['end_sample']), None)
        labels = '' if case is None else ','.join(f'{index}:60:1' for index in case['expected_labels'])
        rows.append(dict(sample=str(sample), tick=str(frame['tick']), quiet='0', signal_samples=str(sample + 1),
                         labels=labels, matched_labels='', voices='',
                         candidates=candidate(case['candidate_note'], selection=1) if case else ''))
    return rows


class OrdinaryPartialComparisonTests(unittest.TestCase):
    def test_fifth_difference_retains_harmonic_index_and_cancels_common_detuning(self):
        times = (63 + 64 * np.arange(1800)) / RATE
        centers = 120. * np.arange(1, 7)
        offset = 2800 - 1200 * np.log2(5)
        detuning = np.full(6, 2.)
        detuning[4] += offset
        delta_hz = centers * np.expm1(detuning * np.log(2) / 1200)
        signal = np.exp(2j * np.pi * delta_hz[:, None] * times)
        for measure in (trajectories, phase_window_trajectories):
            pair = pair_observations(measure(times, signal, centers[0]))
            with self.subTest(measure=measure.__name__):
                self.assertTrue(pair['valid'].any())
                np.testing.assert_allclose(pair['difference'][pair['valid']], offset, atol=1e-8)

    def test_missing_fundamental_or_fifth_is_unknown_not_zero(self):
        times = np.arange(40) / 1500
        for band in (0, 4):
            signal = np.ones((6, len(times)), dtype=complex)
            signal[band] = np.nan
            pair = pair_observations(trajectories(times, signal, 120.))
            summary = summarize_pair(pair, dict(start_sample=0, end_sample=END))
            self.assertEqual(summary['valid_pairs'], 0)
            self.assertEqual(summary['valid_pair_fraction'], 0)
            self.assertTrue(all(value is None for value in summary['fifth_minus_fundamental_cents'].values()))
            self.assertIsNone(summarize_pair(pair, dict(start_sample=END, end_sample=END + 64))['valid_pair_fraction'])

    def test_motion_reader_rejects_missing_prefix_clock_changes_and_moving_centers(self):
        header, frames, _, _ = motion_fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'motion.jsonl'
            def write(rows):
                path.write_text('\n'.join(json.dumps(row) for row in [header, *rows]) + '\n')
            write(frames)
            self.assertEqual(len(read_motion(path, 42)[0]), END // 64)
            for change in ('missing', 'clock', 'frequency'):
                altered = copy.deepcopy(frames)
                if change == 'missing':
                    altered = altered[1:]
                elif change == 'clock':
                    altered[20]['tick'] += 1
                else:
                    altered[20]['frequency_hz'][4] += .1
                write(altered)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    read_motion(path, 42)
            frames[8]['tracks_available'] = False
            for frame in frames:
                frame['frequency_hz'][5] = 0
            write(frames)
            _, signal, _ = read_motion(path, 42)
            self.assertTrue(np.isnan(signal[:, 8]).all())
            self.assertTrue(np.isnan(signal[5]).all())

    def test_case_examples_use_only_available_past_estimates_and_record_unobserved_candidates(self):
        _, frames, signal, centers = motion_fixture()
        outcomes = outcomes_fixture(frames)
        outcomes[80]['candidates'] = ''
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(frames, signal, centers, outcomes, 42, Path(directory))
            chord, gap = result['cases']
            self.assertEqual(chord['counts']['candidate_unobserved'], 1)
            self.assertGreater(chord['counts']['candidate_selection_1'], 0)
            self.assertIsNone(chord['example']['estimates']['conditioned_160ms'])
            estimate = gap['example']['estimates']['conditioned_160ms']
            self.assertLessEqual(estimate['available_sample'], gap['example']['sample'])
            self.assertEqual(estimate['age_samples'], gap['example']['sample'] - estimate['available_sample'])
            self.assertGreater(estimate['age_samples'], 0)
            self.assertGreater(gap['summaries']['conditioned_160ms']['all']['windows_starting_before_case'], 0)
            self.assertEqual(gap['summaries']['raw']['candidate_below_threshold']['valid_pairs'], gap['counts']['frames'])
            with gzip.open(Path(directory) / result['observations']['file'], 'rt') as stream:
                self.assertIn('available_sample', next(stream))
            json.dumps(result, allow_nan=False)

    def test_annotation_or_outcome_clock_mismatch_cannot_be_scored_as_the_fixed_case(self):
        _, frames, signal, centers = motion_fixture(47)
        with tempfile.TemporaryDirectory() as directory:
            outcomes = outcomes_fixture(frames)
            outcomes[-1]['labels'] = '10:75:128'
            with self.assertRaisesRegex(ValueError, 'annotation'):
                analyze(frames, signal, centers, outcomes, 47, Path(directory))
            outcomes = outcomes_fixture(frames)
            outcomes[-1]['sample'] = str(END)
            with self.assertRaisesRegex(ValueError, 'clocks'):
                analyze(frames, signal, centers, outcomes, 47, Path(directory))

    def test_reference_requires_fixed_cases_full_input_identity_and_complete_digests(self):
        reference = json.loads(REFERENCE.read_text())
        manifest = dict(source=copy.deepcopy(reference['source']), files=copy.deepcopy(reference['inputs']))
        validate_reference(reference, manifest)
        for change in (lambda r: r['cases'][0].update(candidate_note=74),
                       lambda r: r['source'].update(input_release='another-release'),
                       lambda r: r['inputs']['ordinary.wav'].update(sha256='0' * 64),
                       lambda r: r['replay_reference'].pop('outcome_sha256'),
                       lambda r: r['replay_reference'].update(sample_rate=48000)):
            altered = copy.deepcopy(reference)
            change(altered)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_reference(altered, manifest)

    def test_aggregate_parity_cannot_hide_raw_outcome_or_sample_clock_changes(self):
        with tempfile.TemporaryDirectory() as directory, patch(MODULE + 'read_replay', return_value={'output': {'matched': 7}}):
            paths = [Path(directory) / name for name in ('replay.tsv', 'midi.tsv', 'outcome.tsv')]
            replay, midi, outcome = paths
            replay.write_text(f'samples\tsample_rate\n{SAMPLES}\t{RATE}\n')
            midi.write_text('saved MIDI\n')
            outcome.write_text('saved outcome\n')
            saved = dict(zip(('tsv_sha256', 'midi_sha256', 'outcome_sha256'), map(digest, paths)))
            saved['output'] = {'matched': 7}
            self.assertTrue(verify_capture(*paths, saved)['saved_reference_bit_identical'])
            outcome.write_text('changed outcome\n')
            with self.assertRaisesRegex(ValueError, 'saved reference'):
                verify_capture(*paths, saved)
            saved['outcome_sha256'] = digest(outcome)
            replay.write_text(f'samples\tsample_rate\n{SAMPLES - 1}\t{RATE}\n')
            saved['tsv_sha256'] = digest(replay)
            with self.assertRaisesRegex(ValueError, 'sample clock'):
                verify_capture(*paths, saved)

    def test_runner_observes_two_fixed_parents_without_changing_admission_or_timing(self):
        self.check_runner(fail_second=False)

    def test_partial_failure_cannot_be_reported_as_complete(self):
        self.check_runner(fail_second=True)

    def check_runner(self, *, fail_second):
        reference = json.loads(REFERENCE.read_text())
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            binary = root / 'binary'
            binary.write_text('not an executable')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(dict(source=reference['source'], files=reference['inputs'])))
            commands = []
            def replay(command, **kwargs):
                commands.append(command)
                if fail_second and len(commands) == 2:
                    raise RuntimeError('second replay failed')
                kwargs['stdout'].write('placeholder\n')
                for flag in ('--midi-event-trace', '--outcome-trace', '--partial-motion-trace'):
                    Path(command[command.index(flag) + 1]).write_text('placeholder\n')
            stack.enter_context(patch(MODULE + 'subprocess.run', side_effect=replay))
            for name, value in [('verify_inputs', None), ('verify_capture', {'saved_reference_bit_identical': True}),
                                ('read_motion', ([], [], [])), ('outcome_window', []), ('analyze', {}),
                                ('compress_trace_window', {})]:
                stack.enter_context(patch(MODULE + name, side_effect=lambda *a, value=value, **k: copy.deepcopy(value)))
            if fail_second:
                with self.assertRaisesRegex(RuntimeError, 'second replay'):
                    run(binary, root/'corpus', manifest, REFERENCE, root/'output')
            else:
                run(binary, root/'corpus', manifest, REFERENCE, root/'output')
            report = json.loads((root/'output/report.json').read_text())
            self.assertEqual(report['state'], 'failed' if fail_second else 'completed')
            self.assertTrue(report['final'])
            self.assertIn('finished_at', report)
            self.assertEqual(report.get('saved_references_bit_identical', False), not fail_second)
            self.assertEqual(len(commands), 2)
            for command, note in zip(commands, (47, 42)):
                for flag, expected in [('--partial-motion-note', str(note)), ('--partial-motion-start', '0'),
                                       ('--partial-motion-end', '2.45'), ('--block', '512')]:
                    self.assertEqual(command[command.index(flag) + 1], expected)
                self.assertEqual([value for value in command if value.startswith('--diagnostic')], FLAGS)
                self.assertNotIn('--timing', command)


if __name__ == '__main__':
    unittest.main()
