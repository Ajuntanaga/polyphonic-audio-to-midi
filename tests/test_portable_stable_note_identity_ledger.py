"""Synthetic provenance and measurement tests; native execution stays on GHA."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.portable_stable_note_identity_ledger import (
    CALLBACK_FIELDS, EVENT_FIELDS, label_metrics, pitch_safety, pitch_timeline,
    read_callbacks, read_tags, sink_spans,
)


def event(sample, kind, voice, sequence, note=37):
    return dict(sample=sample, kind=kind, note=note,
                velocity=90 if kind == 'on' else 0, voice_id=voice, sequence=sequence)


def callback(source, identity=None, channel=None):
    voice = source['voice_id'] if identity is None else identity
    return dict(sample=source['sample'], phase='source', kind=source['kind'],
                note=source['note'], velocity=source['velocity'], voice_id=voice,
                channel=voice + 1 if channel is None else channel,
                source_sequence=source['sequence'])


class StableIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.events = [event(10, 'on', 0, 0), event(30, 'off', 0, 1),
                       event(30, 'on', 1, 2), event(70, 'off', 1, 3)]
        self.tags = {0: 255, 1: 1, 2: 0, 3: 255}
        self.label = dict(label_index=17, midi_note=37, start_sample=10, end_sample=70)

    def write_callbacks(self, rows):
        path = self.root / 'callbacks.tsv'
        path.write_text('# m3_ledger_callbacks_v1\n' + '\t'.join(CALLBACK_FIELDS) + '\n' +
                        ''.join('\t'.join(str(row[key]) for key in CALLBACK_FIELDS) + '\n'
                                for row in rows))
        return path

    def test_tags_can_only_add_provenance_to_an_identical_source(self):
        path = self.root / 'tagged.tsv'
        rows = ['\t'.join(str(row[key]) for key in EVENT_FIELDS) for row in self.events]
        text = '# m3_midi_events_v2\n' + '\t'.join((*EVENT_FIELDS, 'continuation_voice_id')) + '\n'
        text += ''.join(row + '\t' + str(self.tags[index]) + '\n' for index, row in enumerate(rows))
        path.write_text(text)
        tags, checksum = read_tags(path, self.events)
        reference = '# m3_midi_events_v1\n' + '\t'.join(EVENT_FIELDS) + '\n' + '\n'.join(rows) + '\n'
        self.assertEqual(tags, self.tags)
        self.assertEqual(checksum, hashlib.sha256(reference.encode()).hexdigest())
        for changed in (text.replace('30\ton\t37', '31\ton\t37'),
                        text.replace('\t255\n', '\t8\n', 1),
                        '\n'.join(text.splitlines()[:-1]) + '\n'):
            path.write_text(changed)
            with self.assertRaises(ValueError):
                read_tags(path, self.events)

    def test_continuation_improves_sink_hold_without_changing_pitch_coverage(self):
        before = [callback(row) for row in self.events]
        after = [callback(self.events[0], 0), callback(self.events[3], 0)]
        physical, suppressed = read_callbacks(self.write_callbacks(before), self.events,
                                               self.tags, stable=False)
        self.assertEqual(suppressed, 0)
        stable, suppressed = read_callbacks(self.write_callbacks(after), self.events,
                                             self.tags, stable=True)
        self.assertEqual(suppressed, 1)
        old_spans, _ = sink_spans(physical, 100)
        new_spans, _ = sink_spans(stable, 100)
        self.assertEqual(pitch_timeline(old_spans, 100), pitch_timeline(new_spans, 100))
        old = label_metrics(old_spans, physical, [self.label])[0]
        new = label_metrics(new_spans, stable, [self.label])[0]
        self.assertEqual((old['pitch_present_samples'], new['pitch_present_samples']), (60, 60))
        self.assertEqual((old['longest_sink_hold_samples'], new['longest_sink_hold_samples']), (40, 60))
        self.assertEqual((old['note_ons_inside_label'], new['note_ons_inside_label']), (2, 1))

    def test_untagged_or_one_sided_suppression_and_default_drop_are_rejected(self):
        path = self.write_callbacks([callback(self.events[0]), callback(self.events[3], 0)])
        for tags in ({key: 255 for key in self.tags}, {**self.tags, 2: 255}):
            with self.assertRaisesRegex(ValueError, 'reciprocal'):
                read_callbacks(path, self.events, tags, stable=True)
        path = self.write_callbacks([callback(self.events[0]), callback(self.events[3])])
        with self.assertRaisesRegex(ValueError, 'Default ledger dropped'):
            read_callbacks(path, self.events, self.tags, stable=False)

    def test_changed_payload_duplicate_source_and_physical_remapping_are_rejected(self):
        rows = [callback(row) for row in self.events]
        changed = copy.deepcopy(rows)
        changed[0]['velocity'] = 100
        duplicate = rows + [rows[-1]]
        remapped = copy.deepcopy(rows)
        remapped[0]['voice_id'] = 3
        for candidate in (changed, duplicate, remapped):
            with self.assertRaises(ValueError):
                read_callbacks(self.write_callbacks(candidate), self.events, self.tags, stable=False)

    def test_real_repluck_is_preserved_and_invalid_release_identity_is_rejected(self):
        rows = [callback(row) for row in self.events]
        parsed, count = read_callbacks(self.write_callbacks(rows), self.events,
                                         {key: 255 for key in self.tags}, stable=True)
        self.assertEqual(count, 0)
        spans, open_notes = sink_spans(parsed, 100)
        self.assertEqual((len(spans), open_notes), (2, []))
        rows[1]['channel'] = 8
        with self.assertRaisesRegex(ValueError, 'release does not match'):
            sink_spans(rows, 100)

    def test_unisons_preserve_multiplicity_and_do_not_double_count_label_presence(self):
        spans = [(10, 50, 37), (20, 70, 37)]
        timeline = pitch_timeline(spans, 100)
        self.assertIn((20, 50, ((37, 2),)), timeline)
        self.assertNotEqual(timeline, pitch_timeline([(10, 70, 37)], 100))
        result = label_metrics(spans, [], [self.label])[0]
        self.assertEqual(result['pitch_present_samples'], 60)
        self.assertEqual(result['longest_sink_hold_samples'], 50)

    def test_false_gap_outputs_are_extra_voices_and_boundaries_are_half_open(self):
        events = [callback(event(0, 'on', 0, 0)), callback(event(80, 'off', 0, 1)),
                  callback(event(20, 'on', 1, 2, 44)), callback(event(30, 'off', 1, 3, 44))]
        events.sort(key=lambda row: row['sample'])
        spans, _ = sink_spans(events, 100)
        safety = pitch_safety(pitch_timeline(spans, 100), events, [self.label])
        self.assertEqual(safety, dict(false_gap_voice_samples=20, false_wrong_note_voice_samples=10,
                                    false_gap_onsets=1, false_wrong_note_onsets=1))
        on_end = [callback(event(70, 'on', 0, 0))]
        end_spans, opens = sink_spans(on_end, 100)
        self.assertEqual(opens, [37])
        self.assertEqual(pitch_safety(pitch_timeline(end_spans, 100), on_end,
                                     [self.label])['false_gap_voice_samples'], 30)
        self.assertEqual(label_metrics(end_spans, on_end, [self.label])[0]['pitch_present_samples'], 0)


if __name__ == '__main__':
    unittest.main()
