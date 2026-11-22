import json
import unittest
import numpy as np

from tools.basic_pitch_onnx_numerics import array_difference, choose_probes


class NumericsTest(unittest.TestCase):
    def test_layout_and_nonfinite_fail_closed(self):
        self.assertFalse(array_difference(np.zeros((1, 3)), np.zeros((3, 1)))['comparable'])
        with self.assertRaises(ValueError):
            array_difference(np.array([np.nan]), np.array([0.]))
        row = array_difference(np.array([1., 4.]), np.array([2., 1.]))
        self.assertEqual((row['max_absolute'], row['max_index'], row['unequal']), (3., [1], 2))
        self.assertEqual(json.loads(json.dumps(row))['max_index'], [1])

    def test_exact_name_matching_and_bounds(self):
        row = dict(name='signal:0', dtype='float32', op='Relu', shape=[1, 3])
        self.assertEqual(choose_probes([row], {'signal:0'}), [row])
        for names, count, elements in (({'other:0'}, 256, 20), ({'signal:0'}, 0, 20), ({'signal:0'}, 256, 2)):
            with self.assertRaises(ValueError):
                choose_probes([row], names, count, elements)


if __name__ == '__main__':
    unittest.main()
