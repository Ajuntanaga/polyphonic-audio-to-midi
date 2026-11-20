"""Bounded GHA-only recorded joint-fit diagnostic; no detector policy changes.

Manifest schema 1: windows contain id, wave (relative to input root),
wave_sha256, sample_rate_hz, begin/end (exclusive), and frequency_sets.
Each set has input_role, fundamentals_hz, and provenance (source, sha256,
sample). Detector provenance sample must be no later than window begin.
Oracle and detector sets are independently supplied, never filled from each
other. Isolated controls use the same schema and explicit input roles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from tools.cross_pitch_shape_fit import fit_shape


def read_input_wave(path):
    """Accept the two pinned corpus encodings without resampling or normalization."""
    rate, samples = wavfile.read(path)
    if rate <= 0 or samples.ndim != 1:
        raise ValueError('Expected mono waveform with positive sample rate')
    if samples.dtype == np.int16:
        samples = samples.astype(np.float64) / 32768.0
    elif samples.dtype != np.float32:
        raise ValueError('Expected PCM16 or float32 waveform')
    if not np.isfinite(samples).all():
        raise ValueError('Nonfinite waveform')
    return rate, samples


def evaluate_window(samples, rate, window):
    begin, end = window['begin'], window['end']
    if (type(begin) is not int or type(end) is not int or
            not 0 <= begin < end <= len(samples) or end - begin > rate * .320):
        raise ValueError('Expected bounded window of at most 320ms')
    if rate != window['sample_rate_hz']:
        raise ValueError('Sample rate mismatch')
    sets = window['frequency_sets']
    if not 1 <= len(sets) <= 2 or len({s['input_role'] for s in sets}) != len(sets):
        raise ValueError('Expected one or two distinct input roles')
    results = []
    for spec in sets:
        provenance = spec['provenance']
        if (not provenance['source'] or len(provenance['sha256']) != 64 or
                type(provenance['sample']) is not int):
            raise ValueError('Frequency provenance required')
        if spec['input_role'] == 'detector_candidates' and provenance['sample'] > begin:
            raise ValueError('Detector frequencies must precede the fitted window')
        result = fit_shape(samples[begin:end], rate, spec['fundamentals_hz'],
                           input_role=spec['input_role'], harmonics=6)
        results.append({'provenance': provenance, **result})
    return {'id': window['id'], 'begin': begin, 'end': end,
            'wave_sha256': window['wave_sha256'], 'onset_verified': False,
            'fits': results}


def run(manifest, root):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Recorded audio execution requires GitHub Actions')
    windows = manifest['windows']
    if (manifest['schema_version'] != 1 or not 1 <= len(windows) <= 32 or
            len({w['id'] for w in windows}) != len(windows)):
        raise ValueError('Expected at most 32 uniquely identified windows')
    root = Path(root).resolve()
    results = []
    # Group by input to avoid repeatedly decoding the same waveform.
    for name in dict.fromkeys(w['wave'] for w in windows):
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Waveform outside input root')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        selected = [w for w in windows if w['wave'] == name]
        if any(w['wave_sha256'] != digest for w in selected):
            raise ValueError('Waveform hash mismatch')
        for window in selected:
            for spec in window['frequency_sets']:
                provenance = spec['provenance']
                source = (root / provenance['source']).resolve()
                if not source.is_relative_to(root):
                    raise ValueError('Frequency source outside input root')
                with source.open('rb') as stream:
                    source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
                if source_hash != provenance['sha256']:
                    raise ValueError('Frequency source hash mismatch')
        rate, samples = read_input_wave(path)
        results.extend(evaluate_window(samples, rate, w) for w in selected)
    return {'schema_version': 1, 'policy_admission': False,
            'installed_output_changed': False,
            'interpretation': 'Supplied-frequency offline fits, not tracking or timing gains',
            'windows': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    report = run(json.loads(raw), args.input_root)
    report['manifest_sha256'] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
