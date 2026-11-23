"""Pure helpers for the frozen period-cancellation mechanism screen.

Recorded audio belongs to portable_period_cancellation on GitHub only. This
module implements no detector policy, MIDI path or installed configuration.
"""
import math

import numpy as np


SETTINGS = dict(sample_rate=96000, context_samples=16384, period_window=4096,
    readout_window=8192, fft_size=32768, note_low=32, note_high=84,
    yin_threshold=0.1, harmonics=6,
    partial_grid_cents=[-35, -70/3, -35/3, 0, 35/3, 70/3, 35],
    power_floor=1e-12, examples_per_role=1024,
    seeds=dict(train=20261121, calibration=20261122, test=20261123),
    calibration_false_fraction=0.01, primary_note_minimum=60,
    primary_level_max_db=-12, minimum_primary_queries=100, minimum_gain_pp=5,
    minimum_median_sir_gain_db=3, minimum_target_power_gain_db=-6,
    minimum_target_retention_fraction=0.75, identity_tolerance=1e-12)
ARMS = ('raw', 'mixture_period', 'component_period_oracle')
HARMONIC_INTERVALS = {12, 19, 24, 28, 31, 36}


def power(signal):
    return float(np.mean(np.square(signal, dtype=np.float64)))


def checked_context(past):
    past = np.asarray(past, dtype=np.float64)
    if past.shape != (SETTINGS['context_samples'],) or not np.isfinite(past).all():
        raise ValueError('Expected a finite, fixed-length past-only context')
    return past


def difference_curve(past, maximum_lag):
    """Fixed-length squared difference, all positive lags, using FFT dot sums."""
    past = checked_context(past)
    width = SETTINGS['period_window']
    if not 1 <= maximum_lag <= len(past)-width:
        raise ValueError('Lag does not fit the past context')
    buf = past[-(width+maximum_lag):]
    ref = buf[-width:]
    size = 1 << (len(buf)+width-2).bit_length()
    dots = np.fft.irfft(np.fft.rfft(buf, size)*np.fft.rfft(ref[::-1], size), size)
    starts = maximum_lag-np.arange(maximum_lag+1)
    prefix = np.r_[0., np.cumsum(buf*buf)]
    energies = prefix[starts+width]-prefix[starts]
    result = np.maximum(0., (float(ref@ref)+energies-2*dots[starts+width-1])/width)
    result[0] = 0.
    return result


def estimate_period(past):
    past = checked_context(past)
    rate = SETTINGS['sample_rate']
    low = math.floor(rate/(440*2**((SETTINGS['note_high']-69)/12)))
    high = math.ceil(rate/(440*2**((SETTINGS['note_low']-69)/12)))
    if power(past[-SETTINGS['period_window']:]) <= SETTINGS['power_floor']:
        return dict(delay_samples=None, cmnd=None, method='power_floor_identity')
    differences = difference_curve(past, high+1)
    cumulative = np.cumsum(differences[1:])
    cmnd = np.ones(len(differences), dtype=np.float64)
    np.divide(differences[1:]*np.arange(1, len(differences)), cumulative,
              out=cmnd[1:], where=cumulative > 0)
    troughs = [i for i in range(low, high+1) if cmnd[i] < SETTINGS['yin_threshold']
               and cmnd[i] <= cmnd[i-1] and cmnd[i] <= cmnd[i+1]]
    at = troughs[0] if troughs else int(low+np.argmin(cmnd[low:high+1]))
    denominator = cmnd[at-1]-2*cmnd[at]+cmnd[at+1]
    offset = (0.5*(cmnd[at-1]-cmnd[at+1])/denominator if denominator > 0 else 0.)
    delay = float(np.clip(at+np.clip(offset, -0.5, 0.5), low, high))
    return dict(delay_samples=delay, cmnd=float(cmnd[at]),
                method='first_trough' if troughs else 'global_minimum')


def filtered(past, delay):
    past = checked_context(past)
    width = SETTINGS['readout_window']
    if delay is None:
        return past[-width:].copy()
    if not math.isfinite(delay) or not 1 <= delay < len(past)-width:
        raise ValueError('Invalid cancellation delay')
    integer = math.floor(delay)
    fraction = delay-integer
    indices = np.arange(len(past)-width, len(past))-integer
    delayed = (1-fraction)*past[indices]+fraction*past[indices-1]
    return past[-width:]-delayed


