from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.basic_pitch_onnx_export import (INPUT, INPUT_SHAPE, OUTPUTS, OUTPUT_SHAPE, checked_weights,
    compare_outputs, compare_streams, export_model, weight_fingerprint)


class ExactExportTest(unittest.TestCase):
    def test_checkpoint_validated_by_name_shape_dtype_and_finiteness(self):
        manifest = [dict(name='kernel:0', shape=[2], dtype='float32')]
        arrays = {'model_0': np.array([1, 2], np.float32), 'optimizer_0': np.array(3)}
        result = checked_weights(manifest, ['kernel:0'], arrays)
        arrays['model_0'][0] = 99
        self.assertEqual(result[0].tolist(), [1, 2])
        for names, values in [(['other:0'], arrays), (['kernel:0'], {}),
                (['kernel:0'], {'model_0': np.array([1, 2], np.float64)}),
                (['kernel:0'], {'model_0': np.array([1, np.nan], np.float32)}),
                (['kernel:0'], {'model_0': np.ones((1, 2), np.float32)})]:
            with self.assertRaises(ValueError):
                checked_weights(manifest, names, values)
        self.assertNotEqual(weight_fingerprint(manifest, result),
                            weight_fingerprint(manifest, [arrays['model_0']]))

    def test_tiny_threshold_crossing_rejects_even_inside_numeric_tolerance(self):
        before = {k: np.zeros(OUTPUT_SHAPE, np.float32) for k in ('note', 'onset')}
        after = {k: v.copy() for k, v in before.items()}
        before['note'][0, 0, 0] = np.nextafter(np.float32(.3), np.float32(0))
        after['note'][0, 0, 0] = np.float32(.3)
        before['onset'][0, 0, 0] = after['onset'][0, 0, 0] = .5
        result = compare_outputs(before, after, 1e-4)
        self.assertTrue(result['numerical_pass'])
        self.assertFalse(result['thresholds_identical'])
        self.assertFalse(result['decoder_events_identical'])
        self.assertFalse(result['parity_pass'])
        self.assertTrue(compare_outputs(before, before, 0)['parity_pass'])

    def test_invalid_probabilities_are_not_counted_as_parity(self):
        values = {k: np.zeros(OUTPUT_SHAPE, np.float32) for k in ('note', 'onset')}
        values['note'][0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            compare_outputs(values, values, 1e-4)

    def test_local_export_stops_before_loading_model_dependencies(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(RuntimeError):
                export_model(None, Path('must-not-create.onnx'))

    @unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true'
        and os.environ.get('GITHUB_REPOSITORY') == 'Ajuntanaga/m3-offload',
        'TensorFlow conversion runs only in the authorized GitHub CPU worker')
    def test_captured_constant_and_changed_weight_export_as_one_input(self):
        import tensorflow as tf
        import onnxruntime as ort

        class CapturedModel(tf.Module):
            def __init__(self):
                super().__init__()
                self.weight = tf.Variable(.2, dtype=tf.float32, name='weight')
                self.spectral = tf.constant(np.linspace(-1, 1, np.prod(OUTPUT_SHAPE),
                                                        dtype=np.float32).reshape(OUTPUT_SHAPE))

            @tf.function(input_signature=[tf.TensorSpec(INPUT_SHAPE, tf.float32)], autograph=False)
            def __call__(self, signal):
                excitation = .01 * tf.reduce_mean(signal)
                return dict(note=tf.sigmoid(self.spectral + self.weight + excitation),
                            onset=tf.sigmoid(self.spectral - self.weight + excitation))

        model = CapturedModel()
        signal = np.full(INPUT_SHAPE, .125, dtype=np.float32)
        hashes = []
        with tempfile.TemporaryDirectory() as directory:
            for i, weight in enumerate((.2, .6)):
                model.weight.assign(weight)
                before = model.weight.numpy().copy()
                reference = {key: value.numpy() for key, value in model(signal).items()}
                destination = Path(directory) / f'model-{i}.onnx'
                diagnostic = Path(directory) / f'model-{i}.json'
                result = export_model(model, destination, diagnostics_path=diagnostic)
                options = ort.SessionOptions()
                options.intra_op_num_threads = options.inter_op_num_threads = 1
                session = ort.InferenceSession(str(destination), options,
                                               providers=['CPUExecutionProvider'])
                self.assertEqual([v.name for v in session.get_inputs()], [INPUT])
                values = session.run(list(OUTPUTS.values()), {INPUT: signal})
                for key, converted in zip(OUTPUTS, values):
                    np.testing.assert_allclose(converted, reference[key], atol=1e-6, rtol=0)
                np.testing.assert_array_equal(model.weight.numpy(), before)
                detail = json.loads(diagnostic.read_text())
                self.assertEqual(detail['stage'], 'complete')
                self.assertGreaterEqual(len(detail['captures']), 2)
                self.assertEqual(len(detail['frozen_inputs']), 1)
                hashes.append(result['sha256'])
        self.assertNotEqual(*hashes)

    def test_stream_comparison_ignores_cpu_time_but_not_source_clock_or_decisions(self):
        a = dict(note=np.zeros((4, 88), np.float32), onset=np.zeros((4, 88), np.float32),
                 frames=np.array([[i, i*256, 1860+i//2*512, 8320+i//2*2240] for i in range(4)]))
        a['note'][:, 0] = .8
        events = dict(events=[dict(kind='on', note=21, frame=2, available_ns=10, emitted_ns=20)],
                      cleanup=dict(notes=[21]))
        changed = dict(events=[dict(events['events'][0], emitted_ns=500)], cleanup=dict(notes=[21]))
        self.assertTrue(compare_streams(a, a, events, changed, 0)['parity_pass'])
        changed['events'][0]['available_ns'] = 11
        self.assertFalse(compare_streams(a, a, events, changed, 0)['parity_pass'])
        changed['events'][0]['frame'] = 3
        with self.assertRaises(ValueError):
            compare_streams(a, a, events, changed, 0)


if __name__ == '__main__':
    unittest.main()
