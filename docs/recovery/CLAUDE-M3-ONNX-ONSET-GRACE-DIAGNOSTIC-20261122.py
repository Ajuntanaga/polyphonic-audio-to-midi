"""POST HOC, NOT PRE-REGISTERED.  Why does an onset grace not recover labels 263 and 364?  Saved data only.

Written after CLAUDE-M3-ONNX-ONSET-GRACE-20261122.py showed labels 263 and 364 losing the same 34.83 / 50.57 ms at every grace G up to 100 ms.  For
each such label this prints, in ms relative to the label's start sample, the CURRENT spans, the cropped-adapted model spans and the native-confirmation
spans of the label's own pitch in a window around the label start.  Spans are listed as [start, end) in ms.

Usage: python3 -P -E CLAUDE-M3-ONNX-ONSET-GRACE-DIAGNOSTIC-20261122.py ORD_ADAPTED
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('on', os.path.join(HERE, 'CLAUDE-M3-ONNX-SUPPORT-20261122.py'))
on = importlib.util.module_from_spec(spec)
spec.loader.exec_module(on)
ad = on.ad
OUT = os.path.join(HERE, 'CLAUDE-M3-ONNX-ONSET-GRACE-DIAGNOSTIC-20261122.json')
LABELS = (263, 364, 389, 398, 42)
BEFORE_MS, AFTER_MS = 1500.0, 300.0


def near(spans, pitch, s, ms_per, before, after):
    lo_, hi_ = s - before / ms_per, s + after / ms_per
    return [[round((l - s) * ms_per, 1), round((r - s) * ms_per, 1)] for l, r, p in spans if p == pitch and r > lo_ and l < hi_]


def main(p_adapt):
    ctx = ad.dataset_context('ordinary')
    ms = 1000.0 / ctx['rate']
    model = ad.spans_from_events(ad.read_events(p_adapt), ctx['horizon'], 'emitted_ns')[0]
    labels = {lab['label_index']: lab for lab in ctx['labels']}
    out = {}
    for idx in LABELS:
        lab = labels[idx]
        s, e, p = lab['start_sample'], lab['end_sample'], lab['midi_note']
        row = dict(label=idx, pitch=p, label_length_ms=round((e - s) * ms, 1),
                   current=near(ctx['cur_spans'], p, s, ms, BEFORE_MS, AFTER_MS),
                   model=near(model, p, s, ms, BEFORE_MS, AFTER_MS),
                   native=near([tuple(x) for x in ctx['native']], p, s, ms, BEFORE_MS, AFTER_MS))
        # previous label of the same pitch
        prev = [l2 for l2 in ctx['labels'] if l2['midi_note'] == p and l2['end_sample'] <= s]
        row['previous_same_pitch_label_ends_ms_before'] = round((s - max(l2['end_sample'] for l2 in prev)) * ms, 1) if prev else None
        out[idx] = row
        print(json.dumps(row))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
