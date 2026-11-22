import json
import unittest
import numpy as np

from tools.basic_pitch_onnx_numerics import array_difference, choose_probes


class NumericsTest(unittest.TestCase):
    def test_layout_and_nonfinite_fail_closed(self):
        self.assertFalse(array_difference(np.zeros((1, 3)), np.zeros((3, 1)))['comparable'])
        row = array_difference(np.array([np.nan]), np.array([0.]))
        self.assertFalse(row['comparable'])
        self.assertEqual(row['nonfinite_kind_mismatches'], 1)
        self.assertIsNone(row['common_finite_max_absolute'])
        row = array_difference(np.array([1., 4.]), np.array([2., 1.]))
        self.assertEqual((row['max_absolute'], row['max_index'], row['unequal']), (3., [1], 2))
        self.assertEqual(json.loads(json.dumps(row))['max_index'], [1])

    def test_masked_nonfinite_observations_are_retained_not_passed(self):
        a = np.array([np.nan, np.inf, -np.inf, 1., 2.])
        b = np.array([np.nan, np.inf, np.inf, 1., 4.])
        row = array_difference(a, b)
        self.assertFalse(row['comparable'])
        self.assertEqual(row['reference_nonfinite'], dict(finite=2, nan=1, positive_infinity=1, negative_infinity=1))
        self.assertEqual(row['nonfinite_kind_mismatches'], 1)
        self.assertEqual(row['common_finite_max_absolute'], 2.)
        json.dumps(row, allow_nan=False)
        self.assertFalse(array_difference(np.array([]), np.array([]))['comparable'])

    def test_exact_name_matching_and_bounds(self):
        row = dict(name='signal:0', dtype='float32', op='Relu', shape=[1, 3])
        self.assertEqual(choose_probes([row], {'signal:0'}), [row])
        for names, count, elements in (({'other:0'}, 256, 20), ({'signal:0'}, 0, 20), ({'signal:0'}, 256, 2)):
            with self.assertRaises(ValueError):
                choose_probes([row], names, count, elements)


if __name__ == '__main__':
    unittest.main()
