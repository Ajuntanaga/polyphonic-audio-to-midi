import os
from types import SimpleNamespace
import unittest

from tools.basic_pitch_flat_normalization import (POWER_SUFFIX, NORMALIZED_SUFFIX,
    SPECTRAL_SHAPE, locate_boundary, guard_graph)


class FlatNormalizationTest(unittest.TestCase):
    def test_boundary_requires_unique_expected_operators(self):
        nodes = [SimpleNamespace(name='model'+POWER_SUFFIX, op='Square'),
                 SimpleNamespace(name='model'+NORMALIZED_SUFFIX, op='Reshape')]
        self.assertEqual(locate_boundary(SimpleNamespace(node=nodes)), tuple(n.name for n in nodes))
        for values in (nodes[:1], nodes+nodes[:1], [nodes[0], SimpleNamespace(name=nodes[1].name, op='Div')]):
            with self.assertRaises(ValueError):
                locate_boundary(SimpleNamespace(node=values))

    @unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true'
        and os.environ.get('GITHUB_REPOSITORY') == 'Ajuntanaga/m3-offload',
        'TensorFlow graph execution only on the authorized GitHub worker')
    def test_guard_zeroes_constant_power_and_preserves_nonconstant_bits(self):
        import numpy as np
        import tensorflow as tf
        graph = tf.Graph()
        with graph.as_default():
            power = tf.compat.v1.placeholder(tf.float32, SPECTRAL_SHAPE, name='power')
            normalized = tf.compat.v1.placeholder(tf.float32, SPECTRAL_SHAPE, name='normalized')
            output = tf.identity(normalized, name='downstream')
        old = graph.as_graph_def(add_shapes=True)
        unchanged = old.SerializeToString()
        updated, metadata = guard_graph(old, power.op.name, normalized.op.name)
        self.assertEqual(unchanged, old.SerializeToString())
        self.assertEqual(metadata['rewired_edges'], 1)
        wrapped = tf.compat.v1.wrap_function(lambda: tf.import_graph_def(updated, name=''), [])
        call = wrapped.prune([wrapped.graph.get_tensor_by_name(t.name) for t in (power, normalized)],
                             wrapped.graph.get_tensor_by_name(output.name))
        values = np.linspace(-1, 1, np.prod(SPECTRAL_SHAPE), dtype=np.float32).reshape(SPECTRAL_SHAPE)
        values_tensor = tf.convert_to_tensor(values)
        for level in (0., 1e-12, 1., 100.):
            p = np.full(SPECTRAL_SHAPE, level, np.float32)
            np.testing.assert_array_equal(call(tf.convert_to_tensor(p), values_tensor).numpy(),
                                          np.zeros_like(values))
            p.flat[-1] = (np.finfo(np.float32).tiny if level == 0.
                          else np.nextafter(p.flat[-1], np.float32(np.inf)))
            np.testing.assert_array_equal(call(tf.convert_to_tensor(p), values_tensor).numpy(), values)
        with self.assertRaisesRegex(ValueError, 'collision'):
            guard_graph(updated, power.op.name, normalized.op.name)


if __name__ == '__main__':
    unittest.main()
