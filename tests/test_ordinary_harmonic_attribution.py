import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import ordinary_harmonic_attribution as subject


def spec(data):
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def events(spans):
    rows = []
    for left, right, note, lane in spans:
        rows.append(dict(sample=left, kind='on', note=note, velocity=100, voice_id=lane))
        if right is not None:
            rows.append(dict(sample=right, kind='off', note=note, velocity=0, voice_id=lane))
    rows.sort(key=lambda row: (row['sample'], row['kind'] != 'off'))
    return [dict(row, sequence=index) for index, row in enumerate(rows)]


def fixture():
    labels = [dict(label_index=index, midi_note=note, string_mask=mask,
                   start_sample=left, end_sample=right)
              for index, (note, mask, left, right) in enumerate(
                  [(60, 1, 0, 20), (60, 1, 5, 15), (64, 0, 0, 20)])]
    current = events([(0, 20, 60, 0), (0, 20, 64, 2)])
    trial = events([(0, 5, 60, 0), (5, 10, 60, 1), (15, 20, 60, 0),
                    (15, 18, 60, 1), (0, 20, 64, 2), (7, 12, 67, 3),
                    (20, None, 67, 3)])
    return labels, {subject.CURRENT: current, subject.TRIAL: trial}


class OutputAttributionTests(unittest.TestCase):
    def test_pitch_loss_wrong_assignment_and_extra_lane_are_separated(self):
        labels, traces = fixture()
        result, changes, counts = subject.compare(traces, labels, 24, subject.CueContext([]), [0, 1, 2])
        first = result['cases'][0]
        self.assertEqual(first['loss_causes'], dict(pitch_absent=5,
            wrong_or_incomplete_assignment=5, extra_or_unassigned_voice=3))
        self.assertEqual(first['lost_exact_samples'], 13)
        self.assertEqual(counts[subject.TRIAL][0], dict(exact=7, pitch_present=15))
        self.assertEqual(counts[subject.TRIAL][1], dict(exact=0, pitch_present=5))
        self.assertEqual(counts[subject.TRIAL][2], dict(exact=20, pitch_present=20))
        self.assertEqual(result['totals'][subject.CURRENT], dict(matched=40))
        self.assertEqual(result['totals'][subject.TRIAL], dict(matched=30,
            false_wrong_string=8, false_wrong_note=5, false_gap=4))
        # The overlapping note60 label does not double-count emitted voice duration.
        for kind in subject.KINDS:
            self.assertEqual(sum(row['sign'] * row['voice_samples'] for row in changes
                                 if row['classification'] == kind),
                result['totals'][subject.TRIAL].get(kind, 0) - result['totals'][subject.CURRENT].get(kind, 0))

    def test_same_sample_repluck_has_no_hold_or_output_difference(self):
        labels = [dict(label_index=0, midi_note=60, string_mask=1, start_sample=0, end_sample=10)]
        traces = {subject.CURRENT: events([(0, None, 60, 0)]),
                  subject.TRIAL: events([(0, 5, 60, 0), (5, None, 60, 0)])}
        result, changes, counts = subject.compare(traces, labels, 10, subject.CueContext([]), [0])
        self.assertEqual(changes, [])
        self.assertEqual(result['cases'][0]['net_exact_change'], 0)
        self.assertEqual(counts[subject.TRIAL][0]['exact'], 10)

    def test_conflicting_lane_owner_is_not_silently_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'pairing'):
            subject.compare({subject.CURRENT: events([(0, None, 60, 0), (2, None, 64, 0)]),
                             subject.TRIAL: []}, [], 10, subject.CueContext([]), [])

    def test_unassigned_voice_is_not_an_exact_known_string(self):
        active = {0: dict(voice_id=255, note=60)}
        self.assertFalse(subject.pitch_state(active, 60, 1)['exact'])
        self.assertTrue(subject.pitch_state(active, 60, 0)['exact'])


class CueAssociationTests(unittest.TestCase):
    def test_never_attaches_a_future_cue_and_marks_expiry(self):
        context = subject.CueContext([dict(start_sample=1024, end_sample=2048, note=75, evidence={})])
        self.assertIsNone(context.preceding(1023, 75))
        self.assertIsNone(context.preceding(1500, 74))
        self.assertTrue(context.preceding(1024, 75)['in_force'])
        self.assertEqual(context.preceding(2048, 75)['age_samples'], 1024)
        self.assertFalse(context.preceding(2048, 75)['in_force'])
        self.assertEqual(context.active(2048), [])

    def test_cue_evidence_pairing_and_causal_baseline(self):
        data = (subject.CUE_HEADER + '1024\t2048\t75\n').encode()
        row = dict(admitted=True, available_sample=1023, baseline_state_sample=63, candidate_note=75)
        evidence = gzip.compress(json.dumps(row).encode())
        cues, _ = subject.read_cues(data, evidence, 4096, 1)
        self.assertEqual(cues[0]['note'], 75)
        row['baseline_state_sample'] = 64
        with self.assertRaisesRegex(ValueError, 'noncausal'):
            subject.read_cues(data, gzip.compress(json.dumps(row).encode()), 4096, 1)
        with self.assertRaisesRegex(ValueError, 'correspondence'):
            subject.read_cues(data, gzip.compress(b''), 4096, 1)


