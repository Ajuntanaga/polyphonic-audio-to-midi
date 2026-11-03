"""Causal measurements of *mixture* harmonic motion, never source-count votes.

Inputs are measured, complex, demodulated harmonic tracks. Phase differences
describe those filtered tracks; they do not establish a source's instantaneous
frequency, an SNR, or a source-dominant reference. No label or fitted component
is accepted as an input. All summaries use only the supplied prefix.
"""

from __future__ import annotations

import itertools

import numpy as np


def condition_mixture_tracks(times, signal, *, observation_period,
                             time_constant=0.015):
    """Apply two causal complex EMA stages before differentiating phase.

    The fixed 15 ms reference matches the production fundamental's phasor
    smoothing, but this offline filter does not replicate its active-state
    resets or frequency smoother. It cannot undo aliases already present in
    the captured tracks or turn a mixture into a source-pure measurement.
    Missing values/time gaps reset both stages; no future sample fills a gap.
    """
    times = np.asarray(times, dtype=float)
    signal = np.asarray(signal, dtype=complex)
    if (times.ndim != 1 or not len(times) or signal.ndim != 2
            or signal.shape[1] != len(times) or not 1 <= len(signal) <= 6
            or not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0)
            or not np.isfinite(observation_period) or observation_period <= 0
            or not np.isfinite(time_constant) or time_constant <= 0):
        raise ValueError('expected finite increasing times, bands and positive clocks')
    result = np.full_like(signal, complex(np.nan, np.nan))
    first = np.zeros(len(signal), dtype=complex)
    second = np.zeros_like(first)
    for index in range(len(times)):
        dt = observation_period if index == 0 else times[index] - times[index - 1]
        if dt > 3 * observation_period:
            first[:] = second[:] = 0
            dt = observation_period
        valid = np.isfinite(signal[:, index])
        first[~valid] = second[~valid] = 0
        mix = -np.expm1(-dt / time_constant)
        first[valid] += mix * (signal[valid, index] - first[valid])
        second[valid] += mix * (first[valid] - second[valid])
        result[valid, index] = second[valid]
    return result


def trajectories(times, signal, center_hz, *, relative_floor=1e-3,
                 maximum_phase_increment=0.8 * np.pi):
    """Return aligned past-only phase and envelope increments.

    The amplitude floor is relative to the largest earlier measured amplitude
    across bands. It is gain invariant, but is not a calibrated noise floor.
    Large increments are withheld rather than unwrapped across uncertain gaps.
    Unobserved aliases can still exist; this is a conservative sampling check,
    not proof of phase validity. Invalid samples are never bridged.
    """
    times = np.asarray(times, dtype=float)
    signal = np.asarray(signal, dtype=complex)
    if (times.ndim != 1 or len(times) < 3 or signal.ndim != 2
            or signal.shape[1] != len(times) or not 1 <= signal.shape[0] <= 6):
        raise ValueError('expected at least three times and one through six bands')
    if (not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0)
            or not np.isfinite(center_hz) or center_hz <= 0):
        raise ValueError('times must increase and center frequency must be positive')
    if not (0 < relative_floor < 1 and 0 < maximum_phase_increment < np.pi):
        raise ValueError('invalid amplitude or phase increment bound')
    finite = np.isfinite(signal.real) & np.isfinite(signal.imag)
    amplitude = np.abs(np.where(finite, signal, 0))
    prior_peak = np.maximum.accumulate(np.max(amplitude, axis=0))
    observed = finite & (amplitude > relative_floor * prior_peak[None, :])
    dt = np.diff(times)
    # A missing stretch may contain any number of phase turns. Use only earlier
    # cadence information, so appending a denser suffix cannot alter this prefix.
    contiguous = dt <= 3 * np.minimum.accumulate(dt)
    step_phase = np.angle(signal[:, 1:] * np.conj(signal[:, :-1]))
    valid = (observed[:, 1:] & observed[:, :-1]
             & contiguous[None, :]
             & np.isfinite(step_phase)
             & (np.abs(step_phase) < maximum_phase_increment))
    harmonic = np.arange(1, len(signal) + 1)[:, None]
    relative_hz = step_phase / (2 * np.pi * dt[None, :] * harmonic)
    ratio = 1 + relative_hz / center_hz
    valid &= ratio > 0
    # These diagnostic flags may overlap. Their union is the existing rejection
    # rule; recording a reason must not change a measurement or admit a sample.
    rejection_reasons = {
        'nonfinite_sample': ~(finite[:, 1:] & finite[:, :-1]),
        'weak_or_zero_amplitude': ((finite[:, 1:] & ~observed[:, 1:])
                                   | (finite[:, :-1] & ~observed[:, :-1])),
        'observation_gap': np.broadcast_to(~contiguous, valid.shape).copy(),
        'nonfinite_phase_step': ((finite[:, 1:] & finite[:, :-1]) & ~np.isfinite(step_phase)),
        'phase_step': np.isfinite(step_phase) & (np.abs(step_phase) >= maximum_phase_increment),
        'invalid_frequency': np.isfinite(step_phase) & ~(ratio > 0),
    }
    amplitude_ratio = np.zeros_like(amplitude)
    np.divide(amplitude, prior_peak[None, :], out=amplitude_ratio,
              where=finite & (prior_peak[None, :] > 0))
    amplitude_ratio[~finite] = np.nan
    cents = np.full_like(relative_hz, np.nan)
    np.log2(ratio, out=cents, where=valid)
    cents *= 1200
    log_amplitude = np.full_like(amplitude, np.nan)
    np.log(amplitude, out=log_amplitude, where=observed)
    envelope_rate = np.diff(log_amplitude, axis=1) / dt[None, :]
    envelope_rate[~valid] = np.nan
    # Both frequency estimates must be observed. Do not cross a missing sample.
    motion_valid = valid[:, 1:] & valid[:, :-1]
    midpoint_spacing = (dt[1:] + dt[:-1]) / 2
    frequency_motion = np.diff(cents, axis=1) / midpoint_spacing[None, :]
    frequency_motion[~motion_valid] = np.nan
    return {'increment_times': times[1:], 'valid': valid, 'cents': cents,
            'envelope_rate': envelope_rate, 'motion_times': times[2:],
            'motion_valid': motion_valid, 'frequency_motion': frequency_motion,
            'rejection_reasons': rejection_reasons,
            'minimum_endpoint_amplitude_ratio': np.minimum(
                amplitude_ratio[:, 1:], amplitude_ratio[:, :-1]),
            'relative_amplitude_floor': relative_floor}


