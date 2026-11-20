"""Same-window spectral/resonator diagnostic; recorded audio runs on GHA only.

This isolates power-estimator differences at a shared frequency. It does not
reimplement the factory builder's autocorrelation or reconstruct its bank.
"""
import numpy as np


def paired_measurement(samples, rate, begin, rows):
    half = round(rate * .080)
    if rate <= 0 or half < 128 or begin < 0 or begin + 2 * half > len(samples):
        raise ValueError('Incomplete paired measurement window')
    halves = []
    for offset in (0, half):
        start = begin + offset
        ticks = [r for r in rows if start <= int(r['sample']) < start + half]
        x = np.asarray(samples[start:start + half], dtype=float)
        if x.ndim != 1 or not np.isfinite(x).all():
            raise ValueError('Invalid mono samples')
        valid = bool(ticks) and all(r['independent_phase_valid'] == '1' for r in ticks)
        cents = np.asarray([float(r['independent_phase_cents']) for r in ticks])
        valid = valid and bool(np.isfinite(cents).all())
        record = dict(start_sample=start, samples=half, ticks=len(ticks), eligible=valid)
        if not valid:
            record['reason'] = 'Independent phase unavailable for one or more ticks; no frequency substituted'
            halves.append(record)
            continue
        frequency = 440 * 2 ** ((52 - 69) / 12 + float(np.median(cents)) / 1200)
        # Same averaging decimator as labeled calibration, before mean removal.
        decimation = max(1, (int(rate) + 23999) // 24000)
        y = x[:len(x) // decimation * decimation].reshape(-1, decimation).mean(axis=1)
        y = (y - y.mean()) * np.hanning(len(y))
        t = np.arange(len(y)) / (rate / decimation)
        def power(hz):
            return float(abs(np.dot(y, np.exp(-2j * np.pi * hz * t))) ** 2)
        exact, peak, peak_cents = [], [], []
        for h in range(1, 7):
            hz = frequency * h
            exact.append(power(hz))
            offsets = np.array([0.]) if h == 1 else np.arange(-20, 61) * .5
            powers = [power(hz * 2 ** (c / 1200)) for c in offsets]
            best = int(np.argmax(powers))
            peak.append(powers[best]); peak_cents.append(float(offsets[best]))
        runtime = np.asarray([[float(r[f'corrected_harmonic_energy_{h}']) for h in range(1, 7)] for r in ticks])
        if not np.isfinite(runtime).all() or np.any(runtime < 0):
            raise ValueError('Invalid runtime power')
        powers = dict(spectral_exact=exact, spectral_peak=peak, runtime=runtime.mean(axis=0).tolist())
        positive = all(np.all(np.asarray(p) > 0) for p in powers.values())
        record.update(eligible=bool(positive), frequency_hz=frequency,
                      independent_cents_range=[float(cents.min()), float(cents.max())],
                      peak_offset_cents=peak_cents, power=powers,
                      shares={key: (np.asarray(p)/sum(p)).tolist() if sum(p) > 0 else None for key, p in powers.items()})
        if not positive:
            record['reason'] = 'Nonpositive harmonic power; no floor substituted'
        halves.append(record)
    return dict(halves=halves, eligible=all(h['eligible'] for h in halves),
                limitation='Same two 80ms label-relative windows. Spectral frequency is median independent phase; runtime retains its actual cell/phase behavior and prior state. Peak search follows factory range, but this is not the factory fundamental estimator or a rebuilt bank. Powers have different normalization; compare shares only.')
