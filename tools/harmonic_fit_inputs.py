"""Bind offline coupled-fit inputs to the capture and measured profile source."""

from __future__ import annotations

import itertools


def validate_coupled_inputs(prepared, control, profiles, control_hashes, profile_hashes):
    identity = ('dataset', 'capture_path', 'capture_sha256', 'calibration_sha256',
                'sample_rate', 'sources', 'windows', 'prepared_npz_sha256')
    if any(control.get('metadata', {}).get(key) != prepared.get(key) for key in identity):
        raise ValueError('control capture, calibration or observation identity differs')
    if control.get('fit_source_sha256') != control_hashes:
        raise ValueError('control source identity differs')
    if profiles.get('source_sha256') != profile_hashes:
        raise ValueError('profile extraction source identity differs')
    strings = sorted(source['string'] for source in prepared['sources'])
    if set(profiles['isolated']['prototypes']) != {str(string) for string in strings}:
        raise ValueError('profile source strings differ')
    if any(window['note'] != profiles['manifest']['note'] for window in prepared['windows']):
        raise ValueError('profile pitch differs')
    if {c['string'] for c in profiles['manifest']['clips'] if c['pass'] == 1} != set(strings):
        raise ValueError('profile training source strings differ')
    rows = control['results']
    if (len(rows) != len(prepared['windows']) or
            sorted(row['index'] for row in rows) != list(range(len(rows)))):
        raise ValueError('control window indices differ or are duplicated')
    families = ('static', 'pitch_drift', 'gain_drift', 'pitch_and_gain')
    masks = [sum(1 << s for s in selected) for count in range(1, min(4, len(strings)) + 1)
             for selected in itertools.combinations(strings, count)]
    expected = {(mask, family) for mask in masks for family in families}
    for row in rows:
        pairs = [(m['mask'], m['fit_family']) for m in row['models']]
        if len(pairs) != len(expected) or set(pairs) != expected:
            raise ValueError('control masks or model families differ or are duplicated')
        window = prepared['windows'][row['index']]
        if row['note'] != window['note'] or row['training_samples'] != window['training_samples']:
            raise ValueError('control fit does not match its observation window')
