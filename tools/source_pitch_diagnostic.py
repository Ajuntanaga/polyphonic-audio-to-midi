"""Source-crop periodicity and level diagnostics; no labels are changed.

Pure helpers for synthetic tests. Recorded input belongs to the GitHub runner.
This is a fixed-window YIN-style estimator (difference, cumulative normalization,
first threshold trough, parabolic interpolation), without temporal correction.
Periodicity agreement is not proof of audibility or the played string.
"""
from collections import Counter, defaultdict
import math

import numpy as np
from scipy.signal import correlate, resample_poly

from tools.direct_spectrum_learning import SETTINGS


# Retain 48 kHz so high-register harmonic signals have enough lag resolution;
# at 12 kHz a clean missing-fundamental MIDI84 signal skipped its first trough.
PARAMETERS = dict(downsample=2, note_min=28, note_max=96,
    trough_threshold=0.1, target_tolerance_cents=50.0,
    numerical_silence_rms=1e-12, component_rms=0.05)
CLASSES = ('periodic_target', 'periodic_other', 'unresolved_periodicity', 'silent')


def normalized_difference(signal, max_lag):
    """Fixed integration length at every lag, including cumulative lags from 1."""
    signal = np.asarray(signal, dtype=np.float64)
    width = len(signal)-max_lag
    if width <= max_lag or not np.isfinite(signal).all():
        raise ValueError('Invalid difference-function input')
    base = signal[:width]
    cross = correlate(signal, base, mode='valid', method='fft')
    cumulative = np.r_[0.0, np.cumsum(signal*signal)]
    energy = cumulative[width:width+max_lag+1]-cumulative[:max_lag+1]
    difference = np.maximum(float(base@base)+energy-2*cross, 0.0)
    difference[0] = 0.0
    denominator = np.cumsum(difference[1:])
    normalized = np.ones(max_lag+1)
    np.divide(difference[1:]*np.arange(1, max_lag+1), denominator,
              out=normalized[1:], where=denominator > 0)
    return difference, normalized


def diagnose_crop(crop, note, expected_cents):
    crop = np.asarray(crop, dtype=np.float64)
    if crop.shape != (16384,) or not np.isfinite(crop).all():
        raise ValueError('Expected one finite 16384-sample source crop')
    rms = float(np.sqrt(np.mean(crop*crop)))
    gain = PARAMETERS['component_rms']/max(rms, SETTINGS['normalization_floor'])
    result = dict(rms=rms, rms_dbfs=20*math.log10(max(rms, 1e-15)),
        normalization_gain_db=20*math.log10(gain), f0_hz=None,
        estimated_midi=None, cmnd_trough=None, threshold_trough_found=False,
        cents_from_label=None, cents_from_expected=None, classification='silent')
    if rms <= PARAMETERS['numerical_silence_rms']:
        return result
    signal = resample_poly(crop, 1, PARAMETERS['downsample'])
    signal -= signal.mean()
    rate = SETTINGS['sample_rate']/PARAMETERS['downsample']
    low = 440*2**((PARAMETERS['note_min']-69)/12)
    high = 440*2**((PARAMETERS['note_max']-69)/12)
    first, last = math.floor(rate/high), math.ceil(rate/low)
    _, cmnd = normalized_difference(signal, last+1)
    minima = [lag for lag in range(first, last+1)
              if cmnd[lag] <= cmnd[lag-1] and cmnd[lag] < cmnd[lag+1]]
    below = [lag for lag in minima if cmnd[lag] < PARAMETERS['trough_threshold']]
    lag = below[0] if below else int(np.argmin(cmnd[first:last+1]))+first
    denominator = cmnd[lag-1]-2*cmnd[lag]+cmnd[lag+1]
    shift = 0.5*(cmnd[lag-1]-cmnd[lag+1])/denominator if denominator > 0 else 0.0
    period = lag+float(np.clip(shift, -.5, .5))
    frequency = rate/period
    midi = 69+12*math.log2(frequency/440)
    cents = 100*(midi-note)
    periodic = bool(below) and low <= frequency <= high
    category = ('periodic_target' if abs(cents) <= PARAMETERS['target_tolerance_cents']
                else 'periodic_other') if periodic else 'unresolved_periodicity'
    result.update(f0_hz=frequency, estimated_midi=midi, cmnd_trough=float(cmnd[lag]),
        threshold_trough_found=bool(below), cents_from_label=cents,
        cents_from_expected=cents-float(expected_cents), classification=category)
    return result


