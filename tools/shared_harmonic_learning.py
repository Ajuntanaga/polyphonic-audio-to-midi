"""Pitch-relative features and one shared binary classifier for all 53 pitches.

Recorded fitting belongs to the portable GitHub runner. This is an offline
presence experiment, not a MIDI policy, string model or native implementation.
"""
import math

import numpy as np

from tools.direct_spectrum_learning import SETTINGS
from tools.spectral_ablation import complete_chord_gate
from tools.spectral_dictionary import stratified_summary


PARAMETERS = dict(harmonic_multipliers=[0.5, 1.0, 2.0, 3.0, 4.0, 5.0],
    offsets_semitones=[-0.4, -0.2, 0.0, 0.2, 0.4],
    relative_db_clip=[-100.0, 20.0], rms_db_clip=[-120.0, 20.0],
    power_floor=1e-20, rms2_floor=1e-12, feature_dtype='float32',
    training_precision_percent=99.0, prediction_batch_mixtures=128,
    pooling='all candidate pitches from training mixtures; one scaler and binary classifier',
    identity_inputs=False, class_reweighting=False)
MODEL_PARAMS = dict(hidden_layer_sizes=[64, 32], activation='relu', solver='adam',
    alpha=0.0001, batch_size=2048, learning_rate_init=0.001, max_iter=80,
    shuffle=True, random_state=20261121, early_stopping=False, tol=0.0,
    n_iter_no_change=81, verbose=True)
NOTE_COUNT = SETTINGS['note_high']-SETTINGS['note_low']+1
FEATURE_COUNT = len(SETTINGS['windows'])*(len(PARAMETERS['harmonic_multipliers'])*
    len(PARAMETERS['offsets_semitones'])+1)


class HarmonicFeatures:
    """Same 62 coordinates for every candidate, using only trailing samples.

    Flatten order is candidate note, window, harmonic, offset, then window RMS.
    Fixed FFT resolution means this is not exactly shift-equivariant.
    """
    def __init__(self):
        notes = np.arange(SETTINGS['note_low'], SETTINGS['note_high']+1)
        fundamental = 440.0*2.0**((notes-69.0)/12.0)
        ratios = (np.asarray(PARAMETERS['harmonic_multipliers'])[:, None]*
                  2.0**(np.asarray(PARAMETERS['offsets_semitones'])[None, :]/12.0))
        self.frequency = fundamental[:, None, None]*ratios[None, :, :]
        self.windows = {n: np.hanning(n) for n in SETTINGS['windows']}
        self.fft_frequency = {n: np.fft.rfftfreq(n, 1/SETTINGS['sample_rate']) for n in self.windows}
        self.coordinate_names = [name for n in SETTINGS['windows'] for name in
            [*(f'w{n}:h{h:g}:offset{o:g}:relative_db'
               for h in PARAMETERS['harmonic_multipliers'] for o in PARAMETERS['offsets_semitones']),
             f'w{n}:rms_db']]
        # These names document output order; pitch IDs never enter the classifier.
        self.names = [f'note{note}:{name}' for note in notes for name in self.coordinate_names]

    def __call__(self, past):
        past = np.asarray(past, dtype=np.float64)
        if past.shape != (max(SETTINGS['windows']),) or not np.isfinite(past).all():
            raise ValueError('Expected one finite trailing context')
        result = []
        for n, window in self.windows.items():
            signal = past[-n:]
            rms2 = float(np.mean(signal*signal))
            spectrum = np.fft.rfft(signal*window)/window.sum()
            power = np.interp(self.frequency.ravel(), self.fft_frequency[n],
                              np.abs(spectrum)**2).reshape(NOTE_COUNT, -1)
            relative = 10*np.log10(np.maximum(power, PARAMETERS['power_floor'])/
                                  max(rms2, PARAMETERS['rms2_floor']))
            absolute = np.clip(10*math.log10(max(rms2, PARAMETERS['rms2_floor'])),
                               *PARAMETERS['rms_db_clip'])
            result.append(np.c_[np.clip(relative, *PARAMETERS['relative_db_clip']),
                                np.full(NOTE_COUNT, absolute)])
        return np.concatenate(result, axis=1).astype(np.float32).ravel()


def candidate_rows(features, feature_count=FEATURE_COUNT):
    """Preserve mixture-major, pitch-minor alignment with truth.reshape(-1)."""
    values = np.asarray(features, dtype=np.float32)
    if (not isinstance(feature_count, int) or feature_count <= 0 or
            values.ndim != 2 or values.shape[1] != NOTE_COUNT*feature_count
            or not np.isfinite(values).all()):
        raise ValueError('Invalid harmonic feature matrix')
    return values.reshape(-1, feature_count)


class SharedHarmonicModel:
    def __init__(self, scaler, classifier, cutoff=None):
        self.scaler, self.classifier, self.cutoff = scaler, classifier, cutoff

    def activity(self, features):
        values = candidate_rows(features)
        classes = np.asarray(self.classifier.classes_)
        if not np.array_equal(classes, [False, True]):
            raise ValueError('Expected both binary presence classes in order')
        batch = PARAMETERS['prediction_batch_mixtures']*NOTE_COUNT
        result = np.empty(len(values), dtype=np.float64)
        for start in range(0, len(values), batch):
            probability = np.asarray(self.classifier.predict_proba(
                self.scaler.transform(values[start:start+batch])), dtype=np.float64)
            if (probability.shape != (min(batch, len(values)-start), 2)
                    or not np.isfinite(probability).all()
                    or (probability < 0).any() or (probability > 1).any()):
                raise ValueError('Invalid binary probabilities')
            result[start:start+batch] = probability[:, 1]
        return result.reshape(-1, NOTE_COUNT)

    def predict_proba(self, features):
        """Legacy continuous scorer consumes binary occupancy at its fixed 0.5."""
        if self.cutoff is None or not np.isfinite(self.cutoff) or self.cutoff <= 0:
            raise ValueError('Training cutoff has not been frozen')
        return (self.activity(features) >= self.cutoff).astype(np.float64)


def summarize(probability, truth, cutoff):
    result = stratified_summary(probability, truth, cutoff)
    result['activity_semantics'] = 'Shared binary classifier probability; one training-only global cutoff.'
    return result


def acceptance_gate(summary, *, training=False):
    return bool(complete_chord_gate(summary) and
        (not training or summary['overall']['precision_percent'] >= PARAMETERS['training_precision_percent']))
