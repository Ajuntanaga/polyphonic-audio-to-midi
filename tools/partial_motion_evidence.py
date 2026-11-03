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
            'motion_valid': motion_valid, 'frequency_motion': frequency_motion}


def _correlation(a, b):
    a, b = a - np.mean(a), b - np.mean(b)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    # Flat trajectories have no measured correlation; do not call them agreement.
    if denominator <= 1e-12 * max(1, len(a)):
        return None
    return float(np.clip(np.dot(a, b) / denominator, -1, 1))


def summarize_motion(times, signal, center_hz, *, minimum_increments=12):
    """Extract window features; absent motion remains null, not a zero vote."""
    if minimum_increments < 3:
        raise ValueError('at least three increments are required')
    track = trajectories(times, signal, center_hz)
    pairs = []
    for first, second in itertools.combinations(range(len(signal)), 2):
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
        'harmonic_bands': len(signal), 'samples': len(times),
        'valid_increment_counts': track['valid'].sum(axis=1).tolist(),
        'pairs': pairs, 'measurement_kind': 'filtered_mixture_tracks',
        'source_dominant_reference': 'not measured',
        'string_mask_decision': None, 'posterior_probability': None,
    }


def validate_join(first, second):
    """Fail closed on absent or conflicting causal observation identities."""
    keys = ('audio_sha256', 'calibration_sha256', 'sample_rate',
            'sample_origin', 'decision_sample', 'note', 'settings_sha256')
    missing = [key for key in keys if first.get(key) is None or second.get(key) is None]
    mismatched = [key for key in keys if key not in missing and first[key] != second[key]]
    return {'joinable': not missing and not mismatched,
            'missing': missing, 'mismatched': mismatched}
