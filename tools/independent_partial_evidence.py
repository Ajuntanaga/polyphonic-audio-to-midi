"""Causal, offline partial measurements; no MIDI decisions or fitted sources.

Peaks are measured from the mixture alone. Optional recorded components only
score where the measured energy came from; they never choose a peak or cue.
The fixed odd-partial cue is a falsifiable diagnostic, not a validated policy.
"""
from __future__ import annotations

import math

import numpy as np


CONFIG = dict(window_samples=16384, fft_samples=65536, hop_samples=1024,
              harmonics=6, peak_range_cents=50.0, odd_relative_power_floor=0.01,
              odd_agreement_cents=25.0,
              sideband_inner_window_bins=3.0, sideband_outer_window_bins=5.0)

# Frozen before examining calibration-pass-2 crops. This is a diagnostic screen,
# not a MIDI admission rule, and does not inherit the global power-floor cue.
FROZEN_SCREEN = dict(pair_prominence_db_exclusive=8.593275855114637,
                     agreement_cents_inclusive=25.0,
                     fitting_run='independent-partials-local-reference-20261103T2226Z')


def frozen_pair_screen(value):
    """Use mixture features only; missing evidence always abstains."""
    third, fifth = (value['partials'][h] for h in (2, 4))
    if third is None or fifth is None:
        return 'missing_peak'
    contrast = [peak.get('local_prominence_db') for peak in (third, fifth)]
    if any(number is None or not math.isfinite(number) for number in contrast):
        return 'missing_reference'
    if min(contrast) <= FROZEN_SCREEN['pair_prominence_db_exclusive']:
        return 'below_prominence'
    agreement = value.get('odd_raw_agreement_cents')
    if agreement is None or not math.isfinite(agreement):
        return 'missing_agreement'
    if not 0 <= agreement <= FROZEN_SCREEN['agreement_cents_inclusive']:
        return 'pitch_disagreement'
    return 'cue'


def frozen_cue_intervals(rows, *, sample_count, hop_samples=CONFIG['hop_samples']):
    """Export past-only note cues with a fixed expiry and no annotation input.

    A window ending at inclusive sample s is usable starting at s+1. Its cue
    expires one analysis hop later even if observations are missing. Intervals
    are half-open and contain no string assignment or component provenance.
    """
    if (type(sample_count) is not int or sample_count <= 0 or
            type(hop_samples) is not int or hop_samples <= 0):
        raise ValueError('invalid sidecar sample clock')
    previous = -1
    result = []
    for row in rows:
        sample = row['sample']
        if (type(sample) is not int or not previous < sample < sample_count or
                (sample + 1) % hop_samples != 0):
            raise ValueError('invalid observation clock for sidecar')
        previous = sample
        begin, end = sample + 1, min(sample + 1 + hop_samples, sample_count)
        if not row['history_available'] or begin == end:
            continue
        for note, value in sorted(row['notes'].items(), key=lambda item: int(item[0])):
            number = int(note)
            if str(number) != note or not 0 <= number <= 127:
                raise ValueError('invalid sidecar note')
            if frozen_pair_screen(value) == 'cue':
                result.append(dict(begin_sample=begin, end_sample=end, midi_note=number))
    return result


def score_frozen_screen(rows, *, start_sample, end_sample, window_samples):
    """Score fixed observations, separating causal window tail from clear gaps.

    Sample indices are inclusive; the first window wholly after the labeled
    interval ends at end_sample + window_samples - 1. Tail cues are reported,
    not silently counted as either note recovery or false output in a clear gap.
    """
    if not 0 <= start_sample < end_sample or window_samples < 1:
        raise ValueError('invalid scoring span or window')
    groups = {}
    previous = -1
    for row in rows:
        sample = row['sample']
        if sample <= previous:
            raise ValueError('non-increasing observation clock')
        previous = sample
        section = ('before_note' if sample < start_sample else
                   'note_interval' if sample < end_sample else
                   'window_tail' if sample < end_sample + window_samples - 1 else
                   'clear_gap')
        group = groups.setdefault(section, dict(frames=0, unavailable_history=0, notes={}))
        group['frames'] += 1
        if not row['history_available']:
            group['unavailable_history'] += 1
            continue
        for note, value in row['notes'].items():
            destination = group['notes'].setdefault(note, dict(observed_frames=0,
                cue_frames=0, first_cue_sample=None, last_cue_sample=None, reasons={}))
            destination['observed_frames'] += 1
            reason = frozen_pair_screen(value)
            destination['reasons'][reason] = destination['reasons'].get(reason, 0) + 1
            if reason == 'cue':
                destination['cue_frames'] += 1
                if destination['first_cue_sample'] is None:
                    destination['first_cue_sample'] = sample
                destination['last_cue_sample'] = sample
    return groups


