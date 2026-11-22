"""Small synthetic report-gate tests; no model or audio execution."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.basic_pitch_cached_diagnosis import decode_cached
from tools.portable_neural_lab import crop_identity


class CropIdentityTests(unittest.TestCase):
    def test_activation_and_event_changes_fail_independently(self):
        # A value straddling the decoder threshold can change MIDI despite
        # remaining inside the numerical tolerance. Both gates are required.
        cached=dict(note=np.zeros((4,88),dtype=np.float32),onset=np.zeros((4,88),dtype=np.float32),
                    frames=np.array([[i,0,0,640*(i+1)] for i in range(4)]))
        cached['note'][0,0]=np.float32(0.3)-np.float32(2e-7)
        cached['onset'][0,0]=1
        original,opened=decode_cached(cached['note'],cached['onset'])
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'summary.json').write_text(json.dumps(dict(paired_identity_pass=True,source_samples=2560,frames=4)))
            (folder/'frames.tsv').write_text('frame\tsource_end\n'+''.join(f'{i}\t{640*(i+1)}\n' for i in range(4)))
            cached['note'].tofile(folder/'notes.f32');cached['onset'].tofile(folder/'onsets.f32')
            self.assertTrue(crop_identity(folder,cached,original,opened,2560)['passed'])
            # A legacy or merely close full/crop result cannot certify the new
            # corrected adapter, even when the cached decoder agrees exactly.
            self.assertFalse(crop_identity(folder,cached,original,opened,2560,corrected=True)['passed'])
            summary=dict(paired_identity_pass=True,source_samples=2560,frames=4,
                         corrected_temporal_contract=True,readouts_bit_identical=True)
            (folder/'summary.json').write_text(json.dumps(summary))
            self.assertTrue(crop_identity(folder,cached,original,opened,2560,corrected=True)['passed'])
            summary['readouts_bit_identical']=False
            (folder/'summary.json').write_text(json.dumps(summary))
            self.assertFalse(crop_identity(folder,cached,original,opened,2560,corrected=True)['passed'])
            changed=cached['note'].copy();changed[0,0]+=np.float32(4e-7);changed.tofile(folder/'notes.f32')
            report=crop_identity(folder,cached,original,opened,2560)
            self.assertTrue(report['gates']['cached_note_error'])
            self.assertFalse(report['gates']['cached_generated_sequence'])
            self.assertFalse(report['passed'])
            changed=cached['note'].copy();changed[3,1]=0.001;changed.tofile(folder/'notes.f32')
            report=crop_identity(folder,cached,original,opened,2560)
            self.assertTrue(report['gates']['cached_generated_sequence'])
            self.assertFalse(report['gates']['cached_note_error'])
            self.assertFalse(report['passed'])


if __name__=='__main__': unittest.main()
