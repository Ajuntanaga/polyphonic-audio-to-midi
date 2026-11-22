import os
from types import SimpleNamespace
import unittest

from tools.basic_pitch_flat_normalization import (POWER_SUFFIX, NORMALIZED_SUFFIX,
    SPECTRAL_SHAPE, locate_boundary, guard_graph, checked_pair, CorrectedBackend)


class FlatNormalizationTest(unittest.TestCase):
    def test_boundary_requires_unique_expected_operators(self):
        nodes = [SimpleNamespace(name='model'+POWER_SUFFIX, op='Square'),
                 SimpleNamespace(name='model'+NORMALIZED_SUFFIX, op='Reshape')]
        self.assertEqual(locate_boundary(SimpleNamespace(node=nodes)), tuple(n.name for n in nodes))
        for values in (nodes[:1], nodes+nodes[:1], [nodes[0], SimpleNamespace(name=nodes[1].name, op='Div')]):
            with self.assertRaises(ValueError):
                locate_boundary(SimpleNamespace(node=values))

    def test_corrected_pair_accepts_note_and_onset_without_contour(self):
        import numpy as np
        values = {key: np.full((1, 172, 88), level, np.float32)
                  for key, level in [('note', .25), ('onset', .75)]}
        note, onset = checked_pair(values)
        np.testing.assert_array_equal(note, values['note'][0])
        np.testing.assert_array_equal(onset, values['onset'][0])

    def test_corrected_pair_rejects_invalid_outputs(self):
        import numpy as np
        valid = {key: np.zeros((1, 172, 88), np.float32) for key in ('note', 'onset')}
        for values in ({'note': valid['note']}, dict(valid, contour=valid['note']),
                       dict(valid, note=np.zeros((172, 88), np.float32)),
                       dict(valid, note=np.full((1, 172, 88), np.nan)),
                       dict(valid, onset=np.full((1, 172, 88), 1.1))):
            with self.assertRaises(ValueError):
                checked_pair(values)

    @unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true'
        and os.environ.get('GITHUB_REPOSITORY') == 'Ajuntanaga/m3-offload',
        'TensorFlow execution only on the authorized GitHub worker')
    def test_corrected_backend_warmup_and_prediction_use_two_output_contract(self):
        import numpy as np
        import tensorflow as tf
        class PairModel:
            def __call__(self, signal):
                self_shape = tuple(signal.shape)
                if self_shape != (1, 43844, 1):
                    raise ValueError('Wrong input shape')
                return {'note': tf.fill((1, 172, 88), .25),
                        'onset': tf.fill((1, 172, 88), .75)}
        backend = CorrectedBackend(PairModel(), tf)
        note, onset = backend.predict(np.zeros(43844, np.float32))
        np.testing.assert_array_equal(note, np.full((172, 88), .25, np.float32))
        np.testing.assert_array_equal(onset, np.full((172, 88), .75, np.float32))

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
