"""Shared pitch rule with joint harmonic context; offline CPU experiment only.

The existing trailing harmonic features are unchanged. Dilated convolutions
mix their pitch rows before a shared presence readout. This changes capacity
as well as context, so comparison with the independent MLP is not an ablation
that isolates context. No string, MIDI or production policy is implemented.
"""
import numpy as np

from tools.shared_harmonic_learning import (FEATURE_COUNT, NOTE_COUNT,
    HarmonicFeatures, PARAMETERS as FEATURE_PARAMETERS, candidate_rows, acceptance_gate)
from tools.spectral_dictionary import stratified_summary


PARAMETERS = dict(FEATURE_PARAMETERS,
    pooling='training mixtures and pitches for one coordinate scaler; pitch-context convolutions with shared readout')
MODEL_PARAMS = dict(channels=32, dilations=[1, 4, 12, 19], kernel_size=3,
    activation='relu', residual=True, padding='zero', loss='BCEWithLogitsLoss',
    class_reweighting=False, optimizer='Adam', learning_rate=0.001,
    weight_decay=0.0001, batch_size=128, epochs=80, seed=20261121,
    torch_threads=1, deterministic=True, early_stopping=False,
    normalization='training-only mean/std per shared coordinate over mixtures and pitches')


def fit_normalization(features):
    rows = candidate_rows(features)
    if not len(rows):
        raise ValueError('Empty training features')
    mean = rows.mean(axis=0, dtype=np.float64)
    scale = rows.std(axis=0, dtype=np.float64)
    scale[scale < 1e-12] = 1.0
    return mean.astype(np.float32), scale.astype(np.float32)


def normalized_context(features, mean, scale):
    rows = candidate_rows(features)
    mean, scale = np.asarray(mean), np.asarray(scale)
    if (mean.shape != (FEATURE_COUNT,) or scale.shape != (FEATURE_COUNT,)
            or not np.isfinite(mean).all() or not np.isfinite(scale).all()
            or (scale <= 0).any()):
        raise ValueError('Invalid frozen normalization')
    normalized = ((rows-mean)/scale).astype(np.float32)
    if not np.isfinite(normalized).all():
        raise ValueError('Nonfinite normalized input')
    return np.ascontiguousarray(normalized.reshape(-1, NOTE_COUNT, FEATURE_COUNT).transpose(0, 2, 1))


def make_network():
    import torch

    class PitchContext(torch.nn.Module):
        def __init__(self):
            super().__init__()
            width = MODEL_PARAMS['channels']
            self.input = torch.nn.Conv1d(FEATURE_COUNT, width, 1)
            self.context = torch.nn.ModuleList(torch.nn.Conv1d(width, width,
                MODEL_PARAMS['kernel_size'], dilation=d, padding=d)
                for d in MODEL_PARAMS['dilations'])
            self.output = torch.nn.Conv1d(width, 1, 1)

        def forward(self, values):
            values = torch.relu(self.input(values))
            for layer in self.context:
                values = torch.relu(values+layer(values))
            return self.output(values).squeeze(1)

    return PitchContext()


class HarmonicContextModel:
    def __init__(self, mean, scale, network, cutoff=None):
        self.mean, self.scale, self.network, self.cutoff = mean, scale, network, cutoff

    def activity(self, features):
        import torch
        # Validate the entire shape even when an empty prediction batch is supplied.
        rows = candidate_rows(features)
        mixtures = len(rows)//NOTE_COUNT
        values = rows.reshape(mixtures, NOTE_COUNT*FEATURE_COUNT)
        result = np.empty((mixtures, NOTE_COUNT), dtype=np.float64)
        self.network.eval()
        with torch.inference_mode():
            for start in range(0, mixtures, MODEL_PARAMS['batch_size']):
                batch = normalized_context(values[start:start+MODEL_PARAMS['batch_size']], self.mean, self.scale)
                probability = torch.sigmoid(self.network(torch.from_numpy(batch))).cpu().numpy()
                if (probability.shape != (len(batch), NOTE_COUNT)
                        or not np.isfinite(probability).all()
                        or (probability < 0).any() or (probability > 1).any()):
                    raise ValueError('Invalid joint-context probabilities')
                result[start:start+len(batch)] = probability
        return result

    def predict_proba(self, features):
        if self.cutoff is None or not np.isfinite(self.cutoff) or self.cutoff <= 0:
            raise ValueError('Training cutoff has not been frozen')
        return (self.activity(features) >= self.cutoff).astype(np.float64)


def summarize(probability, truth, cutoff):
    result = stratified_summary(probability, truth, cutoff)
    result['activity_semantics'] = 'Shared convolutional pitch-context probability; one training-only global cutoff.'
    return result
