import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from tools.controlled_descriptor_overlap import read_float_wave, write_float_wave
from tools.prepare_runtime_profile_clips import extract, sha256


class ExtractionTests(unittest.TestCase):
    def test_local_recorded_extraction_refused(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'false'}):
            with self.assertRaises(RuntimeError):
                extract({}, Path('/unused'), Path('/unused'))

    def test_synthetic_exact_samples_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            samples=np.arange(1000,dtype=np.float32)/1000
            wave=root/'raw.wav';write_float_wave(wave,1000,samples)
            entries=[]
            for i in range(91):
                entries.append(dict(segment_id=f'take{i}',raw_wave='raw.wav',
                    recorded_raw_wave_sha256=sha256(wave),sample_rate_hz=1000,
                    start_sample=300,end_sample=800,string=i%6,midi_note=52+(i//6)%5,
                    calibration_pass=1+i%3,label_index=i))
            with patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}):
                result=extract({'clips':entries},root,root/'clips')
            self.assertEqual(len(result['clips']),91)
            for c in result['clips']:
                rate, actual=read_float_wave(root/'clips'/c['clip'])
                np.testing.assert_array_equal(actual,samples[50:800])
                self.assertEqual((rate,c['labeled_begin'],c['labeled_end']),(1000,250,750))
                self.assertFalse(c['onset_verified'])


if __name__=='__main__': unittest.main()
