"""Synthetic alignment/gradient checks; recorded fitting remains GitHub-only."""
from contextlib import redirect_stdout
from importlib.util import find_spec
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import harmonic_context_learning as context
from tools import harmonic_grid_consistency as grid
from tools import portable_harmonic_context_learning as runner


class GridSpecTests(unittest.TestCase):
    def test_original_inputs_network_plans_and_gates_remain_fixed(self):
        root = Path(__file__).resolve().parents[1]/'docs/recovery'
        base = json.loads((root/'harmonic-setwise-learning-20261121.json').read_text())
        spec = json.loads((root/'harmonic-grid-consistency-20261121.json').read_text())
        for key in ('mixture_and_clock_settings', 'harmonic_parameters', 'references',
                    'input_releases', 'datasets', 'gates', 'training_plan_identity',
                    'model_parameters', 'objective'):
            self.assertEqual(spec[key], base[key], key)
        self.assertEqual(spec['training_grid_consistency'], grid.GRID_CONSISTENCY)


@unittest.skipUnless(find_spec('torch'), 'Pinned CPU Torch checks run on GitHub')
class GridConsistencyTests(unittest.TestCase):
    def test_direction_zero_fill_and_no_wrap_or_mutation(self):
        import torch
        original = torch.arange(2*62*53, dtype=torch.float64).reshape(2, 62, 53)
        before = original.clone()
        shifted = grid.shifted_grid(original)
        self.assertEqual(shifted.dtype, original.dtype)
        self.assertEqual(shifted.device, original.device)
        self.assertTrue(torch.equal(shifted[:, :, 1:], original[:, :, :-1]))
        self.assertTrue(torch.equal(shifted[:, :, 0], torch.zeros_like(original[:, :, 0])))
        shifted.fill_(0)
        self.assertTrue(torch.equal(original, before))

    def test_overlap_formula_excluded_edges_and_stopped_teacher(self):
        import torch
        teacher = torch.zeros(2, 53, dtype=torch.float64, requires_grad=True)
        student = torch.zeros(2, 53, dtype=torch.float64, requires_grad=True)
        with torch.no_grad():
            teacher[:, -1] = 99  # Dropped input row has no consistency target.
            student[:, 0] = -99  # Mean-filled row has no consistency target.
            student[0, 1] = .5   # Huber quadratic part: .125.
            student[1, 52] = 2   # Huber linear part: 1.5.
        loss = grid.grid_consistency_loss(teacher, student)
        self.assertAlmostEqual(float(loss.detach()), 1.625/104, places=14)
        loss.backward()
        self.assertIsNone(teacher.grad)
        self.assertEqual(float(student.grad[:, 0].abs().sum()), 0)
        self.assertAlmostEqual(float(student.grad[0, 1]), .5/104, places=14)
        self.assertAlmostEqual(float(student.grad[1, 52]), 1/104, places=14)
        shifted = torch.cat((torch.zeros(2, 1), teacher.detach()[:, :-1]), dim=1)
        self.assertEqual(float(grid.grid_consistency_loss(teacher, shifted)), 0)

    def test_shape_errors_fail_before_broadcast(self):
        import torch
        for shape in ((2, 62, 52), (0, 62, 53), (2, 0, 53), (2, 53)):
            with self.assertRaises(ValueError):
                grid.shifted_grid(torch.zeros(shape))
        for left, right in (((2, 52), (2, 52)), ((0, 53), (0, 53)),
                            ((2, 53), (1, 53)), ((53,), (53,))):
            with self.assertRaises(ValueError):
                grid.grid_consistency_loss(torch.zeros(left), torch.zeros(right))

    def test_one_fit_same_steps_two_forwards_and_persisted_inference(self):
        import torch
        rng = np.random.default_rng(7)
        raw = rng.normal(size=(9, 53, 62)).astype(np.float32)
        features, truth = raw.reshape(9, -1), raw[:, :, 0] > .5
        params = dict(context.SETWISE_PARAMS, epochs=3, batch_size=4)
        with patch.object(runner, 'remote_only'), redirect_stdout(io.StringIO()):
            with patch.object(runner, 'setwise_loss', wraps=context.setwise_loss) as supervised, \
                 patch.object(runner, 'shifted_grid', wraps=grid.shifted_grid) as shift:
                model, fit = runner.fit_model(features, truth, model_params=params,
                                              grid_consistency=grid.GRID_CONSISTENCY)
            self.assertEqual(supervised.call_count, 9)
            self.assertEqual(shift.call_count, 9)
            self.assertEqual(fit['optimizer_steps'], 9)
            self.assertEqual(fit['training_forwards_per_step'], 2)
            self.assertEqual(fit['parameter_count'], 14465)
            self.assertEqual(fit['fits'], 1)
            self.assertFalse(fit['held_out_used'])
            np.testing.assert_allclose(fit['loss_curve'], np.array(fit['supervised_loss_curve'])
                                       + np.array(fit['consistency_loss_curve']), rtol=2e-7)
            np.testing.assert_allclose(model.mean, raw.mean(axis=(0, 1)), rtol=1e-5, atol=1e-7)
            model.cutoff = .7
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'model.pt'
                runner.save_model(path, model, context.HarmonicFeatures(), model_params=params,
                                  grid_consistency=grid.GRID_CONSISTENCY)
                saved = torch.load(path, map_location='cpu', weights_only=True)
                self.assertEqual(saved['training_grid_consistency'], grid.GRID_CONSISTENCY)
                self.assertEqual(saved['model_parameters'], params)
                restored = context.make_network()
                restored.load_state_dict(saved['state_dict'])
                recovered = context.HarmonicContextModel(saved['mean'].numpy(),
                    saved['scale'].numpy(), restored, saved['cutoff'])
                np.testing.assert_array_equal(recovered.activity(features), model.activity(features))


if __name__ == '__main__':
    unittest.main()
