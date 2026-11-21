"""Tiny synthetic loss checks; recorded training remains on GitHub CPU only."""
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
from tools import portable_harmonic_context_learning as runner


class CompleteSetSpecTests(unittest.TestCase):
    def test_only_objective_changes_and_gates_remain_fixed(self):
        root = Path(__file__).resolve().parents[1]
        old = json.loads((root/'docs/recovery/harmonic-context-learning-20261121.json').read_text())
        new = json.loads((root/'docs/recovery/harmonic-complete-set-learning-20261121.json').read_text())
        self.assertEqual({k for k in context.MODEL_PARAMS
                          if context.MODEL_PARAMS[k] != context.COMPLETE_SET_PARAMS[k]}, {'loss'})
        self.assertEqual(set(context.MODEL_PARAMS), set(context.COMPLETE_SET_PARAMS))
        for key in ('mixture_and_clock_settings', 'harmonic_parameters', 'references',
                    'input_releases', 'datasets', 'gates'):
            self.assertEqual(new[key], old[key], key)
        self.assertEqual(new['model_parameters'], context.COMPLETE_SET_PARAMS)


@unittest.skipUnless(find_spec('torch'), 'Pinned CPU torch checks run on GitHub')
class CompleteSetLossTests(unittest.TestCase):
    def test_formula_and_gradient_focus_on_worst_true_and_false(self):
        import torch
        from torch.nn import functional as F
        logits = torch.tensor([[2., -1., 1., -2.]], requires_grad=True)
        truth = torch.tensor([[1., 1., 0., 0.]])
        base = F.binary_cross_entropy_with_logits(logits, truth)
        loss = context.complete_set_loss(logits, truth)
        self.assertAlmostEqual(float(loss-base), float(F.softplus(torch.tensor(1.))), places=6)
        extra = torch.autograd.grad(loss-base, logits)[0]
        self.assertEqual(float(extra[0, 0]), 0)
        self.assertEqual(float(extra[0, 3]), 0)
        self.assertLess(float(extra[0, 1]), 0)
        self.assertGreater(float(extra[0, 2]), 0)
        # Moving both hard pitches in the desired direction reduces this loss.
        corrected = logits.detach()+torch.tensor([[0., .2, -.2, 0.]])
        self.assertLess(float(context.complete_set_loss(corrected, truth)), float(loss))

    def test_silence_and_all_true_use_only_the_present_polarity(self):
        import torch
        from torch.nn import functional as F
        logits = torch.tensor([[-2., 1., 0.]], requires_grad=True)
        truth = torch.zeros_like(logits)
        loss = context.complete_set_loss(logits, truth)
        base = F.binary_cross_entropy_with_logits(logits, truth)
        self.assertAlmostEqual(float(loss-base), float(F.softplus(torch.tensor(1.))), places=6)
        self.assertTrue(torch.all(torch.autograd.grad(loss, logits)[0] > 0))
        # Symmetry also exercises the no-negative case without an infinity mask.
        self.assertAlmostEqual(float(loss), float(context.complete_set_loss(-logits, 1-truth)), places=6)

    def test_pitch_order_batch_reduction_ties_and_extremes(self):
        import torch
        logits = torch.tensor([[1000., -1000., 0., 0.], [-1., -1., -1., -1.]], requires_grad=True)
        truth = torch.tensor([[0., 1., 1., 0.], [0., 0., 0., 0.]])
        loss = context.complete_set_loss(logits, truth)
        separate = sum(context.complete_set_loss(logits[i:i+1], truth[i:i+1]) for i in range(2))/2
        perm = [2, 0, 3, 1]
        self.assertTrue(torch.allclose(loss, separate))
        self.assertTrue(torch.allclose(loss, context.complete_set_loss(logits[:, perm], truth[:, perm])))
        loss.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())
        self.assertTrue(torch.allclose(logits.grad[1], logits.grad[1, 0].expand(4)))

    def test_invalid_target_or_empty_matrix_is_rejected(self):
        import torch
        for logits, target in ((torch.zeros(0, 4), torch.zeros(0, 4)),
                               (torch.zeros(2, 4), torch.zeros(2, 3)),
                               (torch.zeros(2, 4), torch.full((2, 4), .5))):
            with self.assertRaises(ValueError):
                context.complete_set_loss(logits, target)

    def test_new_fit_uses_and_persists_the_objective(self):
        import torch
        rng = np.random.default_rng(7)
        raw = rng.normal(size=(32, 53, 62)).astype(np.float32)
        truth = raw[:, :, 0] > .5
        features = raw.reshape(32, -1)
        params = dict(context.COMPLETE_SET_PARAMS, epochs=10)
        with patch.object(runner, 'remote_only'), redirect_stdout(io.StringIO()):
            with patch.object(runner, 'complete_set_loss', wraps=context.complete_set_loss) as criterion:
                model, fit = runner.fit_model(features, truth, model_params=params)
            self.assertEqual(criterion.call_count, 10)
            self.assertEqual(fit['objective'], params['loss'])
            self.assertLess(fit['final_loss'], fit['loss_curve'][0])
            self.assertFalse(fit['held_out_used'])
            model.cutoff = .7
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'model.pt'
                runner.save_model(path, model, context.HarmonicFeatures(), model_params=params)
                saved = torch.load(path, map_location='cpu', weights_only=True)
                self.assertEqual(saved['model_parameters'], params)
                self.assertEqual(saved['cutoff'], .7)
                restored = context.make_network()
                restored.load_state_dict(saved['state_dict'])
                recovered = context.HarmonicContextModel(saved['mean'].numpy(),
                    saved['scale'].numpy(), restored, saved['cutoff'])
                np.testing.assert_array_equal(recovered.activity(features), model.activity(features))


if __name__ == '__main__':
    unittest.main()
