"""Tiny synthetic ONNX graph checks; run on GitHub with pinned ONNX/ORT."""
import copy
import unittest

import numpy as np
import onnx
import onnxruntime as ort
from onnx import helper, numpy_helper, TensorProto

from tools.basic_pitch_recent_normalization import MINIMUM, RANGE, LOG_POWER, OFFSET, rewrite_normalization


def fixture():
    nodes = [
        helper.make_node('ReduceMin', [LOG_POWER], [MINIMUM], name=MINIMUM, axes=[1, 2], keepdims=0),
        helper.make_node('Reshape', [MINIMUM, 'scalar_shape'], ['min3'], name='reshape_min'),
        helper.make_node('Sub', [LOG_POWER, 'min3'], [OFFSET], name='offset'),
        helper.make_node('ReduceMax', [OFFSET], [RANGE], name=RANGE, axes=[1, 2], keepdims=0),
        helper.make_node('Reshape', [RANGE, 'scalar_shape'], ['width3'], name='reshape_width'),
        helper.make_node('Div', [OFFSET, 'width3'], ['ratio'], name='divide'),
        helper.make_node('Equal', ['width3', 'zero'], ['flat'], name='is_flat'),
        helper.make_node('Where', ['flat', 'zero', 'ratio'], ['normalized'], name='divide_no_nan')]
    graph = helper.make_graph(nodes, 'synthetic_log_power',
        [helper.make_tensor_value_info(LOG_POWER, TensorProto.FLOAT, [None, 172, 3])],
        [helper.make_tensor_value_info('normalized', TensorProto.FLOAT, [None, 172, 3])],
        [numpy_helper.from_array(np.array([-1, 1, 1], dtype=np.int64), 'scalar_shape'),
         numpy_helper.from_array(np.array(0, dtype=np.float32), 'zero')])
    return helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=10)


class NormalizationGraphTests(unittest.TestCase):
    def evaluate(self, original, recent, values):
        model = rewrite_normalization(original, recent)
        options = ort.SessionOptions(); options.intra_op_num_threads = 1; options.inter_op_num_threads = 1
        session = ort.InferenceSession(model.SerializeToString(), sess_options=options, providers=['CPUExecutionProvider'])
        return session.run(['normalized', MINIMUM, RANGE], {LOG_POWER: values})

    def test_direct_arithmetic_and_old_extrema_no_longer_control_tail(self):
        values = np.random.default_rng(8).uniform(-10, 0, (2, 172, 3)).astype(np.float32)
        values[:, 0, 0] = -200; values[:, 2, 2] = 100
        original = fixture(); before = original.SerializeToString()
        for recent in (False, True):
            normalized, minimum, width = self.evaluate(original, recent, values)
            region = values[:, 144:172] if recent else values
            low = region.min(axis=(1, 2))
            span = region.max(axis=(1, 2)) - low
            expected = (values - low[:, None, None]) / span[:, None, None]
            np.testing.assert_array_equal(minimum, low)
            np.testing.assert_allclose(width, span, rtol=1e-7)
            np.testing.assert_allclose(normalized, expected, rtol=1e-6)
        self.assertEqual(original.SerializeToString(), before)
        changed = values.copy(); changed[:, :144] *= 5
        old_tail = self.evaluate(original, True, values)[0][:, 144:]
        np.testing.assert_array_equal(old_tail, self.evaluate(original, True, changed)[0][:, 144:])
        self.assertFalse(np.array_equal(self.evaluate(original, False, values)[0][:, 144:],
                                       self.evaluate(original, False, changed)[0][:, 144:]))

    def test_flat_windows_are_finite_zero_and_original_initializers_preserved(self):
        original = fixture()
        for recent in (False, True):
            actual, low, width = self.evaluate(original, recent, np.full((1, 172, 3), -100, dtype=np.float32))
            np.testing.assert_array_equal(actual, np.zeros_like(actual))
            self.assertEqual(width.tolist(), [0])
            model = rewrite_normalization(original, recent)
            after = {v.name: v.SerializeToString() for v in model.graph.initializer}
            for value in original.graph.initializer:
                self.assertEqual(after[value.name], value.SerializeToString())

    def test_unexpected_reduction_fails_closed(self):
        original = fixture()
        mutated = copy.deepcopy(original)
        mutated.graph.node[0].input[0] = 'different_input'
        with self.assertRaises(ValueError): rewrite_normalization(mutated, True)
        mutated = copy.deepcopy(original)
        del mutated.graph.node[0]
        with self.assertRaises(ValueError): rewrite_normalization(mutated, True)


if __name__ == '__main__': unittest.main()
