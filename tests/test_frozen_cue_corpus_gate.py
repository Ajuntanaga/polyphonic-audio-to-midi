from pathlib import Path
import tempfile
import unittest
import wave

from tools.frozen_cue_corpus_gate import (
    COUNTS, ERRORS, LABEL_FIELDS, compare_replays, read_corpus_wave, read_replay,
)


def fixture():
    labels = [dict(label_index=i, start_sample=i * 100, end_sample=(i + 1) * 100,
                   midi_note=36 + i, string_mask=mask, calibration_pass=0,
                   labeled=100, matched=50) for i, mask in enumerate((1, 7, 15))]
    output = dict(labeled=300, matched=150, fingerprint='0123456789abcdef',
                  **{key: 0 for key in ERRORS})
    return dict(output=output, labels=labels)


class FrozenCueCorpusGateTests(unittest.TestCase):
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
