"""Dense local spectral shape with a shared encoder, for one remote screen.

The original fixed FFT/RMS windows and pitch-context network are retained.
Denser observations and a learned shape encoder change together. This does
not establish source separation, exact pitch equivariance or MIDI readiness.
"""
import numpy as np

from tools.shared_harmonic_learning import HarmonicFeatures, SETTINGS, candidate_rows
from tools.harmonic_context_learning import make_network


SPECTRAL_PATCHES = dict(
    name='harmonic_spectral_patches_v1',
    offsets_semitones=[i/6 for i in range(-12, 13)],
    harmonic_multipliers=[0.5, 1.0, 2.0, 3.0, 4.0, 5.0],
    windows=[4096, 16384],
    feature_count=302,
    encoder_channels=[2, 4, 4],
    encoder_kernel_size=3,
    encoder_padding=1,
    encoder_activation='relu',
    encoder_sharing='same two offset convolutions for every candidate pitch and harmonic',
    encoder_readout='retain all 25 positions; concatenate six 100-value patches and two RMS values',
    context_input_channels=602,
    parameter_count=31825,
    feature_storage_dtype='float32',
    normalization='training-only float64 two-pass moments in 2048-candidate-row chunks; float32 mean/std',
    normalization_chunk_rows=2048,
    training_storage='normalize each shuffled minibatch on demand; one optimizer step per original batch',
    identity_features=False,
    hard_rejection=False)


class HarmonicPatchFeatures(HarmonicFeatures):
    """25 samples around each partial; base extraction retains causal windows."""
    storage_dtype = np.float32

    def __init__(self):
        super().__init__()
        notes = np.arange(SETTINGS['note_low'], SETTINGS['note_high']+1)
        fundamental = 440.0*2.0**((notes-69.0)/12.0)
        ratios = (np.asarray(SPECTRAL_PATCHES['harmonic_multipliers'])[:, None]*
                  2.0**(np.asarray(SPECTRAL_PATCHES['offsets_semitones'])[None, :]/12.0))
        self.frequency = fundamental[:, None, None]*ratios[None, :, :]
        if not np.isfinite(self.frequency).all() or self.frequency.max() > SETTINGS['sample_rate']/2:
            raise ValueError('Spectral patch exceeds Nyquist')
        self.coordinate_names = [name for n in SETTINGS['windows'] for name in
            [*(f'w{n}:h{h:g}:offset{o:.9g}:relative_db'
               for h in SPECTRAL_PATCHES['harmonic_multipliers']
               for o in SPECTRAL_PATCHES['offsets_semitones']), f'w{n}:rms_db']]
        self.names = [f'note{note}:{name}' for note in notes for name in self.coordinate_names]


def fit_patch_normalization(features):
    """Bounded scratch space, including constant coordinates; training only."""
    rows = candidate_rows(features, SPECTRAL_PATCHES['feature_count'])
    if not len(rows):
        raise ValueError('Empty training features')
    chunk = SPECTRAL_PATCHES['normalization_chunk_rows']
    mean = np.zeros(rows.shape[1], dtype=np.float64)
    for start in range(0, len(rows), chunk):
        mean += rows[start:start+chunk].sum(axis=0, dtype=np.float64)
    mean /= len(rows)
    variance = np.zeros_like(mean)
    for start in range(0, len(rows), chunk):
        delta = rows[start:start+chunk].astype(np.float64)-mean
        variance += np.einsum('ij,ij->j', delta, delta)
    scale = np.sqrt(variance/len(rows))
    scale[scale < 1e-12] = 1.0
    return mean.astype(np.float32), scale.astype(np.float32)


def make_patch_network():
    import torch

    class SpectralPatchContext(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.shape = torch.nn.Sequential(
                torch.nn.Conv1d(2, 4, 3, padding=1), torch.nn.ReLU(),
                torch.nn.Conv1d(4, 4, 3, padding=1), torch.nn.ReLU())
            self.pitch_context = make_network(SPECTRAL_PATCHES['context_input_channels'])

        def encode(self, values):
            if values.ndim != 3 or values.shape[1] != SPECTRAL_PATCHES['feature_count']:
                raise ValueError('Expected batch, 302 coordinates, candidate pitch')
            batch, _, notes = values.shape
            windows = values.transpose(1, 2).reshape(batch, notes, 2, 151)
            patches = windows[..., :150].reshape(batch, notes, 2, 6, 25)
            patches = patches.permute(0, 1, 3, 2, 4).reshape(batch*notes*6, 2, 25)
            shaped = self.shape(patches).reshape(batch, notes, 600)
            return torch.cat((shaped, windows[..., 150]), dim=2).transpose(1, 2)

        def forward(self, values):
            return self.pitch_context(self.encode(values))

    return SpectralPatchContext()
