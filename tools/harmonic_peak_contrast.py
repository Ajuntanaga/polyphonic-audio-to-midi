"""Additional trailing spectral observations; no hard harmonicity rejection.

The original 62 coordinates remain byte-identical. Appended coordinates expose
peak location, prominence and disagreement across partials to the shared model.
Zero padding interpolates the spectrum; it does not improve physical resolution.
Recorded extraction/fitting belongs exclusively to the GitHub CPU runner.
"""
import numpy as np

from tools.direct_spectrum_learning import SETTINGS
from tools.shared_harmonic_learning import (HarmonicFeatures, NOTE_COUNT,
    FEATURE_COUNT as BASE_FEATURE_COUNT, PARAMETERS)


CONTRAST = dict(name='harmonic_peak_contrast_v1', harmonics=[1, 2, 3, 4, 5],
    search_radius_cents=40.0, zero_padding_factor=8, flank_native_bins=3.0,
    prominence_db_clip=[-60.0, 60.0], interpolation='three-bin log-power parabola',
    peak_rule='largest local maximum with interpolated frequency within the fixed neighborhood',
    no_peak='nominal-frequency power and flank contrast; offset=0, valid=0',
    coherence='power-weighted standard deviation of valid partial offsets in cents; zero for fewer than two',
    flank_rule='mean linear power at peak +/- three native FFT bins; negative frequency reflected',
    normalization='original trailing-window RMS; training-only coordinate scaling',
    hard_rejection=False)
PER_WINDOW = 4*len(CONTRAST['harmonics'])+2
FEATURE_COUNT = BASE_FEATURE_COUNT + len(SETTINGS['windows'])*PER_WINDOW


class HarmonicContrastFeatures:
    """106 coordinates: original 62, then 22 for each trailing window.

    Each harmonic: relative peak dB, offset cents, flank prominence dB, valid.
    Each window ends with weighted offset dispersion and valid-peak fraction.
    Missing/unresolved partials are explicit; no annotation or pitch ID is input.
    """
    contrast_parameters = CONTRAST

    def __init__(self):
        self.base = HarmonicFeatures()
        notes = np.arange(SETTINGS['note_low'], SETTINGS['note_high']+1)
        self.centers = (440*2.0**((notes[:, None]-69)/12.0)*
                        np.asarray(CONTRAST['harmonics'])[None, :]).ravel()
        ratio = 2**(CONTRAST['search_radius_cents']/1200)
        self.low, self.high = self.centers/ratio, self.centers*ratio
        self.grids = {}
        for n in SETTINGS['windows']:
            size = n*CONTRAST['zero_padding_factor']
            df = SETTINGS['sample_rate']/size
            # Include the adjacent bins whose interpolated vertex can fall inside.
            lo = np.floor(self.low/df).astype(int)-1
            hi = np.ceil(self.high/df).astype(int)+1
            indices = lo[:, None]+np.arange(int((hi-lo).max())+1)[None, :]
            self.grids[n] = (size, df, indices, indices <= hi[:, None])
        self.coordinate_names = self.base.coordinate_names + [name
            for n in SETTINGS['windows'] for name in [
                *(f'w{n}:h{h}:peak_{field}' for h in CONTRAST['harmonics']
                  for field in ('relative_db', 'offset_cents', 'prominence_db', 'valid')),
                f'w{n}:peak_offset_dispersion_cents', f'w{n}:valid_peak_fraction']]
        self.names = [f'note{note}:{name}' for note in notes for name in self.coordinate_names]

    def __call__(self, past):
        # This also validates input length/finiteness before the extra FFTs.
        base = self.base(past).reshape(NOTE_COUNT, BASE_FEATURE_COUNT)
        past = np.asarray(past, dtype=np.float64)
        blocks = [base]
        for n, window in self.base.windows.items():
            signal = past[-n:]
            rms2 = max(float(np.mean(signal*signal)), PARAMETERS['rms2_floor'])
            size, df, indices, in_grid = self.grids[n]
            power = np.abs(np.fft.rfft(signal*window, n=size)/window.sum())**2
            logp = 10*np.log10(np.maximum(power, PARAMETERS['power_floor']))
            left, middle, right = logp[indices-1], logp[indices], logp[indices+1]
            curvature = left-2*middle+right
            local = ((middle > left) & (middle >= right) & (curvature < 0) &
                     (power[indices] > PARAMETERS['power_floor']))
            offset = np.zeros_like(middle)
            np.divide(0.5*(left-right), curvature, out=offset, where=local)
            offset = np.clip(offset, -0.5, 0.5)
            frequency = (indices+offset)*df
            peak_log = middle-0.25*(left-right)*offset
            eligible = local & in_grid & (frequency >= self.low[:, None]) & (frequency <= self.high[:, None])
            chosen = np.argmax(np.where(eligible, peak_log, -np.inf), axis=1)
            row = np.arange(len(self.centers))
            valid = eligible[row, chosen]
            nominal = np.interp(self.centers/df, np.arange(len(power)), power)
            peak_frequency = np.where(valid, frequency[row, chosen], self.centers)
            peak_db = np.where(valid, peak_log[row, chosen],
                               10*np.log10(np.maximum(nominal, PARAMETERS['power_floor'])))
            peak_power = 10**(peak_db/10)
            cents = np.where(valid, 1200*np.log2(peak_frequency/self.centers), 0)
            flank_distance = CONTRAST['flank_native_bins']*SETTINGS['sample_rate']/n
            flank_freq = np.abs(peak_frequency[:, None]+np.array([-1, 1])*flank_distance)
            flank = np.interp(flank_freq.ravel()/df, np.arange(len(power)), power).reshape(-1, 2).mean(axis=1)
            prominence = np.clip(peak_db-10*np.log10(np.maximum(flank, PARAMETERS['power_floor'])),
                                 *CONTRAST['prominence_db_clip'])
            relative = np.clip(peak_db-10*np.log10(rms2), *PARAMETERS['relative_db_clip'])
            hcount = len(CONTRAST['harmonics'])
            detail = np.stack((relative, cents, prominence, valid), axis=1).reshape(NOTE_COUNT, 4*hcount)
            weights = (peak_power*valid).reshape(NOTE_COUNT, hcount)
            cents = cents.reshape(NOTE_COUNT, hcount)
            total = weights.sum(axis=1)
            center = np.divide((weights*cents).sum(axis=1), total, out=np.zeros(NOTE_COUNT), where=total > 0)
            variance = np.divide((weights*(cents-center[:, None])**2).sum(axis=1), total,
                                 out=np.zeros(NOTE_COUNT), where=total > 0)
            blocks.append(np.c_[detail, np.sqrt(variance), valid.reshape(NOTE_COUNT, hcount).mean(axis=1)])
        return np.concatenate(blocks, axis=1).astype(np.float32).ravel()