class RetainedArchiveTests(unittest.TestCase):
    def make_archives(self, root, *, incorrect_held=False):
        labels, traces = fixture()
        held = {subject.CURRENT: [20, 10, 20], subject.TRIAL: [7, 0, 20]}
        totals = {subject.CURRENT: [40, 0, 0, 0], subject.TRIAL: [30, 5, 8, 4]}
        saved = dict(final=True, source=dict(commit='a' * 40, run_id='123'), runs={})
        bulk_path, small_path = root / 'bulk.zip', root / 'small.zip'
        with zipfile.ZipFile(bulk_path, 'w') as archive:
            for mode, rows in traces.items():
                fields = ('sample', 'kind', 'note', 'velocity', 'voice_id', 'sequence')
                raw = ('# m3_midi_events_v1\n' + '\t'.join(fields) + '\n' +
                       ''.join('\t'.join(str(row[field]) for field in fields) + '\n' for row in rows)).encode()
                packed = gzip.compress(raw)
                name = mode + '.tsv.gz'
                archive.writestr('nested/' + name, packed)
                trace = dict(file=name, **spec(packed), raw_bytes=len(raw),
                             raw_sha256=hashlib.sha256(raw).hexdigest())
                lifecycle = dict(transitions=len(rows),
                    labels=[dict(row, exact_held_samples=held[mode][index]) for index, row in enumerate(labels)],
                    output_safety=dict(counts={kind + '_voice_samples': value
                                              for kind, value in zip(subject.KINDS, totals[mode])}))
                saved['runs'][mode] = dict(sample_count=24, sample_rate=96000,
                                          midi_lifecycle=lifecycle, midi_trace=trace)
            cues, evidence = subject.CUE_HEADER.encode(), gzip.compress(b'')
            archive.writestr('ordinary-harmonic-admission-cues.tsv', cues)
            archive.writestr('ordinary-harmonic-admission-evidence.jsonl.gz', evidence)
            saved['cue_generation'] = dict(cue_spans=0, cue_bytes=len(cues),
                cue_sha256=hashlib.sha256(cues).hexdigest(), evidence_bytes=len(evidence),
                evidence_sha256=hashlib.sha256(evidence).hexdigest())
        if incorrect_held:
            saved['runs'][subject.TRIAL]['midi_lifecycle']['labels'][0]['exact_held_samples'] += 1
        report = json.dumps(saved).encode()
        with zipfile.ZipFile(small_path, 'w') as archive:
            archive.writestr('ordinary-harmonic-admission/report.json', report)
        reference = dict(schema='m3_ordinary_harmonic_attribution_references_v1',
            source_commit='a' * 40, run_id=123, focus_labels=[0, 1, 2],
            report=dict(file='ordinary-harmonic-admission/report.json', **spec(report)),
            small_artifact=spec(small_path.read_bytes()), bulk_artifact=spec(bulk_path.read_bytes()))
        reference_path = root / 'reference.json'
        reference_path.write_text(json.dumps(reference))
        return reference_path, small_path, bulk_path

    def test_verified_archive_analysis_reproduces_saved_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self.make_archives(root)
            result = subject.analyze(*paths, root / 'output')
            self.assertTrue(result['saved_metric_reproduction_pass'])
            self.assertEqual(result['cases'][0]['net_exact_change'], -13)
            self.assertEqual(result['change_totals']['false_gap'], dict(added=4, removed=0))
            self.assertEqual(result['native_replays'], 0)

    def test_incorrect_saved_metric_stops_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self.make_archives(root, incorrect_held=True)
            with self.assertRaisesRegex(ValueError, 'coverage does not reproduce'):
                subject.analyze(*paths, root / 'output')

    def test_changed_archive_stops_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self.make_archives(root)
            with paths[2].open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                subject.analyze(*paths, root / 'output')

    def test_ambiguous_member_stops_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'ambiguous.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('a/data.tsv', b'x')
                archive.writestr('b/data.tsv', b'x')
            with zipfile.ZipFile(path) as archive, self.assertRaisesRegex(ValueError, 'unique'):
                subject.member(archive, 'data.tsv', spec(b'x'))


if __name__ == '__main__':
    unittest.main()
