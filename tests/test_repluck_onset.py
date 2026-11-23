"""Synthetic contract tests only: no native execution, model or audio."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.candidate_outcome_analysis import HEADER, CANDIDATE_FIELDS_V4
from tools.midi_lifecycle_analysis import EVENT_FIELDS
from tools.portable_repluck_onset import extract_member, read_snapshot, replay_command
from tools.portable_stable_note_identity_ledger import read_callbacks
from tools.repluck_onset_analysis import (read_tagged, read_target, window, onset_summary,
    event_attribution, attribute_fixture, require_callback_identity, require_ledger_integrity)


def candidate(**changes):
    row = dict.fromkeys(CANDIDATE_FIELDS_V4, 0)
    row.update(note=60, active=1, selection=4, onset_observed=1, energy_observed=1)
    row.update(changes)
    return row


def points():
    return [dict(sample=63+64*i, tick=i+1, quiet=0, signal_samples=64*(i+1),
                 candidate=candidate(onset=1 if i == 0 else 0), target_voices=[])
            for i in range(4)]


def event(**changes):
    row = dict(sample=191, kind='on', note=60, velocity=100, voice_id=1, sequence=2)
    row.update(changes)
    return row


class OnsetContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def trace(self, rows):
        path = self.root/'outcome.tsv'
        text = '# m3_candidate_outcome_v4\n' + HEADER
        for p in rows:
            value = '' if p['candidate'] is None else ':'.join(str(p['candidate'][k]) for k in CANDIDATE_FIELDS_V4)
            text += f"{p['sample']}\t{p['tick']}\t0\t{p['signal_samples']}\t\t\t\t{value}\n"
        path.write_text(text)
        return path

    def test_complete_trace_preserves_missing_candidate(self):
        rows = points(); rows[1]['candidate'] = None
        observed = read_target(self.trace(rows), samples=256, note=60)
        self.assertEqual(observed, rows)
        self.assertEqual(onset_summary(observed)['onset_unavailable'], 1)

    def test_grid_gap_duplicate_and_short_fail(self):
        for bad in ('gap', 'duplicate', 'short', 'tick'):
            with self.subTest(bad=bad):
                rows = points()
                if bad == 'gap': rows[1]['sample'] += 64
                if bad == 'duplicate': rows[1]['sample'] = rows[0]['sample']
                if bad == 'short': rows.pop()
                if bad == 'tick': rows[2]['tick'] += 1
                with self.assertRaises(ValueError):
                    read_target(self.trace(rows), samples=256, note=60)

    def test_old_tuple_cannot_masquerade_as_v4(self):
        path = self.trace(points())
        text = path.read_text().splitlines()
        text[2] = text[2].rsplit(':', 1)[0]
        path.write_text('\n'.join(text)+'\n')
        with self.assertRaises(ValueError): read_target(path, samples=256, note=60)

    def test_window_exact_boundaries(self):
        self.assertEqual([p['sample'] for p in window(points(), 64, 191)], [127, 191])
        self.assertEqual(window(points(), 192, 254), [])
        self.assertEqual(len(window(points(), -500, 999)), 4)

    def test_unobserved_zero_is_unavailable(self):
        rows = points()
        for p in rows: p['candidate']['onset_observed'] = 0
        summary = onset_summary(rows)
        self.assertIsNone(summary['maximum_onset'])
        self.assertEqual(summary['onset_unavailable'], 4)

    def attribution(self, rows, *, delivered=None):
        return event_attribution(rows, points(), event(), {2:0}, set() if delivered is None else delivered,
                                 marker=0, sample_rate=96000)

    def test_earlier_valid_onset_continuous_zero_handoff(self):
        result = self.attribution(points())
        self.assertTrue(result['instantaneous_onset_memory_pattern'])
        self.assertEqual(result['since_insertion']['first_positive_sample'], 63)

    def test_coasting_gap_prevents_continuity_claim(self):
        rows=points(); rows[1]['candidate']['selection']=5
        self.assertFalse(self.attribution(rows)['instantaneous_onset_memory_pattern'])

    def test_missing_row_prevents_continuity_claim(self):
        rows=points(); rows[1]['candidate']=None
        self.assertFalse(self.attribution(rows)['instantaneous_onset_memory_pattern'])

    def test_invalid_current_onset_prevents_claim(self):
        rows=points(); rows[2]['candidate']['onset_observed']=0
        self.assertFalse(self.attribution(rows)['instantaneous_onset_memory_pattern'])

    def test_delivered_event_is_not_suppressed(self):
        self.assertFalse(self.attribution(points(), delivered={2})['instantaneous_onset_memory_pattern'])

    def test_off_grid_event_fails(self):
        with self.assertRaises(ValueError):
            event_attribution(points(),points(),event(sample=192),{2:0},set(),marker=0,sample_rate=96000)

    def test_missing_saved_response_fails(self):
        with self.assertRaises(ValueError):
            attribute_fixture(points(),points(),[],{},[],[191],marker=0,note=60,sample_rate=96000)

    def test_stable_channel_is_not_identity_slot(self):
        source=event(); source.update(channel=4,voice_id=0)
        vst3=event(voice_id=3,velocity=100/127); vst3['channel']=3
        require_callback_identity([source],[vst3],stable=True)
        with self.assertRaises(ValueError): require_callback_identity([source],[vst3],stable=False)

    def test_payload_changes_fail(self):
        source=event(); vst3=event(velocity=100/127); vst3['channel']=1
        require_callback_identity([source],[vst3],stable=False)
        for field,value in (('sample',192),('kind','off'),('note',61),('channel',2),('velocity',.5)):
            changed=dict(vst3); changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                require_callback_identity([source],[changed],stable=False)

    def test_tag_projection_and_invalid_tag(self):
        tagged=self.root/'midi.tsv'
        tagged.write_text('# m3_midi_events_v2\n'+'\t'.join((*EVENT_FIELDS,'continuation_voice_id'))+
                          '\n191\ton\t60\t100\t1\t2\t0\n')
        events,tags,sha=read_tagged(tagged,self.root/'normal.tsv',samples=256,transitions=1)
        self.assertEqual(events,[event()]); self.assertEqual(tags,{2:0})
        self.assertEqual(sha,hashlib.sha256((self.root/'normal.tsv').read_bytes()).hexdigest())
        tagged.write_text(tagged.read_text().replace('\t2\t0\n','\t2\t9\n'))
        with self.assertRaises(ValueError):
            read_tagged(tagged,self.root/'bad-normal.tsv',samples=256,transitions=1)

    def test_reciprocal_pair_required(self):
        path=self.root/'ledger.tsv'
        path.write_text('# m3_ledger_callbacks_v1\nsample\tphase\tkind\tnote\tvelocity\tvoice_id\tchannel\tsource_sequence\n')
        events=[event(kind='off',velocity=0,voice_id=0,sequence=1),event()]
        callbacks,pairs=read_callbacks(path,events,{1:1,2:0},stable=True)
        self.assertEqual((callbacks,pairs),([],1))
        with self.assertRaises(ValueError): read_callbacks(path,events,{1:1,2:255},stable=True)

    def test_archive_duplicate_and_wrong_hash_fail(self):
        archive=self.root/'data.zip'; payload=b'synthetic contract'
        sha=hashlib.sha256(payload).hexdigest()
        with zipfile.ZipFile(archive,'w') as z: z.writestr('prefix/reference.txt',payload)
        extract_member(archive,'reference.txt',self.root/'okay',sha)
        with self.assertRaises(ValueError): extract_member(archive,'reference.txt',self.root/'bad','0'*64)
        with zipfile.ZipFile(archive,'a') as z: z.writestr('other/reference.txt',payload)
        with self.assertRaises(ValueError): extract_member(archive,'reference.txt',self.root/'ambiguous',sha)

    def test_command_changes_only_observation_path(self):
        base=replay_command('bin','fixture','cal','midi')
        self.assertEqual(replay_command('bin','fixture','cal','midi','out'),base+['--outcome-trace','out'])
        self.assertIn('--diagnostic-batch-cell-update',base)
        self.assertIn('--diagnostic-stable-note-identity',base)

    def test_snapshot_clock_must_match(self):
        path=self.root/'snapshot.tsv'
        path.write_text('samples\tsample_rate\ttransitions\n256\t96000\t2\n')
        self.assertEqual(read_snapshot(path,256,96000)['transitions'],'2')
        with self.assertRaises(ValueError): read_snapshot(path,255,96000)

    def test_ledger_fault_or_bad_accounting_fails(self):
        n=dict.fromkeys(('queue_rejected_events','unqueued_after_failure','cleanup_callbacks',
                        'blocked_blocks','detection_disabled_blocks','callback_pairing_errors'),0)
        n.update(output_blocked_at_eof=False,cleanup_pending_at_eof=False,source_callbacks=0,
                 transferred_pairs=1,suppressed_source_events=2)
        require_ledger_integrity(n,[],1)
        for key,value in (('callback_pairing_errors',1),('source_callbacks',1),
                          ('transferred_pairs',0),('output_blocked_at_eof',True)):
            bad=dict(n); bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): require_ledger_integrity(bad,[],1)


if __name__ == '__main__':
    unittest.main()