def contrast_summary(features, truth, probability, cutoff):
    """Descriptive distributions only, with no threshold choice or new fit."""
    values = np.asarray(features).reshape(-1, NOTE_COUNT, FEATURE_COUNT)
    truth = np.asarray(truth, dtype=bool)
    probability = np.asarray(probability)
    if truth.shape != values.shape[:2] or probability.shape != truth.shape:
        raise ValueError('Misaligned contrast diagnostics')
    prediction = probability >= cutoff
    groups = dict(expected=truth, found=truth & prediction,
                  missing=truth & ~prediction, extra=~truth & prediction)
    result = dict(scope='Candidate-pitch cells on sampled mixtures; descriptive, not independent samples.',
                  definitions='Peak absence is explicit; prominence summary uses valid peaks only.', windows={})
    for wi, n in enumerate(SETTINGS['windows']):
        block = values[:, :, BASE_FEATURE_COUNT+wi*PER_WINDOW:BASE_FEATURE_COUNT+(wi+1)*PER_WINDOW]
        detail = block[:, :, :-2].reshape(*truth.shape, len(CONTRAST['harmonics']), 4)
        count = detail[..., 3].sum(axis=-1)
        prominence = np.divide((detail[..., 2]*detail[..., 3]).sum(axis=-1), count,
                               out=np.full(truth.shape, np.nan), where=count > 0)
        metrics = dict(mean_valid_prominence_db=prominence,
                       offset_dispersion_cents=block[..., -2], valid_peak_fraction=block[..., -1])
        result['windows'][str(n)] = {}
        for name, mask in groups.items():
            row = dict(candidate_cells=int(mask.sum()), metrics={})
            for metric, array in metrics.items():
                subset = array[mask]
                subset = subset[np.isfinite(subset)]
                row['metrics'][metric] = dict(available=int(len(subset)),
                    p10_p50_p90=np.quantile(subset, [.1, .5, .9]).tolist() if len(subset) else None)
            result['windows'][str(n)][name] = row
    return result
