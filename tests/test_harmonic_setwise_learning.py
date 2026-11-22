"""Synthetic setwise objective checks; no recorded processing or local Torch install."""
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


class SetwiseSpecTests(unittest.TestCase):
    def test_only_loss_changes_and_existing_gates_and_sources_are_preserved(self):
        root = Path(__file__).resolve().parents[1]/'docs/recovery'
        previous = json.loads((root/'harmonic-complete-set-learning-20261121.json').read_text())
        spec = json.loads((root/'harmonic-setwise-learning-20261121.json').read_text())
        self.assertEqual(set(context.SETWISE_PARAMS), set(context.COMPLETE_SET_PARAMS))
        self.assertEqual({k for k in context.SETWISE_PARAMS
            if context.SETWISE_PARAMS[k] != context.COMPLETE_SET_PARAMS[k]}, {'loss'})
        for key in ('mixture_and_clock_settings', 'harmonic_parameters', 'references',
                    'input_releases', 'datasets', 'gates', 'training_plan_identity'):
            self.assertEqual(spec[key], previous[key], key)
        self.assertEqual(spec['model_parameters'], context.SETWISE_PARAMS)
        self.assertEqual(spec['objective']['name'], context.SETWISE_PARAMS['loss'])


@unittest.skipUnless(find_spec('torch'), 'Pinned CPU Torch checks run on GitHub')
class SetwiseLossTests(unittest.TestCase):
    def test_formula_and_extra_gradients_reach_non_worst_pitches(self):
        import torch
        from torch.nn import functional as F
        logits = torch.tensor([[2., -1., 1., -2.]], dtype=torch.float64, requires_grad=True)
        truth = torch.tensor([[1., 1., 0., 0.]], dtype=torch.float64)
        extra = context.setwise_loss(logits, truth)-F.binary_cross_entropy_with_logits(logits, truth)
        expected = 2*torch.log1p(torch.exp(torch.tensor(1., dtype=torch.float64))
                                + torch.exp(torch.tensor(-2., dtype=torch.float64)))
        self.assertAlmostEqual(float(extra), float(expected), places=12)
        gradient = torch.autograd.grad(extra, logits)[0]
        self.assertTrue(torch.all(gradient[:, :2] < 0))
        self.assertTrue(torch.all(gradient[:, 2:] > 0))
        self.assertGreater(abs(float(gradient[0, 1])), abs(float(gradient[0, 0])))
        self.assertGreater(float(gradient[0, 2]), float(gradient[0, 3]))

    def test_additional_false_pitch_is_penalized_even_with_same_worst(self):
        import torch
        from torch.nn import functional as F
        truth = torch.tensor([[1., 0., 0.]])
        one = torch.tensor([[3., 1., -5.]])
        two = torch.tensor([[3., 1., .9]])
        additional = lambda z: context.setwise_loss(z, truth)-F.binary_cross_entropy_with_logits(z, truth)
        self.assertGreater(float(additional(two)), float(additional(one)))
        corrected = torch.tensor([[3., .8, .7]])
        self.assertLess(float(context.setwise_loss(corrected, truth)), float(context.setwise_loss(two, truth)))

    def test_empty_polarity_silence_all_true_and_zero_logits(self):
        import torch
        from torch.nn import functional as F
        logits = torch.zeros((1, 3), dtype=torch.float64, requires_grad=True)
        truth = torch.zeros_like(logits)
        loss = context.setwise_loss(logits, truth)
        extra = loss-F.binary_cross_entropy_with_logits(logits, truth)
        self.assertAlmostEqual(float(extra), np.log(4), places=12)
        self.assertTrue(torch.all(torch.autograd.grad(loss, logits)[0] > 0))
        self.assertEqual(float(loss), float(context.setwise_loss(-logits, 1-truth)))
        # Two positives, one negative: log(1+2)+log(1+1), with no polarity averaging.
        mixed = torch.tensor([[1., 1., 0.]], dtype=torch.float64)
        self.assertAlmostEqual(float(context.setwise_loss(logits, mixed)
            - F.binary_cross_entropy_with_logits(logits, mixed)), np.log(3)+np.log(2), places=12)

    def test_stability_permutation_batch_mean_and_ties(self):
        import torch
        logits = torch.tensor([[1000., -1000., 0., 0.], [-1., -1., -1., -1.]], requires_grad=True)
        truth = torch.tensor([[0., 1., 1., 0.], [0., 0., 0., 0.]])
        loss = context.setwise_loss(logits, truth)
        separate = sum(context.setwise_loss(logits[i:i+1], truth[i:i+1]) for i in range(2))/2
        permutation = [2, 0, 3, 1]
        self.assertTrue(torch.isfinite(loss))
        self.assertTrue(torch.allclose(loss, separate))
        self.assertTrue(torch.allclose(loss, context.setwise_loss(logits[:, permutation], truth[:, permutation])))
        loss.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())
        self.assertTrue(torch.allclose(logits.grad[1], logits.grad[1, 0].expand(4)))

    def test_invalid_targets_or_matrices_are_rejected(self):
        import torch
        for logits, targets in ((torch.zeros(0, 4), torch.zeros(0, 4)),
                                (torch.zeros(2, 4), torch.zeros(2, 3)),
                                (torch.zeros(2, 4), torch.full((2, 4), .5)),
                                (torch.zeros(4), torch.zeros(4))):
            with self.assertRaises(ValueError):
                context.setwise_loss(logits, targets)

    def test_fit_dispatch_and_persisted_model(self):
        import torch
        rng = np.random.default_rng(7)
        raw = rng.normal(size=(32, 53, 62)).astype(np.float32)
        truth = raw[:, :, 0] > .5
        features = raw.reshape(32, -1)
        params = dict(context.SETWISE_PARAMS, epochs=10)
        with patch.object(runner, 'remote_only'), redirect_stdout(io.StringIO()):
            with patch.object(runner, 'setwise_loss', wraps=context.setwise_loss) as criterion:
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
                restored = context.make_network()
                restored.load_state_dict(saved['state_dict'])
                recovered = context.HarmonicContextModel(saved['mean'].numpy(),
                    saved['scale'].numpy(), restored, saved['cutoff'])
                np.testing.assert_array_equal(recovered.activity(features), model.activity(features))


if __name__ == '__main__':
    unittest.main()
