"""Diagnostic early-label string evidence; run recorded audio only on GHA.

Fixed features and leave-one-pass-out evaluation. No detector policy changes.
The label edge is not asserted to be an acoustic attack.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from tools.controlled_descriptor_overlap import read_float_wave


def features(samples, rate, begin, end, note):
    count = round(rate * .080)
    if not 0 <= begin < end <= len(samples) or begin + 2 * count > end:
        raise ValueError('Insufficient early labeled audio')
    fundamental = 440 * 2 ** ((note - 69) / 12)
    powers = []
    widths = []
    for offset in (0, count):
        wave = samples[begin + offset:begin + offset + count].astype(float)
        wave -= wave.mean()
        power = np.abs(np.fft.rfft(wave * np.hanning(count))) ** 2
        hz = np.fft.rfftfreq(count, 1 / rate)
        energy, width = [], []
        for harmonic in range(1, 7):
            center = fundamental * harmonic
            band = np.abs(hz - center) <= fundamental * .35
            if not band.any() or center + fundamental * .35 >= rate / 2:
                raise ValueError('Unsupported harmonic band')
            p, f = power[band], hz[band]
            total = float(p.sum())
            centroid = float(np.dot(p, f) / max(total, 1e-30))
            energy.append(total)
            width.append(float(np.sqrt(np.dot(p, (f - centroid) ** 2) /
                                       max(total, 1e-30)) / fundamental))
        powers.append(energy)
        widths.append(width)
    powers = np.asarray(powers)
    if powers.sum() <= 1e-20:
        raise ValueError('Silent labeled segment')
    # A common floor avoids log(0); no held-out population statistic is used.
    log_power = np.log10(np.maximum(powers, powers.max() * 1e-10))
    shape = log_power.mean(axis=0)
    shape -= shape.mean()
    change = log_power[1] - log_power[0]
    prefix = samples[max(0, begin - 2 * count):begin]
    return {'shape': shape.tolist(), 'change': change.tolist(),
            'width': np.mean(widths, axis=0).tolist()}, {
        'prefix_samples': len(prefix),
        'prefix_nonzero_samples': int(np.count_nonzero(prefix)),
        'onset_verified': False,
        'window_reference': 'first 160ms of labeled interval'}


def evaluate(rows, lanes, groups):
    selected = [r for r in rows if r['string'] in lanes]
    if {r['pass'] for r in selected} != {1, 2, 3}:
        raise ValueError('Expected three recording passes')
    predictions, folds = [], []
    for held_pass in (1, 2, 3):
        train = [r for r in selected if r['pass'] != held_pass]
        test = [r for r in selected if r['pass'] == held_pass]
        if any(not any(r['string'] == lane for r in subset)
               for lane in lanes for subset in (train, test)):
            raise ValueError('Missing class in fold')
        def vector(row):
            return np.concatenate([row['features'][g] for g in groups])
        x = np.asarray([vector(r) for r in train])
        center, scale = x.mean(axis=0), x.std(axis=0)
        scale = np.maximum(scale, 1e-6)
        normalized = (x - center) / scale
        prototypes = np.asarray([normalized[[r['string'] == lane for r in train]].mean(axis=0)
                                 for lane in lanes])
        folds.append({'held_pass': held_pass, 'training_clips': [r['clip'] for r in train],
                      'test_clips': [r['clip'] for r in test],
                      'training_center': center.tolist(), 'training_scale': scale.tolist()})
        for row in test:
            distances = np.mean((prototypes - (vector(row) - center) / scale) ** 2, axis=1)
            order = np.argsort(distances)
            tied = bool(np.isclose(distances[order[0]], distances[order[1]], rtol=1e-9, atol=1e-12))
            prediction = None if tied else lanes[int(order[0])]
            predictions.append({'clip': row['clip'], 'held_pass': held_pass,
                                'expected': row['string'], 'predicted': prediction,
                                'distances': distances.tolist()})
    for fold in folds:
        outcomes = [r for r in predictions if r['held_pass'] == fold['held_pass']]
        fold.update(total=len(outcomes),
                    correct=sum(r['expected'] == r['predicted'] for r in outcomes),
                    abstained=sum(r['predicted'] is None for r in outcomes))
    correct = sum(r['expected'] == r['predicted'] for r in predictions)
    recall = {str(lane): {'correct': sum(r['expected'] == lane and r['predicted'] == lane for r in predictions),
                         'total': sum(r['expected'] == lane for r in predictions)} for lane in lanes}
    return {'lanes': lanes, 'features': groups, 'correct': correct,
            'total': len(predictions), 'per_class': recall, 'folds': folds,
            'predictions': predictions, 'metric': 'held-out isolated clips, not labeled-frame matches'}


def run(corpus, manifest, output):
    data = json.loads(manifest.read_text())
    rows = []
    seen = set()
    for item in data['clips']:
        name = item['clip']
        if Path(name).name != name or name in seen or item['midi_note'] != data['note']:
            raise ValueError('Invalid or duplicate clip identity')
        seen.add(name)
        path = corpus / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Clip hash mismatch: ' + name)
        rate, samples = read_float_wave(path)
        measured, context = features(samples, rate, item['labeled_begin'], item['labeled_end'], data['note'])
        rows.append({**item, 'features': measured, 'context': context})
    lanes = sorted({r['string'] for r in rows})
    if data['note'] != 52 or lanes != list(range(6)):
        raise ValueError('This bounded study requires note52 and all six feasible lanes')
    groups = [('shape',), ('change',), ('width',), ('shape', 'change', 'width')]
    result = {'schema': 'm3_short_window_identity_v1', 'measurements': rows,
              'source': data.get('source', {}),
              'input_provenance': {k: v for k, v in data.items() if k != 'clips'},
              'evaluations': [evaluate(rows, subset, list(g)) for subset in ([0, 1], lanes) for g in groups],
              'input_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
              'installed_output_changed': False, 'promotion_accepted': False,
              'limitations': ['Same-session pass holdout; sparse clips, no independent sessions.',
                             'Label-relative windows; nonzero prefix does not prove acoustic onset.',
                             'Known pitch and isolated recordings; no chord or realtime validation.',
                             'Fixed exploratory feature ablations; no model selection or tuned thresholds.']}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('corpus', 'manifest', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    run(args.corpus, args.manifest, args.output)
