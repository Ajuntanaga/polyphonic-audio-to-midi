"""Systematic source-take observations, without label correction or fitting.

Recorded audio is processed only by the guarded GitHub runner. These functions
also accept synthetic signals for local tests. A periodic estimate and spectral
peak are descriptions of a waveform, not proof of its intended or played note.
"""
from collections import Counter
import math

import numpy as np
from scipy.signal import find_peaks

from tools.source_pitch_diagnostic import diagnose_crop


PARAMETERS = dict(sample_rate=96000, short_window=16384, step=8192,
    spectrum_window=65536, fft_padding=4, harmonics=8, spectral_low_hz=20.,
    spectral_high_hz=20000., band_native_bins=2., band_cents=50., top_peaks=8)


def select_sources(rows):
    """All all-other test takes, earliest all-target same-cell control per role."""
    if len({r['source_key'] for r in rows}) != len(rows):
        raise ValueError('Duplicate diagnostic source')
    def all_class(row, name):
        crops = row['unique_crops']
        return crops['count'] > 0 and crops['classes'][name] == crops['count']
    flagged = sorted((r for r in rows if r['role'] == 'test'
        and all_class(r, 'periodic_other')), key=lambda r: (
            r['source_key'].split(':')[0], int(r['source_key'].split(':')[1])))
    pairs, keys = [], set()
    for row in flagged:
        keys.add(row['source_key'])
        controls = {}
        for role in ('train', 'calibration'):
            eligible = [r for r in rows if r['role'] == role
                and r['note'] == row['note'] and r['string_mask'] == row['string_mask']
                and r['source_key'].split(':')[0] == row['source_key'].split(':')[0]
                and all_class(r, 'periodic_target')]
            control = min(eligible, key=lambda r: int(r['source_key'].split(':')[1])) if eligible else None
            controls[role] = control['source_key'] if control else None
            if control:
                keys.add(control['source_key'])
        pairs.append(dict(flagged=row['source_key'], controls=controls))
    return dict(pairs=pairs, source_keys=sorted(keys),
        flagged_count=len(flagged), unique_control_count=len(keys)-len(flagged))


def window_starts(length):
    width, step = PARAMETERS['short_window'], PARAMETERS['step']
    if length < width:
        raise ValueError('Take shorter than short window')
    return sorted(set(range(0, length-width+1, step)) | {length-width})