class PartialReadout:
    def __init__(self):
        self.window = np.hanning(SETTINGS['readout_window'])
        self.normalizer = 2/float(self.window.sum())**2
        notes = np.arange(SETTINGS['note_low'], SETTINGS['note_high']+1)
        fundamentals = 440*2.**((notes-69)/12)
        self.query = (fundamentals[:, None, None]
                      * np.arange(1, SETTINGS['harmonics']+1)[None, :, None]
                      * 2.**(np.asarray(SETTINGS['partial_grid_cents'])[None, None, :]/1200))
        self.frequency = np.fft.rfftfreq(SETTINGS['fft_size'], 1/SETTINGS['sample_rate'])
        self.weights = 1/np.arange(1, SETTINGS['harmonics']+1)

    def __call__(self, signal):
        signal = np.asarray(signal, dtype=np.float64)
        if signal.shape != self.window.shape or not np.isfinite(signal).all():
            raise ValueError('Invalid readout window')
        spectrum = np.abs(np.fft.rfft(signal*self.window, SETTINGS['fft_size']))**2
        partials = np.interp(self.query.ravel(), self.frequency, spectrum).reshape(self.query.shape)
        scores = (partials.max(axis=2)*self.weights).sum(axis=1)*self.normalizer
        scores /= max(power(signal), SETTINGS['power_floor'])
        if not np.isfinite(scores).all() or np.any(scores < 0):
            raise ValueError('Nonfinite or negative readout')
        return scores


def evaluate_wave(past, components, readout):
    """The primary arm sees only past; component access is oracle/accounting only."""
    past = checked_context(past)
    components = [checked_context(c) for c in components]
    period = estimate_period(past)
    if components:
        strongest = int(np.argmax([power(c[-SETTINGS['readout_window']:]) for c in components]))
        oracle = estimate_period(components[strongest])
    else:
        oracle = dict(delay_samples=None, cmnd=None, method='empty_components_identity')
    metadata = dict(raw=dict(delay_samples=None, cmnd=None, method='unchanged'),
                    mixture_period=period, component_period_oracle=oracle)
    result, maximum_error = {}, 0.
    for name in ARMS:
        delay = metadata[name]['delay_samples']
        signal = filtered(past, delay)
        component_outputs = [filtered(c, delay) for c in components]
        summed = sum(component_outputs, start=np.zeros_like(signal))
        error = float(np.max(np.abs(signal-summed)))
        maximum_error = max(maximum_error, error)
        result[name] = dict(scores=readout(signal), metadata=metadata[name],
                            components=component_outputs)
    return result, maximum_error


def gain_db(after, before):
    floor = SETTINGS['power_floor']
    return 10*math.log10(max(after, floor)/max(before, floor))


def mixture_queries(row, mixed, components, readout):
    """Distinct-pitch positive/leave-pitch-out pairs; no label enters primary DSP."""
    components = [checked_context(c) for c in components]
    mixed = checked_context(mixed)
    if len(components) != len(row['components']):
        raise ValueError('Component metadata/audio count mismatch')
    recomposed = sum(components, start=np.zeros_like(mixed))
    recomposition_error = float(np.max(np.abs(mixed-recomposed)))
    positive, linearity_error = evaluate_wave(mixed, components, readout)
    if not components:
        return [], dict(recomposition_error=recomposition_error, linearity_error=linearity_error,
                        silence_maximum_score={a: float(positive[a]['scores'].max()) for a in ARMS})
    width = SETTINGS['readout_window']
    component_powers = [power(c[-width:]) for c in components]
    strongest = int(np.argmax(component_powers))
    strongest_note = row['components'][strongest]['note']
    pitches = sorted({c['note'] for c in row['components']})
    queries = []
    for note in pitches:
        own = [i for i, c in enumerate(row['components']) if c['note'] == note]
        other = [i for i in range(len(components)) if i not in own]
        target = sum((components[i] for i in own), start=np.zeros_like(mixed))
        negative_wave = sum((components[i] for i in other), start=np.zeros_like(mixed))
        recomposition_error = max(recomposition_error, float(np.max(np.abs(mixed-target-negative_wave))))
        negative, error = evaluate_wave(negative_wave, [components[i] for i in other], readout)
        linearity_error = max(linearity_error, error)
        relative_db = gain_db(max(component_powers[i] for i in own), max(component_powers))
        primary = note >= SETTINGS['primary_note_minimum'] and relative_db <= SETTINGS['primary_level_max_db']
        item = dict(example=row['example'], role=row['role'], note=int(note),
            distinct_pitches=len(pitches), components=len(components), own_components=len(own),
            relative_level_db=relative_db, primary=bool(primary), strongest_component_note=int(strongest_note),
            harmonic_to_strongest=note-strongest_note in HARMONIC_INTERVALS,
            band='below48' if note < 48 else '48-59' if note < 60 else '60-71' if note < 72 else '72+',
            arms={})
        target_raw_power = power(target[-width:])
        other_raw_power = power(negative_wave[-width:])
        for arm in ARMS:
            filtered_components = positive[arm]['components']
            target_output = sum((filtered_components[i] for i in own), start=np.zeros(width))
            other_output = sum((filtered_components[i] for i in other), start=np.zeros(width))
            target_gain = gain_db(power(target_output), target_raw_power)
            sir_gain = target_gain-gain_db(power(other_output), other_raw_power) if other else None
            col = note-SETTINGS['note_low']
            item['arms'][arm] = dict(present_score=float(positive[arm]['scores'][col]),
                absent_score=float(negative[arm]['scores'][col]),
                present_period=positive[arm]['metadata'], absent_period=negative[arm]['metadata'],
                target_power_gain_db=target_gain, sir_gain_db=sir_gain)
        queries.append(item)
    return queries, dict(recomposition_error=recomposition_error, linearity_error=linearity_error,
                         silence_maximum_score=None)


