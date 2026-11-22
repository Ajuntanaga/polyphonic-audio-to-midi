"""Synthetic events and fake replay output only; no audio/native/model execution."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_midi_lifecycle_analysis import event, label, trace
from tools import portable_joint_rapid_reset as runner
from tools.frozen_cue_corpus_gate import COUNTS, LABEL_FIELDS
from tools.portable_corpus_replay import MEASUREMENT_SCOPE


def pin(data):
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


class SupportTests(unittest.TestCase):
    def test_completion_clock_rounds_up_preserves_ties_and_never_invents_off(self):
        events = [dict(emitted_ns=1, kind='on', note=60),
                  dict(emitted_ns=1000000, kind='off', note=60),
                  dict(emitted_ns=1000000, kind='on', note=64),
                  dict(emitted_ns=2000000, kind='off', note=64)]
        text, audit = runner.support_table(dict(events=events), 192)
        self.assertEqual(text, 'm3_joint_release_support_v1\t96000\n'
                         '1\t1\t60\n96\t0\t60\n96\t1\t64\n')
        self.assertEqual(audit['beyond_recording_events'], 1)
        text, _ = runner.support_table(dict(events=events[:1]), 192)
        self.assertEqual(text.count('\n'), 2)

    def test_unordered_unpaired_and_invalid_events_fail(self):
        on = dict(emitted_ns=10, kind='on', note=60)
        for events in ([on, on], [dict(on, kind='off')],
                       [on, dict(on, emitted_ns=9, kind='off')],
                       [dict(on, emitted_ns=True)], [dict(on, note=128)]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                runner.support_table(dict(events=events), 100)

    def test_budget_requires_both_limits_and_rejects_new_misses(self):
        self.assertTrue(runner.label_budget([(0, 48000, 45600)])['passed'])
        self.assertFalse(runner.label_budget([(0, 96000, 93599)])['passed'])
        self.assertFalse(runner.label_budget([(0, 10000, 9499)])['passed'])
        self.assertEqual(runner.label_budget([(0, 1, 0)])['newly_completely_missed'], [0])
        self.assertTrue(runner.label_budget([(0, 0, 0)])['passed'])

    def test_counters_reconcile_and_are_required_once(self):
        line = ('m3_replay: joint_rapid_release eligible=10 warmup=1 model_veto=2 '
                'released=6 refused=1 reactivated=3\n')
        self.assertEqual(runner.parse_counters(line)['reactivated'], 3)
        for bad in ('', line + line, line.replace('eligible=10', 'eligible=11'),
                    line.replace('reactivated=3', 'reactivated=7')):
            with self.assertRaises(ValueError):
                runner.parse_counters(bad)


class ScreenTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.corpus = self.root / 'corpus'
        self.corpus.mkdir()
        self.binary = self.root / 'not-executable'
        self.binary.write_bytes(b'placeholder, never executed')
        self.manifest = self.root / 'manifest.json'
        self.spec = self.root / 'spec.json'
        self.output = self.root / 'output'
        self.calls = []
        self.fail_timing = False
        self.trial_end = 13440
        self.ref = self.snapshot(False)
        self.midi = self.root / 'reference-midi.tsv'
        trace(self.midi, [event(1920, 'on'), event(15360, 'off')])
        source = dict(input_release='synthetic', input_bundle_sha256='synthetic',
                      original_input_manifest_sha256='synthetic')
        files, datasets = {}, {}
        for name in ('ordinary', 'extended-middle'):
            for filename in (name + '.wav', name + '.tsv', 'calibration.m3cb', 'templates.tsv'):
                data = ('synthetic ' + filename).encode()
                (self.corpus / filename).write_bytes(data)
                files[filename] = pin(data)
            reference = self.root / (name + '-reference.json')
            reference.write_text(json.dumps(dict(dataset=name, settings=runner.SETTINGS,
                block_samples=512, reference_flags={'current-on': ['--diagnostic-spectral-lane-collision']},
                source=source, inputs={f: files[f] for f in (name + '.wav', name + '.tsv',
                                                        'calibration.m3cb', 'templates.tsv')},
                runs={'current-on': dict(sample_count=19200, sample_rate=96000,
                    tsv_sha256=pin(self.ref.encode())['sha256'],
                    midi_trace_sha256=pin(self.midi.read_bytes())['sha256'])})))
            datasets[name] = dict(reference=str(reference))
        self.manifest.write_text(json.dumps(dict(source=source, files=files)))
        self.spec.write_text(json.dumps(dict(datasets=datasets, artifact={'id': 1},
            budget=dict(maximum_loss_ms=25, maximum_relative_loss=0.05),
            ordinary_gap_reduction_minimum=.20)))

    def snapshot(self, trial):
        output = dict.fromkeys(COUNTS, 0)
        output.update(labeled=10, matched=10, false_gap_voices=20 if trial else 40,
                      false_positive_voices=20 if trial else 40)
        output.update(fingerprint='0123456789abcde' + ('1' if trial else '0'),
                      samples=19200, sample_rate=96000, transitions=2)
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(output), delimiter='\t')
        writer.writeheader(); writer.writerow(output)
        writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS, delimiter='\t')
        writer.writeheader(); writer.writerow(label(0, 1920, 11520))
        return stream.getvalue()

    def support(self, spec, bulk, logs):
        result = {}
        for name in spec['datasets']:
            path = bulk / (name + '-model-events.json')
            path.write_text(json.dumps(dict(events=[dict(emitted_ns=0, kind='on', note=64)])))
            result[name] = path
        return result

    def replay(self, command, *, stdout, stderr, timeout, check):
        self.calls.append(command)
        trial = '--diagnostic-joint-rapid-release' in command
        block = int(command[command.index('--block') + 1])
        stdout.write(self.snapshot(trial))
        if '--midi-event-trace' in command:
            self.assertNotIn('--diagnostic-core-timing', command)
            trace(Path(command[command.index('--midi-event-trace') + 1]),
                  [event(1920, 'on'), event(self.trial_end if trial else 15360, 'off')])
        if '--diagnostic-core-timing' in command:
            timing = dict(schema='m3_replay_core_timing_v1', fingerprint_identical=True,
                fingerprint='0123456789abcde' + ('1' if trial else '0'),
                block_samples=block, sample_rate=96000, measurement_scope=MEASUREMENT_SCOPE,
                allocation_guard=True, cpp_allocations=0, cpp_frees=0, c_allocations=0, c_frees=0,
                p99_ns=1000, maximum_ns=400000 if self.fail_timing else 2000,
                deadline_overruns=1 if self.fail_timing else 0)
            Path(command[command.index('--diagnostic-core-timing') + 1]).write_text(json.dumps(timing))
        if trial:
            stderr.write('m3_replay: joint_rapid_release eligible=3 warmup=1 model_veto=1 '
                         'released=1 refused=0 reactivated=0\n')

    def execute(self):
        args = argparse.Namespace(binary=self.binary, corpus=self.corpus, manifest=self.manifest,
                                  spec=self.spec, output=self.output)
        with patch.dict(runner.os.environ, {'GITHUB_ACTIONS': 'true'}), \
                patch.object(runner, 'fetch_support', side_effect=self.support), \
                patch.object(runner.subprocess, 'run', side_effect=self.replay):
            return runner.run(args)

    def test_paired_screen_keeps_timing_separate_and_scores_both_corpora(self):
        result = self.execute()
        self.assertEqual(len(self.calls), 16)
        self.assertTrue(result['screen_accepted'])
        self.assertFalse(result['promotion_accepted'])
        self.assertFalse(result['installed_output_changed'])
        for name, data in result['datasets'].items():
            self.assertTrue(data['saved_current_identity'])
            self.assertTrue(data['processing_pass'])
            self.assertEqual(data['comparison']['gap_reduction_fraction'], .5)
            self.assertTrue(data['comparison']['pitch']['no_pitch_safety_regression'])
            self.assertTrue(data['mechanism_buffer_identity'])
        for command in self.calls:
            self.assertIn('--diagnostic-spectral-lane-collision', command)
            if '--diagnostic-joint-rapid-release' in command:
                self.assertTrue(Path(command[-1]).name.endswith('-support.tsv'))

    def test_timing_failure_rejects_a_quality_pass(self):
        self.fail_timing = True
        result = self.execute()
        self.assertFalse(result['screen_accepted'])
        self.assertTrue(result['utility_pass'])
        self.assertFalse(result['datasets']['ordinary']['processing_pass'])

    def test_one_label_loss_rejects_even_large_gap_cleanup(self):
        self.trial_end = 10000
        result = self.execute()
        self.assertFalse(result['screen_accepted'])
        comparison = result['datasets']['ordinary']['comparison']
        self.assertTrue(result['utility_pass'])
        self.assertFalse(comparison['label_budgets']['pitch_present_samples']['passed'])
        self.assertFalse(comparison['pitch']['no_pitch_safety_regression'])

    def test_reference_mismatch_stops_before_any_trial(self):
        spec = json.loads(self.spec.read_text())
        path = Path(spec['datasets']['ordinary']['reference'])
        reference = json.loads(path.read_text())
        reference['runs']['current-on']['midi_trace_sha256'] = '0' * 64
        path.write_text(json.dumps(reference))
        with self.assertRaisesRegex(ValueError, 'identity failed'):
            self.execute()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads((self.output / 'report/report.json').read_text())['state'], 'failed')


if __name__ == '__main__':
    unittest.main()
