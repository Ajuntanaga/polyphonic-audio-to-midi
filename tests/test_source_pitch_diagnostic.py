"""Synthetic periodicity, exact-crop integrity and count-conservation checks."""
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import hashlib

import numpy as np

from tools.source_pitch_diagnostic import (normalized_difference, diagnose_crop,
    crop_inventory, summarize)
from tools import portable_source_pitch_diagnostic as runner


def tone(note, amplitude=.05, harmonics=(1,)):
    time = np.arange(16384)/96000
    frequency = 440*2**((note-69)/12)
    return amplitude*sum(np.sin(2*np.pi*frequency*k*time)/k for k in harmonics)


class SourcePitchDiagnosticTests(unittest.TestCase):
    def test_fft_difference_matches_definition_at_every_lag(self):
        signal = np.random.default_rng(1).normal(size=1024)
        actual, normalized = normalized_difference(signal, 200)
        expected = np.array([np.sum((signal[:824]-signal[lag:lag+824])**2)
                             for lag in range(201)])
        np.testing.assert_allclose(actual, expected, atol=1e-10)
        np.testing.assert_allclose(normalized[1:],
            expected[1:]*np.arange(1,201)/np.cumsum(expected[1:]), atol=1e-10)

    def test_clean_pitches_across_register_and_missing_fundamental(self):
        for note in (32,40,52,60,72,84,95):
            for harmonics in ((1,), (1,2,3,4), (2,3,4)):
                with self.subTest(note=note,harmonics=harmonics):
                    result = diagnose_crop(tone(note,harmonics=harmonics),note,0)
                    self.assertEqual(result['classification'],'periodic_target')
                    self.assertLess(abs(result['cents_from_label']),20)

    def test_label_does_not_steer_estimator(self):
        wave = tone(48)
        correct, wrong = diagnose_crop(wave,48,0), diagnose_crop(wave,60,0)
        self.assertEqual(correct['f0_hz'],wrong['f0_hz'])
        self.assertEqual(wrong['classification'],'periodic_other')
        self.assertAlmostEqual(wrong['cents_from_label'],-1200,delta=10)

    def test_silence_noise_and_weak_tone_retained(self):
        self.assertEqual(diagnose_crop(np.zeros(16384),52,0)['classification'],'silent')
        noise = np.random.default_rng(2).normal(0,.01,16384)
        self.assertEqual(diagnose_crop(noise,52,0)['classification'],'unresolved_periodicity')
        result = diagnose_crop(tone(52,amplitude=1e-5),52,0)
        self.assertEqual(result['classification'],'periodic_target')
        self.assertGreater(result['normalization_gain_db'],70)

    def test_expected_cents_is_report_only(self):
        a,b = [diagnose_crop(tone(52.2),52,cents) for cents in (0,20)]
        self.assertEqual(a['classification'],b['classification'])
        self.assertEqual(a['f0_hz'],b['f0_hz'])
        self.assertAlmostEqual(a['cents_from_expected']-b['cents_from_expected'],20)

    def test_crop_identity_and_weighted_totals(self):
        take = dict(key='synthetic:0',stem='synthetic',role='train',midi_note=52,
                    string_mask=1,start_sample=0,end_sample=32768,expected_cents=0)
        component = dict(source_key=take['key'],stem='synthetic',note=52,string_mask=1,
                         crop_begin=0,crop_end=16384)
        plan = [dict(role='train',components=[component]),
                dict(role='train',components=[component]),dict(role='train',components=[])]
        template = dict(source_key=take['key'],stem='synthetic',note=52,string_mask=1,
                        crops=[(0,16384)])
        rows = crop_inventory([take],dict(train=plan),[template])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['mixture_exposures'],2)
        self.assertEqual(rows[0]['template_exposures'],1)
        rows[0].update(diagnose_crop(tone(52),52,0))
        summary = summarize([take],rows,dict(train=plan))
        self.assertEqual(summary['roles']['train']['component_exposures']['count'],2)
        self.assertEqual(summary['roles']['train']['mixtures']['classes'],
                         dict(all_components_periodic_target=2,intentional_silence=1))
        with self.assertRaisesRegex(ValueError,'crosses roles'):
            crop_inventory([dict(take,role='test')],dict(train=plan),[])
        with self.assertRaisesRegex(ValueError,'every source'):
            crop_inventory([take],dict(train=[]),[])
        with self.assertRaisesRegex(ValueError,'differs from'):
            crop_inventory([take],dict(train=[dict(role='train',
                components=[dict(component,note=53)])]),[])

    def test_remote_guard_precedes_output_and_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)/'must-not-exist'
            with patch.object(runner,'remote_only',side_effect=RuntimeError('remote guard')):
                with self.assertRaisesRegex(RuntimeError,'remote guard'):
                    runner.run(Path('unused'),destination)
            self.assertFalse(destination.exists())

    def test_expected_cents_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            labels = folder/'labels.tsv'
            for value, valid in [('12.5', True), ('12.6', False), ('nan', False)]:
                labels.write_text('expected_cents\n'+value+'\n')
                manifest = dict(files=[dict(labels_path='labels.tsv',
                    labels_sha256=hashlib.sha256(labels.read_bytes()).hexdigest(),
                    takes=[dict(expected_cents=12.5)])])
                with self.subTest(value=value), patch.object(runner,'remote_only'):
                    if valid:
                        self.assertEqual(runner.verify_expected_cents(manifest,folder),1)
                    else:
                        with self.assertRaisesRegex(ValueError,'expected_cents differs'):
                            runner.verify_expected_cents(manifest,folder)


if __name__ == '__main__':
    unittest.main()
