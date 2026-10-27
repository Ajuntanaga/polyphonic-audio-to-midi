"""Offline, causal multi-harmonic fits for already-admitted pitch candidates.

This module receives no note labels or desired string masks. Frequencies are
estimated from the older part of a captured window; its newer part only scores
the frozen fit. It cannot produce MIDI or alter the detector's release rules.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np
from scipy.optimize import least_squares


OPEN_NOTES = (32, 36, 40, 44, 48, 52, 56, 60)


def _validate(times: Any, signal: Any, center: float, note: int,
              sources: list[dict[str, Any]], training: int) -> tuple[Any, Any]:
    t = np.asarray(times, dtype=float)
    z = np.asarray(signal, dtype=np.complex128)
    if (t.ndim != 1 or z.shape != (3, len(t)) or len(t) < 30 or
            not np.isfinite(t).all() or not np.isfinite(z).all() or
            np.any(np.diff(t) <= 0) or not 12 <= training <= len(t) - 12 or
            not math.isfinite(center) or center <= 0):
        raise ValueError("invalid harmonic window")
    if len(sources) > 8 or len({s["string"] for s in sources}) != len(sources):
        raise ValueError("invalid source set")
    for source in sources:
        string = source["string"]
        if (not isinstance(string, int) or not 0 <= string < 8 or
                not 0 <= source["fret"] <= 24 or
                note != OPEN_NOTES[string] + source["fret"] or
                len(source["partial_cents"]) != 3 or len(source["profile"]) != 3 or
                not all(math.isfinite(v) for v in source["partial_cents"] + source["profile"]) or
                min(source["profile"]) < 0 or not (source["valid_mask"] & 1) or
                not math.isfinite(source["cents"])):
            raise ValueError("infeasible or invalid string/fret template")
    return t - t[0], z


def _frequencies(center: float, cents: Any, sources: list[dict[str, Any]]) -> Any:
    partials = np.asarray([s["partial_cents"] for s in sources]).T
    # A partial offset is measured relative to h * the string's fundamental.
    return np.arange(1, 4)[:, None] * center * (
        np.exp2((np.asarray(cents)[None, :] + partials) / 1200) - 1)


def _linear(t: Any, z: Any, frequencies: Any, sources: list[dict[str, Any]],
            scale: Any, harmonic_mask: int = 7) -> dict[str, Any]:
    amplitudes = np.zeros((3, len(sources)), dtype=np.complex128)
    prediction = np.zeros_like(z)
    conditioning = np.zeros(3)
    active = np.zeros((3, len(sources)), dtype=bool)
    for h in range(3):
        active[h] = [bool(s["valid_mask"] & harmonic_mask & (1 << h)) for s in sources]
        positions = np.flatnonzero(active[h])
        if not len(positions):
            continue
        basis = np.exp(2j * np.pi * t[:, None] * frequencies[h, positions])
        coefficients, _, _, singular = np.linalg.lstsq(basis, z[h], rcond=1e-8)
        amplitudes[h, positions] = coefficients
        prediction[h] = basis @ coefficients
        conditioning[h] = float(singular[-1] / singular[0])
    residual = (prediction - z) / scale[:, None]
    for h in range(3):
        if not harmonic_mask & (1 << h):
            residual[h] = 0
    return {"amplitudes": amplitudes, "prediction": prediction,
            "loss_by_harmonic": np.mean(np.abs(residual) ** 2, axis=1),
            "residual": np.concatenate((residual.real.ravel(), residual.imag.ravel())),
            "conditioning": conditioning, "active": active}


def _starting_points(t: Any, z: Any, center: float,
                     sources: list[dict[str, Any]], harmonic_mask: int) -> list[Any]:
    # Every start depends on training audio and calibration only. Per-template
    # matched-filter peaks cover independent motion beyond old calibrated cents.
    grid = np.linspace(-49.9, 49.9, 101)
    calibrated = np.clip([s["cents"] for s in sources], -49.9, 49.9)
    active_peak = max(float(np.max(np.abs(z[h]))) for h in range(3)
                      if harmonic_mask & (1 << h))
    if active_peak == 0:
        return [calibrated]
    choices = []
    for source in sources:
        power = np.zeros(len(grid))
        for h in range(3):
            if not source["valid_mask"] & harmonic_mask & (1 << h):
                continue
            frequency = (h + 1) * center * (np.exp2((grid + source["partial_cents"][h]) / 1200) - 1)
            weight = np.hanning(len(t))
            energy = max(float(np.mean(np.abs(z[h]) ** 2)), 1e-30)
            power += math.sqrt(source["profile"][h]) * np.abs(
                np.exp(-2j * np.pi * frequency[:, None] * t) @ (weight * z[h])) ** 2 / energy
        peaks = []
        # These are search seeds, not a source count or a resolution claim.
        for index in np.argsort(power)[::-1]:
            if all(abs(grid[index] - p) >= 4 for p in peaks):
                peaks.append(float(grid[index]))
            if len(peaks) == 4:
                break
        choices.append(peaks)
    return [calibrated, *[np.asarray(v) for v in itertools.product(*choices)]]


def fit_mask(times: Any, signal: Any, center: float,
             sources: list[dict[str, Any]], training: int,
             sample_rate: int, harmonic_mask: int | None = None) -> dict[str, Any]:
    """Fit one feasible mask; callers validate inputs and never pass labels."""
    if harmonic_mask is None:
        harmonic_mask = 7
        for source in sources:
            harmonic_mask &= source["valid_mask"]
    band_count = harmonic_mask.bit_count()
    if band_count == 0:
        raise ValueError("no common measured harmonic offsets")
    train_t, train_z = times[:training], signal[:, :training]
    test_t, test_z = times[training:], signal[:, training:]
    # Fixed training-only band weights avoid loud fundamentals hiding a useful
    # upper harmonic. The floor prevents normalising an empty band to unit noise.
    energies = np.mean(np.abs(train_z) ** 2, axis=1)
    for h in range(3):
        if not harmonic_mask & (1 << h):
            energies[h] = 0
    scale = np.sqrt(np.maximum(energies, max(float(energies.max()), 1e-30) * 1e-3))

    def residual(cents: Any) -> Any:
        return _linear(train_t, train_z, _frequencies(center, cents, sources),
                       sources, scale, harmonic_mask)["residual"]

    starts = _starting_points(train_t, train_z, center, sources, harmonic_mask)
    starts.sort(key=lambda value: float(np.sum(residual(value) ** 2)))
    best = None
    for start in starts[:8]:
        result = least_squares(residual, start, bounds=(-50, 50),
                               max_nfev=100, ftol=1e-8, xtol=1e-8, gtol=1e-8)
        score = float(np.sum(result.fun ** 2))
        if best is None or score < best[0]:
            best = (score, result)
    result = best[1]
    frequencies = _frequencies(center, result.x, sources)
    train = _linear(train_t, train_z, frequencies, sources, scale, harmonic_mask)
    test = _linear(test_t, test_z, frequencies, sources, scale, harmonic_mask)
    prediction = np.zeros_like(test_z)
    for h in range(3):
        prediction[h] = np.exp(2j * np.pi * test_t[:, None] * frequencies[h]) @ train["amplitudes"][h]
    prediction_loss = np.mean(np.abs((prediction - test_z) / scale[:, None]) ** 2, axis=1)
    for h in range(3):
        if not harmonic_mask & (1 << h):
            prediction_loss[h] = 0
    members = []
    for i, source in enumerate(sources):
        others = [s for j, s in enumerate(sources) if j != i]
        reduced = np.delete(frequencies, i, axis=1)
        train_drop = _linear(train_t, train_z, reduced, others, scale, harmonic_mask)
        test_drop = _linear(test_t, test_z, reduced, others, scale, harmonic_mask)
        support_train = train_drop["loss_by_harmonic"] - train["loss_by_harmonic"]
        support_test = test_drop["loss_by_harmonic"] - test["loss_by_harmonic"]
        resolved = (train["conditioning"] > 1e-4) & (test["conditioning"] > 1e-4)
        supported = (support_train >= 0.005) & (support_test >= 0.005) & resolved & train["active"][:, i]
        # Remove the known filters' gain before comparing harmonic energy shape.
        decay = math.exp(-1 / (0.040 * sample_rate))
        dc_decay = math.exp(-2 * math.pi * 15 / sample_rate)
        residual_phase = 2 * np.pi * frequencies[:, i] / sample_rate
        actual_phase = 2 * np.pi * (np.arange(1, 4) * center + frequencies[:, i]) / sample_rate
        gain = ((1 - decay) / np.abs(1 - decay * np.exp(-1j * residual_phase)) *
                np.abs(1 - np.exp(-1j * actual_phase)) /
                np.abs(1 - dc_decay * np.exp(-1j * actual_phase)))
        actual = np.abs(test["amplitudes"][:, i] / gain) ** 2
        expected = np.asarray(source["profile"]) * train["active"][:, i]
        similarity = 0.0
        if actual.sum() > 0 and expected.sum() > 0:
            similarity = float(np.sum(np.sqrt(actual / actual.sum() * expected / expected.sum())))
        members.append({"string": source["string"], "cents": float(result.x[i]),
                        "training_support_by_harmonic": support_train.tolist(),
                        "test_support_by_harmonic": support_test.tolist(),
                        "supported_harmonics": int(supported.sum()),
                        "profile_similarity": similarity})
    return {"mask": sum(1 << s["string"] for s in sources), "members": members,
            "converged": bool(result.success), "at_pitch_boundary": bool(np.any(np.abs(result.x) >= 49.9)),
            "comparison_harmonic_mask": harmonic_mask,
            "training_loss": float(train["loss_by_harmonic"].sum() / band_count),
            "test_refit_loss": float(test["loss_by_harmonic"].sum() / band_count),
            "test_prediction_loss": float(prediction_loss.sum() / band_count),
            "training_loss_by_harmonic": train["loss_by_harmonic"].tolist(),
            "test_refit_loss_by_harmonic": test["loss_by_harmonic"].tolist(),
            "test_prediction_loss_by_harmonic": prediction_loss.tolist(),
            "minimum_supported_harmonics": min(m["supported_harmonics"] for m in members),
            "minimum_profile_similarity": min(m["profile_similarity"] for m in members)}


def fit_window(times: Any, signal: Any, center: float, note: int,
               sources: list[dict[str, Any]], training: int,
               sample_rate: int) -> dict[str, Any]:
    times, signal = _validate(times, signal, center, note, sources, training)
    if sample_rate <= 0:
        raise ValueError("invalid sample rate")
    # Unknown partial detuning does not mean zero harmonic energy. Use exactly
    # the same known bands for every mask in this comparison. Other bands remain
    # in the captured data for a future bounded nuisance-frequency model.
    harmonic_mask = 7
    for source in sources:
        harmonic_mask &= source["valid_mask"]
    largest_frequency = 0.0
    for source in sources:
        for h, partial in enumerate(source["partial_cents"]):
            if harmonic_mask & (1 << h):
                largest_frequency = max(largest_frequency, *(abs((h + 1) * center *
                    (2 ** ((edge + partial) / 1200) - 1)) for edge in (-50, 50)))
    median_guard = largest_frequency < 0.5 / float(np.median(np.diff(times)))
    gap_guard = largest_frequency < 0.5 / float(np.max(np.diff(times)))
    models = []
    for count in range(1, min(4, len(sources)) + 1):
        for selected in itertools.combinations(sorted(sources, key=lambda s: s["string"]), count):
            models.append(fit_mask(times, signal, center, list(selected), training,
                                   sample_rate, harmonic_mask))
    for model in models:
        smaller = [m for m in models if m["mask"] != model["mask"] and
                   (m["mask"] & model["mask"]) == m["mask"]]
        model["test_gain_over_best_subset"] = (
            min(m["test_refit_loss"] for m in smaller) - model["test_refit_loss"]
            if smaller else None)
        model["prediction_gain_over_best_subset"] = (
            min(m["test_prediction_loss"] for m in smaller) - model["test_prediction_loss"]
            if smaller else None)
        # Screening disposition only. Profile agreement is reported, not used
        # as a hard timbre gate. Neither lower residual nor a larger mask alone
        # establishes another physical source.
        model["cross_band_residual_support"] = bool(
            model["converged"] and not model["at_pitch_boundary"] and
            model["minimum_supported_harmonics"] >= 2 and
            (not smaller or model["test_gain_over_best_subset"] >= 0.005))
        model["independent_cross_band_support"] = bool(
            median_guard and gap_guard and model["cross_band_residual_support"])
    return {"note": note, "samples": len(times), "training_samples": training,
            "span_seconds": float(times[-1]), "models": models,
            "comparison_harmonic_mask": harmonic_mask,
            "unknown_detuning_policy": "Omit a band from every compared model if any feasible source lacks its measured detuning; missing detuning is not harmonic absence.",
            "maximum_scanned_residual_hz": largest_frequency,
            "median_spacing_guard_passed": median_guard,
            "conservative_spacing_guard_passed": gap_guard,
            "interpretation": "Only older samples fit frequencies and band weights. Newer samples report frozen-amplitude prediction and separate nuisance-amplitude refit. Cross-band support is a diagnostic screen, not a MIDI decision; overlapping windows are not independent trials."}