def _correlation(a, b):
    a, b = a - np.mean(a), b - np.mean(b)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    # Flat trajectories have no measured correlation; do not call them agreement.
    if denominator <= 1e-12 * max(1, len(a)):
        return None
    return float(np.clip(np.dot(a, b) / denominator, -1, 1))


def phase_window_trajectories(times, signal, center_hz, *, window_seconds=0.160):
    """Fit phase slopes on complete past windows, emitting once per window.

    This offline observation uses the existing 160 ms phase-evidence timescale.
    It neither shortens the three-second unison admission window nor identifies
    strings. A least-squares slope describes the preceding window, not the
    instantaneous frequency at its end. All increments in a window must pass
    the causal amplitude, gap and phase-step checks; none are interpolated.
    """
    if not np.isfinite(window_seconds) or window_seconds <= 0:
        raise ValueError('phase window must be positive and finite')
    times = np.asarray(times, dtype=float)
    signal = np.asarray(signal, dtype=complex)
    increments = trajectories(times, signal, center_hz)
    count = int(np.ceil((times[-1] - times[0]) / window_seconds))
    deadlines = times[0] + window_seconds * np.arange(1, count + 1)
    # Emit only once that deadline has actually been observed. Repeated indexes
    # after a capture gap cannot manufacture additional measurements.
    ends = np.unique(np.searchsorted(times, deadlines, side='left'))
    ends = ends[ends < len(times)]
    starts = np.searchsorted(times, times[ends] - window_seconds, side='right') - 1
    valid = np.zeros((len(signal), len(ends)), dtype=bool)
    cents = np.full(valid.shape, np.nan)
    envelope_rate = np.full(valid.shape, np.nan)
    phase_fit_rms = np.full(valid.shape, np.nan)
    rejection_reasons = {key: np.zeros_like(valid)
                         for key in increments['rejection_reasons']}
    rejection_reasons['insufficient_observations'] = np.zeros_like(valid)
    estimate_times = np.full(len(ends), np.nan)
    phase_steps = np.angle(signal[:, 1:] * np.conj(signal[:, :-1]))
    for column, (start, end) in enumerate(zip(starts, ends)):
        if start < 0 or end - start < 2:
            rejection_reasons['insufficient_observations'][:, column] = True
            continue
        relative_time = times[start:end + 1] - times[start]
        centered = relative_time - np.mean(relative_time)
        variance = float(np.dot(centered, centered))
        if variance <= 0:
            rejection_reasons['insufficient_observations'][:, column] = True
            continue
        # Effective slope time for a quadratic phase, including irregular clocks.
        estimate_times[column] = (times[start] + np.mean(relative_time)
                                  + np.sum(centered ** 3) / (2 * variance))
        for band in range(len(signal)):
            for reason, rejected in increments['rejection_reasons'].items():
                rejection_reasons[reason][band, column] = rejected[band, start:end].any()
            if not increments['valid'][band, start:end].all():
                continue
            phase = np.r_[0., np.cumsum(phase_steps[band, start:end])]
            slope = np.dot(centered, phase) / variance
            ratio = 1 + slope / (2 * np.pi * (band + 1) * center_hz)
            if not np.isfinite(ratio) or ratio <= 0:
                rejection_reasons['invalid_frequency'][band, column] = True
                continue
            cents[band, column] = 1200 * np.log2(ratio)
            log_amplitude = np.log(np.abs(signal[band, start:end + 1]))
            envelope_rate[band, column] = np.dot(centered, log_amplitude) / variance
            residual = phase - np.mean(phase) - slope * centered
            phase_fit_rms[band, column] = np.sqrt(np.mean(residual ** 2))
            valid[band, column] = True
    elapsed = np.diff(estimate_times)
    consecutive = ((np.diff(times[ends]) <= 1.5 * window_seconds)
                   & np.isfinite(elapsed) & (elapsed > 0))
    motion_valid = valid[:, 1:] & valid[:, :-1] & consecutive[None, :]
    motion = np.full((len(signal), max(0, len(ends) - 1)), np.nan)
    np.divide(np.diff(cents, axis=1), elapsed[None, :], out=motion, where=motion_valid)
    return {'increment_times': times[ends], 'estimate_times': estimate_times,
            'valid': valid, 'cents': cents, 'envelope_rate': envelope_rate,
            'motion_times': times[ends[1:]], 'motion_valid': motion_valid,
            'frequency_motion': motion, 'window_seconds': window_seconds,
            'phase_fit_rms_radians': phase_fit_rms,
            'rejection_reasons': rejection_reasons}


