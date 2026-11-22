"""Frame-local partial spectral whitening for the fixed harmonic classifier.

Adapted from Klapuri (ISMIR 2006), section 2.1. Unlike the paper, retain the
baseline FFT sizes and normalize the weighted spectrum back to its original
power sum. No source template, target pitch or other frame sets the envelope.
"""
import math

import numpy as np

from tools.direct_spectrum_learning import SETTINGS
from tools.shared_harmonic_learning import HarmonicFeatures, NOTE_COUNT, PARAMETERS


WHITENING = dict(name='frame_local_critical_band_whitening_v1',
    reference='https://doi.org/10.5281/zenodo.1416740',
    bands=30, center_scale_hz=229.0, center_divisor=21.4, exponent=0.33,
    band_power_floor_fraction=1e-12,
    envelope='triangular power bands; sigma_b^(-0.67); linear amplitude-gain interpolation',
    endpoints='constant first/last center coefficient outside the centers',
    normalization='preserve original one-sided FFT power sum after whitening',
    fft='unchanged 4096/16384 Hann FFTs; no added zero padding',
    features_per_candidate=62, rms_coordinates='unchanged original waveform RMS',
    scope='same frame-local operation for training, held-out and continuous inputs')


class CriticalBandWhitener:
    def __init__(self, size):
        self.size = size
        self.frequency = np.fft.rfftfreq(size, 1/SETTINGS['sample_rate'])
        anchors = WHITENING['center_scale_hz']*(
            10**((np.arange(WHITENING['bands']+2)+1)/WHITENING['center_divisor'])-1)
        self.centers = anchors[1:-1]
        self.limit = int(np.searchsorted(self.frequency, anchors[-1], side='right'))
        bins = self.frequency[:self.limit][None, :]
        rising = (bins-anchors[:-2, None])/(anchors[1:-1]-anchors[:-2])[:, None]
        falling = (anchors[2:, None]-bins)/(anchors[2:]-anchors[1:-1])[:, None]
        self.weights = np.maximum(0, np.minimum(rising, falling))

    def __call__(self, power):
        power = np.asarray(power, dtype=np.float64)
        if (power.shape != self.frequency.shape or not np.isfinite(power).all()
                or (power < 0).any()):
            raise ValueError('Expected a finite nonnegative one-sided power spectrum')
        total = float(power.sum())
        if not np.isfinite(total):
            raise ValueError('Nonfinite spectral power sum')
        if total == 0:
            return power.copy()
        # Unit-total power makes the numerical floor relative and prevents a
        # common input gain from changing the whitening shape.
        unit = power/total
        variance = (self.weights @ unit[:self.limit])/self.size
        floor = WHITENING['band_power_floor_fraction']/self.size
        band_gain = np.maximum(variance, floor)**((WHITENING['exponent']-1)/2)
        gain = np.interp(self.frequency, self.centers, band_gain)
        weighted = unit*gain*gain
        return weighted*(total/float(weighted.sum()))


class HarmonicWhitenedFeatures(HarmonicFeatures):
    """Same 62 coordinates and trailing context, with the 60 powers whitened."""
    whitening_parameters = WHITENING

    def __init__(self):
        super().__init__()
        self.whiteners = {size: CriticalBandWhitener(size) for size in self.windows}
        self.coordinate_names = [name.replace(':relative_db', ':whitened_relative_db')
                                 for name in self.coordinate_names]
        self.names = [f'note{note}:{name}'
            for note in range(SETTINGS['note_low'], SETTINGS['note_high']+1)
            for name in self.coordinate_names]

    def __call__(self, past):
        past = np.asarray(past, dtype=np.float64)
        if past.shape != (max(SETTINGS['windows']),) or not np.isfinite(past).all():
            raise ValueError('Expected one finite trailing context')
        result = []
        for size, window in self.windows.items():
            signal = past[-size:]
            rms2 = float(np.mean(signal*signal))
            spectrum = np.fft.rfft(signal*window)/window.sum()
            whitened = self.whiteners[size](np.abs(spectrum)**2)
            power = np.interp(self.frequency.ravel(), self.fft_frequency[size],
                              whitened).reshape(NOTE_COUNT, -1)
            relative = 10*np.log10(np.maximum(power, PARAMETERS['power_floor'])/
                                  max(rms2, PARAMETERS['rms2_floor']))
            absolute = np.clip(10*math.log10(max(rms2, PARAMETERS['rms2_floor'])),
                               *PARAMETERS['rms_db_clip'])
            result.append(np.c_[np.clip(relative, *PARAMETERS['relative_db_clip']),
                                np.full(NOTE_COUNT, absolute)])
        return np.concatenate(result, axis=1).astype(np.float32).ravel()
