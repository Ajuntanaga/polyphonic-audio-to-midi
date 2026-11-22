"""Training-only feature-grid consistency; not an audio pitch transposition."""

GRID_CONSISTENCY = {
    'name': 'one_row_training_grid_consistency_v1',
    'shift_rows': 1,
    'input_note_count': 53,
    'overlap_rows': 52,
    'fill': 'zero after training-only normalization; no wrap',
    'teacher': 'original logits detached; same network, no separate teacher',
    'loss': 'mean Huber over batch and overlapping rows',
    'delta': 1.0,
    'weight': 1.0,
    'optimizer_steps_changed': False,
    'supervised_targets_changed': False,
    'inference_changed': False,
}


def shifted_grid(inputs):
    """Move normalized rows right by one; discard the last, mean-fill the first."""
    import torch
    if inputs.ndim != 3 or not inputs.shape[0] or not inputs.shape[1] or inputs.shape[2] != 53:
        raise ValueError('Expected a nonempty batch of 53 normalized pitch rows')
    return torch.cat((torch.zeros_like(inputs[:, :, :1]), inputs[:, :, :-1]), dim=2)


def grid_consistency_loss(original, shifted):
    """Compare corresponding rows, with gradients only through shifted logits."""
    from torch.nn import functional as F
    if (original.ndim != 2 or not original.shape[0] or original.shape[1] != 53
            or shifted.shape != original.shape):
        raise ValueError('Expected aligned nonempty batches of 53 pitch logits')
    return F.huber_loss(shifted[:, 1:], original[:, :-1].detach(),
                        delta=GRID_CONSISTENCY['delta'], reduction='mean')