def _distribution(values):
    return (dict(count=len(values), minimum=float(min(values)),
                 median=float(np.median(values)), maximum=float(max(values)))
            if values else None)


def _local_reference(power, frequencies, center, window_bin_hz, cfg):
    """Fixed nominal sidebands; the larger side median is the reference.

    Window bins use sample_rate/window_samples, not the zero-padded FFT grid.
    This is spectral contrast, not noise SNR or independent-source evidence.
    A missing or zero reference remains unavailable rather than infinite.
    """
    inner = cfg['sideband_inner_window_bins'] * window_bin_hz
    outer = cfg['sideband_outer_window_bins'] * window_bin_hz
    if center - outer <= frequencies[0] or center + outer >= frequencies[-1]:
        return None
    sides = [power[(frequencies >= center - outer) & (frequencies < center - inner)],
             power[(frequencies > center + inner) & (frequencies <= center + outer)]]
    if any(not len(side) for side in sides):
        return None
    reference = max(float(np.median(side)) for side in sides)
    return reference if reference > 0 else None


def _audio(values):
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 1 or not len(result) or not np.isfinite(result).all():
        raise ValueError('expected nonempty finite mono audio')
    return result


def measure(audio, sample_rate, notes=(36, 37), *, components=None, config=None):
    """Yield fixed-clock observations from windows ending at the current sample.

    Missing history and absent local peaks remain unavailable. The same signal
    calculation runs in source-only controls. No annotations or learned tuning
    enter the spectrum, peak search, or third/fifth-harmonic agreement cue.
    """
    wave = _audio(audio)
    cfg = dict(CONFIG if config is None else config)
    window, fft, hop = (cfg[key] for key in ('window_samples', 'fft_samples', 'hop_samples'))
    if (not isinstance(sample_rate, (int, float)) or not math.isfinite(sample_rate) or
            sample_rate <= 0 or any(type(x) is not int or x <= 0 for x in (window, fft, hop)) or
            window < 4 or fft < window or cfg['harmonics'] != 6 or
            not 0 < cfg['peak_range_cents'] <= 50 or
            not 0 < cfg['odd_relative_power_floor'] <= 1 or
            not 0 <= cfg['odd_agreement_cents'] <= 100 or
            not 2 <= cfg['sideband_inner_window_bins'] < cfg['sideband_outer_window_bins'] or
            not math.isfinite(cfg['sideband_outer_window_bins']) or
            not notes or len(set(notes)) != len(notes) or
            any(type(note) is not int or not 0 <= note <= 127 for note in notes)):
        raise ValueError('invalid analysis geometry')
    sources = {key: _audio(values) for key, values in (components or {}).items()}
    if any(values.shape != wave.shape for values in sources.values()):
        raise ValueError('component shape differs from mixture')
    frequencies = np.fft.rfftfreq(fft, 1.0 / sample_rate)
    if max(440.0 * 2 ** ((note - 69) / 12) * 6 for note in notes) * 2 ** (50 / 1200) >= sample_rate / 2:
        raise ValueError('analysis harmonics exceed Nyquist')
    taper = np.hanning(window)
    normalizer = 2.0 / float(taper.sum())
    for stop in range(hop, len(wave) + 1, hop):
        result = dict(sample=stop - 1, history_available=stop >= window, notes={})
        if stop < window:
            yield result
            continue
        segment = wave[stop - window:stop]
        transform = np.fft.rfft(segment * taper, n=fft) * normalizer
        power = np.abs(transform) ** 2
        scene_peak_power = float(power.max())
        # Both neighbors are required. Silence and flat spectra have no peaks.
        peaks = np.flatnonzero((power[1:-1] > power[:-2]) &
                               (power[1:-1] > power[2:])) + 1
        source_power = {key: np.abs(np.fft.rfft(values[stop - window:stop] * taper,
                                              n=fft) * normalizer) ** 2
                        for key, values in sources.items()}
        for note in notes:
            fundamental = 440.0 * 2 ** ((note - 69) / 12)
            partials = []
            for harmonic in range(1, 7):
                center = fundamental * harmonic
                # Interpolate first, then apply the half-open note corridor.
                # This avoids rejecting a valid edge peak due to FFT binning.
                margin = sample_rate / fft
                low = center * 2 ** (-cfg['peak_range_cents'] / 1200)
                high = center * 2 ** (cfg['peak_range_cents'] / 1200)
                possible = peaks[(frequencies[peaks] >= low - margin) &
                                 (frequencies[peaks] < high + margin)]
                chosen = []
                for index in possible:
                    log_power = np.log(np.maximum(power[index - 1:index + 2], np.finfo(float).tiny))
                    denominator = log_power[0] - 2 * log_power[1] + log_power[2]
                    delta = 0.5 * (log_power[0] - log_power[2]) / denominator
                    hz = (float(index) + float(delta)) * sample_rate / fft
                    cents = 1200 * math.log2(hz / center)
                    if not -cfg['peak_range_cents'] <= cents < cfg['peak_range_cents']:
                        continue
                    chosen.append((float(power[index]), int(index), hz, cents))
                peak = None
                if chosen:
                    amplitude, index, hz, cents = max(chosen)
                    peak = dict(frequency_hz=hz, cents=cents, power=amplitude,
                                fft_bin=index)
                    reference = _local_reference(power, frequencies, center,
                                                 sample_rate / window, cfg)
                    peak['local_reference_power'] = reference
                    peak['local_prominence_db'] = (
                        10 * (math.log10(amplitude) - math.log10(reference))
                        if reference is not None else None)
                    if sources:
                        powers = {key: float(values[index]) for key, values in source_power.items()}
                        total = sum(powers.values())
                        peak['oracle_component_power'] = powers
                        peak['oracle_component_power_share'] = {
                            key: value / total if total > 0 else None for key, value in powers.items()}
                partials.append(peak)
            largest = max((peak['power'] for peak in partials if peak), default=0.0)
            for peak in partials:
                if peak:
                    # A candidate containing only Hann sidelobes must not make
                    # those sidelobes look strong by normalizing to itself.
                    peak['candidate_relative_power'] = peak['power'] / largest if largest > 0 else 0.0
                    peak['relative_power'] = peak['power'] / scene_peak_power if scene_peak_power > 0 else 0.0
            third, fifth = partials[2], partials[4]
            support = [bool(peak and peak['relative_power'] >= cfg['odd_relative_power_floor'])
                       for peak in (third, fifth)]
            agreement = (abs(third['cents'] - fifth['cents'])
                         if all(support) else None)
            result['notes'][str(note)] = dict(partials=partials, odd_support=support,
                odd_raw_agreement_cents=(abs(third['cents'] - fifth['cents'])
                                         if third and fifth else None),
                odd_agreement_cents=agreement,
                odd_pair_cue=bool(agreement is not None and agreement <= cfg['odd_agreement_cents']))
        yield result


