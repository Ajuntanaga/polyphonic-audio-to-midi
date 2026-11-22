"""POST HOC, NOT PRE-REGISTERED.  Where in each label does the cropped-ONNX filter lose time?  Saved data only.

Written after CLAUDE-M3-ONNX-HOLD-GRID-20261122.py showed that the budget-failing losses do not shrink with a longer forward hold (label 364 loses
50.57 ms at every D up to 600).  A forward hold only extends the support past where a model span ENDS, so it cannot recover time at the START of a
note.  For every label that loses time at D = 220 this splits the lost CURRENT-present samples of the label's own pitch into head (before the first
filtered sample), tail (after the last) and middle (gaps between), and reports the onset offset (first filtered sample minus first CURRENT sample).
Cross-check: head + middle + tail must equal the scorer's own lost_ms per label.

Usage: python3 -P -E CLAUDE-M3-ONNX-HOLD-GRID-DIAGNOSTIC-20261122.py ORD_UNMOD ORD_ADAPTED
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('on', os.path.join(HERE, 'CLAUDE-M3-ONNX-SUPPORT-20261122.py'))
on = importlib.util.module_from_spec(spec)
spec.loader.exec_module(on)
ad, lo = on.ad, on.lo
from tools.native_neural_consensus import intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import union_spans  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-ONNX-HOLD-GRID-DIAGNOSTIC-20261122.json')


def filtered(ctx, model_spans, d):
    support = union_spans([*model_spans, *ctx['native']], sample_count=ctx['horizon'])
    held = ad.dil.dilate(support, int(d * ctx['rate'] / 1000), ctx['horizon'])
    return union_spans(intersect_spans(ctx['cur_spans'], held, sample_count=ctx['horizon']), sample_count=ctx['horizon'])


def clip(spans, pitch, s, e):
    return sorted((max(l, s), min(r, e)) for l, r, p in spans if p == pitch and r > s and l < e)


def total(iv):
    return sum(r - l for l, r in iv)


def split(cur_iv, fil_iv):
    """Lost samples of cur_iv not covered by fil_iv, split by position relative to the first and last covered sample."""
    if not cur_iv:
        return dict(head=0, middle=0, tail=0, onset_offset=None)
    if not fil_iv:
        return dict(head=total(cur_iv), middle=0, tail=0, onset_offset=None)
    first, last = fil_iv[0][0], fil_iv[-1][1]
    head = sum(max(0, min(r, first) - l) for l, r in cur_iv)
    tail = sum(max(0, r - max(l, last)) for l, r in cur_iv)
    lost = total(cur_iv) - total([(max(l, a), min(r, b)) for l, r in cur_iv for a, b in fil_iv if min(r, b) > max(l, a)])
    return dict(head=head, middle=lost - head - tail, tail=tail, onset_offset=first - cur_iv[0][0])


def main(p_unmod, p_adapt):
    ctx = ad.dataset_context('ordinary')
    horizon, ms = ctx['horizon'], 1000.0 / ctx['rate']
    labels = {lab['label_index']: lab for lab in ctx['labels']}
    out = {}
    for tag, path in (('cropped unmodified', p_unmod), ('cropped adapted', p_adapt)):
        spans = ad.spans_from_events(ad.read_events(path), horizon, 'emitted_ns')[0]
        out[tag] = {}
        for d in (220, 600):
            scorer = {r['label']: r for r in lo.loss_rows(ctx, spans, d)}
            fil = filtered(ctx, spans, d)
            rows = []
            for idx in sorted(scorer):
                lab = labels[idx]
                s, e, p = lab['start_sample'], lab['end_sample'], lab['midi_note']
                sp = split(clip(ctx['cur_spans'], p, s, e), clip(fil, p, s, e))
                rows.append(dict(label=idx, pitch=p, scorer_lost_ms=scorer[idx]['lost_ms'], head_ms=round(sp['head'] * ms, 2), middle_ms=round(sp['middle'] * ms, 2),
                                 tail_ms=round(sp['tail'] * ms, 2), onset_offset_ms=None if sp['onset_offset'] is None else round(sp['onset_offset'] * ms, 2),
                                 reconciles=abs((sp['head'] + sp['middle'] + sp['tail']) * ms - scorer[idx]['lost_ms']) < 0.05))
            out[tag][f'D{d}'] = rows
            print(tag, f'D={d}')
            for r in rows:
                print('  ', json.dumps(r))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
