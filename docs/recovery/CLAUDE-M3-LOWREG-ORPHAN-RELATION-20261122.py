"""What are CURRENT's lower-band orphan spans?  Saved spans and labels only.

No audio, model run or job.  The false-output anatomy (CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY-20261121) found that
CURRENT's lower band (below MIDI 60) has 4,038,208 orphan false samples on the ordinary corpus (36.5% of its 11.07M
lower false output; 219 of 517 spans): the sounded pitch overlaps NO label of its own pitch.  The tail-state work
dealt with the tails (58%); this asks what the orphans are.  For every orphan span, each stretch with a constant set
of active labels is classified by the interval d = span pitch - label pitch to the active labels:
  gap     no label active at all (output in silence between notes)
  octave  some active label has d a nonzero multiple of 12 (reported below / above the label, nearest such label)
  fifth   else some active label has d mod 12 == 7 (twelfth-like: 19, 31, -5, -17, ...)
  near    else some active label has |d| <= 2 (neighbor, bend, detune)
  other   anything else
Sample-weighted, each sample counted once.  Sanity check T0: the orphan false total for ordinary lower spans must equal
the anatomy result, 4,038,208.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the anatomy numbers above and the saved span/label structures.  NOT seen: any orphan classification.
Predictions, each can fail:
  O0  the lower orphan false total reproduces 4,038,208 exactly.
  O1  at least 50% of orphan samples are in `gap` (no label active).
  O2  among orphan samples with some label active, `octave` is at least 50%.
  O3  among orphan samples with some label active, `near` is at least 20%.
  O4  among `octave` orphan samples, at least 60% are BELOW the label pitch (a sub-octave).
Report the whole breakdown whatever it shows.  Pitch occupancy only; no lane, unison, timing or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ORPHAN-RELATION-20261122.py   (reads the pinned report and baseline JSONs)
"""
import importlib.util
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('audit', os.path.join(HERE, 'CLAUDE-M3-TAIL-CLIP-LOSS-AUDIT-20261121.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
split = audit.split
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORPHAN-RELATION-20261122.json')
SR = split.SAMPLE_RATE


def classify(pitch, active):
    if not active:
        return 'gap', None
    diffs = [pitch - n for n in active]
    octs = [d for d in diffs if d != 0 and d % 12 == 0]
    if octs:
        near = min(octs, key=abs)
        return 'octave', 'below' if near < 0 else 'above'
    if any(d % 12 == 7 for d in diffs):
        return 'fifth', None
    if any(abs(d) <= 2 for d in diffs):
        return 'near', None
    return 'other', None


def run():
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    name = 'ordinary'
    base = baseline['datasets'][name]
    horizon = report['datasets'][name]['common_support']['sample_count']
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    spans = clip_spans(base['pitch_spans'], horizon)
    cuts = sorted({s for l in labels for s in (l['start_sample'], l['end_sample'])})
    samples = Counter()
    direction = Counter()
    spans_by_class = Counter()
    pitch_samples = Counter()
    lengths = []
    orphan_total = 0
    n_orphan = 0
    for left, right, note in spans:
        if note >= split.SPLIT:
            continue
        own = [l for l in labels if l['midi_note'] == note and l['start_sample'] < right and l['end_sample'] > left]
        if own:
            continue
        n_orphan += 1
        lengths.append(right - left)
        orphan_total += right - left
        pitch_samples[note] += right - left
        edges = [left] + [c for c in cuts if left < c < right] + [right]
        seen = set()
        for a, b in zip(edges, edges[1:]):
            active = [l['midi_note'] for l in labels if l['start_sample'] < b and l['end_sample'] > a]
            kind, side = classify(note, active)
            samples[kind] += b - a
            seen.add(kind)
            if kind == 'octave':
                direction[side] += b - a
        for kind in seen:
            spans_by_class[kind] += 1
    lengths.sort()
    with_label = sum(v for k, v in samples.items() if k != 'gap')
    out = dict(
        orphan_spans=n_orphan, orphan_samples=orphan_total, anatomy_pin=4038208,
        class_samples={k: samples[k] for k in ('gap', 'octave', 'fifth', 'near', 'other')},
        class_share_of_orphan={k: round(samples[k] / orphan_total, 3) for k in ('gap', 'octave', 'fifth', 'near', 'other')},
        class_share_with_label_active={k: round(samples[k] / with_label, 3) if with_label else None
                                       for k in ('octave', 'fifth', 'near', 'other')},
        spans_touching_class={k: spans_by_class[k] for k in ('gap', 'octave', 'fifth', 'near', 'other')},
        octave_direction_samples=dict(direction),
        octave_below_share=round(direction['below'] / (direction['below'] + direction['above']), 3)
        if direction['below'] + direction['above'] else None,
        orphan_span_ms_quantiles=[round(lengths[int(q * (len(lengths) - 1))] * 1000 / SR, 1) for q in (0, .25, .5, .75, 1)],
        orphan_samples_by_pitch=dict(sorted(pitch_samples.items())))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(), indent=1))