def summarize(rows, *, start_sample, end_sample, sample_rate, notes=(36, 37)):
    """Annotations only partition already-computed observations for evaluation."""
    if not 0 <= start_sample < end_sample or sample_rate <= 0:
        raise ValueError('invalid scoring span')
    groups = {}
    previous = -1
    for row in rows:
        sample = row['sample']
        if sample <= previous:
            raise ValueError('non-increasing observation clock')
        previous = sample
        if sample < start_sample:
            age = 'before_note'
        elif sample >= end_sample:
            age = 'after_note'
        elif (sample - start_sample) / sample_rate < 0.1:
            age = 'attack_0_100ms'
        elif (sample - start_sample) / sample_rate < 0.35:
            age = 'early_100_350ms'
        else:
            age = 'sustain_350ms_plus'
        group = groups.setdefault(age, dict(frames=0, unavailable_history=0, notes={}))
        group['frames'] += 1
        if not row['history_available']:
            group['unavailable_history'] += 1
            continue
        for note in notes:
            value = row['notes'][str(note)]
            measured = group['notes'].setdefault(str(note), dict(
                observed_frames=0, odd_pair_cue_frames=0, odd_pair_target_dominated_frames=0,
                third_supported_frames=0, fifth_supported_frames=0,
                odd_both_peak_frames=0, odd_both_supported_frames=0,
                odd_raw_agreement_cents=[],
                partials=[dict(peak_frames=0, relative_power=[], cents=[],
                               local_prominence_db=[], oracle_target_share=[]) for _ in range(6)]))
            measured['observed_frames'] += 1
            measured['third_supported_frames'] += int(value['odd_support'][0])
            measured['fifth_supported_frames'] += int(value['odd_support'][1])
            measured['odd_both_supported_frames'] += int(all(value['odd_support']))
            if value['odd_raw_agreement_cents'] is not None:
                measured['odd_both_peak_frames'] += 1
                measured['odd_raw_agreement_cents'].append(value['odd_raw_agreement_cents'])
            measured['odd_pair_cue_frames'] += int(value['odd_pair_cue'])
            if value['odd_pair_cue']:
                shares = [(value['partials'][h].get('oracle_component_power_share') or {}).get('target')
                          for h in (2, 4)]
                measured['odd_pair_target_dominated_frames'] += int(
                    all(share is not None and share >= 0.9 for share in shares))
            for dest, peak in zip(measured['partials'], value['partials']):
                if peak is None:
                    continue
                dest['peak_frames'] += 1
                dest['relative_power'].append(peak['relative_power'])
                dest['cents'].append(peak['cents'])
                if peak['local_prominence_db'] is not None:
                    dest['local_prominence_db'].append(peak['local_prominence_db'])
                share = peak.get('oracle_component_power_share', {}).get('target')
                if share is not None:
                    dest['oracle_target_share'].append(share)
    for group in groups.values():
        for value in group['notes'].values():
            value['odd_raw_agreement_cents_distribution'] = _distribution(
                value.pop('odd_raw_agreement_cents'))
            for partial in value['partials']:
                for key in ('relative_power', 'cents', 'local_prominence_db', 'oracle_target_share'):
                    partial[key + '_distribution'] = _distribution(partial.pop(key))
    return groups