def crop_key(row):
    return row['source_key'], int(row['crop_begin']), int(row['crop_end'])


def crop_inventory(takes, plans, templates):
    """Every actual component/template crop, deduplicated without dropping a take."""
    by_key = {take['key']: take for take in takes}
    inventory = {}
    def add(component, exposure):
        key = crop_key(component)
        take = by_key[component['source_key']]
        if (component['stem'] != take['stem'] or component['note'] != take['midi_note']
                or component['string_mask'] != take['string_mask']
                or not take['start_sample'] <= key[1] < key[2] <= take['end_sample']
                or key[2]-key[1] != 16384):
            raise ValueError('Saved crop differs from source manifest')
        row = inventory.setdefault(key, dict(source_key=key[0], stem=take['stem'],
            role=take['role'], note=take['midi_note'], expected_cents=take['expected_cents'],
            crop_begin=key[1], crop_end=key[2], mixture_exposures=0, template_exposures=0))
        row[exposure] += 1
    for role, plan in plans.items():
        for row in plan:
            if row['role'] != role:
                raise ValueError('Mixture role differs')
            for component in row['components']:
                if by_key[component['source_key']]['role'] != role:
                    raise ValueError('Source crosses roles')
                add(component, 'mixture_exposures')
    if set(key[0] for key in inventory) != set(by_key):
        raise ValueError('Not every source take has a mixture crop')
    for row in templates:
        if by_key[row['source_key']]['role'] != 'train':
            raise ValueError('Template crosses training role')
        for left, right in row['crops']:
            add(dict(row, crop_begin=left, crop_end=right), 'template_exposures')
    return [inventory[key] for key in sorted(inventory)]


def describe(rows, weight=None):
    counts = Counter()
    for row in rows:
        counts[row['classification']] += row[weight] if weight else 1
    result = dict(count=sum(counts.values()),
        classes={name: counts[name] for name in CLASSES})
    if weight is None:
        for name in ('rms_dbfs', 'normalization_gain_db'):
            result[name+'_p05_p50_p95'] = np.percentile(
                [row[name] for row in rows], [5,50,95]).tolist() if rows else None
        result['gain_ge20db_windows'] = sum(row['normalization_gain_db'] >= 20 for row in rows)
        result['gain_ge40db_windows'] = sum(row['normalization_gain_db'] >= 40 for row in rows)
        estimates = [int(round(row['estimated_midi'])) for row in rows
                     if row['classification'].startswith('periodic_')]
        result['periodic_nearest_midi_histogram'] = dict(sorted(Counter(estimates).items()))
    return result


def summarize(takes, rows, plans):
    by_source = defaultdict(list)
    lookup = {}
    for row in rows:
        by_source[row['source_key']].append(row)
        key = crop_key(row)
        if key in lookup:
            raise ValueError('Duplicate crop measurement')
        lookup[key] = row
    if set(by_source) != {take['key'] for take in takes}:
        raise ValueError('Measured source coverage differs')
    sources = []
    for take in takes:
        subset = by_source[take['key']]
        sources.append(dict(source_key=take['key'], role=take['role'], note=take['midi_note'],
            string_mask=take['string_mask'], expected_cents=take['expected_cents'],
            unique_crops=describe(subset), mixture_exposures=describe(subset, 'mixture_exposures'),
            template_exposures=describe(subset, 'template_exposures')))
    roles = {}
    for role, plan in plans.items():
        subset = [row for row in rows if row['role'] == role]
        mixture_classes = Counter()
        for example in plan:
            categories = [lookup[crop_key(component)]['classification']
                          for component in example['components']]
            category = ('intentional_silence' if not categories else
                'all_components_periodic_target' if all(c == 'periodic_target' for c in categories)
                else 'contains_periodic_other' if 'periodic_other' in categories
                else 'contains_unresolved_or_silent')
            mixture_classes[category] += 1
        exposure = describe(subset, 'mixture_exposures')
        if exposure['count'] != sum(len(example['components']) for example in plan):
            raise ValueError('Component exposure conservation failed')
        roles[role] = dict(takes=sum(take['role'] == role for take in takes),
            unique_crops=describe(subset), component_exposures=exposure,
            mixtures=dict(examples=len(plan), classes=dict(mixture_classes)))
    return dict(source_count=len(sources), unique_crop_count=len(rows),
                all_sources_retained=True, sources=sources, roles=roles)