def calibrate_cutoff(negative_scores):
    scores = np.asarray(negative_scores, dtype=np.float64)
    if scores.ndim != 1 or len(scores) == 0 or not np.isfinite(scores).all() or np.any(scores < 0):
        raise ValueError('Invalid calibration negatives')
    allowed = math.floor(SETTINGS['calibration_false_fraction']*len(scores))
    cutoff = float(np.nextafter(np.sort(scores)[::-1][allowed], np.inf))
    return dict(cutoff=cutoff, negatives=len(scores), allowed_false=allowed,
                observed_false=int((scores >= cutoff).sum()))


def summarize_queries(queries, cutoffs):
    def part(rows):
        out = dict(queries=len(rows), arms={})
        for arm in ARMS:
            cutoff = cutoffs[arm]['cutoff']
            found = sum(r['arms'][arm]['present_score'] >= cutoff for r in rows)
            false = sum(r['arms'][arm]['absent_score'] >= cutoff for r in rows)
            gains = [r['arms'][arm]['sir_gain_db'] for r in rows if r['arms'][arm]['sir_gain_db'] is not None]
            retained = sum(r['arms'][arm]['target_power_gain_db'] >= SETTINGS['minimum_target_power_gain_db'] for r in rows)
            out['arms'][arm] = dict(found=found, false_responses=false,
                recall_percent=100*found/len(rows) if rows else None,
                false_percent=100*false/len(rows) if rows else None,
                median_sir_gain_db=float(np.median(gains)) if gains else None,
                target_retention_fraction=retained/len(rows) if rows else None)
        return out
    return dict(all=part(queries), primary=part([r for r in queries if r['primary']]),
        by_band={band: part([r for r in queries if r['band'] == band])
                 for band in ('below48', '48-59', '60-71', '72+')},
        by_polyphony={str(n): part([r for r in queries if r['distinct_pitches'] == n])
                      for n in range(1, 6)},
        primary_by_harmonic_relation={str(related): part([r for r in queries
                    if r['primary'] and r['harmonic_to_strongest'] == related]) for related in (False, True)})


def decision(summary, integrity_pass, silence_scores, cutoffs, arm='mixture_period'):
    subset, all_rows = summary['primary'], summary['all']
    raw, candidate = subset['arms']['raw'], subset['arms'][arm]
    n = subset['queries']
    delta = 100*(candidate['found']-raw['found'])/n if n else None
    gates = dict(integrity=bool(integrity_pass),
        enough_primary_queries=n >= SETTINGS['minimum_primary_queries'],
        primary_gain=delta is not None and delta >= SETTINGS['minimum_gain_pp'],
        all_false_noninferior=all_rows['arms'][arm]['false_responses'] <= all_rows['arms']['raw']['false_responses'],
        primary_false_noninferior=candidate['false_responses'] <= raw['false_responses'],
        silence_clean=silence_scores[arm] < cutoffs[arm]['cutoff'],
        median_sir_gain=candidate['median_sir_gain_db'] is not None and candidate['median_sir_gain_db'] >= SETTINGS['minimum_median_sir_gain_db'],
        target_power_retained=candidate['target_retention_fraction'] is not None and candidate['target_retention_fraction'] >= SETTINGS['minimum_target_retention_fraction'])
    return dict(arm=arm, primary_gain_pp=delta, gates=gates,
                pass_all=all(gates.values()),
                verdict='MECHANISM_LEAD_ONLY' if all(gates.values()) else 'REJECTED_FIXED_MECHANISM_SCREEN')