def context_bounds(start, length):
    width = min(PARAMETERS['spectrum_window'], length)
    left = min(max(0, start+PARAMETERS['short_window']//2-width//2), length-width)
    return left, left+width


def source_context(take, takes):
    siblings = sorted((t for t in takes if t['stem'] == take['stem']
        and t['calibration_pass'] == take['calibration_pass']), key=lambda t: t['label_index'])
    position = next(i for i, row in enumerate(siblings) if row['key'] == take['key'])
    return dict(previous_note=siblings[position-1]['midi_note'] if position else None,
        next_note=siblings[position+1]['midi_note'] if position+1 < len(siblings) else None,
        open_note=min(t['midi_note'] for t in takes if t['stem'] == take['stem']))


def hypotheses(take, context, estimate):
    note = take['midi_note']
    values = dict(label=float(note), expected=note+take['expected_cents']/100.,
        label_minus_octave=float(note-12), label_plus_octave=float(note+12),
        open_string=float(context['open_note']))
    for name in ('previous_note', 'next_note'):
        if context[name] is not None:
            values[name] = float(context[name])
    if estimate['estimated_midi'] is not None:
        values['periodicity_estimate'] = estimate['estimated_midi']
    return values


def spectrum(signal):
    """Hann power spectrum; padding interpolates, not increases resolution."""
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1 or len(signal) < PARAMETERS['short_window'] or not np.isfinite(signal).all():
        raise ValueError('Invalid spectrum input')
    centered = signal-signal.mean()
    nfft = PARAMETERS['fft_padding'] * len(signal)
    power = np.abs(np.fft.rfft(centered*np.hanning(len(signal)), n=nfft))**2
    frequency = np.fft.rfftfreq(nfft, 1/PARAMETERS['sample_rate'])
    usable = (frequency >= PARAMETERS['spectral_low_hz']) & (frequency <= PARAMETERS['spectral_high_hz'])
    total = float(power[usable].sum())
    peaks, _ = find_peaks(power)
    peaks = [int(i) for i in peaks if usable[i]]
    peaks.sort(key=lambda i: power[i], reverse=True)
    top = []
    for i in peaks[:PARAMETERS['top_peaks']]:
        # Interpolation uses adjacent log-power bins, without a pitch hypothesis.
        y = np.log(np.maximum(power[i-1:i+2], 1e-300))
        denominator = y[0]-2*y[1]+y[2]
        shift = .5*(y[0]-y[2])/denominator if denominator < 0 else 0.
        hz = (i+float(np.clip(shift, -.5, .5)))*PARAMETERS['sample_rate']/nfft
        top.append(dict(hz=hz, midi=69+12*math.log2(hz/440.),
            peak_bin_fraction=float(power[i]/total) if total else 0.))
    return dict(frequency=frequency, power=power, usable=usable, total=total,
        native_bin_hz=PARAMETERS['sample_rate']/len(signal), top_peaks=top)


def harmonic_evidence(spec, midi):
    fundamental = 440*2**((midi-69)/12)
    masks, shares = [], []
    for harmonic in range(1, PARAMETERS['harmonics']+1):
        hz = fundamental*harmonic
        radius = max(PARAMETERS['band_native_bins']*spec['native_bin_hz'],
            hz*(2**(PARAMETERS['band_cents']/1200)-1))
        mask = (np.abs(spec['frequency']-hz) <= radius) & spec['usable']
        masks.append(mask)
        shares.append(float(spec['power'][mask].sum()/spec['total']) if spec['total'] else 0.)
    def union_share(selected):
        mask = np.logical_or.reduce(selected)
        return float(spec['power'][mask].sum()/spec['total']) if spec['total'] else 0.
    return dict(midi=float(midi), fundamental_hz=fundamental, harmonic_fractions=shares,
        union_fraction=union_share(masks), odd_union_fraction=union_share(masks[::2]),
        even_union_fraction=union_share(masks[1::2]))


def measure_take(signal, take, context):
    signal = np.asarray(signal, dtype=np.float64)
    if signal.shape != (take['end_sample']-take['start_sample'],) or not np.isfinite(signal).all():
        raise ValueError('Take waveform length or finiteness mismatch')
    rows, cached = [], {}
    for start in window_starts(len(signal)):
        estimate = diagnose_crop(signal[start:start+PARAMETERS['short_window']],
                                 take['midi_note'], take['expected_cents'])
        bounds = context_bounds(start, len(signal))
        if bounds not in cached:
            cached[bounds] = spectrum(signal[bounds[0]:bounds[1]])
        spec = cached[bounds]
        rows.append(dict(source_key=take['key'], start=start,
            end=start+PARAMETERS['short_window'], context_begin=bounds[0], context_end=bounds[1],
            **estimate, spectral_native_bin_hz=spec['native_bin_hz'],
            top_spectral_peaks=spec['top_peaks'],
            hypotheses={name: harmonic_evidence(spec, midi)
                for name, midi in hypotheses(take, context, estimate).items()}))
    categories = Counter(r['classification'] for r in rows)
    periodic = [r for r in rows if r['classification'].startswith('periodic_')]
    histogram = Counter(int(round(r['estimated_midi'])) for r in periodic)
    dominant_histogram = Counter(int(round(r['top_spectral_peaks'][0]['midi']))
        for r in rows if r['top_spectral_peaks'] and r['classification'] != 'silent')
    summary = dict(source_key=take['key'], role=take['role'], note=take['midi_note'],
        string_mask=take['string_mask'], expected_cents=take['expected_cents'], context=context,
        sample_count=len(signal), windows=len(rows), unique_spectral_windows=len(cached),
        classifications=dict(categories), periodic_nearest_midi_histogram=dict(sorted(histogram.items())),
        dominant_spectral_peak_midi_histogram=dict(sorted(dominant_histogram.items())),
        rms_dbfs_p05_p50_p95=np.percentile([r['rms_dbfs'] for r in rows], [5,50,95]).tolist(),
        hypothesis_medians={name: {field: float(np.median([r['hypotheses'][name][field] for r in rows]))
            for field in ('union_fraction', 'odd_union_fraction', 'even_union_fraction')}
            for name in hypotheses(take, context, dict(estimated_midi=None))},
        trajectory=[{key: row[key] for key in ('start','end','classification','estimated_midi',
            'cmnd_trough','rms_dbfs','context_begin','context_end','spectral_native_bin_hz')}
            for row in rows])
    return summary, rows
