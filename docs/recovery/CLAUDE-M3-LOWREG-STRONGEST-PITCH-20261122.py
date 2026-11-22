"""POST-HOC audit after CLAUDE-M3-LOWREG-ACTIVATION-FATE-20261122 (declared as post-hoc, not pre-registered).

The fate check found R2 false: for the 53 A-silent lower labels whose activation is absent, the strongest
mean activation during the label is NOT an octave or fifth of the label pitch.  Where is it?  Descriptive only:
histogram of (strongest pitch - label pitch), and how the strongest compares with the label-pitch activation.
Written 2026-11-22 after the fate result.  Saved arrays only.  Usage as the fate script (python3 -P -E ...).
"""
import gzip
import json
import os
import sys
from collections import Counter

import importlib.util
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('fate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ACTIVATION-FATE-20261122.py'))
fate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fate)
split = fate.split
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-STRONGEST-PITCH-20261122.json')


def run(evidence_dir, stream_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    data = report['datasets']['ordinary']
    base = baseline['datasets']['ordinary']
    horizon = data['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    with gzip.open(os.path.join(evidence_dir, 'ordinary-bridge-events.json.gz'), 'rt', encoding='utf-8') as stream:
        a_spans = [tuple(s) for s in json.load(stream)['arm_spans']['A']]
    arrays = np.load(os.path.join(stream_dir, 'ordinary-stream.npz'), allow_pickle=False)
    note, onset = arrays['note'], arrays['onset']
    rows = []
    for row in score(a_spans, labels, **clock)['labels']:
        if row['midi_note'] >= split.SPLIT or row['present_samples'] != 0:
            continue
        act = fate.label_activation(row, note, onset)
        if act and fate.classify(act) == 'absent':
            rows.append((row['midi_note'], act))
    deltas = Counter(a['strongest'] - m for m, a in rows)
    above = sum(1 for m, a in rows if a['strongest'] > m)
    ratio = sorted(round(a['own_mean'] / a['strongest_mean'], 2) for m, a in rows)
    out = dict(n=len(rows), strongest_minus_label_pitch=dict(sorted(deltas.items())),
               strongest_above_label=above, strongest_within_2_semitones=sum(abs(d) <= 2 for d in deltas.elements()),
               strongest_at_or_above_60=sum(1 for m, a in rows if a['strongest'] >= 60),
               own_over_strongest_mean_quantiles=[ratio[int(q * (len(ratio) - 1))] for q in (0, .25, .5, .75, 1)],
               strongest_mean_quantiles=[round(float(q), 3) for q in np.quantile([a['strongest_mean'] for m, a in rows], [.1, .5, .9])])
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1], sys.argv[2])))