def summarize_reference_quality(increments, windows, enabled_bands, start_time, end_time):
    """Explain measurement availability; never infer SNR or source purity.

    Inputs must already cover the full causal prefix. Scoring boundaries only
    choose observations by their availability time. Disabled detector bands are
    reported separately from weak signal. Rejection reasons overlap, and a low
    phase-fit residual means a locally smooth mixture, not a source reference.
    """
    enabled = np.asarray(enabled_bands, dtype=bool)
    bands = len(increments['valid'])
    if (enabled.shape != (bands,) or len(windows['valid']) != bands
            or not np.isfinite(start_time) or not np.isfinite(end_time)
            or end_time <= start_time):
        raise ValueError('expected matching bands and a finite increasing scoring span')

    def select(track):
        return ((track['increment_times'] >= start_time)
                & (track['increment_times'] < end_time))

    def quantiles(values):
        values = values[np.isfinite(values)]
        return ({'p10': float(np.percentile(values, 10)),
                 'p50': float(np.percentile(values, 50)),
                 'p90': float(np.percentile(values, 90))} if len(values)
                else {'p10': None, 'p50': None, 'p90': None})

    increment_keep, window_keep = select(increments), select(windows)
    total_increments, total_windows = int(increment_keep.sum()), int(window_keep.sum())
    result = []
    for band in range(bands):
        active = bool(enabled[band])
        valid_increments = int(increments['valid'][band, increment_keep].sum()) if active else 0
        valid_windows = int(windows['valid'][band, window_keep].sum()) if active else 0
        result.append({
            'harmonic': band + 1, 'enabled': active,
            'increments': total_increments, 'valid_increments': valid_increments,
            'valid_increment_fraction': valid_increments / total_increments if total_increments else None,
            'windows': total_windows, 'valid_windows': valid_windows,
            'valid_window_fraction': valid_windows / total_windows if total_windows else None,
            'rejected_increment_counts': {key: int(flags[band, increment_keep].sum())
                                          for key, flags in increments['rejection_reasons'].items()}
                if active else {'disabled_band': total_increments},
            'rejected_window_counts': {key: int(flags[band, window_keep].sum())
                                       for key, flags in windows['rejection_reasons'].items()}
                if active else {'disabled_band': total_windows},
            'minimum_endpoint_amplitude_ratio': quantiles(
                increments['minimum_endpoint_amplitude_ratio'][band, increment_keep]) if active else None,
            'phase_fit_rms_radians': quantiles(
                windows['phase_fit_rms_radians'][band, window_keep]) if active else None,
        })
    return {'bands': result, 'rejection_counts_overlap': True,
            'amplitude_reference': 'largest amplitude across bands observed so far; not a noise floor',
            'relative_amplitude_floor': increments['relative_amplitude_floor'],
            'phase_fit_meaning': 'linear-phase fit residual on accepted windows; not source purity',
            'scoring': 'availability timestamp inside span; past window may begin before span',
            'source_dominant_reference': 'not measured', 'string_mask_decision': None}


