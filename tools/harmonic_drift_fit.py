"""Offline comparison of constant pitch, linear pitch drift and gain evolution."""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

try:
    from .joint_harmonic_fit import fit_window as static_window
except ImportError:
    from joint_harmonic_fit import fit_window as static_window


def _basis(times, center, sources, starts, ends, growth, span, harmonic):
    partial = np.exp2(np.asarray([s["partial_cents"][harmonic] for s in sources]) / 1200)
    first = center * np.exp2(starts / 1200)
    last = center * np.exp2(ends / 1200)
    phase = (harmonic + 1) * ((first * partial - center)[None, :] * times[:, None] +
        0.5 * ((last - first) * partial / span)[None, :] * times[:, None] ** 2)
    return np.exp(growth[None, :] * times[:, None] + 2j * np.pi * phase)


def _linear(times, signal, center, sources, starts, ends, growth, span, scale, bands):
    amplitude = np.zeros((3, len(sources)), dtype=complex)
    prediction = np.zeros_like(signal)
    conditioning = np.zeros(3)
    for h in range(3):
        if not bands & (1 << h) or not sources:
            continue
        basis = _basis(times, center, sources, starts, ends, growth, span, h)
        norms = np.linalg.norm(basis, axis=0)
        normal = basis / norms
        coef, _, _, singular = np.linalg.lstsq(normal, signal[h], rcond=1e-8)
        amplitude[h] = coef / norms
        prediction[h] = basis @ amplitude[h]
        conditioning[h] = singular[-1] / singular[0]
    residual = (prediction - signal) / scale[:, None]
    for h in range(3):
        if not bands & (1 << h):
            residual[h] = 0
    return {"amplitude": amplitude, "conditioning": conditioning,
            "loss": np.mean(np.abs(residual) ** 2, axis=1),
            "residual": np.concatenate((residual.real.ravel(), residual.imag.ravel()))}


def _fit_model(times, signal, center, sources, training, bands, control, family):
    count = len(sources)
    span = float(times[-1])
    pitch_drift = family in ("pitch_drift", "pitch_and_gain")
    gain_drift = family in ("gain_drift", "pitch_and_gain")
    frequencies = np.asarray([m["cents"] for m in control["members"]])
    energy = np.mean(np.abs(signal[:, :training]) ** 2, axis=1)
    for h in range(3):
        if not bands & (1 << h):
            energy[h] = 0
    scale = np.sqrt(np.maximum(energy, max(float(energy.max()), 1e-30) * 1e-3))

    def unpack(parameters):
        first = parameters[:count]
        last = parameters[count:2 * count] if pitch_drift else first
        gain_offset = 2 * count if pitch_drift else count
        growth = parameters[gain_offset:] if gain_drift else np.zeros(count)
        return first, last, growth

    def solve(parameters, begin, end, selected=None):
        first, last, growth = unpack(parameters)
        positions = list(range(count)) if selected is None else selected
        return _linear(times[begin:end], signal[:, begin:end], center,
                       [sources[i] for i in positions], first[positions], last[positions],
                       growth[positions], span, scale, bands)

    candidates = []
    for movement in (0, -3, 3):
        initial = list(np.clip(frequencies - (movement if pitch_drift else 0), -49.9, 49.9))
        if pitch_drift:
            initial += list(np.clip(frequencies + movement, -49.9, 49.9))
        if gain_drift:
            initial += [0.05 * movement] * count
        low = [-50] * (count * (2 if pitch_drift else 1))
        high = [50] * len(low)
        if gain_drift:
            low += [-1] * count
            high += [1] * count
        result = least_squares(lambda p: solve(p, 0, training)["residual"], initial,
                               bounds=(low, high), max_nfev=150,
                               ftol=1e-8, xtol=1e-8, gtol=1e-8)
        candidates.append((float(np.sum(result.fun ** 2)), result))
    fitted = min(candidates, key=lambda item: item[0])[1]
    first, last, growth = unpack(fitted.x)
    train = solve(fitted.x, 0, training)
    test = solve(fitted.x, training, len(times))
    prediction = np.zeros_like(signal[:, training:])
    for h in range(3):
        if bands & (1 << h):
            prediction[h] = _basis(times[training:], center, sources, first, last,
                                   growth, span, h) @ train["amplitude"][h]
    prediction_loss = np.mean(np.abs((prediction - signal[:, training:]) / scale[:, None]) ** 2, axis=1)
    for h in range(3):
        if not bands & (1 << h):
            prediction_loss[h] = 0
    members = []
    for i, source in enumerate(sources):
        positions = [j for j in range(count) if j != i]
        train_support = solve(fitted.x, 0, training, positions)["loss"] - train["loss"]
        test_support = solve(fitted.x, training, len(times), positions)["loss"] - test["loss"]
        supports = ((train_support >= 0.005) & (test_support >= 0.005) &
                    (train["conditioning"] > 1e-4) & (test["conditioning"] > 1e-4))
        members.append({"string": source["string"], "cents_at_start": float(first[i]),
                        "cents_at_end": float(last[i]), "growth_per_second": float(growth[i]),
                        "training_support_by_harmonic": train_support.tolist(),
                        "test_support_by_harmonic": test_support.tolist(),
                        "supported_harmonics": int(supports.sum())})
    return {"mask": control["mask"], "fit_family": family, "members": members,
            "comparison_harmonic_mask": bands, "converged": bool(fitted.success),
            "at_pitch_boundary": bool(np.any(np.abs(first) >= 49.9) or np.any(np.abs(last) >= 49.9)),
            "at_growth_boundary": bool(np.any(np.abs(growth) >= 0.999)),
            "training_loss": float(train["loss"].sum() / bands.bit_count()),
            "test_refit_loss": float(test["loss"].sum() / bands.bit_count()),
            "test_prediction_loss": float(prediction_loss.sum() / bands.bit_count()),
            "minimum_supported_harmonics": min(m["supported_harmonics"] for m in members)}


