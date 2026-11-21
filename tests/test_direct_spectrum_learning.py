"""Synthetic only: no recordings, fitting, downloads or model runtime."""
import copy
import unittest

import numpy as np

from tools.direct_spectrum_learning import (SETTINGS, SpectrumFeatures,
    classification_summary, fifo_clock, mixture_plan, prediction_spans,
    render_mixture, representation_gate, trailing_context, validate_manifest)


def manifest():
    files = []
    for lane in range(5):
        takes = [dict(label_index=p-1, start_sample=(p-1)*20000,
            end_sample=p*20000, midi_note=40+lane, string_mask=1 << lane,
            calibration_pass=p, source_start_sample=(p-1)*20000,
            source_end_sample=p*20000) for p in (1, 2, 3)]
        files.append(dict(stem=f's{lane}', sample_rate=96000, sample_count=60000,
            original_wave_sha256=f'hash{lane}', takes=takes))
    return dict(files=files)


class DirectSpectrumTests(unittest.TestCase):
    def test_source_roles_and_original_overlap_rejection(self):
        doc = manifest()
        takes, counts = validate_manifest(doc)
        self.assertEqual(counts, dict(train=5, calibration=5, test=5))
        self.assertEqual(len(takes), 15)
        # Even if the staged WAV intervals differ, original audio must not cross roles.
        doc['files'][0]['takes'][1].update(source_start_sample=10000, source_end_sample=30000)
        with self.assertRaisesRegex(ValueError, 'crosses source roles'):
            validate_manifest(doc)

    def test_plan_reproducible_role_disjoint_retains_every_take(self):
        takes, _ = validate_manifest(manifest())
        plans = {}
        for i, role in enumerate(('train', 'calibration', 'test')):
            plan = mixture_plan(takes, role=role, count=100, seed=i)
            self.assertEqual(plan, mixture_plan(takes, role=role, count=100, seed=i))
            allowed = {t['key']: t for t in takes if t['role'] == role}
            seen = set()
            for j, row in enumerate(plan):
                self.assertEqual(not row['components'], j % 20 == 0)
                self.assertEqual(len({c['string_mask'] for c in row['components']}), len(row['components']))
                for c in row['components']:
                    source = allowed[c['source_key']]
                    seen.add(c['source_key'])
                    self.assertLessEqual(source['start_sample'], c['crop_begin'])
                    self.assertLessEqual(c['crop_end'], source['end_sample'])
                    self.assertEqual(c['crop_end']-c['crop_begin'], 16384)
            self.assertEqual(seen, set(allowed))
            plans[role] = seen
        self.assertFalse(plans['train'] & plans['test'])
        self.assertFalse(plans['calibration'] & plans['test'])

    def test_waveform_phase_cancellation_and_unison_target(self):
        tone = np.sin(np.arange(16384)*0.13)
        waves = {'a': tone, 'b': -tone}
        components = [dict(stem=s, crop_begin=0, crop_end=16384, gain_db=0, note=60)
                      for s in waves]
        mixed, target = render_mixture(dict(components=components, gain_db=0), waves)
        np.testing.assert_array_equal(mixed, np.zeros(16384))
        self.assertEqual(int(target.sum()), 1)
        self.assertTrue(target[28])
        silent, empty = render_mixture(dict(components=[], gain_db=0), waves)
        self.assertEqual(np.count_nonzero(silent), 0)
        self.assertFalse(empty.any())

    def test_features_use_only_trailing_past_and_preserve_level(self):
        extractor = SpectrumFeatures()
        wave = np.sin(np.arange(20000)*2*np.pi*220/96000)*0.01
        changed = wave.copy()
        changed[17000:] = 100
        np.testing.assert_array_equal(extractor(trailing_context(wave, 17000)),
                                      extractor(trailing_context(changed, 17000)))
        features = extractor(wave[:16384])
        louder = extractor(wave[:16384]*2)
        self.assertEqual(features.shape, (556,))
        self.assertEqual(len(extractor.names), 556)
        for offset in (0, 278):
            np.testing.assert_allclose(features[offset:offset+277], louder[offset:offset+277], atol=1e-9)
            self.assertAlmostEqual(louder[offset+277]-features[offset+277], 20*np.log10(2))
        self.assertTrue(np.isfinite(extractor(np.zeros(16384))).all())
        np.testing.assert_array_equal(trailing_context(np.ones(10), 3)[-4:], [0, 1, 1, 1])

    def test_fifo_never_backdates_and_includes_queue(self):
        timing = fifo_clock([512, 1024, 1536], [10_000_000, 1_000_000, 0])
        self.assertEqual(timing[0].tolist(), [512, 5333334, 10000000, 15333334, 0])
        self.assertEqual(timing[1, 3], 16333334)
        self.assertEqual(timing[1, 4], 4666667)
        self.assertEqual(timing[2, 3], 16333334)
        self.assertTrue(np.all(timing[:, 3] >= timing[:, 1]))
        with self.assertRaises(ValueError):
            fifo_clock([512, 512], [0, 0])

    def test_completion_spans_zero_time_duplicates_and_eof(self):
        probabilities = np.zeros((4, 53))
        probabilities[0:2, 28] = .5
        probabilities[3, 30] = 1
        spans = prediction_spans(probabilities, [100, 200, 200, 2000], 1000)
        self.assertEqual(spans, [(100, 200, 60)])
        probabilities[2, 28] = .5
        self.assertEqual(prediction_spans(probabilities, [100, 200, 200, 2000], 1000), [(100, 1000, 60)])

    def test_classification_gates_include_silence_false_outputs(self):
        target = np.zeros((3, 53), dtype=bool)
        target[0, 28] = True
        target[1, 10:12] = True
        summary = classification_summary(target.astype(float), target)
        self.assertTrue(representation_gate(summary))
        probability = target.astype(float)
        probability[2, 40] = 1
        summary = classification_summary(probability, target)
        self.assertEqual(summary['overall']['precision_percent'], 75)
        self.assertEqual(summary['silence_false_predictions'], 1)
        self.assertFalse(representation_gate(summary))


if __name__ == '__main__':
    unittest.main()
