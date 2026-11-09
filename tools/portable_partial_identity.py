"""Offline string-identity screen from isolated upper-harmonic measurements.

Ascending attacks supply prototypes; descending and checkpoint attacks are
held out. This screen does not change calibration, replay output, or MIDI.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.controlled_descriptor_overlap import read_float_wave
from tools.harmonic_balance_audit import measure_clip


SETTINGS = dict(minimum_upper_power_ratio=0.001, maximum_abs_partial_cents=35.0,
                minimum_valid_fraction=0.75, minimum_valid_frames=3,
                maximum_distance_cents=3.0, minimum_margin_cents=1.0)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feature(frames):
    """Do not turn weak or edge-of-search partials into known zero offsets."""
    valid = []
    for frame in frames:
        powers = np.asarray(frame['power'], dtype=float)
        cents = np.asarray(frame['partial_cents'], dtype=float)
        if (powers.shape != (3,) or cents.shape != (3,)
                or not np.isfinite(powers).all() or not np.isfinite(cents).all()
                or np.any(powers < 0)):
            raise ValueError('Invalid harmonic measurement')
        if (powers[0] > 0 and np.all(powers[1:] / powers[0] >=
                                   SETTINGS['minimum_upper_power_ratio'])
                and np.all(np.abs(cents[1:]) <= SETTINGS['maximum_abs_partial_cents'])):
            valid.append(cents[1:])
    fraction = len(valid) / len(frames) if frames else 0.0
    eligible = (len(valid) >= SETTINGS['minimum_valid_frames']
                and fraction >= SETTINGS['minimum_valid_fraction'])
    median = np.median(valid, axis=0) if valid else None
    return dict(frames=len(frames), valid_frames=len(valid), valid_fraction=fraction,
                eligible=eligible,
                partial_cents=median.tolist() if median is not None else None,
                mad_cents=np.median(np.abs(valid - median), axis=0).tolist()
                if median is not None else None)


def summarize(clips, expected_strings):
    """Freeze training before scoring holdouts; all feasible strings compete."""
    expected_strings = sorted(expected_strings)
    if sorted({c['string'] for c in clips}) != expected_strings:
        raise ValueError('Incomplete feasible-string coverage')
    if any(c['pass'] not in (1, 2, 3) for c in clips):
        raise ValueError('Unknown recording pass')
    if len({c['clip'] for c in clips}) != len(clips):
        raise ValueError('Duplicate attack')
    training, prototypes = {}, {}
    for string in expected_strings:
        attacks = [c for c in clips if c['string'] == string and c['pass'] == 1]
        passes = {c['pass'] for c in clips if c['string'] == string}
        if len(attacks) != 1 or passes != {1, 2, 3}:
            raise ValueError('Expected one training attack and separate holdouts per string')
        row = feature(attacks[0]['frames'])
        training[str(string)] = dict(clip=attacks[0]['clip'], **row)
        if row['eligible']:
            prototypes[str(string)] = row['partial_cents']
    complete = len(prototypes) == len(expected_strings)
    heldout = []
    for clip in clips:
        if clip['pass'] == 1:
            continue
        measured = feature(clip['frames'])
        distances = {}
        if measured['eligible']:
            distances = {string: float(np.sqrt(np.mean(
                (np.asarray(measured['partial_cents']) - value) ** 2)))
                for string, value in prototypes.items()}
        ranked = sorted(distances, key=lambda string: (distances[string], int(string)))
        margin = distances[ranked[1]] - distances[ranked[0]] if len(ranked) > 1 else None
        accepted = (complete and len(ranked) >= 2
                    and distances[ranked[0]] <= SETTINGS['maximum_distance_cents']
                    and margin >= SETTINGS['minimum_margin_cents'])
        heldout.append(dict(clip=clip['clip'], recording_pass=clip['pass'],
            expected_string=clip['string'], measurement=measured,
            distances_cents=distances, margin_cents=margin,
            nearest_string=int(ranked[0]) if ranked else None,
            admitted_string=int(ranked[0]) if accepted else None))
    correct = sum(r['admitted_string'] == r['expected_string'] for r in heldout)
    wrong = sum(r['admitted_string'] is not None and
                r['admitted_string'] != r['expected_string'] for r in heldout)
    return dict(settings=SETTINGS, training=training, prototypes=prototypes,
                all_feasible_prototypes_measured=complete, heldout=heldout,
                heldout_attacks=len(heldout), correctly_admitted_attacks=correct,
                wrongly_admitted_attacks=wrong,
                abstained_attacks=len(heldout) - correct - wrong,
                isolated_screen_pass=complete and correct == len(heldout),
                metric='isolated held-out attacks, not labeled-frame matches')


def run(manifest_path, corpus, output):
    manifest = json.loads(manifest_path.read_text())
    note = manifest['note']
    if (manifest.get('training_pass') != 1 or manifest.get('holdout_passes') != [2, 3]
            or type(note) is not int or not 0 <= note <= 127):
        raise ValueError('Unexpected split or note')
    expected = [s for s in range(8) if 0 <= note - (32 + 4 * s) <= 24]
    clips = []
    for item in manifest['clips']:
        name = item['clip']
        if Path(name).name != name or item['midi_note'] != note:
            raise ValueError('Invalid clip identity')
        path = corpus / name
        if digest(path) != item['sha256']:
            raise ValueError('Clip hash differs: ' + name)
        rate, samples = read_float_wave(path)
        frames = measure_clip(samples, rate, 440 * 2 ** ((note - 69) / 12),
                              item['labeled_begin'], item['labeled_end'])
        clips.append(dict(item, sample_rate=rate, frames=frames))
    result = dict(schema='m3_isolated_partial_identity_v1',
        created_at=datetime.now(timezone.utc).isoformat(),
        source=manifest.get('source', {}), note=note,
        input_manifest_sha256=digest(manifest_path),
        input_provenance={k: v for k, v in manifest.items() if k != 'clips'},
        measurements=clips, summary=summarize(clips, expected),
        installed_output_changed=False, promotion_accepted=False,
        labeled_frame_gain='not measured', unison_assignment='not measured',
        native_timing='not measured', live_readiness='not measured',
        limitations=[
            'Same-session isolated plucks only; overlapping windows are not independent attacks.',
            'Fixed exploratory quality and distance limits are not plugin acceptance thresholds.',
            'This peak search does not validate labels or reject every competing fundamental.',
            'Passing requires a later real-unison and absent-string control before native work.'])
    output.mkdir(parents=True, exist_ok=False)
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result['summary'], allow_nan=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.manifest, args.corpus, args.output)
