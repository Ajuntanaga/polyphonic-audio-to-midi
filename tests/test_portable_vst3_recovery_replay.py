"""Small recovery accounting contracts; native recorded replay runs on GitHub."""
import copy
from pathlib import Path
import tempfile
import unittest

from tools.portable_vst3_corpus_replay import read_callbacks
from tools.portable_vst3_recovery_replay import assess


class Vst3RecoveryReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'callbacks.tsv'
        self.rows = [(100, 'on', 60, .75, -1060, 0),
                     (512, 'off', 60, 0, -1060, 0),
                     (2200, 'on', 62, .5, -1062, 0)]
        self.clock = dict(sample_count=2048, sample_rate=96000)
        self.native = dict(schema='m3_vst3_recovery_native_v1', scenario='reject-off-panic',
            trial=True, routing='per_voice', **self.clock, sample_bits=32, block_samples=512,
            queue_rejections=0, output_blocked_blocks=3, dry_audio_mismatches=0,
            process_failures=0, rejection_injected=True, unexpected_early_block=False,
            calibration_merge_matches=True, invalid_event=False, trace_write_failed=False,
            rejected_event=dict(sample=400, note=60, note_id=-1060, channel=0),
            boundaries=[])
        values = [('fault', 512, 512, 2, 1, True, False),
                  ('cleanup', 1024, 512, 2, 2, True, False),
                  ('panic', 1536, 512, 2, 2, True, True),
                  ('ready', 2048, 512, 2, 2, False, False),
                  ('end', 3584, 2048, 3, 3, False, False)]
        for name, timeline, recording, transitions, accepted, blocked, hold in values:
            self.native['boundaries'].append(dict(name=name, timeline_samples=timeline,
                recording_samples=recording, detector_samples=recording,
                detector_transitions=transitions, accepted_events=accepted,
                event_add_attempts=accepted + 1, output_blocked=blocked, panic_hold=hold))

    def check(self, native=None, rows=None):
        native = self.native if native is None else native
        rows = self.rows if rows is None else rows
        self.path.write_text('# m3_vst3_corpus_events_v1\nsample\tkind\tnote\tvelocity\tnote_id\tchannel\n'
            + ''.join('\t'.join(map(str, row)) + '\n' for row in rows))
        callbacks = read_callbacks(self.path, sample_count=3584,
            expected_count=native['boundaries'][-1]['accepted_events'], include_events=True)
        return assess(native, callbacks, clock=self.clock, sample_bits=32), callbacks

    def test_exact_cleanup_and_complete_resume_pass_without_hiding_eof_open(self):
        assessment, callbacks = self.check()
        self.assertTrue(assessment['gate_pass'])
        self.assertEqual(assessment['accepted_cleanup_note_offs'], 1)
        self.assertEqual(assessment['post_recovery_note_ons'], 1)
        self.assertEqual(assessment['expected_resumed_recording_samples'], 1536)
        self.assertEqual(callbacks['note_ons_open_at_eof'][0]['note'], 62)

    def test_refused_note_must_be_owned_and_cleanup_must_release_exact_identity(self):
        native = copy.deepcopy(self.native)
        native['rejected_event'].update(note=61, note_id=-1061)
        result, _ = self.check(native)
        self.assertFalse(result['gates']['rejection_is_real_owned_off'])
        rows = list(self.rows)
        rows[1] = (512, 'off', 61, 0, -1061, 0)
        result, _ = self.check(rows=rows)
        self.assertFalse(result['gates']['prior_owners_released_once'])
        self.assertFalse(result['gates']['legal_callback_ownership'])

    def test_early_reenable_extra_rejection_and_late_cleanup_fail(self):
        native = copy.deepcopy(self.native)
        native['boundaries'][1]['output_blocked'] = False
        result, _ = self.check(native)
        self.assertFalse(result['gates']['expected_recovery_states'])
        native = copy.deepcopy(self.native)
        native['boundaries'][-1]['event_add_attempts'] += 1
        result, _ = self.check(native)
        self.assertFalse(result['gates']['exactly_one_callback_refused'])
        rows = list(self.rows)
        rows[1] = (513, *rows[1][1:])
        result, _ = self.check(rows=rows)
        self.assertFalse(result['gates']['prior_owners_released_once'])

    def test_dry_passthrough_cannot_hide_missing_detector_work_or_callback(self):
        for field in ('detector_samples', 'detector_transitions'):
            native = copy.deepcopy(self.native)
            native['boundaries'][-1][field] -= 1
            result, _ = self.check(native)
            self.assertTrue(result['gates']['dry_audio_preserved'])
            self.assertFalse(result['gate_pass'])

    def test_missing_stages_wrong_clock_and_callback_accounting_are_rejected(self):
        cases = []
        native = copy.deepcopy(self.native)
        native['boundaries'].pop(2)
        cases.append(native)
        native = copy.deepcopy(self.native)
        native['sample_count'] = 2047
        cases.append(native)
        native = copy.deepcopy(self.native)
        native['boundaries'][1]['accepted_events'] = 1
        cases.append(native)
        native = copy.deepcopy(self.native)
        native['boundaries'][0]['panic_hold'] = 0
        cases.append(native)
        for native in cases:
            with self.subTest(native=native), self.assertRaises(ValueError):
                self.check(native)


if __name__ == '__main__':
    unittest.main()
