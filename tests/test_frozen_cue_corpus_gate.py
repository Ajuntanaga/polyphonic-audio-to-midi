from pathlib import Path
from copy import deepcopy
import tempfile
import unittest
import wave

from tools.frozen_cue_corpus_gate import (
    COUNTS, ERRORS, LABEL_FIELDS, compare_replays, read_corpus_wave, read_replay,
    reuse_frozen_cue_checkpoint,
)


def fixture():
    labels = [dict(label_index=i, start_sample=i * 100, end_sample=(i + 1) * 100,
                   midi_note=36 + i, string_mask=mask, calibration_pass=0,
                   labeled=100, matched=50) for i, mask in enumerate((1, 7, 15))]
    output = dict(labeled=300, matched=150, fingerprint='0123456789abcdef',
                  **{key: 0 for key in ERRORS})
    return dict(output=output, labels=labels)


class FrozenCueCorpusGateTests(unittest.TestCase):
    def cue_checkpoint(self):
        return dict(source_run='accepted-small-screen', dataset='constructed',
            settings={'max-polyphony': 5}, cue_free_lane_reassignment=True,
            cue_pitch_admission=False, config={'window_samples': 16384},
            frozen_screen={'agreement_cents_inclusive': 25.0}, cue_notes=[36],
            sample_rate=96000, sample_count=32768, source_report_sha256='1' * 64,
            corpus_manifest_sha256='2' * 64, baseline_binary_sha256='3' * 64,
            binary_sha256='4' * 64, calibration_sha256='5' * 64,
            wav_sha256='6' * 64, tsv_sha256='7' * 64,
            analysis_source_sha256={'independent_partial_evidence': '8' * 64},
            feature_samples_processed=32768, cue_sha256='9' * 64,
            cue_intervals=1, cue_intervals_by_note={'36': 1},
            state='running', final=False, replays={'baseline': {'partial': True}})

    def test_finished_cues_can_resume_without_reusing_partial_replays(self):
        saved = self.cue_checkpoint()
        reused = reuse_frozen_cue_checkpoint(saved, saved, cue_sha256='9' * 64)
        self.assertEqual(reused['cue_intervals'], 1)
        self.assertEqual(reused['feature_samples_processed'], 32768)
        self.assertNotIn('replays', reused)
        self.assertNotIn('state', reused)

    def test_checkpoint_must_match_recording_calibration_binary_and_rules(self):
        expected = self.cue_checkpoint()
        for key in ('source_run', 'dataset', 'settings', 'cue_pitch_admission', 'config',
                    'frozen_screen', 'binary_sha256', 'calibration_sha256', 'wav_sha256',
                    'tsv_sha256', 'source_report_sha256', 'corpus_manifest_sha256'):
            saved = deepcopy(expected)
            saved[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError):
                reuse_frozen_cue_checkpoint(saved, expected, cue_sha256='9' * 64)
        saved = deepcopy(expected)
        saved['analysis_source_sha256']['independent_partial_evidence'] = 'a' * 64
        with self.assertRaisesRegex(ValueError, 'calculation changed'):
            reuse_frozen_cue_checkpoint(saved, expected, cue_sha256='9' * 64)

    def test_partial_extraction_and_missing_counts_are_rejected(self):
        expected = self.cue_checkpoint()
        for key, value in (('feature_samples_processed', 31744),
                           ('cue_intervals_by_note', {}), ('cue_intervals', 2)):
            saved = deepcopy(expected)
            saved[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                reuse_frozen_cue_checkpoint(saved, expected, cue_sha256='9' * 64)

    def test_changed_or_unhashed_cue_file_is_rejected(self):
        expected = self.cue_checkpoint()
        with self.assertRaisesRegex(ValueError, 'file hash differs'):
            reuse_frozen_cue_checkpoint(expected, expected, cue_sha256='a' * 64)
        saved = deepcopy(expected)
        del saved['cue_sha256']
        with self.assertRaisesRegex(ValueError, 'file hash differs'):
            reuse_frozen_cue_checkpoint(saved, expected, cue_sha256='9' * 64)

    def test_pcm16_decoding_matches_native_endpoint_scale(self):
        import numpy as np
        samples = np.array([-32768, -1, 0, 1, 32767], dtype='<i2')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pcm.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 96000, len(samples), 'NONE', 'not compressed'))
                stream.writeframes(samples.tobytes())
            rate, values = read_corpus_wave(path)
            self.assertEqual(rate, 96000)
            np.testing.assert_array_equal(values, samples.astype(np.float32) / 32768)
            path.write_bytes(path.read_bytes()[:-2])
            with self.assertRaisesRegex(ValueError, 'incomplete PCM16'):
                read_corpus_wave(path)

    def test_float_samples_are_preserved_and_stereo_is_rejected(self):
        import numpy as np
        from tools.controlled_descriptor_overlap import write_float_wave
        samples = np.array([-0.33, 0, 1.25], dtype='<f4')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'float.wav'
            write_float_wave(path, 96000, samples)
            rate, values = read_corpus_wave(path)
            self.assertEqual(rate, 96000)
            self.assertEqual(values.tobytes(), samples.tobytes())
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((2, 2, 96000, 1, 'NONE', 'not compressed'))
                stream.writeframes(b'\0' * 4)
            with self.assertRaisesRegex(ValueError, 'mono PCM16'):
                read_corpus_wave(path)

    def test_total_gain_cannot_hide_one_lost_label(self):
        before, after = fixture(), fixture()
        after['labels'][0]['matched'] += 10
        after['labels'][1]['matched'] -= 1
        after['output']['matched'] += 9
        result = compare_replays(before, after)
        self.assertFalse(result['gate_pass'])
        self.assertEqual(result['lost_labels'], [1])

    def test_each_error_ceiling_is_independent(self):
        for key in ERRORS:
            with self.subTest(key=key):
                before, after = fixture(), fixture()
                after['output'][key] += 1
                self.assertFalse(compare_replays(before, after)['gate_pass'])

    def test_identity_change_and_missing_labels_fail_closed(self):
        for key in LABEL_FIELDS[:-1]:
            after = fixture()
            after['labels'][0][key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare_replays(fixture(), after)
        after = fixture()
        after['labels'].pop()
        with self.assertRaises(ValueError):
            compare_replays(fixture(), after)

    def test_unchanged_and_safe_gain_are_distinct(self):
        before, after = fixture(), fixture()
        self.assertTrue(compare_replays(before, after)['output_bit_identical'])
        after['labels'][0]['matched'] += 1
        after['output']['matched'] += 1
        result = compare_replays(before, after)
        self.assertTrue(result['gate_pass'])
        self.assertFalse(result['output_bit_identical'])

    def test_native_tsv_keeps_exact_three_and_four_string_counts(self):
        data = fixture()
        header = ('fingerprint', *COUNTS)
        text = '\t'.join(header) + '\n'
        text += '\t'.join(str(data['output'][key]) for key in header) + '\n'
        text += '\t'.join(LABEL_FIELDS) + '\n'
        text += ''.join('\t'.join(str(row[key]) for key in LABEL_FIELDS) + '\n'
                        for row in data['labels'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'replay.tsv'
            path.write_text(text)
            result = read_replay(path)
            self.assertEqual(result['labels'], data['labels'])
            for count in ('1', '3', '4'):
                self.assertEqual(result['exact_matches_by_string_count'][count],
                                 dict(labeled=100, matched=50))
            path.write_text(text.replace('\t300\t150\t', '\t300\t151\t'))
            with self.assertRaisesRegex(ValueError, 'accounting disagree'):
                read_replay(path)


if __name__ == '__main__':
    unittest.main()
