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
COMPLETE_SET_PARAMS = dict(MODEL_PARAMS,
    loss='mean_bce_plus_worst_polarity_logistic_v1')
SETWISE_PARAMS = dict(MODEL_PARAMS,
    loss='mean_bce_plus_setwise_logsumexp_v1')


def setwise_loss(logits, targets):
    """Mean pitch BCE plus all-positive/all-negative zero-bounded logsumexp.

    The two set terms are summed per mixture, then averaged across mixtures.
    A zero sentinel gives empty polarities zero loss and keeps extreme finite
    logits stable. This trains set separation without using cardinality at
    inference; it does not guarantee preservation of individual examples.
    """
    import torch
    from torch.nn import functional as F
    if logits.ndim != 2 or logits.shape != targets.shape or not logits.numel():
        raise ValueError('Expected nonempty aligned mixture/pitch matrices')
    if not torch.all((targets == 0) | (targets == 1)):
        raise ValueError('Expected binary complete-set targets')
    positive = targets.bool()
    zero = logits.new_zeros((len(logits), 1))
    true_term = torch.logsumexp(torch.cat((zero,
        (-logits).masked_fill(~positive, -torch.inf)), dim=1), dim=1)
    false_term = torch.logsumexp(torch.cat((zero,
        logits.masked_fill(positive, -torch.inf)), dim=1), dim=1)
    return (F.binary_cross_entropy_with_logits(logits, targets.to(logits.dtype))
            + (true_term + false_term).mean())


def complete_set_loss(logits, targets):
    """Mean pitch BCE plus one equally weighted worst-polarity term per mixture.

    For a voiced mixture the added term is the mean of the weakest true
    pitch's logistic loss and the strongest false pitch's logistic loss.
    Silence has only the false-pitch term. No annotated cardinality is used
    at inference, and absolute pitch loss remains in the objective.
    """
    import torch
    from torch.nn import functional as F
    if logits.ndim != 2 or logits.shape != targets.shape or not logits.numel():
        raise ValueError('Expected nonempty aligned mixture/pitch matrices')
    if not torch.all((targets == 0) | (targets == 1)):
        raise ValueError('Expected binary complete-set targets')
    positive = targets.bool()
    negative = ~positive
    weakest_true = F.softplus(-logits).masked_fill(negative, 0).amax(dim=1)
    strongest_false = F.softplus(logits).masked_fill(positive, 0).amax(dim=1)
    polarities = positive.any(dim=1).to(logits.dtype) + negative.any(dim=1).to(logits.dtype)
    worst = ((weakest_true + strongest_false) / polarities).mean()
    return F.binary_cross_entropy_with_logits(logits, targets.to(logits.dtype)) + worst


def fit_normalization(features, feature_count=FEATURE_COUNT):
    rows = candidate_rows(features, feature_count)
    if not len(rows):
        raise ValueError('Empty training features')
    mean = rows.mean(axis=0, dtype=np.float64)
    scale = rows.std(axis=0, dtype=np.float64)
    scale[scale < 1e-12] = 1.0
    return mean.astype(np.float32), scale.astype(np.float32)


def normalized_context(features, mean, scale, feature_count=FEATURE_COUNT):
    rows = candidate_rows(features, feature_count)
    mean, scale = np.asarray(mean), np.asarray(scale)
    if (mean.shape != (feature_count,) or scale.shape != (feature_count,)
            or not np.isfinite(mean).all() or not np.isfinite(scale).all()
            or (scale <= 0).any()):
        raise ValueError('Invalid frozen normalization')
    normalized = ((rows-mean)/scale).astype(np.float32)
    if not np.isfinite(normalized).all():
        raise ValueError('Nonfinite normalized input')
    return np.ascontiguousarray(normalized.reshape(-1, NOTE_COUNT, feature_count).transpose(0, 2, 1))


def make_network(feature_count=FEATURE_COUNT):
    import torch
    if not isinstance(feature_count, int) or feature_count <= 0:
        raise ValueError('Invalid feature count')

    class PitchContext(torch.nn.Module):
        def __init__(self):
            super().__init__()
            width = MODEL_PARAMS['channels']
            self.input = torch.nn.Conv1d(feature_count, width, 1)
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
        feature_count = len(self.mean)
        # Validate the entire shape even when an empty prediction batch is supplied.
        rows = candidate_rows(features, feature_count)
        mixtures = len(rows)//NOTE_COUNT
        values = rows.reshape(mixtures, NOTE_COUNT*feature_count)
        result = np.empty((mixtures, NOTE_COUNT), dtype=np.float64)
        self.network.eval()
        with torch.inference_mode():
            for start in range(0, mixtures, MODEL_PARAMS['batch_size']):
                batch = normalized_context(values[start:start+MODEL_PARAMS['batch_size']], self.mean, self.scale,
                                           feature_count)
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
