"""Past-only harmonic phase motion, alongside unchanged amplitude features.

This supplies learned evidence, not a phase gate or source-ownership rule.
Recorded extraction and model fitting belong to the GitHub runner.
"""
import numpy as np

from tools.direct_spectrum_learning import SETTINGS
from tools.shared_harmonic_learning import (
    FEATURE_COUNT as BASE_FEATURE_COUNT, NOTE_COUNT, HarmonicFeatures)


PHASE_MOTION = dict(name='harmonic_phase_motion_v1', window=8192, hop=512,
    end_offsets=[1024, 512, 0], harmonic_multipliers=[0.5, 1.0, 2.0, 3.0, 4.0, 5.0],
    fft_window='symmetric Hann, normalized by window sum',
    bin_rule='nearest native FFT bin, floor(frequency*window/sample_rate+0.5)',
    increment='conj(X_previous)*X_current',
    residual='sum(increments)*exp(-2j*pi*nominal_frequency*hop/sample_rate)',
    denominator='max(sum(abs(increments)), power_floor)', power_floor=1e-20,
    coordinates=['real', 'imag'], silence_value=0.0, hard_rejection=False,
    total_span_samples=9216, base_coordinates='62 values unchanged')
SINGLE_PITCH_BASELINE = dict(run_id=44965135706, examples=3132,
    exact_sets=3115, false_positive=13, false_negative=5)
FEATURE_COUNT = BASE_FEATURE_COUNT+2*len(PHASE_MOTION['harmonic_multipliers'])


def phase_residual(coefficients, nominal_phase_step):
    """Amplitude-weighted mean of two phase increments, nominal step removed.

The magnitude is at most one. Equal opposing increments cancel. Below the
fixed power floor, the value tends continuously to zero rather than dividing
noise by zero. No claim of independent increments or sinusoid validity.
"""
    values = np.asarray(coefficients, dtype=np.complex128)
    steps = np.asarray(nominal_phase_step, dtype=np.float64)
    if values.shape != (3, *steps.shape) or not np.isfinite(values).all() or not np.isfinite(steps).all():
        raise ValueError('Expected three finite coefficient frames and matching phase steps')
    increments = values[:-1].conj()*values[1:]
    denominator = np.maximum(np.abs(increments).sum(axis=0), PHASE_MOTION['power_floor'])
    return increments.sum(axis=0)*np.exp(-1j*steps)/denominator


class HarmonicPhaseFeatures:
    phase_parameters = PHASE_MOTION

    def __init__(self):
        self.base = HarmonicFeatures()
        notes = np.arange(SETTINGS['note_low'], SETTINGS['note_high']+1)
        frequency = (440.0*2.0**((notes[:, None]-69)/12)*
                     np.asarray(PHASE_MOTION['harmonic_multipliers'])[None, :])
        self.bins = np.floor(frequency*PHASE_MOTION['window']/SETTINGS['sample_rate']+.5).astype(int)
        self.phase_step = 2*np.pi*frequency*PHASE_MOTION['hop']/SETTINGS['sample_rate']
        self.window = np.hanning(PHASE_MOTION['window'])
        self.window_sum = self.window.sum()
        self.coordinate_names = self.base.coordinate_names+[
            f'w8192:hop512:h{h:g}:phase_{part}'
            for h in PHASE_MOTION['harmonic_multipliers'] for part in PHASE_MOTION['coordinates']]
        self.names = [f'note{note}:{name}' for note in notes for name in self.coordinate_names]

    def __call__(self, past):
        past = np.asarray(past, dtype=np.float64)
        # The base extractor validates the full finite, past-only context.
        base = self.base(past).reshape(NOTE_COUNT, BASE_FEATURE_COUNT)
        frames = []
        for offset in PHASE_MOTION['end_offsets']:
            end = len(past)-offset
            spectrum = np.fft.rfft(past[end-len(self.window):end]*self.window)/self.window_sum
            frames.append(spectrum[self.bins])
        residual = phase_residual(np.asarray(frames), self.phase_step)
        phase = np.stack((residual.real, residual.imag), axis=-1).reshape(NOTE_COUNT, -1)
        return np.concatenate((base, phase), axis=1).astype(np.float32).ravel()


def single_pitch_preservation(probability, truth, cutoff):
    """Additional frozen non-inferiority gate before continuous replay."""
    probability, truth = np.asarray(probability), np.asarray(truth, dtype=bool)
    if (probability.shape != truth.shape or truth.ndim != 2 or truth.shape[1] != NOTE_COUNT
            or not np.isfinite(probability).all() or not np.isfinite(cutoff)):
        raise ValueError('Invalid single-pitch comparison')
    singles = truth.sum(axis=1) == 1
    targets, guess = truth[singles], probability[singles] >= cutoff
    measured = dict(examples=int(singles.sum()), exact_sets=int(np.all(targets == guess, axis=1).sum()),
        false_positive=int((~targets & guess).sum()), false_negative=int((targets & ~guess).sum()))
    baseline = SINGLE_PITCH_BASELINE
    passed = (measured['examples'] == baseline['examples'] and
        measured['exact_sets'] >= baseline['exact_sets'] and
        measured['false_positive'] <= baseline['false_positive'] and
        measured['false_negative'] <= baseline['false_negative'])
    return dict(baseline=baseline, current=measured, passed=bool(passed),
        scope='Unaugmented setwise training singleton non-inferiority; held-out and continuous gates still required')
