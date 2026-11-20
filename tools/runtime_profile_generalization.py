"""Saved runtime-profile evaluation with explicit held-out pass or pitch splits.

Input shares must come from runtime measurements, never spectral bank templates.
This module does not read audio or change detector policy.
"""
import numpy as np


def evaluate(rows, *, holdout, lanes, harmonics=6):
    if harmonics not in (4, 6):
        raise ValueError('Expected four or six harmonics')
    if holdout not in ('pass', 'midi_note') or len(lanes) < 2 or len(set(lanes)) != len(lanes):
        raise ValueError('Explicit pass/pitch split and distinct lanes required')
    if len({r['clip'] for r in rows}) != len(rows):
        raise ValueError('Duplicate clip identity')
    selected = [r for r in rows if r['string'] in lanes]
    vectors = {}
    for r in selected:
        if r['measurement_source'] != 'runtime':
            raise ValueError('Runtime measurements required')
        if r['eligible']:
            x = np.asarray(r['shares'], dtype=float)
            if x.shape != (harmonics,) or not np.isfinite(x).all() or np.any(x <= 0):
                raise ValueError(f'{harmonics} finite positive shares required')
            x = np.log(x / x.sum())
            vectors[r['clip']] = x - x.mean()
    folds = []
    for held in sorted({r[holdout] for r in selected}):
        train = [r for r in selected if r[holdout] != held and r['eligible']]
        test = [r for r in selected if r[holdout] == held]
        supported = all(any(r['string'] == lane for r in train) for lane in lanes)
        outcomes = []
        if supported:
            x = np.asarray([vectors[r['clip']] for r in train])
            center, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
            z = (x-center)/scale
            prototypes = np.asarray([z[[r['string'] == lane for r in train]].mean(axis=0) for lane in lanes])
        for r in test:
            prediction = None
            reason = 'unsupported training lanes' if not supported else 'ineligible measurement'
            if supported and r['eligible']:
                distances = np.mean((prototypes-(vectors[r['clip']]-center)/scale)**2,axis=1)
                order = np.argsort(distances)
                reason = 'tied distances'
                if not np.isclose(distances[order[0]],distances[order[1]],rtol=1e-9,atol=1e-12):
                    prediction = lanes[int(order[0])]
                    reason = 'measured'
            outcomes.append(dict(clip=r['clip'], expected=r['string'], predicted=prediction, reason=reason))
        folds.append(dict(held=held, training_clips=[r['clip'] for r in train], outcomes=outcomes))
    outcomes = [o for f in folds for o in f['outcomes']]
    return dict(holdout=holdout, lanes=lanes, total=len(outcomes), correct=sum(o['expected']==o['predicted'] for o in outcomes),
                abstained=sum(o['predicted'] is None for o in outcomes), folds=folds,
                limitation='Offline isolated-profile generalization only; no chord, continuity, timing or MIDI acceptance.')
