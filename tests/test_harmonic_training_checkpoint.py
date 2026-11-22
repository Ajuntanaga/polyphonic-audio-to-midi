"""Recovery identity and atomicity; all actual model execution stays on GitHub."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import harmonic_training_checkpoint as checkpoint
from tools import portable_harmonic_context_learning as runner
from tools import portable_harmonic_training_recovery as recovery


class RecoveryEnvelopeTests(unittest.TestCase):
    def test_execution_guard_precedes_files_and_model(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'absent'
            result = subprocess.run([sys.executable, '-m',
                'tools.portable_harmonic_training_recovery', '--execution-spec', 'absent',
                '--output', str(output)], capture_output=True, text=True,
                env={k: v for k, v in os.environ.items() if k != 'GITHUB_ACTIONS'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires GitHub Actions', result.stderr)
            self.assertFalse(output.exists())

    def test_original_scientific_spec_is_pinned_and_forwarded(self):
        root = Path(__file__).resolve().parents[1]
        execution = root/'docs/recovery/harmonic-training-recovery-20261122.json'
        output, resume = Path('unused-output'), Path('already-verified-training-state.pt')
        with patch.object(recovery, 'remote_only'), patch.object(recovery, 'run') as run:
            recovery.run_recovery(execution, output, resume)
        run.assert_called_once_with(root/recovery.EXECUTION['scientific_specification'],
            output, training_recovery=recovery.EXECUTION, resume_checkpoint=resume)
        with tempfile.TemporaryDirectory() as directory:
            changed = dict(recovery.EXECUTION, max_worker_minutes=240)
            path = Path(directory)/'changed.json'
            path.write_text(json.dumps(changed))
            with patch.object(recovery, 'remote_only'), patch.object(recovery, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'envelope mismatch'):
                    recovery.run_recovery(path, output)
                run.assert_not_called()

    def test_byte_identity_pins_shape_dtype_and_values(self):
        values = np.arange(12, dtype=np.float32).reshape(3, 4)
        actual = checkpoint.array_identity(values)
        self.assertEqual(actual['sha256'], hashlib.sha256(values.tobytes()).hexdigest())
        self.assertNotEqual(actual, checkpoint.array_identity(values.reshape(2, 6)))
        with self.assertRaisesRegex(ValueError, 'C-contiguous'):
            checkpoint.array_identity(values[:, ::2])


@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'Model execution stays on GitHub')
class CheckpointModelTests(unittest.TestCase):
    def setUp(self):
        self.features = np.random.default_rng(91).normal(size=(3, 53*302)).astype(np.float32)
        self.truth = np.zeros((3, 53), bool)
        self.truth[0, [3, 15]] = True
        self.truth[1, [21, 32, 44]] = True
        self.context = dict(source='synthetic-fixed-source', specification='synthetic-fixed-spec')

    def fit(self, **kwargs):
        return runner.fit_model(self.features, self.truth, runner.SETWISE_PARAMS,
            spectral_patches=runner.SPECTRAL_PATCHES, **kwargs)

    def assert_state_equal(self, left, right):
        import torch
        if isinstance(left, torch.Tensor):
            self.assertTrue(torch.equal(left, right))
        elif isinstance(left, dict):
            self.assertEqual(left.keys(), right.keys())
            for key in left:
                self.assert_state_equal(left[key], right[key])
        elif isinstance(left, (tuple, list)):
            self.assertEqual(len(left), len(right))
            for a, b in zip(left, right):
                self.assert_state_equal(a, b)
        else:
            self.assertEqual(left, right)

    def test_uninterrupted_checkpointed_and_resumed_are_exact(self):
        import torch
        plain_model, plain_fit = self.fit()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            whole, interrupted, resumed = (root/name for name in ('whole.pt', 'interrupted.pt', 'resumed.pt'))
            model, fit = self.fit(checkpoint_path=whole, checkpoint_context=self.context)
            np.testing.assert_array_equal(model.activity(self.features), plain_model.activity(self.features))
            self.assertEqual(fit['loss_curve'], plain_fit['loss_curve'])
            original_save = runner.save_training_checkpoint
            def interrupt_after_save(*args, **kwargs):
                original_save(*args, **kwargs)
                if len(args[7]) == 2:
                    raise InterruptedError('synthetic interruption after epoch 2')
            with patch.object(runner, 'save_training_checkpoint', side_effect=interrupt_after_save):
                with self.assertRaises(InterruptedError):
                    self.fit(checkpoint_path=interrupted, checkpoint_context=self.context)
            recovered, recovered_fit = self.fit(checkpoint_path=resumed,
                resume_checkpoint=interrupted, checkpoint_context=self.context)
            self.assertEqual(recovered_fit['recovery']['resumed_from_epoch'], 2)
            self.assertEqual(recovered_fit['recovery']['epochs_executed_this_invocation'], 78)
            self.assertEqual(recovered_fit['loss_curve'], plain_fit['loss_curve'])
            np.testing.assert_array_equal(recovered.activity(self.features), plain_model.activity(self.features))
            a = torch.load(whole, weights_only=True, map_location='cpu')
            b = torch.load(resumed, weights_only=True, map_location='cpu')
            for key in ('identity', 'network', 'optimizer', 'shuffle_rng', 'torch_rng',
                        'mean', 'scale', 'loss_curve', 'completed_epochs'):
                self.assert_state_equal(a[key], b[key])
            done, done_fit = self.fit(checkpoint_path=root/'done.pt',
                resume_checkpoint=resumed, checkpoint_context=self.context)
            self.assertEqual(done_fit['recovery']['epochs_executed_this_invocation'], 0)
            np.testing.assert_array_equal(done.activity(self.features), plain_model.activity(self.features))

            for change in ('source', 'features', 'truth', 'optimizer'):
                with self.subTest(change=change):
                    saved = torch.load(interrupted, weights_only=True, map_location='cpu')
                    if change == 'optimizer':
                        next(iter(saved['optimizer']['state'].values()))['step'] += 1
                    else:
                        key = 'context' if change == 'source' else change
                        saved['identity'][key] = {'changed': True}
                    bad = root/'bad.pt'
                    torch.save(saved, bad)
                    with self.assertRaises(ValueError):
                        self.fit(checkpoint_path=root/'rejected.pt', resume_checkpoint=bad,
                                 checkpoint_context=self.context)
            self.assertFalse((root/'rejected.pt').exists())

            prior = interrupted.read_bytes()
            network = model.network
            optimizer = torch.optim.Adam(network.parameters())
            generator = torch.Generator().manual_seed(42)
            with patch.object(torch, 'save', side_effect=OSError('synthetic partial write')):
                with self.assertRaises(OSError):
                    checkpoint.save_training_checkpoint(interrupted, network, optimizer,
                        generator, model.mean, model.scale, a['identity'], [1.0], 1.0)
            self.assertEqual(interrupted.read_bytes(), prior)
            self.assertFalse(interrupted.with_name('interrupted.pt.tmp').exists())


if __name__ == '__main__':
    unittest.main()
