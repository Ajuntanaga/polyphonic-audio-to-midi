"""Synthetic portable-runner checks; no audio, fitting, downloads or inference."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.pitch_detector_comparison import digest, read_labels, score
from tools import portable_direct_spectrum_learning as runner


class PortableSpectrumTests(unittest.TestCase):
    def test_role_feature_storage_is_opt_in_and_keeps_source_coverage(self):
        class Extractor:
            names = ['coordinate_a', 'coordinate_b']
            def __call__(self, audio):
                return np.array([.25, -.5], np.float32)
        plan = [dict(components=[dict(source_key='take')])]
        takes = [dict(key='take', role='train')]
        truth = np.zeros(53, bool)
        truth[9] = True
        with tempfile.TemporaryDirectory() as directory:
            for requested in (None, np.float32):
                extractor = Extractor()
                if requested is not None:
                    extractor.storage_dtype = requested
                with patch.object(runner, 'remote_only'), \
                     patch.object(runner, 'mixture_plan', return_value=plan), \
                     patch.object(runner, 'render_mixture', return_value=(None, truth)):
                    features, labels, counts = runner.role_examples('train', takes, {}, extractor, Path(directory))
                self.assertEqual(features.dtype, np.float64 if requested is None else requested)
                np.testing.assert_array_equal(features, [[.25, -.5]])
                np.testing.assert_array_equal(labels, truth[None, :])
                self.assertEqual(counts, {'take': 1})

    def test_remote_guard_precedes_dependencies_and_file_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m',
                'tools.portable_direct_spectrum_learning', '--spec', 'absent',
                '--output', str(output)], capture_output=True, text=True,
                env={k: v for k, v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())

    def test_measured_completion_scoring_and_labels_after_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = Path(directory)
            corpus, bulk = inputs/'corpus', inputs/'bulk'
            corpus.mkdir()
            bulk.mkdir()
            wav, tsv = corpus/'ordinary.wav', corpus/'ordinary.tsv'
            wav.write_bytes(b'synthetic placeholder, never opened as audio')
            tsv.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n'
                           '512\t1536\t60\t1\n')
            config = dict(sample_rate=96000, sample_count=1536,
                wav_sha256=digest(wav), labels_sha256=digest(tsv))
            spans = [(512, 1536, 60)]
            baseline = dict(pitch_spans=spans,
                measurement=score(spans, read_labels(tsv), sample_rate=96000, sample_count=1536))
            observed_ends, calls = [], []
            def extractor(context):
                observed_ends.append(context[-1])
                return np.zeros(556)
            class Scaler:
                def transform(self, features):
                    return features
            class Model:
                def predict_proba(self, features):
                    calls.append(len(calls))
                    result = np.zeros((1, 53))
                    result[0, 60-32] = .9
                    return result
            def delayed_labels(path):
                self.assertEqual(len(calls), 3)
                return read_labels(path)
            with patch.object(runner, 'remote_only'), \
                 patch.object(runner, 'load_wave', return_value=np.arange(1536, dtype=float)), \
                 patch.object(runner, 'read_labels', side_effect=delayed_labels), \
                 patch.object(runner.time, 'perf_counter_ns', side_effect=[0,1000,10000,11000,20000,21000]):
                report = runner.continuous_dataset('ordinary', config, baseline, inputs,
                                                    extractor, Scaler(), Model(), bulk)
            np.testing.assert_allclose(observed_ends, np.array([511,1023,1535])*10**(-9/20))
            self.assertTrue(report['current_complete_score_identity'])
            primary = report['arms']['primary_fifo']['comparison']
            diagnostic = report['arms']['source_availability_diagnostic']['comparison']
            self.assertEqual(primary['label_deltas'][0]['present_samples_delta'], -1)
            self.assertEqual(diagnostic['label_deltas'][0]['present_samples_delta'], 0)
            self.assertEqual(report['timing']['service_ns_max'], 1000)
            self.assertEqual(report['timing']['results_after_recording_end'], 1)
            self.assertEqual(report['eof']['last_prediction_active_notes'], [60])
            with np.load(bulk/'ordinary-predictions.npz', allow_pickle=False) as tape:
                self.assertEqual(tape['emitted_samples'].tolist(), [513,1025,1537])

    def test_source_labels_fail_before_waveform_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wav, tsv = root/'source.wav', root/'source.tsv'
            wav.write_bytes(b'never read as audio')
            tsv.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\n'
                           '0\t20000\t60\t1\t2\n')
            manifest = dict(files=[dict(raw_path=wav.name, labels_path=tsv.name,
                raw_sha256=digest(wav), labels_sha256=digest(tsv), takes=[dict(
                    label_index=0, start_sample=0, end_sample=20000, midi_note=60,
                    string_mask=1, calibration_pass=1)])])
            with patch.object(runner, 'remote_only'), patch.object(runner, 'load_wave') as loader:
                with self.assertRaisesRegex(ValueError, 'Source label metadata differs'):
                    runner.source_waves(manifest, root)
                loader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
