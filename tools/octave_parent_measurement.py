"""Observation-only octave-parent arithmetic; no admission thresholds or audio I/O."""
import numpy as np

PARENTS = (44, 48, 60, 62, 69)


def production_harmonics(note):
    if note not in PARENTS:
        raise ValueError('Outside frozen parent selection')
    return 6 if note <= 52 else 4


def six_frequency_energy(samples, rate, note, cents=0):
    """Hann projections: amplitude squared, not runtime cells or separated sources."""
    x = np.asarray(samples, dtype=float)
    if x.ndim != 1 or len(x) < 4 or not np.isfinite(x).all():
        raise ValueError('Finite mono window required')
    if not np.isfinite(rate) or rate <= 0 or not np.isfinite(cents):
        raise ValueError('Invalid rate or cents')
    production_harmonics(note)
    frequency = 440 * 2 ** ((note - 69 + cents / 100) / 12)
    if frequency * 6 >= rate / 2:
        raise ValueError('Six harmonics exceed Nyquist')
    window = np.hanning(len(x))
    t = np.arange(len(x)) / rate
    return [float((2 * abs(np.dot(x * window, np.exp(-2j * np.pi * frequency * h * t))) / window.sum()) ** 2)
            for h in range(1, 7)]


def held_pass_errors(rows, field):
    """Same pitch/lane oracle; exclude whole pass, retain unavailable takes."""
    def ratio(row):
        values = row.get(field)
        if values is None:
            return None
        a = np.asarray(values, dtype=float)
        expected = production_harmonics(row['note']) if field == 'runtime_energy' else 6
        if a.shape != (expected,) or not np.isfinite(a).all() or np.any(a <= 0):
            return None
        return 10 * np.log10(a[1:] / a[0])
    features = [ratio(r) for r in rows]
    result = []
    for i, row in enumerate(rows):
        train = [v for r, v in zip(rows, features) if v is not None and
                 r['note'] == row['note'] and r['lane'] == row['lane'] and
                 r['held_pass'] != row['held_pass']]
        available = features[i] is not None and bool(train)
        result.append(dict(take_id=row['take_id'], training_count=len(train),
            available=available, reason=None if available else
            ('invalid_observation' if features[i] is None else 'no_other_pass'),
            error_db=(features[i] - np.median(train, axis=0)).tolist() if available else None))
    return result
