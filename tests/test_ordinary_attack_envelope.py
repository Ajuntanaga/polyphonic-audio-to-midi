"""Metadata contracts only: no audio, signal processing or corpus execution."""
import csv
import hashlib
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import portable_ordinary_attack_envelope as observation


def event(sequence, sample, kind='on', note=60, voice=0, continuation=255):
    return dict(sequence=str(sequence), sample=str(sample), kind=kind, note=str(note),
                velocity='64', voice_id=str(voice), continuation_voice_id=str(continuation))


def callback(row):
    return dict(source_sequence=row['sequence'], sample=row['sample'], kind=row['kind'], note=row['note'])


class MetadataContracts(unittest.TestCase):
    def test_reciprocal_suppression_and_callback_identity(self):
        rows = [event(0, 100), event(1, 200, 'off', voice=0, continuation=1),
                event(2, 200, voice=1, continuation=0), event(3, 300, 'off', voice=1)]
        callbacks = [callback(rows[0]), callback(rows[3])]
        source, missing, pairs = observation.paired_events(rows, callbacks)
        self.assertEqual((len(source), missing, pairs), (4, {1, 2}, 1))
        with self.assertRaises(ValueError):
            observation.paired_events(rows, callbacks + callbacks[:1])
        with self.assertRaises(ValueError):
            observation.paired_events(rows, [dict(callbacks[0], sample='99'), callbacks[1]])
        with self.assertRaises(ValueError):
            observation.paired_events(rows, callbacks + [callback(rows[1])])

    def test_attack_zone_is_inclusive_and_counts_each_event_once(self):
        labels = [(100, 200, 60), (100, 220, 60), (100, 220, 61)]
        source = {i: {k: v if k == 'kind' else int(v) for k, v in event(i, s).items()}
                  for i, s in enumerate([74, 75, 100, 110, 111])}
        selected = observation.attack_events(source, {2}, labels, 25, 10)
        self.assertEqual([x['sequence'] for x in selected], [1, 2, 3])
        self.assertEqual([x['label_indices'] for x in selected], [[0, 1]] * 3)
        self.assertEqual([x['suppressed'] for x in selected], [False, True, False])
        self.assertEqual(selected[0]['label_start_offsets_samples'], [-25, -25])

    def test_raw_label_sample_clock_order_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'labels.tsv'
            header = 'start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\n'
            path.write_text(header + '217\t72000\t78\t128\t1\n217\t72000\t58\t64\t2\n')
            self.assertEqual(observation.read_labels(path, 96000), [(217, 72000, 78), (217, 72000, 58)])
            for bad in ['217\t96001\t78\t128\t1\n', '217\t217\t78\t128\t1\n',
                        '217\t72000\t128\t128\t1\n', '217\t72000\t78\t128\n']:
                path.write_text(header + bad)
                with self.assertRaises(ValueError):
                    observation.read_labels(path, 96000)

    def test_annotation_overlap_is_context_not_exclusion(self):
        conf = dict(a4=440, band_low_ratio=.96, band_high_ratio=1.04,
                    annotation_overlap_harmonics=list(range(1, 7)))
        labels = [(0, 1000, 60), (0, 1000, 48), (0, 1000, 61), (0, 60, 36)]
        result = observation.annotation_context(dict(sample=100, note=60), labels, 40, 60, conf)
        self.assertEqual(result['same_pitch_labels_overlapping_window'], [0])
        self.assertEqual(result['annotated_harmonic_overlap'], [dict(label_index=1, note=48, harmonic=2)])
        self.assertFalse(result['no_annotated_harmonic_overlap'])

    def test_quantiles_and_bins_partition_all_rows(self):
        rows = [dict(suppressed=True, label_indices=[i], no_annotated_harmonic_overlap=i % 2 == 0,
                     acoustic=dict(max_20ms_rise_within_40ms_of_event=x, env_at_dbfs=-60 + i))
                for i, x in enumerate([.5, 1., 1.5, 2., 3.])]
        summary = observation.summarize(rows)
        self.assertEqual(summary['suppressed']['all']['rise_bins'], dict(le_1=2, gt_1_lt_2=1, ge_2=2))
        self.assertEqual(summary['suppressed']['all']['local_rise_ratio']['median'], 1.5)
        self.assertEqual(summary['retained']['all']['events'], 0)
        self.assertIsNone(summary['retained']['all']['local_rise_ratio'])
        self.assertEqual(sum(summary['suppressed'][s]['events'] for s in
                             ['no_annotated_harmonic_overlap', 'annotated_harmonic_overlap']), 5)

    def test_exact_archive_members_and_digests(self):
        payload = b'only the named member'
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, dest = root / 'a.zip', root / 'output'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('prefix/tagged-on/events.gz', payload)
                z.writestr('../never-extracted', b'unrelated')
            self.assertEqual(observation.extract_zip(archive, 'tagged-on/events.gz', dest, digest),
                             'prefix/tagged-on/events.gz')
            with self.assertRaises(ValueError):
                observation.verify(dest, '0' * 64)
            with zipfile.ZipFile(archive, 'a') as z:
                z.writestr('other/tagged-on/events.gz', payload)
            with self.assertRaises(ValueError):
                observation.extract_zip(archive, 'tagged-on/events.gz', dest, digest)
            archive = root / 'a.tar.gz'
            with tarfile.open(archive, 'w:gz') as t:
                info = tarfile.TarInfo('./corpus/ordinary.tsv')
                info.size = len(payload)
                t.addfile(info, io.BytesIO(payload))
            self.assertEqual(observation.extract_tar(archive, {'corpus/ordinary.tsv': (dest, digest)}),
                             {'corpus/ordinary.tsv': digest})

    def test_audio_guard_precedes_any_audio_access(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                observation.measure(None, {}, {})


if __name__ == '__main__':
    unittest.main()
