"""Chance control for the orphan-relation result: is the interval to the active labels above what a time-shifted label timeline gives?  Saved spans and labels only.

No audio, model run or job.  The orphan-relation result (CLAUDE-M3-LOWREG-ORPHAN-RELATION-20261122) classified each
lower orphan stretch by the interval to the labels sounding then (octave, fifth, near, other) and said 56% was an octave or
twelfth of an active label.  I flagged but did not quantify that a chord has several active labels, so a relation to
SOME label is likely by chance: octave, fifth and near cover 6 of the 12 pitch-class offsets.  This control keeps the real
orphan spans (found against the real labels) and replaces only the label timeline used for the relation test by a copy
shifted in time by a fixed offset (wrapping inside the common horizon).  That preserves the chord statistics and destroys
the temporal tie between an orphan and its parent label.  It also tests onset alignment: the share of orphan spans that
start within -50 ms to +250 ms of the onset of a label of octave or fifth class.

Shifts, fixed: 7, 13, 29, 41, 53, 67 s.  Real value and shifted mean are reported with the six shifted values.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the orphan-relation class shares (octave 45.6%, fifth 20.0%, near 19.4%, other 15.0% when a label is
active) and the oracle substitution result.  NOT seen: any shifted value.  Predictions, each can fail:
  N1  the real octave share (among label-active orphan samples) exceeds the shifted mean by at least 10 points.
  N2  the real fifth share exceeds the shifted mean by at least 5 points.
  N3  the real share with any related label (octave, fifth or near) exceeds the shifted mean by at least 5 points.
  N4  the real share of orphan spans starting within -50..+250 ms of the onset of an octave or fifth class label is at
      least twice the shifted mean.
Report the whole table whatever it shows.  Pitch occupancy only; no lane, unison, timing or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ORPHAN-NULL-20261122.py
"""
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('orph', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORPHAN-RELATION-20261122.py'))
orph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orph)
split = orph.split
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORPHAN-NULL-20261122.json')
SR = split.SAMPLE_RATE
SHIFTS_S = (0, 7, 13, 29, 41, 53, 67)       # 0 = the real timeline
WINDOW = (-int(0.050 * SR), int(0.250 * SR))


def shifted(labels, shift, horizon):
    out = []
    for l in labels:
        a = (l['start_sample'] + shift) % horizon
        b = min(horizon, a + (l['end_sample'] - l['start_sample']))
        out.append(dict(midi_note=l['midi_note'], start_sample=a, end_sample=b))
    return out


def measure(orphans, timeline):
    cuts = sorted({s for l in timeline for s in (l['start_sample'], l['end_sample'])})
    samples = Counter()
    aligned = 0
    for left, right, note in orphans:
        edges = [left] + [c for c in cuts if left < c < right] + [right]
        for a, b in zip(edges, edges[1:]):
            active = [l['midi_note'] for l in timeline if l['start_sample'] < b and l['end_sample'] > a]
            kind, _side = orph.classify(note, active)
            samples[kind] += b - a
        for l in timeline:
            d = note - l['midi_note']
            if d != 0 and (d % 12 in (0, 7)) and WINDOW[0] <= left - l['start_sample'] <= WINDOW[1]:
                aligned += 1
                break
    with_label = sum(v for k, v in samples.items() if k != 'gap')
    total = sum(samples.values())
    return dict(
        octave=samples['octave'] / with_label, fifth=samples['fifth'] / with_label, near=samples['near'] / with_label,
        other=samples['other'] / with_label, related=(samples['octave'] + samples['fifth'] + samples['near']) / with_label,
        gap_share_of_orphan=samples['gap'] / total, aligned_span_share=aligned / len(orphans))


def run():
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    base = baseline['datasets']['ordinary']
    horizon = report['datasets']['ordinary']['common_support']['sample_count']
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    spans = clip_spans(base['pitch_spans'], horizon)
    orphans = [(l, r, n) for l, r, n in spans if n < split.SPLIT and not any(
        x['midi_note'] == n and x['start_sample'] < r and x['end_sample'] > l for x in labels)]
    rows = {}
    for shift in SHIFTS_S:
        timeline = labels if shift == 0 else shifted(labels, shift * SR, horizon)
        rows[shift] = {k: round(v, 3) for k, v in measure(orphans, timeline).items()}
    keys = ('octave', 'fifth', 'near', 'other', 'related', 'gap_share_of_orphan', 'aligned_span_share')
    mean = {k: round(sum(rows[s][k] for s in SHIFTS_S if s) / (len(SHIFTS_S) - 1), 3) for k in keys}
    out = dict(orphan_spans=len(orphans), real=rows[0], shifted_mean=mean,
               excess_points={k: round(100 * (rows[0][k] - mean[k]), 1) for k in keys},
               shifted_each={str(s): rows[s] for s in SHIFTS_S if s})
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(), indent=1))
