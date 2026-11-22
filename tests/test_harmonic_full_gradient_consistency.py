"""Shared-parameter gradient regression; no recorded inputs or local model fit."""
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


class FullGradientSpecTests(unittest.TestCase):
    def test_only_gradient_policy_changes_from_failed_fit(self):
        root = Path(__file__).resolve().parents[1]/'docs/recovery'
        old = json.loads((root/'harmonic-grid-consistency-20261121.json').read_text())
        new = json.loads((root/'harmonic-full-gradient-consistency-20261122.json').read_text())
        for key in ('mixture_and_clock_settings', 'harmonic_parameters', 'references',
                    'input_releases', 'datasets', 'gates', 'training_plan_identity',
                    'model_parameters', 'objective', 'baseline', 'prospective_comparison'):
            self.assertEqual(new[key], old[key], key)
        self.assertEqual(new['training_grid_consistency'], grid.FULL_GRADIENT_CONSISTENCY)
        changed = {k for k in grid.GRID_CONSISTENCY
                   if grid.GRID_CONSISTENCY[k] != grid.FULL_GRADIENT_CONSISTENCY[k]}
        self.assertEqual(changed, {'name', 'teacher'})

    def test_configuration_rejects_unfrozen_changes(self):
        for mode in (grid.GRID_CONSISTENCY, grid.FULL_GRADIENT_CONSISTENCY):
            grid.validate_consistency(mode)
            for changed in (dict(mode, weight=.5), dict(mode, shift_rows=-1),
                            dict(mode, teacher='fixed independent teacher'), {}):
                with self.assertRaises(ValueError):
                    grid.validate_consistency(changed)


@unittest.skipUnless(find_spec('torch'), 'Pinned CPU Torch checks run on GitHub')
class FullGradientTests(unittest.TestCase):
    def test_both_logit_gradients_and_excluded_edges(self):
        import torch
        original = torch.zeros(2, 53, dtype=torch.float64, requires_grad=True)
        shifted = torch.zeros_like(original, requires_grad=True)
        with torch.no_grad():
            original[:, -1] = 99
            shifted[:, 0] = -99
            shifted[0, 1] = .5
            shifted[1, 52] = 2
        loss = grid.grid_consistency_loss(original, shifted, full_gradient=True)
        self.assertAlmostEqual(float(loss.detach()), 1.625/104, places=14)
        loss.backward()
        self.assertTrue(torch.equal(original.grad[:, :-1], -shifted.grad[:, 1:]))
        self.assertEqual(float(original.grad[:, -1].abs().sum()), 0)
        self.assertEqual(float(shifted.grad[:, 0].abs().sum()), 0)
        self.assertAlmostEqual(float(original.grad[0, 0]), -.5/104, places=14)
        self.assertAlmostEqual(float(original.grad[1, 51]), -1/104, places=14)

    def test_shared_weight_gradient_matches_actual_objective_and_descends(self):
        import torch

        def objective(w, full):
            return grid.grid_consistency_loss((2*w).expand(1, 53), w.expand(1, 53),
                                               full_gradient=full)

        for initial in (.5, 2.):  # Quadratic and linear Huber regions.
            w = torch.tensor(initial, dtype=torch.float64, requires_grad=True)
            finite = float((objective(w+1e-6, True)-objective(w-1e-6, True)).detach())/2e-6
            full = float(torch.autograd.grad(objective(w, True), w)[0])
            semi = float(torch.autograd.grad(objective(w, False), w)[0])
            self.assertAlmostEqual(full, finite, places=8)
            self.assertAlmostEqual(semi, -finite, places=8)
        finals = {}
        for full in (False, True):
            w = torch.tensor(.5, dtype=torch.float64, requires_grad=True)
            for _ in range(20):
                gradient, = torch.autograd.grad(objective(w, full), w)
                with torch.no_grad():
                    w -= .1*gradient
            finals[full] = float(objective(w, True).detach())
        self.assertGreater(finals[False], .125)
        self.assertLess(finals[True], .002)

    def test_training_uses_full_gradient_and_persists_distinct_configuration(self):
        import torch
        rng = np.random.default_rng(7)
        raw = rng.normal(size=(9, 53, 62)).astype(np.float32)
        features, truth = raw.reshape(9, -1), raw[:, :, 0] > .5
        params = dict(context.SETWISE_PARAMS, epochs=3, batch_size=4)
        mode = grid.FULL_GRADIENT_CONSISTENCY
        with patch.object(runner, 'remote_only'), redirect_stdout(io.StringIO()):
            with patch.object(runner, 'grid_consistency_loss', wraps=grid.grid_consistency_loss) as loss:
                model, fit = runner.fit_model(features, truth, model_params=params,
                                              grid_consistency=mode)
            self.assertEqual(loss.call_count, 9)
            self.assertTrue(all(call.kwargs == {'full_gradient': True} for call in loss.call_args_list))
            self.assertEqual(fit['training_grid_consistency'], mode)
            self.assertEqual(fit['optimizer_steps'], 9)
            self.assertEqual(fit['parameter_count'], 14465)
            self.assertEqual(fit['fits'], 1)
            self.assertFalse(fit['held_out_used'])
            np.testing.assert_allclose(fit['loss_curve'], np.array(fit['supervised_loss_curve'])
                                       + np.array(fit['consistency_loss_curve']), rtol=2e-7)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'model.pt'
                runner.save_model(path, model, context.HarmonicFeatures(), model_params=params,
                                  grid_consistency=mode)
                saved = torch.load(path, map_location='cpu', weights_only=True)
                self.assertEqual(saved['training_grid_consistency'], mode)
                restored = context.make_network()
                restored.load_state_dict(saved['state_dict'])
                recovered = context.HarmonicContextModel(saved['mean'].numpy(),
                    saved['scale'].numpy(), restored, saved['cutoff'])
                np.testing.assert_array_equal(recovered.activity(features), model.activity(features))


if __name__ == '__main__':
    unittest.main()
