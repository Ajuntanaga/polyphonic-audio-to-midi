"""Epoch-boundary recovery for the frozen CPU spectral-patch experiment."""
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np

from tools.portable_basic_pitch_comparison import remote_only


SCHEMA = 'm3_harmonic_training_checkpoint_v1'


def array_identity(array):
    """Hash exact training bytes without making a second full feature matrix."""
    array = np.asarray(array)
    if not array.flags.c_contiguous:
        raise ValueError('Checkpoint inputs must be C-contiguous')
    digest = hashlib.sha256()
    data = memoryview(array).cast('B')
    for begin in range(0, len(data), 1024*1024):
        digest.update(data[begin:begin+1024*1024])
    return dict(shape=list(array.shape), dtype=array.dtype.str, sha256=digest.hexdigest())


def training_identity(features, truth, mean, scale, params, patches, context):
    if not isinstance(context, dict) or not context:
        raise ValueError('Checkpoint execution identity is required')
    identity = dict(features=array_identity(features), truth=array_identity(truth),
        mean=array_identity(mean), scale=array_identity(scale),
        model_parameters=params, spectral_patch_parameters=patches, context=context)
    return json.loads(json.dumps(identity, sort_keys=True, allow_nan=False))


def save_training_checkpoint(path, network, optimizer, generator, mean, scale,
                             identity, losses, elapsed_seconds):
    remote_only()
    import torch
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(schema=SCHEMA, identity=identity, completed_epochs=len(losses),
        loss_curve=list(losses), elapsed_training_seconds=float(elapsed_seconds),
        network=network.state_dict(), optimizer=optimizer.state_dict(),
        shuffle_rng=generator.get_state(), torch_rng=torch.get_rng_state(),
        mean=torch.from_numpy(mean), scale=torch.from_numpy(scale))
    temporary = path.with_name(path.name + '.tmp')
    try:
        with temporary.open('wb') as stream:
            torch.save(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def restore_training_checkpoint(path, network, optimizer, generator, mean, scale, identity):
    remote_only()
    import torch
    saved = torch.load(path, map_location='cpu', weights_only=True)
    if saved.get('schema') != SCHEMA or saved.get('identity') != identity:
        raise ValueError('Training checkpoint identity mismatch')
    epoch, losses = saved['completed_epochs'], saved['loss_curve']
    target = identity['model_parameters']['epochs']
    elapsed = saved['elapsed_training_seconds']
    if (type(epoch) is not int or not 1 <= epoch <= target or len(losses) != epoch
            or not all(math.isfinite(value) for value in losses)
            or not math.isfinite(elapsed) or elapsed < 0):
        raise ValueError('Invalid training checkpoint progress')
    if not torch.equal(saved['mean'], torch.from_numpy(mean)) or not torch.equal(
            saved['scale'], torch.from_numpy(scale)):
        raise ValueError('Training checkpoint normalization mismatch')
    if not all(torch.isfinite(value).all() for value in saved['network'].values()):
        raise ValueError('Nonfinite checkpoint weights')
    expected_steps = epoch*((identity['features']['shape'][0]
        + identity['model_parameters']['batch_size']-1)//identity['model_parameters']['batch_size'])
    states = saved['optimizer']['state']
    if len(states) != len(list(network.parameters())) or any(
            float(state['step']) != expected_steps
            or not torch.isfinite(state['exp_avg']).all()
            or not torch.isfinite(state['exp_avg_sq']).all() for state in states.values()):
        raise ValueError('Invalid checkpoint optimizer progress')
    network.load_state_dict(saved['network'], strict=True)
    optimizer.load_state_dict(saved['optimizer'])
    generator.set_state(saved['shuffle_rng'])
    torch.set_rng_state(saved['torch_rng'])
    return epoch, list(losses), float(elapsed)