def compare_local_reference(cases, *, target_note=36, alternate_note=37):
    """Describe in-sample feature overlap; never return an admission decision.

    Each case has rows, source_only, start_sample and end_sample. Annotations
    select evaluation clocks only. Both low-note hypotheses in source-only
    controls, and the absent alternate note in mixtures, are negative examples.
    A control maximum is descriptive, not a fitted or held-out safety threshold.
    """
    if not cases or target_note == alternate_note or not any(
            case['source_only'] for case in cases.values()):
        raise ValueError('target, alternate and source-only controls are required')
    positives, negatives = {}, {}
    for name, case in cases.items():
        if not 0 <= case['start_sample'] < case['end_sample']:
            raise ValueError('invalid scoring span')
        rows = [row for row in case['rows'] if row['history_available'] and
                case['start_sample'] <= row['sample'] < case['end_sample']]
        for note in (target_note, alternate_note):
            records = []
            for row in rows:
                value = row['notes'][str(note)]
                third, fifth = (value['partials'][h] for h in (2, 4))
                pair = (min(third['local_prominence_db'], fifth['local_prominence_db'])
                        if third and fifth and third['local_prominence_db'] is not None and
                        fifth['local_prominence_db'] is not None else None)
                shares = [(peak.get('oracle_component_power_share') or {}).get('target')
                          if peak else None for peak in (third, fifth)]
                records.append(dict(h5=fifth['local_prominence_db'] if fifth else None,
                    odd_pair=pair,
                    h5_target_dominated=shares[1] is not None and shares[1] >= 0.9,
                    odd_pair_target_dominated=all(share is not None and share >= 0.9 for share in shares)))
            destination = negatives if case['source_only'] or note == alternate_note else positives
            destination[name + ':note' + str(note)] = records
    report = dict(target_note=target_note, alternate_note=alternate_note,
                  interpretation='In-sample spectral contrast only; no policy, independence or held-out claim.',
                  negative_cases={}, target_present_cases={}, control_envelopes={})
    for key in ('h5', 'odd_pair'):
        controls = [row[key] for rows in negatives.values() for row in rows if row[key] is not None]
        maximum = max(controls) if controls else None
        report['control_envelopes'][key] = _distribution(controls)
        for section, observations in (('negative_cases', negatives), ('target_present_cases', positives)):
            for name, rows in observations.items():
                dest = report[section].setdefault(name, dict(observed_frames=len(rows)))
                dest[key + '_distribution'] = _distribution([row[key] for row in rows if row[key] is not None])
                if section == 'target_present_cases':
                    selected = ([row for row in rows if row[key] is not None and row[key] > maximum]
                                if maximum is not None else None)
                    dest[key + '_above_negative_max_frames'] = len(selected) if selected is not None else None
                    dest[key + '_above_negative_max_target_dominated_frames'] = (
                        sum(row[key + '_target_dominated'] for row in selected) if selected is not None else None)
    return report
