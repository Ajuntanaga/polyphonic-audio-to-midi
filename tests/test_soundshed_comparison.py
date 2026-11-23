"""Synthetic event/scoring and remote-boundary contracts; no audio or native run."""
import copy
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.test_midi_lifecycle_analysis import label
from tools.pitch_detector_comparison import score
from tools.soundshed_comparison import ARMS, evaluate, read_events, research_screen
from tools import portable_soundshed_comparison as runner


CLOCK = dict(sample_count=200, sample_rate=1000)


class EventTests(unittest.TestCase):
    def read(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.tsv'
            path.write_text('sample\tkind\tnote\tvelocity\tsequence\n' + rows)
            return read_events(path, **CLOCK)

    def test_exact_event_samples_retrigger_pairing_and_eof_hold(self):
        spans, audit = self.read('17\ton\t60\t0.5\t0\n63\toff\t60\t0\t1\n'
                                '63\ton\t60\t0.6\t2\n')
        self.assertEqual(spans, [(17, 63, 60), (63, 200, 60)])
        self.assertTrue(audit['pairing_valid'])
        self.assertEqual(audit['raw_note_ons'], 2)
        self.assertEqual(len(audit['open_at_recording_end']), 1)

    def test_silence_is_valid_but_bad_pairs_are_not(self):
        self.assertEqual(self.read('')[0], [])
        for rows in ('17\toff\t60\t0\t0\n',
                     '17\ton\t60\t0.5\t0\n18\ton\t60\t0.5\t1\n'):
            with self.assertRaises(ValueError):
                self.read(rows)

    def test_no_backdating_invalid_values_or_truncation(self):
        bad = ['200\ton\t60\t0.5\t0\n', '-1\ton\t60\t0.5\t0\n',
               '17\ton\t34\t0.5\t0\n', '17\ton\t60\tnan\t0\n',
               '17\ton\t60\t0.5\t2\n', '17\tbend\t60\t0.5\t0\n',
               '17\ton\t60\t0.5\t0\n16\toff\t60\t0\t1\n']
        for rows in bad:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.read(rows)


class ScoringTests(unittest.TestCase):
    def test_primary_preserves_only_outside_range_and_all_denominators(self):
        labels = [label(0, 20, 120, note=32), label(1, 20, 120, note=64),
                  label(2, 20, 120, note=90)]
        spans = [(20, 120, 32), (20, 120, 90)]
        baseline = dict(pitch_spans=spans, measurement=score(spans, labels, **CLOCK))
        result = evaluate([(20, 120, 64)], labels, baseline, **CLOCK)
        self.assertEqual(result['unsupported_range']['label_indices'], [0, 2])
        self.assertEqual(result['arms']['range_preserving']['comparison']['model_pitch_coverage_percent'], 100)
        self.assertAlmostEqual(result['arms']['soundshed']['comparison']['model_pitch_coverage_percent'], 100 / 3)
        self.assertFalse(result['arms']['range_preserving']['report_only'])
        self.assertTrue(result['arms']['union']['report_only'])

    def test_inside_range_loss_and_bad_baseline_fail(self):
        labels = [label(0, 20, 120, note=40)]
        spans = [(20, 120, 40)]
        baseline = dict(pitch_spans=spans, measurement=score(spans, labels, **CLOCK))
        result = evaluate([], labels, baseline, **CLOCK)
        self.assertEqual(result['arms']['range_preserving']['label_budget']['failed_labels'], 1)
        baseline['measurement']['sample_count'] = 201
        with self.assertRaisesRegex(ValueError, 'does not reproduce'):
            evaluate([], labels, baseline, **CLOCK)

    def test_gain_does_not_hide_extra_gap_or_fragmented_hold(self):
        labels = [label(0, 20, 120), label(1, 20, 120, note=64)]
        spans = [(20, 120, 60)]
        baseline = dict(pitch_spans=spans, measurement=score(spans, labels, **CLOCK))
        result = evaluate([(20, 70, 60), (71, 120, 60), (20, 120, 64), (140, 150, 72)],
                          labels, baseline, **CLOCK)
        budget = result['arms']['range_preserving']['label_budget']
        self.assertFalse(budget['aggregate_safe'])
        self.assertEqual(budget['failures'][0]['reasons'], ['longest_present'])

    def test_both_corpora_useful_gain_and_no_promotion(self):
        row = dict(comparison=dict(pitch_coverage_gain_pp=5.0),
                   label_budget=dict(strict_screen_pass=True, budget_screen_pass=True))
        data = {n: dict(arms={a: copy.deepcopy(row) for a in ARMS})
                for n in ('ordinary', 'extended-middle')}
        self.assertTrue(research_screen(data)['arms']['range_preserving']['budget_pass'])
        data['extended-middle']['arms']['range_preserving']['label_budget']['budget_screen_pass'] = False
        self.assertFalse(research_screen(data)['arms']['range_preserving']['budget_pass'])
        data['ordinary']['arms']['union']['comparison']['pitch_coverage_gain_pp'] = 4.99
        self.assertFalse(research_screen(data)['arms']['union']['budget_pass'])
        self.assertFalse(research_screen(data)['promotion_accepted'])
        with self.assertRaises(ValueError):
            research_screen({'ordinary': data['ordinary']})


class RunnerTests(unittest.TestCase):
    def test_remote_guard_before_any_file_or_optional_import(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'absent'
            result = subprocess.run([sys.executable, '-m', 'tools.portable_soundshed_comparison',
                '--spec', 'absent', '--inputs', 'absent', '--output', str(out)],
                env={k:v for k,v in os.environ.items() if k != 'GITHUB_ACTIONS'},
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(out.exists())

    def test_pinned_nested_asset_and_corruption_no_retry(self):
        payload = b'synthetic fixture only'
        asset = dict(path='core/src/dsp/fixture.h', bytes=len(payload),
            git_blob_sha1=hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest())
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, GITHUB_ACTIONS='true'):
            with patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(payload)) as fetch:
                receipt = runner.download_pinned(asset, Path(directory), 'fixture/upstream', 'a'*40)
                self.assertEqual(receipt['sha256'], hashlib.sha256(payload).hexdigest())
                with self.assertRaisesRegex(ValueError, 'no download retry'):
                    runner.download_pinned(asset, Path(directory), 'fixture/upstream', 'a'*40)
                self.assertEqual(fetch.call_count, 1)
            asset['path'] = 'core/bad.h'
            with patch.object(runner.urllib.request, 'urlopen', return_value=io.BytesIO(payload+b'!')):
                with self.assertRaisesRegex(ValueError, 'Pinned asset differs'):
                    runner.download_pinned(asset, Path(directory), 'fixture/upstream', 'a'*40)

    def test_reference_failure_prevents_adapter_build(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, GITHUB_ACTIONS='true'):
            path = Path(directory)
            with patch.object(runner, 'command', side_effect=['', '0/1 checks passed\n']) as command:
                with self.assertRaisesRegex(ValueError, 'did not all pass'):
                    runner.build_and_check(path, path, path, path)
                self.assertEqual(command.call_count, 2)


if __name__ == '__main__':
    unittest.main()
