import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from tools.basic_pitch_temporal_crop import compare_readout, crop_model, required_input_interval
from tools.portable_basic_pitch_temporal_crop import assess, run, validate_spec


class TemporalCropTest(unittest.TestCase):
    def test_dependency_includes_onset_note_path_and_right_padding(self):
        self.assertEqual([(r['required_start'],r['required_end']) for r in required_input_interval()],
                         [(163,167),(160,170),(157,172),(155,172),(154,172)])
        self.assertEqual(required_input_interval(163,165)[-1]['required_start'],153)

    def test_threshold_event_and_numeric_gates_are_independent(self):
        a = dict(note=np.zeros((2,88),np.float32), onset=np.zeros((2,88),np.float32))
        self.assertTrue(compare_readout(a,copy.deepcopy(a))['parity_pass'])
        b = copy.deepcopy(a)
        b['note'][0,0] = .00011
        self.assertFalse(compare_readout(a,b)['parity_pass'])
        a['note'][0,0] = .3-1e-6
        a['onset'][0,0] = .7
        b = copy.deepcopy(a)
        b['note'][0,0] = .3+1e-6
        result = compare_readout(a,b)
        self.assertTrue(result['numerical_pass'])
        self.assertFalse(result['thresholds_identical'])
        self.assertFalse(result['decoder_events_identical'])
        b['note'][0,0] = np.nan
        with self.assertRaises(ValueError):
            compare_readout(a,b)

    def test_frozen_limits_and_output_contract(self):
        spec = json.loads((Path(__file__).resolve().parents[1]/
            'docs/recovery/basic-pitch-temporal-crop-20261122.json').read_text())
        validate_spec(spec)
        for key,value in [('max_absolute',.001),('graph_modes',['cropped']),
                          ('crop_input_rows',[155,172]),('exposed_output_frames',[163,164]),
                          ('service_p99_limit_ns',21_000_000)]:
            changed = copy.deepcopy(spec)
            changed[key] = value
            with self.assertRaises(ValueError):
                validate_spec(changed)

    def test_four_pairs_required_and_runtime_does_not_accept_quality(self):
        row = dict(original_reference_parity=dict(parity_pass=True),
            cropped_vs_original=dict(parity_pass=True), source_availability_scores_identical=True,
            cropped=dict(timing=dict(inference_block_service_ns=dict(p99=20_000_000),
                queued_before_service_ns=dict(maximum=26_666_667))))
        data = {name: dict(weights={arm: copy.deepcopy(row) for arm in ('unmodified','adapted')})
                for name in ('ordinary','extended-middle')}
        result = assess(data, True)
        self.assertTrue(result['runtime_change_screen_pass'])
        self.assertFalse(result['promotion_accepted'])
        self.assertFalse(result['prior_adaptation_quality_pass'])
        self.assertIn('failed', result['prior_corrected_tensorflow_numerical_gate'])
        for key in ('original_reference_parity','cropped_vs_original'):
            changed = copy.deepcopy(data)
            changed['ordinary']['weights']['adapted'][key]['parity_pass'] = False
            self.assertFalse(assess(changed,True)['runtime_change_screen_pass'])
        self.assertFalse(assess(data,False)['runtime_change_screen_pass'])
        data['ordinary']['weights']['adapted']['cropped']['timing']['inference_block_service_ns']['p99'] += 1
        self.assertFalse(assess(data,True)['runtime_change_screen_pass'])
        del data['ordinary']['weights']['adapted']
        self.assertFalse(assess(data,True)['runtime_change_screen_pass'])

    def test_remote_guards_precede_model_and_path_access(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS':'false'}):
            with self.assertRaises(RuntimeError):
                run(Path('not-read'),Path('not-created'))
            with self.assertRaises(RuntimeError):
                crop_model(Path('not-read'),Path('not-created'))


if __name__ == '__main__':
    unittest.main()