def fit_window(times, signal, center, note, sources, training, sample_rate):
    control = static_window(times, signal, center, note, sources, training, sample_rate)
    t = np.asarray(times, dtype=float)
    t = t - t[0]
    z = np.asarray(signal, dtype=complex)
    models = [{**m, "fit_family": "static", "at_growth_boundary": False} for m in control["models"]]
    for original in control["models"]:
        selected = sorted([s for s in sources if original["mask"] & (1 << s["string"])],
                          key=lambda s: s["string"])
        for family in ("pitch_drift", "gain_drift", "pitch_and_gain"):
            models.append(_fit_model(t, z, center, selected, training,
                                    control["comparison_harmonic_mask"], original, family))
    for model in models:
        # A more flexible two-string explanation competes with every three-
        # string model, even one using a different physical string assignment.
        smaller = [m for m in models if m["mask"].bit_count() < model["mask"].bit_count()]
        model["test_gain_over_best_smaller_model"] = (min(m["test_refit_loss"] for m in smaller) -
                                                     model["test_refit_loss"] if smaller else None)
        model["prediction_gain_over_best_smaller_model"] = (min(m["test_prediction_loss"] for m in smaller) -
                                                           model["test_prediction_loss"] if smaller else None)
        model["independent_cross_band_support"] = bool(
            control["conservative_spacing_guard_passed"] and control["median_spacing_guard_passed"] and
            model["converged"] and not model["at_pitch_boundary"] and not model["at_growth_boundary"] and
            model["minimum_supported_harmonics"] >= 2 and
            (not smaller or (model["test_gain_over_best_smaller_model"] >= 0.005 and
                             model["prediction_gain_over_best_smaller_model"] >= 0)))
    return {**control, "models": models,
            "fit_families": ["static", "pitch_drift", "gain_drift", "pitch_and_gain"],
            "interpretation": "All parameters use older samples only. Pitch follows a straight frequency line between bounded endpoints; gain follows one bounded exponential per string shared across harmonics. These model the smoothed correlations approximately. Newer samples independently score fixed-parameter prediction and amplitude-refit error. Every larger mask competes with every smaller mask across all model families. No MIDI output changes."}
