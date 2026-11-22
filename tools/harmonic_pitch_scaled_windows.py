"""Past-only, candidate-pitch-scaled harmonic windows for one remote screen.

This changes time/frequency resolution, not source labels or the classifier.
It is not a full constant-Q transform, source separator or MIDI policy.
"""
import math

import numpy as np

from tools.shared_harmonic_learning import HarmonicFeatures, PARAMETERS, SETTINGS


PITCH_SCALED_WINDOWS = dict(
    name='harmonic_pitch_scaled_windows_v1',
    anchor_note=32,
    base_windows=[4096, 16384],
    length_rule='floor(base_window * 2**((anchor_note - candidate_note)/12) + 0.5)',
    alignment='Every window ends at the current trailing-context endpoint; no future samples.',
    fft_window='symmetric Hann, normalized by window sum',
    interpolation='linear interpolation of native RFFT power at the original harmonic/offset frequencies',
    normalization='RMS of the same candidate-specific window; original power/RMS floors and clips',
    total_context_samples=16384,
    feature_count=62,
    learned_window_parameters=False,
    hard_rejection=False)


class HarmonicPitchScaledFeatures:
    """Two equal-cycle branches per candidate; output order stays note-major.

    The original lengths are retained at MIDI 32. Higher candidates have
    shorter windows, so nearby high pitches can become harder to separate.
    Integer rounding, interpolation and finite windows prevent exact pitch
    equivariance. All harmonics of a candidate share its window length.
    """
    def __init__(self):
        base = HarmonicFeatures()
        self.note_count = base.note_count
        self.frequency = base.frequency
        notes = np.arange(SETTINGS['note_low'], SETTINGS['note_high']+1)
        self.window_lengths = np.floor(
            np.asarray(PITCH_SCALED_WINDOWS['base_windows'])[None, :]*
            2.0**((PITCH_SCALED_WINDOWS['anchor_note']-notes[:, None])/12.0)+.5).astype(int)
        if (self.window_lengths < 3).any() or (self.window_lengths > max(SETTINGS['windows'])).any():
            raise ValueError('Scaled window is outside the frozen past context')
        self.windows = {int(n): np.hanning(int(n)) for n in np.unique(self.window_lengths)}
        self.fft_frequency = {n: np.fft.rfftfreq(n, 1/SETTINGS['sample_rate']) for n in self.windows}
        self.coordinate_names = [name for n in PITCH_SCALED_WINDOWS['base_windows'] for name in
            [*(f'scaled_w{n}:h{h:g}:offset{o:g}:relative_db'
               for h in PARAMETERS['harmonic_multipliers'] for o in PARAMETERS['offsets_semitones']),
             f'scaled_w{n}:rms_db']]
        self.names = [f'note{note}:{name}' for note in notes for name in self.coordinate_names]

    def __call__(self, past):
        past = np.asarray(past, dtype=np.float64)
        if past.shape != (max(SETTINGS['windows']),) or not np.isfinite(past).all():
            raise ValueError('Expected one finite trailing context')
        spectra = {}
        for n, window in self.windows.items():
            signal = past[-n:]
            rms2 = float(np.mean(signal*signal))
            spectrum = np.fft.rfft(signal*window)/window.sum()
            spectra[n] = (np.abs(spectrum)**2, rms2)
        result = np.empty((self.note_count, len(self.coordinate_names)), dtype=np.float32)
        for row, lengths in enumerate(self.window_lengths):
            for branch, length in enumerate(lengths):
                n = int(length)
                spectrum, rms2 = spectra[n]
                power = np.interp(self.frequency[row].ravel(), self.fft_frequency[n], spectrum)
                relative = 10*np.log10(np.maximum(power, PARAMETERS['power_floor'])/
                                      max(rms2, PARAMETERS['rms2_floor']))
                start = branch*(len(power)+1)
                result[row, start:start+len(power)] = np.clip(relative, *PARAMETERS['relative_db_clip'])
                result[row, start+len(power)] = np.clip(
                    10*math.log10(max(rms2, PARAMETERS['rms2_floor'])), *PARAMETERS['rms_db_clip'])
        return result.ravel()
