"""Per-label loss tables for the adapted-support filter (post hoc, saved data only).

POST HOC, written after CLAUDE-M3-ADAPTED-SUPPORT-RESULT-20261122.md.  The result note lists WHICH labels lose present or longest hold under
arm A, the unchanged-TF events and the adapted-TF events (availability clock); the gate question to the user needs HOW MUCH each loses, because
a per-label tolerance is only worth proposing if the remaining losers are small.  For each support and each hold D this prints, on the ordinary
corpus, the number of losing labels, the total lost pitch-samples, the median and maximum loss in ms and as a share of the label's own CURRENT
present time, how many losers exceed 5, 10, 25 and 50% of their own present time, and the full table of the losers at D = 220.

Usage: python3 -P -E CLAUDE-M3-ADAPTED-SUPPORT-LOSERS-20261122.py ORD_ORIGINAL_EVENTS ORD_ADAPTED_EVENTS
Writes CLAUDE-M3-ADAPTED-SUPPORT-LOSERS-20261122.json next to this file.  No audio, no model, no job.
"""
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ad', os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py'))
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)
from tools.native_neural_consensus import intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-LOSERS-20261122.json')


def loss_rows(ctx, model_spans, d):
    """One row per label whose present or longest hold falls under the filter."""
    support = union_spans([*model_spans, *ctx['native']], sample_count=ctx['horizon'])
    held = ad.dil.dilate(support, int(d * ctx['rate'] / 1000), ctx['horizon'])
    spans = union_spans(intersect_spans(ctx['cur_spans'], held, sample_count=ctx['horizon']), sample_count=ctx['horizon'])
    cmp = compare(ctx['current'], score(spans, ctx['labels'], **ctx['clock']))
    cur = {lab['label_index']: lab for lab in ctx['current']['labels']}
    ms = 1000.0 / ctx['rate']
    rows = []
    for r in cmp['label_deltas']:
        if r['present_samples_delta'] >= 0 and r['longest_present_samples_delta'] >= 0:
            continue
        lab = cur[r['label_index']]
        present = lab['present_samples']
        lost = -min(r['present_samples_delta'], 0)
        longest_lost = -min(r['longest_present_samples_delta'], 0)
        rows.append(dict(label=r['label_index'], pitch=lab['midi_note'], current_present_ms=round(present * ms, 1),
                         lost_ms=round(lost * ms, 2), lost_share=round(lost / present, 4) if present else None,
                         longest_lost_ms=round(longest_lost * ms, 2),
                         longest_lost_share=round(longest_lost / lab['longest_present_samples'], 4) if lab['longest_present_samples'] else None))
    return rows


def summary(rows):
    shares = [max(r['lost_share'] or 0, r['longest_lost_share'] or 0) for r in rows]
    losses = [max(r['lost_ms'], r['longest_lost_ms']) for r in rows]
    return dict(labels_losing=len(rows), median_loss_ms=round(statistics.median(losses), 2) if rows else 0.0,
                max_loss_ms=max(losses, default=0.0),
                median_share=round(statistics.median(shares), 4) if rows else 0.0,
                over_5_10_25_50=[sum(1 for s in shares if s > t) for t in (0.05, 0.10, 0.25, 0.50)])


def main(ord_o, ord_a):
    ctx = ad.dataset_context('ordinary')
    horizon = ctx['horizon']
    views = {'arm A': ctx['arm_a']}
    for tag, path in (('unchanged TF (available_ns)', ord_o), ('adapted TF (available_ns)', ord_a)):
        views[tag] = ad.spans_from_events(ad.read_events(path), horizon, 'available_ns')[0]
    views['arm A union adapted (available_ns)'] = union_spans([*views['arm A'], *views['adapted TF (available_ns)']], sample_count=horizon)
    out = {}
    for d in (220, 50):
        out[f'D{d}'] = {}
        for name, spans in views.items():
            rows = loss_rows(ctx, spans, d)
            out[f'D{d}'][name] = dict(summary=summary(rows), losers=rows)
            print(f'D={d}', name, json.dumps(summary(rows)))
    for name in views:
        print('D=220 losers', name)
        for r in out['D220'][name]['losers']:
            print('  ', json.dumps(r))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