def _summarize_tracks(track, bands, samples, minimum_increments):
    if minimum_increments < 3:
        raise ValueError('at least three increments are required')
    pairs = []
    for first, second in itertools.combinations(range(bands), 2):
        phase_valid = track['motion_valid'][first] & track['motion_valid'][second]
        envelope_valid = track['valid'][first] & track['valid'][second]
        phase_count, envelope_count = int(phase_valid.sum()), int(envelope_valid.sum())
        a, b = track['frequency_motion'][[first, second]][:, phase_valid]
        c, d = track['envelope_rate'][[first, second]][:, envelope_valid]
        pairs.append({
            'harmonics': [first + 1, second + 1],
            'frequency_motion_samples': phase_count,
            'envelope_motion_samples': envelope_count,
            'frequency_motion_correlation': _correlation(a, b)
                if phase_count >= minimum_increments else None,
            'envelope_motion_correlation': _correlation(c, d)
                if envelope_count >= minimum_increments else None,
            'differential_frequency_motion_rms_cents_per_second':
                float(np.sqrt(np.mean((a - b) ** 2)))
                if phase_count >= minimum_increments else None,
        })
    return {
        'harmonic_bands': bands, 'samples': samples,
        'valid_increment_counts': track['valid'].sum(axis=1).tolist(),
        'pairs': pairs, 'measurement_kind': 'filtered_mixture_tracks',
        'source_dominant_reference': 'not measured',
        'string_mask_decision': None, 'posterior_probability': None,
    }


def summarize_motion(times, signal, center_hz, *, minimum_increments=12):
    """Extract window features; absent motion remains null, not a zero vote."""
    return _summarize_tracks(trajectories(times, signal, center_hz),
                             len(signal), len(times), minimum_increments)


def summarize_phase_windows(track, start_time, end_time, *, minimum_increments=12):
    """Score already-causal measurements whose availability is inside a span.

    Annotations select the scoring span only. They never reset the estimator or
    supply its frequency, phase, window clock, or valid-signal history.
    """
    if not np.isfinite(start_time) or not np.isfinite(end_time) or end_time <= start_time:
        raise ValueError('expected a finite increasing scoring span')
    slope_keep = ((track['increment_times'] >= start_time)
                  & (track['increment_times'] < end_time))
    motion_keep = ((track['motion_times'] >= start_time)
                   & (track['motion_times'] < end_time))
    selected = {key: track[key][:, slope_keep]
                for key in ('valid', 'cents', 'envelope_rate')}
    selected.update({key: track[key][:, motion_keep]
                     for key in ('motion_valid', 'frequency_motion')})
    result = _summarize_tracks(selected, len(track['cents']), int(slope_keep.sum()),
                               minimum_increments)
    result.update(window_seconds=track['window_seconds'],
                  frequency_estimator='past-window least-squares phase slope')
    return result


def validate_join(first, second):
    """Fail closed on absent or conflicting causal observation identities."""
    keys = ('audio_sha256', 'calibration_sha256', 'sample_rate',
            'sample_origin', 'decision_sample', 'note', 'settings_sha256')
    missing = [key for key in keys if first.get(key) is None or second.get(key) is None]
    mismatched = [key for key in keys if key not in missing and first[key] != second[key]]
    return {'joinable': not missing and not mismatched,
            'missing': missing, 'mismatched': mismatched}
