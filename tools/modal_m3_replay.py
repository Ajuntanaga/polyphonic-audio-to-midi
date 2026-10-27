#!/usr/bin/env python3
"""Parallel Modal runner for the protected M3 offline replay matrix.

The remote side receives only the replay executable and the corpus files that
participate in accuracy gates.  REAPER, the VST3 bundle, the audio device, and
live deadline/validator checks intentionally remain local.

Set M3_PHYSICAL_RECORDINGS when the original recordings are outside
build/physical-capture/source-recordings.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
from pathlib import Path
import struct
import subprocess
import time
from typing import Any

import modal


APP_NAME = "m3-protected-replay"
VOLUME_NAME = "m3-protected-replay-data"
MOUNT_ROOT = Path("/mnt/m3")
REPO_ROOT = Path(__file__).resolve().parents[1]
PHYSICAL_ROOT = Path(
    os.environ.get(
        "M3_PHYSICAL_RECORDINGS",
        str(REPO_ROOT / "build/physical-capture/source-recordings"),
    )
)
REPLAY_BINARY = REPO_ROOT / "build/contributor/m3_replay"

CORPUS_FILES: dict[str, Path] = {
    "calibration.m3cb": REPO_ROOT
    / "build/physical-capture/unison-spectral-shadow/factory-current-20261012/factory-calibration-v2.m3cb",
    "templates.tsv": Path(
        os.environ.get(
            "M3_SPECTRAL_TEMPLATES",
            REPO_ROOT
            / "build/physical-capture/unison-spectral-shadow/final-review-fixes/blended-template-bank.tsv",
        )
    ),
    "ordinary.wav": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-practical-chords/combinations.wav",
    "ordinary.tsv": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-practical-chords/combinations.tsv",
    "constructed.wav": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-tuning/combinations.wav",
    "constructed.tsv": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-tuning/combinations.tsv",
    "isolated-08.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-08.wav",
    "isolated-08.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-08.tsv",
    "isolated-05.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-05.wav",
    "isolated-05.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-05.tsv",
    "isolated-02.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-02.wav",
    "isolated-02.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-02.tsv",
    "physical-long.wav": PHYSICAL_ROOT
    / "string8-fret8_string7-fret4_string6-open_unison.wav",
    "physical-long.tsv": REPO_ROOT
    / "build/physical-capture/unison-08-07-06/unison-labels.tsv",
    "physical-middle.wav": PHYSICAL_ROOT
    / "string3-open_string4-fret4_string5-fret8.wav",
    "physical-middle.tsv": REPO_ROOT
    / "build/physical-capture/unison-05-04-03/unison-labels.tsv",
    "physical-highmid.wav": PHYSICAL_ROOT
    / "string2-open_string3-fret4_string4-fret8.wav",
    "physical-highmid.tsv": REPO_ROOT
    / "build/physical-capture/unison-04-03-02/unison-labels.tsv",
    "physical-high.wav": PHYSICAL_ROOT
    / "string1-open_strin2-fret4_string3-fret8.wav",
    "physical-high.tsv": REPO_ROOT
    / "build/physical-capture/unison-03-02-01/unison-labels.tsv",
    "extended-middle.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-middle.wav",
    "extended-middle.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-middle.tsv",
    "extended-highmid.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-highmid.wav",
    "extended-highmid.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-highmid.tsv",
    "extended-high.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-high.wav",
    "extended-high.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-high.tsv",
    "physical-four.wav": PHYSICAL_ROOT
    / "string4-open_string5-fret4_string6-fret8_string7-fret12_string8-fret16.wav",
    "physical-four.tsv": REPO_ROOT
    / "build/physical-capture/unison-08-07-06-05-04/diagnostic-spans.tsv",
    "synthetic-four.wav": REPO_ROOT
    / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.wav",
    "synthetic-four.tsv": REPO_ROOT
    / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.tsv",
}

DATASETS = {
    name: {"wav": f"corpus/{name}.wav", "labels": f"corpus/{name}.tsv"}
    for name in (
        "ordinary",
        "constructed",
        "isolated-08",
        "isolated-05",
        "isolated-02",
        "physical-long",
        "physical-middle",
        "physical-highmid",
        "physical-high",
        "extended-middle",
        "extended-highmid",
        "extended-high",
        "physical-four",
        "synthetic-four",
    )
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_aggregate(tsv: str) -> dict[str, Any]:
    rows = csv.DictReader(tsv.splitlines(), delimiter="\t")
    try:
        row = next(rows)
    except StopIteration as error:
        raise ValueError("replay produced no aggregate row") from error
    integer_fields = (
        "labeled",
        "matched",
        "false_gap_voices",
        "false_wrong_note_voices",
        "false_wrong_string_voices",
        "false_positive_voices",
        "transitions",
        "transitions_inside_holds",
        "transitions_in_gaps",
        "cents_observations",
        "joint_pitch_valid_frames",
        "joint_pitch_invalid_frames",
        "dp_replacement_matched",
        "dp_replacement_false_positive",
        "dp_replacement_false_gap",
        "dp_replacement_false_wrong_note",
        "dp_replacement_false_wrong_string",
        "dp_replacement_changed",
    )
    result: dict[str, Any] = {"fingerprint": row["fingerprint"]}
    for field in integer_fields:
        result[field] = int(row[field])
    for field in ("cents_mean_error", "cents_sd", "cents_p95_abs",
                  "joint_pitch_mean_residual"):
        result[field] = float(row[field])
    result["fine_mask_complexity_penalties"] = [
        float(value) for value in row["fine_mask_complexity_penalties"].split(",")
    ]
    for field in (
        "fine_mask_complexity_matched",
        "fine_mask_complexity_false_positive",
        "fine_mask_complexity_false_gap",
        "fine_mask_complexity_false_wrong_note",
        "fine_mask_complexity_false_wrong_string",
        "fine_mask_complexity_changed",
    ):
        result[field] = [int(value) for value in row[field].split(",")]
    for field in (
        "correlation_shadow_ratio",
        "correlation_shadow_age_seconds",
        "correlation_shadow_fundamental_only",
        "correlation_shadow_protect_pending_unison",
        "joint_pitch_thresholds",
        "joint_pitch_overlap_limits",
    ):
        result[field] = [float(value) for value in row[field].split(",")]
    for field in (
        "correlation_shadow_matched",
        "correlation_shadow_false_positive",
        "correlation_shadow_false_gap",
        "correlation_shadow_false_wrong_note",
        "correlation_shadow_false_wrong_string",
        "correlation_shadow_changed",
        "joint_pitch_matched",
        "joint_pitch_false_positive",
        "joint_pitch_false_gap",
        "joint_pitch_false_wrong_note",
        "joint_pitch_false_wrong_string",
        "joint_pitch_changed",
    ):
        result[field] = [int(value) for value in row[field].split(",")]
    # Keep the compact causal tables beside the scores so a remote diagnostic
    # run does not require downloading its much larger per-label TSV. Preserve
    # the exported encodings and sparse cell identifiers for later analysis.
    result["physical_group_diagnostics"] = {
        field: value
        for field, value in row.items()
        if field.startswith("physical_group_")
    }
    return result


app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .env({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
    .apt_install("libstdc++6")
    .pip_install("numpy<3", "scipy<2")
    .add_local_file(REPO_ROOT / "tools/joint_harmonic_fit.py", "/opt/m3/joint_harmonic_fit.py", copy=True)
    .add_local_file(REPO_ROOT / "tools/harmonic_drift_fit.py", "/opt/m3/harmonic_drift_fit.py", copy=True)
    .add_local_file(REPO_ROOT / "tools/harmonic_balance_audit.py", "/opt/m3/harmonic_balance_audit.py", copy=True)
    .add_local_file(REPO_ROOT / "tools/coupled_harmonic_fit.py", "/opt/m3/coupled_harmonic_fit.py", copy=True)
    .add_local_file(REPO_ROOT / "tools/generate_pitch_corrected_corpus.py", "/opt/m3/generate_pitch_corrected_corpus.py", copy=True)
    .add_local_file(REPLAY_BINARY, "/opt/m3/m3_replay", copy=True)
    .run_commands("chmod 0755 /opt/m3/m3_replay")
)


def _fine_window_spectrum(window: dict[str, Any]) -> dict[str, Any]:
    """Describe detector correlations at actual sample times; no source labels."""
    import numpy as np

    samples = np.asarray(window["samples"], dtype=float)
    if samples.ndim != 2 or samples.shape[1] != 3 or len(samples) < 12:
        raise ValueError("invalid fine window dimensions")
    if not np.isfinite(samples).all() or np.any(np.diff(samples[:, 0]) <= 0):
        raise ValueError("invalid fine window samples")
    times = samples[:, 0] - samples[0, 0]
    signal = samples[:, 1] + 1j * samples[:, 2]
    center = float(window["center_hz"])
    harmonic = int(window.get("harmonic", 1))
    if harmonic < 1 or harmonic > 3:
        raise ValueError("inspection supports harmonics1..3")
    lower, upper = center * (2 ** (-50 / 1200) - 1), center * (2 ** (50 / 1200) - 1)
    grid = np.linspace(lower, upper, 801)
    training = int(window["training_samples"])
    if not 3 <= training <= len(samples) - 3:
        raise ValueError("invalid training split")

    def spectrum(begin: int, end: int) -> dict[str, Any]:
        t = times[begin:end]
        span = float(t[-1] - t[0])
        weights = 0.5 - 0.5 * np.cos(2 * np.pi * (t - t[0]) / span)
        values = signal[begin:end]
        amplitude = np.abs(np.exp(-2j * np.pi * harmonic * grid[:, None] * t[None, :]) @
                           (weights * values)) / weights.sum()
        local = [i for i in range(1, len(grid) - 1)
                 if amplitude[i] >= amplitude[i - 1] and amplitude[i] > amplitude[i + 1]]
        strongest = int(np.argmax(amplitude))
        if strongest in (0, len(grid) - 1):
            local.append(strongest)
        local.sort(key=lambda i: float(amplitude[i]), reverse=True)
        selected: list[int] = []
        for i in local:
            if all(abs(grid[i] - grid[j]) >= 0.5 / (span * harmonic) for j in selected):
                selected.append(i)
            if len(selected) == 4:
                break
        denominator = max(float(amplitude[strongest]), 1e-30)
        peaks = [{"offset_hz": float(grid[i]),
                  "cents": float(1200 * np.log2((center + grid[i]) / center)),
                  "relative_amplitude": float(amplitude[i]) / denominator,
                  "at_cell_boundary": i in (0, len(grid) - 1)} for i in selected]
        return {"span_seconds": span, "nominal_resolution_hz": 1 / (span * harmonic),
                "peaks": peaks,
                "at_calibration_relative_amplitude": [
                    {"string": int(string), "offset_hz": float(hz),
                     "relative_amplitude": float(abs(np.vdot(
                         np.exp(2j * np.pi * harmonic * float(hz) * t), weights * values))) /
                         float(weights.sum()) / denominator}
                    for string, hz in window["calibration"]]}

    differences = np.diff(times)
    parts = np.array_split(np.abs(signal) ** 2, 4)
    quarter_rms = [float(np.sqrt(p.mean())) for p in parts]
    scanned_hz = harmonic * max(abs(lower), abs(upper))
    gap_bound_hz = 0.5 / float(np.max(differences))
    median_bound_hz = 0.5 / float(np.median(differences))
    return {"note": int(window["note"]), "harmonic": harmonic,
            "start_seconds": float(samples[0, 0]),
            "end_seconds": float(samples[-1, 0]),
            "prior_output_mask": int(window["prior_output_mask"]),
            "calibration": window["calibration"], "sample_count": len(samples),
            "uniform": bool(np.max(differences) - np.min(differences) < 1e-9),
            "maximum_sample_gap_seconds": float(np.max(differences)),
            "maximum_scanned_residual_hz": scanned_hz,
            "conservative_spacing_guard_passed": scanned_hz < gap_bound_hz,
            "median_spacing_guard_passed": scanned_hz < median_bound_hz,
            "sampling_limit": "Spacing guards cover the scanned frequency range, not rejection of aliased out-of-band signal. Irregular gaps also create spectral-window sidelobes; unresolved or unsupported peaks cannot establish extra strings.",
            "quarter_rms": quarter_rms,
            "last_to_first_rms": quarter_rms[-1] / max(quarter_rms[0], 1e-30),
            "full": spectrum(0, len(samples)),
            "training": spectrum(0, training), "test": spectrum(training, len(samples)),
            "fits": window["fits"]}


def _check_fine_window_spectrum() -> int:
    """Small known-frequency checks run before interpreting recorded data."""
    cases = [(offset, irregular, harmonic) for harmonic in (1, 2, 3)
             for offset, irregular in ((0.7, False), (-0.9, True))]
    for offset, irregular, harmonic in cases:
        times = [n * 0.01 + (0.0002 if irregular and n % 3 == 0 else 0.0)
                 for n in range(300)]
        window = {"samples": [[t, math.cos(2 * math.pi * harmonic * offset * t),
                               math.sin(2 * math.pi * harmonic * offset * t)] for t in times],
                  "center_hz": 82.4069, "training_samples": 200, "note": 40,
                  "harmonic": harmonic, "prior_output_mask": 1,
                  "calibration": [[0, offset]], "fits": []}
        result = _fine_window_spectrum(window)
        for band in ("full", "training", "test"):
            assert abs(result[band]["peaks"][0]["offset_hz"] - offset) < 0.01
        assert result["uniform"] is not irregular
        assert abs(result["last_to_first_rms"] - 1) < 1e-12
        assert result["conservative_spacing_guard_passed"]
        if irregular and harmonic == 1:
            window["samples"][1][0] = window["samples"][0][0]
            try:
                _fine_window_spectrum(window)
            except ValueError:
                pass
            else:
                raise AssertionError("duplicate observation time was accepted")
    window["center_hz"] = 1046.502
    window["harmonic"] = 3
    assert not _fine_window_spectrum(window)["median_spacing_guard_passed"]
    return 8


@app.function(image=image, cpu=1.0, memory=512, timeout=60)
def check_fine_window_spectrum() -> dict[str, Any]:
    return {"known_frequency_checks_passed": _check_fine_window_spectrum()}


@app.local_entrypoint()
def spectrum_checks(output: str = "build/modal/fine-window-spectrum-checks.json") -> None:
    result = check_fine_window_spectrum.remote()
    Path(output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


def _reconstruct_harmonic_correlations(samples: Any, rate: int, center: float,
                                      indices: Any, input_trim: float) -> Any:
    """Match the native15Hz DC blocker and40ms complex one-pole correlator."""
    import numpy as np

    indices = np.asarray(indices, dtype=np.int64)
    if not len(indices) or indices[0] < 0 or indices[-1] >= len(samples) or np.any(np.diff(indices) <= 0):
        raise ValueError("invalid correlation sample indices")
    gain = 10 ** (input_trim / 20)
    dc_decay = math.exp(-2 * math.pi * 15 / rate)
    decay = math.exp(-1 / (0.040 * rate))
    dc_state = 0.0
    previous_sample = 0.0
    states = np.zeros(3, dtype=np.complex128)
    result = np.empty((3, len(indices)), dtype=np.complex128)
    cursor = 0
    for begin in range(0, int(indices[-1]) + 1, 1024):
        end = min(begin + 1024, len(samples), int(indices[-1]) + 1)
        values = np.asarray(samples[begin:end], dtype=float) * gain
        count = len(values)
        powers = dc_decay ** np.arange(1, count + 1)
        drive = np.diff(np.concatenate(([previous_sample], values)))
        dc = powers * (dc_state + np.cumsum(drive / powers))
        dc_state = float(dc[-1])
        previous_sample = float(values[-1])
        powers = decay ** np.arange(1, count + 1)
        selected_end = int(np.searchsorted(indices, end))
        positions = indices[cursor:selected_end] - begin
        sample_numbers = np.arange(begin + 1, end + 1)
        for harmonic in range(1, 4):
            mixed = dc * np.exp(-2j * np.pi * harmonic * center * sample_numbers / rate)
            filtered = powers * (states[harmonic - 1] +
                                 (1 - decay) * np.cumsum(mixed / powers))
            states[harmonic - 1] = filtered[-1]
            result[harmonic - 1, cursor:selected_end] = filtered[positions]
        cursor = selected_end
    return result


@app.function(image=image, volumes={str(MOUNT_ROOT): volume}, cpu=2.0,
              memory=2048, timeout=600)
def inspect_window_harmonics(capture_path: str, dataset_name: str,
                             input_trim: float) -> dict[str, Any]:
    import numpy as np

    path = MOUNT_ROOT / capture_path
    if not path.is_relative_to(MOUNT_ROOT / "results") or ".." in path.parts:
        raise ValueError("capture must be in the replay results volume")
    windows = [json.loads(line) for line in path.read_text().splitlines()]
    if not windows or len(windows) > 512 or len({w["center_hz"] for w in windows}) != 1:
        raise ValueError("harmonic inspection requires a bounded single-note capture")
    rate, samples = _read_float_wave(MOUNT_ROOT / DATASETS[dataset_name]["wav"])
    indices = np.unique(np.concatenate([
        np.rint(np.asarray(w["samples"])[:, 0] * rate).astype(np.int64) - 1 for w in windows]))
    measured = _reconstruct_harmonic_correlations(
        samples, rate, float(windows[0]["center_hz"]), indices, input_trim)
    error_energy = 0.0
    reference_energy = 0.0
    analyzed = []
    for window in windows:
        original = np.asarray(window["samples"])
        locations = np.searchsorted(indices, np.rint(original[:, 0] * rate).astype(np.int64) - 1)
        reference = original[:, 1] + 1j * original[:, 2]
        error_energy += float(np.sum(np.abs(measured[0, locations] - reference) ** 2))
        reference_energy += float(np.sum(np.abs(reference) ** 2))
        for harmonic in (1, 2, 3):
            values = measured[harmonic - 1, locations]
            probe = {**window, "harmonic": harmonic,
                     "samples": np.column_stack((original[:, 0], values.real, values.imag)).tolist()}
            analyzed.append(_fine_window_spectrum(probe))
    relative_error = math.sqrt(error_energy / reference_energy)
    if relative_error >= 1e-6:
        raise ValueError(f"fundamental reconstruction disagrees with native capture: {relative_error:.9g}")
    return {"dataset": dataset_name, "capture_path": capture_path,
            "fundamental_relative_rms_error": relative_error, "windows": analyzed,
            "capture_windows": len(windows), "harmonics": [1, 2, 3],
            "interpretation": "Harmonic offsets are divided by harmonic order and expressed as fundamental-equivalent Hz/cents. Inharmonicity can shift these values; peaks alone do not identify physical strings. Native fundamental reconstruction is verified first."}


@app.local_entrypoint()
def inspect_harmonics(report: str, output: str = "build/modal/fine-window-harmonics.json",
                      dataset: str = "physical-long") -> None:
    source = json.loads(Path(report).read_text())
    row = next(r for r in source["results"] if r["dataset"] == dataset and r["block"] == 512)
    if row.get("correlation_seconds", -1) != -1:
        raise SystemExit("harmonic reconstruction requires the default correlation decay")
    result = inspect_window_harmonics.remote(row["fine_window_path"], dataset, row["input_trim"])
    result["replay_run_id"] = source["run_id"]
    result["replay_binary_sha256"] = source["binary_sha256"]
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": output, "captures": result["capture_windows"],
                      "fundamental_relative_rms_error": result["fundamental_relative_rms_error"]}))


@app.function(image=image, volumes={str(MOUNT_ROOT): volume}, cpu=2.0,
              memory=2048, timeout=600)
def prepare_joint_harmonics(capture_path: str, dataset_name: str,
                            input_trim: float) -> dict[str, Any]:
    import sys
    import numpy as np
    sys.path.insert(0, "/opt/m3")
    from generate_pitch_corrected_corpus import _calibration_image
    from joint_harmonic_fit import OPEN_NOTES

    path = MOUNT_ROOT / capture_path
    if not path.is_relative_to(MOUNT_ROOT / "results") or ".." in path.parts:
        raise ValueError("capture must be in the replay results volume")
    windows = [json.loads(line) for line in path.read_text().splitlines()]
    if not windows or len(windows) > 512 or len({w["note"] for w in windows}) != 1:
        raise ValueError("joint harmonic inspection requires a bounded single-note capture")
    rate, samples = _read_float_wave(MOUNT_ROOT / DATASETS[dataset_name]["wav"])
    indices = np.unique(np.concatenate([
        np.rint(np.asarray(w["samples"])[:, 0] * rate).astype(np.int64) - 1 for w in windows]))
    measured = _reconstruct_harmonic_correlations(
        samples, rate, float(windows[0]["center_hz"]), indices, input_trim)
    error, energy = 0.0, 0.0
    arrays = {}
    for i, window in enumerate(windows):
        original = np.asarray(window["samples"])
        locations = np.searchsorted(indices, np.rint(original[:, 0] * rate).astype(np.int64) - 1)
        reference = original[:, 1] + 1j * original[:, 2]
        error += float(np.sum(np.abs(measured[0, locations] - reference) ** 2))
        energy += float(np.sum(np.abs(reference) ** 2))
        arrays[f"times_{i}"] = original[:, 0]
        arrays[f"signal_{i}"] = measured[:, locations]
    relative_error = math.sqrt(error / energy)
    if relative_error >= 1e-6:
        raise ValueError("native correlation reconstruction failed")
    calibration = _calibration_image(MOUNT_ROOT / "corpus/calibration.m3cb")
    if struct.unpack_from("<H", calibration, 4)[0] != 2:
        raise ValueError("partial detuning requires calibration version2")
    sources = []
    note = int(windows[0]["note"])
    for string, opened in enumerate(OPEN_NOTES):
        fret = note - opened
        if not 0 <= fret <= 24:
            continue
        point = struct.unpack_from("<h6H6hBHHB", calibration, 25 + (string * 25 + fret) * 32)
        if point[-1] == 0 or not (point[13] & 1):
            continue
        sources.append({"string": string, "fret": fret, "cents": point[0] / 256,
                        "profile": [v / 65535 for v in point[1:4]],
                        "partial_cents": [v / 256 for v in point[7:10]],
                        "valid_mask": point[13] & 7})
    prepared_path = path.with_suffix(".joint-inputs.npz")
    np.savez_compressed(prepared_path, **arrays)
    metadata = {"capture_path": capture_path, "dataset": dataset_name,
                "windows": [{k: w[k] for k in ("note", "center_hz", "training_samples", "prior_output_mask")}
                            for w in windows],
                "sources": sources, "sample_rate": rate,
                "fundamental_relative_rms_error": relative_error,
                "calibration_sha256": _sha256(MOUNT_ROOT / "corpus/calibration.m3cb"),
                "capture_sha256": _sha256(path)}
    prepared_path.with_suffix(".json").write_text(json.dumps(metadata))
    volume.commit()
    return {"prepared_path": str(prepared_path.relative_to(MOUNT_ROOT)),
            "windows": len(windows), "metadata": metadata}


@app.function(image=image, volumes={str(MOUNT_ROOT): volume}, cpu=1.0,
              memory=1024, timeout=900, max_containers=16)
def fit_joint_harmonic_window(job: dict[str, Any]) -> dict[str, Any]:
    import sys
    import numpy as np
    sys.path.insert(0, "/opt/m3")
    if job.get("fit_mode", "static") == "coupled":
        from coupled_harmonic_fit import fit_window
    elif job.get("fit_mode", "static") == "drift":
        from harmonic_drift_fit import fit_window
    elif job.get("fit_mode", "static") == "static":
        from joint_harmonic_fit import fit_window
    else:
        raise ValueError("unknown harmonic fit mode")

    volume.reload()
    path = MOUNT_ROOT / job["prepared_path"]
    if not path.is_relative_to(MOUNT_ROOT / "results") or ".." in path.parts:
        raise ValueError("prepared window must be in results")
    metadata = json.loads(path.with_suffix(".json").read_text())
    index = int(job["window"])
    window = metadata["windows"][index]
    with np.load(path, allow_pickle=False) as data:
        times = data[f"times_{index}"]
        signal = data[f"signal_{index}"]
    arguments = [times, signal, window["center_hz"], window["note"],
                 metadata["sources"], window["training_samples"], metadata["sample_rate"]]
    if job.get('fit_mode') == 'coupled':
        arguments.extend((job['prototypes'], job['control_models']))
    result = fit_window(*arguments)
    result.update({"index": index, "start_seconds": float(times[0]),
                   "end_seconds": float(times[-1]), "prior_output_mask": window["prior_output_mask"]})
    # Annotation is deliberately after fitting; the fit module receives neither
    # the labels nor the assignment that entered the fine-analysis decision.
    expected, entirely_inside = 0, True
    with (MOUNT_ROOT / DATASETS[metadata["dataset"]]["labels"]).open() as stream:
        for label in csv.DictReader(stream, delimiter="\t"):
            start = int(label["start_sample"]) / metadata["sample_rate"]
            end = int(label["end_sample"]) / metadata["sample_rate"]
            if int(label["midi_note"]) == window["note"] and start <= times[-1] < end:
                expected |= int(label["string_mask"])
                entirely_inside = entirely_inside and start <= times[0]
    result["expected_mask_at_window_end"] = expected
    result["whole_window_in_labeled_hold"] = bool(expected and entirely_inside)
    # Keep remote results independent of NumPy in the lightweight CLI process.
    json.dumps(result, allow_nan=False)
    return result


@app.local_entrypoint()
def joint_harmonics(report: str, output: str = "build/modal/joint-harmonic-screen.json",
                     dataset: str = "physical-long", prepared_report: str = "",
                     fit_mode: str = "static", control_report: str = "",
                     profile_report: str = "") -> None:
    if fit_mode not in ("static", "drift", "coupled"):
        raise SystemExit("fit-mode must be static, drift or coupled")
    source_names = ['joint_harmonic_fit.py']
    if fit_mode in ('drift', 'coupled'):
        source_names.append('harmonic_drift_fit.py')
    if fit_mode == 'coupled':
        source_names.append('coupled_harmonic_fit.py')
    source_hashes = {name: _sha256(REPO_ROOT / "tools" / name) for name in
                     source_names}
    source = json.loads(Path(report).read_text())
    row = next(r for r in source["results"] if r["dataset"] == dataset and r["block"] == 512)
    if row.get("correlation_seconds", -1) != -1:
        raise SystemExit("joint harmonic reconstruction requires the default decay")
    if prepared_report:
        previous = json.loads(Path(prepared_report).read_text())
        metadata = previous["metadata"]
        if metadata["dataset"] != dataset or metadata["capture_path"] != row["fine_window_path"]:
            raise SystemExit("prepared data does not match the requested capture")
        prepared = {"prepared_path": str(Path(metadata["capture_path"]).with_suffix(".joint-inputs.npz")),
                    "windows": len(metadata["windows"]), "metadata": metadata}
    else:
        prepared = prepare_joint_harmonics.remote(row["fine_window_path"], dataset, row["input_trim"])
    jobs = [{"prepared_path": prepared["prepared_path"], "window": i, "fit_mode": fit_mode}
            for i in range(prepared["windows"])]
    input_hashes = {}
    if fit_mode == 'coupled':
        from tools.harmonic_fit_inputs import validate_coupled_inputs
        if not control_report or not profile_report:
            raise SystemExit('coupled fits require control and measured-profile reports')
        control = json.loads(Path(control_report).read_text())
        profiles = json.loads(Path(profile_report).read_text())
        control_hashes = {name: source_hashes[name] for name in
                          ('joint_harmonic_fit.py', 'harmonic_drift_fit.py')}
        profile_hashes = {**control_hashes, 'harmonic_balance_audit.py':
                          _sha256(REPO_ROOT / 'tools/harmonic_balance_audit.py')}
        validate_coupled_inputs(prepared['metadata'], control, profiles,
                                control_hashes, profile_hashes)
        by_index = {r['index']: r['models'] for r in control['results']}
        for job in jobs:
            job['control_models'] = by_index[job['window']]
            job['prototypes'] = profiles['isolated']['prototypes']
        input_hashes = {'control_report_sha256': _sha256(Path(control_report)),
                        'profile_report_sha256': _sha256(Path(profile_report))}
    results = list(fit_joint_harmonic_window.map(jobs, order_outputs=True))
    result = {"dataset": dataset, "metadata": prepared["metadata"],
              "replay_run_id": source["run_id"], "results": results,
              "prepared_path": prepared["prepared_path"],
              "fit_module_sha256": source_hashes["joint_harmonic_fit.py"],
              "fit_mode": fit_mode, "fit_source_sha256": source_hashes,
              **input_hashes}
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": output, "windows": len(results)}))


@app.function(image=image, volumes={str(MOUNT_ROOT): volume}, cpu=1.0,
              memory=1024, timeout=600)
def inspect_harmonic_balance(manifest_path: str, fitted_report: dict[str, Any]) -> dict[str, Any]:
    import sys
    import numpy as np
    from scipy.io import wavfile
    sys.path.insert(0, "/opt/m3")
    from harmonic_balance_audit import measure_clip, summarize_isolated, score_existing_fit
    volume.reload()
    path = MOUNT_ROOT / manifest_path
    if not path.is_relative_to(MOUNT_ROOT / "results") or ".." in path.parts:
        raise ValueError("profile manifest must be in results")
    manifest = json.loads(path.read_text())
    clips = []
    center = 440 * 2 ** ((manifest['note'] - 69) / 12)
    for clip in manifest['clips']:
        audio = path.parent / clip['clip']
        if Path(clip['clip']).name != clip['clip'] or _sha256(audio) != clip['sha256']:
            raise ValueError("isolated clip identity mismatch")
        rate, values = wavfile.read(audio)
        clips.append({**clip, 'frames': measure_clip(values, rate, center,
                      clip['labeled_begin'], clip['labeled_end'])})
    isolated = summarize_isolated(clips)
    prepared = MOUNT_ROOT / fitted_report['prepared_path']
    if not prepared.is_relative_to(MOUNT_ROOT / 'results') or '..' in prepared.parts:
        raise ValueError('prepared capture must be in results')
    metadata = json.loads(prepared.with_suffix('.json').read_text())
    windows = []
    with np.load(prepared, allow_pickle=False) as data:
        for row in fitted_report['results']:
            index = row['index']
            source = metadata['windows'][index]
            if source['note'] != manifest['note']:
                raise ValueError('profile note does not match recorded fit')
            models = score_existing_fit(data[f'times_{index}'], data[f'signal_{index}'],
                source['center_hz'], metadata['sources'], source['training_samples'],
                metadata['sample_rate'], row['models'], isolated['prototypes'],
                row['comparison_harmonic_mask'])
            windows.append({k: row[k] for k in ('index', 'end_seconds', 'expected_mask_at_window_end',
                'prior_output_mask', 'conservative_spacing_guard_passed', 'whole_window_in_labeled_hold')}
                | {'models': models})
    result = {'manifest': manifest, 'isolated': isolated, 'clips': clips, 'windows': windows,
              'interpretation': 'Ascending isolated audio trains profiles. Descending/checkpoint attacks are held out. Captured fits are unchanged. Powers retain DC filtering and undo only correlation response. Overlapping frames are not independent trials; this is not a MIDI policy.'}
    json.dumps(result, allow_nan=False)
    return result


@app.local_entrypoint()
def harmonic_balance(manifest: str, report: str,
                     output: str = 'build/modal/harmonic-balance-screen.json') -> None:
    path = Path(manifest)
    description = json.loads(path.read_text())
    prefix = 'results/harmonic-balance-input-' + _sha256(path)[:16]
    with volume.batch_upload(force=True) as batch:
        batch.put_file(path, '/' + prefix + '/manifest.json')
        for clip in description['clips']:
            if Path(clip['clip']).name != clip['clip']:
                raise ValueError('unsafe clip name')
            batch.put_file(path.parent / clip['clip'], '/' + prefix + '/' + clip['clip'])
    hashes = {name: _sha256(REPO_ROOT / 'tools' / name) for name in
              ('harmonic_balance_audit.py', 'harmonic_drift_fit.py', 'joint_harmonic_fit.py')}
    fitted = json.loads(Path(report).read_text())
    for name, expected in fitted['fit_source_sha256'].items():
        if hashes[name] != expected:
            raise ValueError('fit source differs from recorded optimizer')
    result = inspect_harmonic_balance.remote(prefix + '/manifest.json', fitted)
    result['source_sha256'] = hashes
    result['fitted_report'] = report
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'output': output, 'isolated_clips': len(result['clips']),
                      'recorded_windows': len(result['windows'])}))


@app.function(image=image, volumes={str(MOUNT_ROOT): volume}, cpu=1.0,
              memory=1024, timeout=120)
def inspect_profile_outliers(manifest_path: str, selected: list[str]) -> dict[str, Any]:
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import find_peaks
    volume.reload()
    path = MOUNT_ROOT / manifest_path
    if not path.is_relative_to(MOUNT_ROOT / 'results') or '..' in path.parts:
        raise ValueError('manifest must be in results')
    manifest = json.loads(path.read_text())
    results = []
    for clip in manifest['clips']:
        if clip['clip'] not in selected:
            continue
        audio = path.parent / clip['clip']
        if Path(clip['clip']).name != clip['clip'] or _sha256(audio) != clip['sha256']:
            raise ValueError('isolated clip identity mismatch')
        rate, values = wavfile.read(audio)
        values = values[clip['labeled_begin']:clip['labeled_end']].astype(float)
        taper = np.hanning(len(values))
        nfft = 4 * (1 << (len(values) - 1).bit_length())
        frequencies = np.fft.rfftfreq(nfft, 1 / rate)
        power = np.abs(np.fft.rfft(values * taper, nfft)) ** 2 / taper.sum() ** 2
        peaks, _ = find_peaks(power, distance=max(1, int(nfft / rate)))
        peaks = [i for i in peaks if 25 <= frequencies[i] <= 2000]
        peaks = sorted(peaks, key=lambda i: -power[i])[:12]
        results.append({'clip': clip['clip'], 'rms': float(np.sqrt(np.mean(values ** 2))),
                        'source_start_sample': clip['source_start_sample'],
                        'peaks': [{'hz': float(frequencies[i]), 'power': float(power[i]),
                                   'midi_pitch': float(69 + 12 * math.log2(frequencies[i] / 440))}
                                  for i in peaks]})
    if len(results) != len(set(selected)):
        raise ValueError('outlier clip not present in manifest')
    return {'clips': results, 'interpretation': 'Broad spectral peaks describe the recorded signal; they do not by themselves establish string identity or change annotations.'}


@app.local_entrypoint()
def harmonic_balance_outliers(manifest: str, clips: str,
                              output: str = 'build/modal/harmonic-balance-outliers.json') -> None:
    prefix = 'results/harmonic-balance-input-' + _sha256(Path(manifest))[:16]
    result = inspect_profile_outliers.remote(prefix + '/manifest.json', clips.split(','))
    Path(output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'output': output, 'clips': len(result['clips'])}))


@app.function(image=image, volumes={str(MOUNT_ROOT): volume}, cpu=2.0,
              memory=2048, timeout=600)
def inspect_fine_windows(capture_path: str, dataset_name: str,
                        partition_paths: list[str]) -> dict[str, Any]:
    selftests = _check_fine_window_spectrum()
    path = MOUNT_ROOT / capture_path
    if not path.is_relative_to(MOUNT_ROOT / "results") or ".." in path.parts:
        raise ValueError("capture must be in the replay results volume")
    partition_hashes = {}
    for capture in partition_paths:
        partition_path = MOUNT_ROOT / capture
        if not partition_path.is_relative_to(MOUNT_ROOT / "results") or ".." in partition_path.parts:
            raise ValueError("capture must be in the replay results volume")
        partition_hashes[capture] = _sha256(partition_path)
    if len(set(partition_hashes.values())) != 1:
        raise ValueError("fine-window captures differ between buffer sizes")
    dataset = DATASETS[dataset_name]
    with (MOUNT_ROOT / dataset["wav"]).open("rb") as stream:
        if stream.read(4) != b"RIFF":
            raise ValueError("missing RIFF")
        stream.seek(12)
        rate = None
        while True:
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError("missing WAVE fmt")
            name, size = struct.unpack("<4sI", header)
            if name == b"fmt ":
                rate = struct.unpack("<HHI", stream.read(8))[2]
                break
            stream.seek(size + (size & 1), 1)
    with (MOUNT_ROOT / dataset["labels"]).open() as stream:
        labels = list(csv.DictReader(stream, delimiter="\t"))
    windows = []
    with path.open() as stream:
        for line in stream:
            if len(windows) >= 512:
                raise ValueError("capture exceeded bounded export")
            item = _fine_window_spectrum(json.loads(line))
            expected = 0
            wholly_labeled = True
            for label in labels:
                if int(label["midi_note"]) != item["note"]:
                    continue
                start = int(label["start_sample"]) / rate
                end = int(label["end_sample"]) / rate
                if start <= item["end_seconds"] < end:
                    expected |= int(label["string_mask"])
                    wholly_labeled = wholly_labeled and start <= item["start_seconds"]
            # Labels are attached only after all spectral measurements.
            item["expected_mask_at_window_end"] = expected
            item["whole_window_in_labeled_hold"] = bool(expected) and wholly_labeled
            windows.append(item)
    return {"capture_path": capture_path, "dataset": dataset_name, "sample_rate": rate,
            "windows": windows, "count": len(windows), "export_cap_reached": len(windows) == 512,
            "known_frequency_checks_passed": selftests,
            "partition_capture_sha256": partition_hashes,
            "interpretation": "These are40ms-smoothed complex detector correlations. Fourier grid spacing is not source-resolution precision; peaks from overlapping sources can be biased. Prior output precedes the current assignment decision. Labels only annotate measured windows."}


@app.local_entrypoint()
def inspect_windows(report: str, output: str = "build/modal/fine-window-inspection.json",
                    dataset: str = "physical-long") -> None:
    source = json.loads(Path(report).read_text())
    row = next(r for r in source["results"] if r["dataset"] == dataset and r["block"] == 512)
    paths = [r["fine_window_path"] for r in source["results"] if r["dataset"] == dataset]
    result = inspect_fine_windows.remote(row["fine_window_path"], dataset, paths)
    result["replay_run_id"] = source["run_id"]
    result["replay_binary_sha256"] = source["binary_sha256"]
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": output, "windows": result["count"]}))


def _read_float_wave(path: Path) -> tuple[int, Any]:
    import numpy as np

    contents = path.read_bytes()
    if contents[:4] != b"RIFF" or contents[8:12] != b"WAVE":
        raise ValueError(f"not a RIFF/WAVE file: {path}")
    position = 12
    format_fields: tuple[int, int, int, int] | None = None
    payload: bytes | None = None
    while position + 8 <= len(contents):
        chunk_id, chunk_size = struct.unpack_from("<4sI", contents, position)
        position += 8
        chunk = contents[position : position + chunk_size]
        position += chunk_size + (chunk_size & 1)
        if chunk_id == b"fmt " and len(chunk) >= 16:
            audio_format, channels, rate, _, _, bits = struct.unpack_from(
                "<HHIIHH", chunk
            )
            format_fields = audio_format, channels, rate, bits
        elif chunk_id == b"data":
            payload = chunk
    if format_fields is None or payload is None:
        raise ValueError(f"missing WAVE format or data: {path}")
    audio_format, channels, rate, bits = format_fields
    if audio_format != 3 or channels != 1 or bits != 32:
        raise ValueError(f"expected mono float32 WAVE: {path}")
    return rate, np.frombuffer(payload, dtype="<f4").copy()


def _write_float_wave(path: Path, rate: int, samples: Any) -> None:
    import numpy as np

    payload = np.asarray(samples, dtype="<f4").tobytes()
    format_chunk = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(format_chunk))
        + format_chunk
        + b"data"
        + struct.pack("<I", len(payload))
        + payload
    )
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def _extend_remote_hold(samples: Any, target: int, rate: int) -> Any:
    import numpy as np

    if samples.shape[0] >= target:
        return samples[:target].copy()
    sustain = samples[
        int(round(samples.shape[0] * 0.35)) :
        int(round(samples.shape[0] * 0.85))
    ]
    if sustain.shape[0] < int(round(0.40 * rate)):
        raise ValueError("recorded hold has no bounded sustain region")
    crossfade = int(round(0.020 * rate))
    result = samples.copy()
    phase = np.linspace(0.0, np.pi / 2.0, crossfade, endpoint=False)
    fade_out = np.cos(phase)
    fade_in = np.sin(phase)
    while result.shape[0] < target:
        overlap = (
            result[-crossfade:] * fade_out + sustain[:crossfade] * fade_in
        ).astype(samples.dtype, copy=False)
        result = np.concatenate(
            (result[:-crossfade], overlap, sustain[crossfade:])
        ).astype(samples.dtype, copy=False)
    return result[:target]


@app.function(
    image=image,
    volumes={str(MOUNT_ROOT): volume},
    cpu=2.0,
    memory=4096,
    timeout=900,
)
def build_extended_upper_hold(name: str) -> dict[str, Any]:
    import numpy as np

    source_wave = MOUNT_ROOT / "corpus" / f"physical-{name}.wav"
    source_labels = MOUNT_ROOT / "corpus" / f"physical-{name}.tsv"
    output_wave = MOUNT_ROOT / "corpus" / f"extended-{name}.wav"
    output_labels = MOUNT_ROOT / "corpus" / f"extended-{name}.tsv"
    rate, samples = _read_float_wave(source_wave)
    with source_labels.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    target = int(round(3.60 * rate))
    minimum = int(round(1.50 * rate))
    silence_count = int(round(0.25 * rate))
    silence = np.zeros(silence_count, dtype=np.float32)
    output_parts = [silence]
    output_rows: list[dict[str, int]] = []
    cursor = silence_count
    for row in rows:
        start = int(row["start_sample"])
        end = int(row["end_sample"])
        if end - start < minimum:
            continue
        extended = _extend_remote_hold(samples[start:end], target, rate)
        output_rows.append(
            {
                "start_sample": cursor,
                "end_sample": cursor + target,
                "midi_note": int(row["midi_note"]),
                "string_mask": int(row["string_mask"]),
            }
        )
        output_parts.extend((extended, silence))
        cursor += target + silence_count
    if not output_rows:
        raise ValueError(f"no long holds in {name}")
    _write_float_wave(output_wave, rate, np.concatenate(output_parts))
    with output_labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=("start_sample", "end_sample", "midi_note", "string_mask"),
        )
        writer.writeheader()
        writer.writerows(output_rows)
    volume.commit()
    return {"dataset": name, "holds": len(output_rows), "rate": rate}


@app.local_entrypoint()
def build_extended_upper() -> None:
    results = list(
        build_extended_upper_hold.map(
            ("middle", "highmid", "high"), order_outputs=True
        )
    )
    print(json.dumps(results, sort_keys=True))


@app.function(
    image=image,
    volumes={str(MOUNT_ROOT): volume},
    cpu=2.0,
    memory=2048,
    max_containers=128,
    nonpreemptible=True,
    timeout=3600,
)
def run_replay(job: dict[str, Any]) -> dict[str, Any]:
    dataset = DATASETS[job["dataset"]]
    output_relative = Path("results") / job["run_id"] / (
        f"{job['dataset']}-b{job['block']}-m{job['selector_margin']}"
        f"-s{job['selector_mask']}-dr{job['dp_similarity']}"
        f"-{job['dp_calibration_margin']}-{job['dp_score_margin']}"
        f"-dm{job['dp_replacement_mask']}"
        f"-pm{job['production_dp_mask']}-fm{int(job['fine_mask_pruning'])}"
        f"-fb{int(job['fine_beat_pruning'])}"
        f"-fc{int(job['collecting_fine_history_carry'])}"
        f"-cw{job.get('correlation_seconds', -1.0)}"
        f"-so{int(job.get('selection_window_only', False))}"
        f"-cs{int(job.get('correlation_shadow_only', False))}"
        f"-jp{int(job.get('joint_pitch_residual', False))}"
        f"-t{job['input_trim']}"
        f"-se{job['sensitivity']}-r{job['response']}"
        f"-p{job['max_polyphony']}-f{job['max_fret']}.tsv"
    )
    output_path = MOUNT_ROOT / output_relative
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "/opt/m3/m3_replay",
        "--wav",
        str(MOUNT_ROOT / dataset["wav"]),
        "--labels",
        str(MOUNT_ROOT / dataset["labels"]),
        "--calibration",
        str(MOUNT_ROOT / "corpus/calibration.m3cb"),
        "--block",
        str(job["block"]),
        "--a4",
        "440",
        "--input-trim",
        str(job["input_trim"]),
        "--sensitivity",
        str(job["sensitivity"]),
        "--response",
        str(job["response"]),
        "--max-polyphony",
        str(job["max_polyphony"]),
        "--max-fret",
        str(job["max_fret"]),
    ]
    if bool(job.get("label_details", False)):
        command += [
            "--label-details",
            "--spectral-shadow-templates",
            str(MOUNT_ROOT / "corpus/templates.tsv"),
        ]
    fine_window_path = output_path.with_suffix(".fine-windows.jsonl")
    if bool(job.get("fine_window_dump", False)):
        command += ["--fine-window-dump", str(fine_window_path)]
        if int(job.get("fine_window_note", -1)) >= 0:
            command += ["--fine-window-note", str(int(job["fine_window_note"]))]
        command += ["--fine-window-start", str(job.get("fine_window_start", 0.0)),
                    "--fine-window-min-spacing", str(job.get("fine_window_min_spacing", 0.5))]
        if float(job.get("fine_window_end", -1.0)) >= 0.0:
            command += ["--fine-window-end", str(job["fine_window_end"])]
    selector_margin = float(job["selector_margin"])
    if selector_margin >= 0.0:
        command += [
            "--diagnostic-calibrated-selector-margin",
            f"{selector_margin:.9g}",
            "--diagnostic-calibrated-selector-string-mask",
            str(int(job["selector_mask"])),
        ]
    if float(job["dp_similarity"]) >= 0.0:
        command += [
            "--diagnostic-dp-replacement-similarity",
            f"{float(job['dp_similarity']):.9g}",
            "--diagnostic-dp-replacement-calibration-margin",
            f"{float(job['dp_calibration_margin']):.9g}",
            "--diagnostic-dp-replacement-score-margin",
            f"{float(job['dp_score_margin']):.9g}",
            "--diagnostic-dp-replacement-string-mask",
            str(int(job["dp_replacement_mask"])),
        ]
    command += [
        "--diagnostic-production-dp-replacement-string-mask",
        str(int(job["production_dp_mask"])),
    ]
    if bool(job.get("fine_mask_pruning", False)):
        command.append("--diagnostic-fine-mask-pruning")
    if bool(job.get("fine_beat_pruning", False)):
        command.append("--diagnostic-fine-beat-pruning")
    if bool(job.get("collecting_fine_history_carry", False)):
        command.append("--diagnostic-collecting-fine-history-carry")
    if float(job.get("correlation_seconds", -1.0)) != -1.0:
        command += [
            "--diagnostic-correlation-seconds",
            f"{float(job['correlation_seconds']):.9g}",
        ]
    if bool(job.get("selection_window_only", False)):
        command.append("--diagnostic-selection-window-only")
    if bool(job.get("correlation_shadow_only", False)):
        command.append("--diagnostic-correlation-shadow-only")
    if bool(job.get("joint_pitch_residual", False)):
        command.append("--diagnostic-joint-pitch-residual")
    started = time.monotonic()
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        timeout=3500,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"m3_replay failed ({completed.returncode}): "
            f"{completed.stderr[-2000:]}"
        )
    capture_metadata = None
    if bool(job.get("fine_window_dump", False)):
        found = re.search(r"fine_window_capture windows=(\d+) cap=(\d+) truncated=([01])", completed.stderr)
        if found is None:
            raise RuntimeError("fine-window export metadata is missing")
        capture_metadata = {"windows": int(found[1]), "cap": int(found[2]),
                            "truncated": found[3] == "1",
                            "sha256": _sha256(fine_window_path),
                            "start_seconds": float(job.get("fine_window_start", 0.0)),
                            "end_seconds": float(job.get("fine_window_end", -1.0)),
                            "min_spacing_seconds": float(job.get("fine_window_min_spacing", 0.5))}
    if bool(job.get("persist_tsv", False)):
        output_path.write_text(completed.stdout, encoding="utf-8")
    if bool(job.get("persist_tsv", False)) or bool(job.get("fine_window_dump", False)):
        volume.commit()
    result = _parse_aggregate(completed.stdout)
    result.update(
        {
            "dataset": job["dataset"],
            "fine_window_path": str(fine_window_path.relative_to(MOUNT_ROOT))
                if bool(job.get("fine_window_dump", False)) else "",
            "fine_window_capture": capture_metadata,
            "block": int(job["block"]),
            "selector_margin": selector_margin,
            "selector_mask": int(job["selector_mask"]),
            "dp_similarity": float(job["dp_similarity"]),
            "dp_calibration_margin": float(job["dp_calibration_margin"]),
            "dp_score_margin": float(job["dp_score_margin"]),
            "dp_replacement_mask": int(job["dp_replacement_mask"]),
            "production_dp_mask": int(job["production_dp_mask"]),
            "fine_mask_pruning": bool(job["fine_mask_pruning"]),
            "fine_beat_pruning": bool(job["fine_beat_pruning"]),
            "collecting_fine_history_carry": bool(
                job["collecting_fine_history_carry"]
            ),
            "input_trim": float(job["input_trim"]),
            "correlation_seconds": float(job.get("correlation_seconds", -1.0)),
            "selection_window_only": bool(job.get("selection_window_only", False)),
            "correlation_shadow_only": bool(job.get("correlation_shadow_only", False)),
            "joint_pitch_residual": bool(job.get("joint_pitch_residual", False)),
            "sensitivity": int(job["sensitivity"]),
            "response": int(job["response"]),
            "max_polyphony": int(job["max_polyphony"]),
            "max_fret": int(job["max_fret"]),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "result_path": (
                str(output_relative) if bool(job.get("persist_tsv", False)) else ""
            ),
            "binary_sha256": job["binary_sha256"],
        }
    )
    return result


@app.local_entrypoint()
def sync_corpus() -> None:
    missing = [str(path) for path in CORPUS_FILES.values() if not path.is_file()]
    if missing:
        raise SystemExit("missing protected corpus files:\n" + "\n".join(missing))
    if not REPLAY_BINARY.is_file() or REPLAY_BINARY.stat().st_size == 0:
        raise SystemExit(f"missing replay executable: {REPLAY_BINARY}")
    manifest: dict[str, dict[str, Any]] = {}
    with volume.batch_upload(force=True) as batch:
        for remote_name, local_path in CORPUS_FILES.items():
            batch.put_file(local_path, f"/corpus/{remote_name}")
            manifest[remote_name] = {
                "bytes": local_path.stat().st_size,
                "sha256": _sha256(local_path),
            }
        batch.put_file(
            io.BytesIO(
                json.dumps(
                    manifest, sort_keys=True, separators=(",", ":")
                ).encode()
            ),
            "/corpus/manifest.json",
        )
    print(
        json.dumps(
            {
                "volume": VOLUME_NAME,
                "files": len(manifest),
                "bytes": sum(item["bytes"] for item in manifest.values()),
            },
            sort_keys=True,
        )
    )


@app.local_entrypoint()
def sweep(
    datasets: str = "ordinary,physical-long",
    blocks: str = "512",
    selector_margins: str = "-1,0.02",
    selector_masks: str = "255",
    dp_similarities: str = "-1",
    dp_calibration_margins: str = "-1",
    dp_score_margins: str = "-1",
    dp_replacement_masks: str = "255",
    production_dp_masks: str = "56",
    fine_mask_pruning: bool = False,
    fine_beat_pruning: bool = False,
    collecting_fine_history_carry: bool = False,
    correlation_seconds: str = "-1",
    selection_window_only: bool = False,
    correlation_shadow_only: bool = False,
    joint_pitch_residual: bool = False,
    input_trims: str = "-9",
    sensitivities: str = "60",
    responses: str = "75",
    max_polyphonies: str = "5",
    max_frets: str = "24",
    label_details: bool = False,
    persist_tsv: bool = False,
    fine_window_dump: bool = False,
    fine_window_note: int = -1,
    fine_window_start: float = 0.0,
    fine_window_end: float = -1.0,
    fine_window_min_spacing: float = 0.5,
    tag: str = "manual",
    output: str = "build/modal/m3-replay-results.json",
) -> None:
    dataset_names = [value.strip() for value in datasets.split(",") if value.strip()]
    if fine_window_dump and not label_details:
        raise SystemExit("fine-window capture requires --label-details")
    if fine_window_note < -1 or fine_window_note > 127 or (fine_window_note >= 0 and not fine_window_dump):
        raise SystemExit("fine-window note requires capture and must be -1 or 0..127")
    if (not all(math.isfinite(v) for v in
                (fine_window_start, fine_window_end, fine_window_min_spacing))
            or fine_window_start < 0.0 or fine_window_min_spacing < 0.0
            or (fine_window_end != -1.0 and fine_window_end <= fine_window_start)):
        raise SystemExit("fine-window range requires 0 <= start < end (or end=-1), spacing >= 0")
    if not fine_window_dump and (fine_window_start, fine_window_end, fine_window_min_spacing) != (0.0, -1.0, 0.5):
        raise SystemExit("fine-window range and spacing require capture")
    unknown = sorted(set(dataset_names) - set(DATASETS))
    if unknown:
        raise SystemExit(f"unknown datasets: {','.join(unknown)}")
    block_sizes = [int(value) for value in blocks.split(",")]
    if any(value <= 0 or value > 4096 for value in block_sizes):
        raise SystemExit("blocks must be in 1..4096")
    margins = [float(value) for value in selector_margins.split(",")]
    if any(value < -1.0 or value > 1.0 for value in margins):
        raise SystemExit("selector margins must be -1 or in 0..1")
    masks = [int(value) for value in selector_masks.split(",")]
    if any(value <= 0 or value > 255 for value in masks):
        raise SystemExit("selector masks must be in 1..255")
    similarities = [float(value) for value in dp_similarities.split(",")]
    calibration_margins = [
        float(value) for value in dp_calibration_margins.split(",")
    ]
    score_margins = [float(value) for value in dp_score_margins.split(",")]
    replacement_masks = [int(value) for value in dp_replacement_masks.split(",")]
    production_masks = [int(value) for value in production_dp_masks.split(",")]
    correlation_windows = [float(value) for value in correlation_seconds.split(",")]
    if any(
        not math.isfinite(value)
        or (value != -1.0 and not 0.020 <= value <= 0.200)
        for value in correlation_windows
    ):
        raise SystemExit("correlation seconds must be -1 or in 0.020..0.200")
    if (selection_window_only or correlation_shadow_only) and any(
        value < 0.0 for value in correlation_windows
    ):
        raise SystemExit("secondary windows require an explicit duration")
    if selection_window_only and correlation_shadow_only:
        raise SystemExit("selection-only and shadow-only modes are exclusive")
    if joint_pitch_residual and any(value != -1.0 for value in correlation_windows):
        raise SystemExit("joint pitch residual requires the production window")
    trims = [float(value) for value in input_trims.split(",")]
    sensitivity_values = [int(value) for value in sensitivities.split(",")]
    response_values = [int(value) for value in responses.split(",")]
    polyphony_values = [int(value) for value in max_polyphonies.split(",")]
    fret_values = [int(value) for value in max_frets.split(",")]
    if any(value < -1.0 or value > 1.0 for value in similarities):
        raise SystemExit("DP similarities must be -1 or in 0..1")
    if any(value < -1.0 or value > 1.0 for value in calibration_margins):
        raise SystemExit("DP calibration margins must be -1 or in 0..1")
    if any(value < -1.0 or value > 10.0 for value in score_margins):
        raise SystemExit("DP score margins must be -1 or in 0..10")
    if any(value <= 0 or value > 255 for value in replacement_masks):
        raise SystemExit("DP replacement masks must be in 1..255")
    if any(value < 0 or value > 255 for value in production_masks):
        raise SystemExit("production DP masks must be in 0..255")
    if any(value < -24.0 or value > 24.0 for value in trims):
        raise SystemExit("input trims must be in -24..24")
    if any(value < 0 or value > 100 for value in sensitivity_values):
        raise SystemExit("sensitivities must be in 0..100")
    if any(value < 0 or value > 100 for value in response_values):
        raise SystemExit("responses must be in 0..100")
    if any(value < 1 or value > 8 for value in polyphony_values):
        raise SystemExit("max polyphonies must be in 1..8")
    if any(value < 0 or value > 36 for value in fret_values):
        raise SystemExit("max frets must be in 0..36")
    dp_disabled = (
        similarities == [-1.0]
        and calibration_margins == [-1.0]
        and score_margins == [-1.0]
    )
    if not dp_disabled and (
        any(value < 0.0 for value in similarities)
        or any(value < 0.0 for value in calibration_margins)
        or any(value < 0.0 for value in score_margins)
    ):
        raise SystemExit("DP replacement requires all three nonnegative knobs")
    binary_sha256 = _sha256(REPLAY_BINARY)
    run_id = f"{tag}-{int(time.time())}-{binary_sha256[:12]}"
    jobs = [
        {
            "dataset": dataset,
            "block": block,
            "selector_margin": margin,
            "selector_mask": mask,
            "label_details": label_details,
            "persist_tsv": persist_tsv or label_details,
            "fine_window_dump": fine_window_dump,
            "fine_window_note": fine_window_note,
            "fine_window_start": fine_window_start,
            "fine_window_end": fine_window_end,
            "fine_window_min_spacing": fine_window_min_spacing,
            "dp_similarity": similarity,
            "dp_calibration_margin": calibration_margin,
            "dp_score_margin": score_margin,
            "dp_replacement_mask": replacement_mask,
            "production_dp_mask": production_mask,
            "fine_mask_pruning": fine_mask_pruning,
            "fine_beat_pruning": fine_beat_pruning,
            "collecting_fine_history_carry": collecting_fine_history_carry,
            "correlation_seconds": correlation_window,
            "selection_window_only": selection_window_only,
            "correlation_shadow_only": correlation_shadow_only,
            "joint_pitch_residual": joint_pitch_residual,
            "input_trim": input_trim,
            "sensitivity": sensitivity,
            "response": response,
            "max_polyphony": max_polyphony,
            "max_fret": max_fret,
            "run_id": run_id,
            "binary_sha256": binary_sha256,
        }
        for dataset in dataset_names
        for block in block_sizes
        for margin in margins
        for mask in masks
        for similarity in similarities
        for calibration_margin in calibration_margins
        for score_margin in score_margins
        for replacement_mask in replacement_masks
        for production_mask in production_masks
        for correlation_window in correlation_windows
        for input_trim in trims
        for sensitivity in sensitivity_values
        for response in response_values
        for max_polyphony in polyphony_values
        for max_fret in fret_values
    ]
    results = list(run_replay.map(jobs, order_outputs=True, return_exceptions=True))
    failures = [repr(value) for value in results if isinstance(value, BaseException)]
    if failures:
        raise SystemExit("remote replay failures:\n" + "\n".join(failures))
    report = {
        "run_id": run_id,
        "binary_sha256": binary_sha256,
        "results": results,
    }
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "binary_sha256": binary_sha256,
                "jobs": len(results),
                "output": str(output_path),
            },
            sort_keys=True,
        )
    )
