"""Post-hoc controls for CLAUDE-M3-ADAPTED-SUPPORT-20261122: how much of the emitted-clock result is just the native confirmation, and which labels still lose.

POST HOC, written after CLAUDE-M3-ADAPTED-SUPPORT-20261122.py had been run on Codex's four event files (both clocks); not part of the
pre-registered predictions.  Two questions, saved data only, no audio or job:
 (1) NATIVE-ONLY CONTROL: the support (native confirmation only, no model spans), held D ms, filter CURRENT intersect support.  If the
     emitted-clock model supports score like this row, the 72 s FIFO backlog made the model spans irrelevant and the emitted-clock comparison
     of unchanged vs adapted says nothing about content.
 (2) LOSERS: which labels (index, MIDI note) lose present or longest hold at D = 220 and D = 50 on ordinary under arm A, and under the
     unchanged and adapted events on the availability clock (the content view), and which are shared.
Usage: python3 -P -E CLAUDE-M3-ADAPTED-SUPPORT-CONTROL-20261122.py ORD_ORIGINAL ORD_ADAPTED
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ad', os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py'))
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)
from tools.native_neural_consensus import intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-CONTROL-20261122.json')


def losers(ctx, model_spans, d):
    support = union_spans([*model_spans, *ctx['native']], sample_count=ctx['horizon'])
    held = ad.dil.dilate(support, int(d * ctx['rate'] / 1000), ctx['horizon'])
    spans = union_spans(intersect_spans(ctx['cur_spans'], held, sample_count=ctx['horizon']), sample_count=ctx['horizon'])
    cmp = compare(ctx['current'], score(spans, ctx['labels'], **ctx['clock']))
    by = {lab['label_index']: lab for lab in ctx['labels']}
    return {r['label_index']: by[r['label_index']]['midi_note'] for r in cmp['label_deltas']
            if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0}


def main(ord_o, ord_a):
    out = dict(native_only_control={}, losers={})
    for dataset in ('ordinary', 'extended-middle'):
        ctx = ad.dataset_context(dataset)
        out['native_only_control'][dataset] = ad.score_filters(ctx, [])
    ctx = ad.dataset_context('ordinary')
    horizon = ctx['horizon']
    views = {'arm A': ctx['arm_a']}
    for tag, path in (('unchanged TF (available_ns)', ord_o), ('adapted TF (available_ns)', ord_a)):
        views[tag] = ad.spans_from_events(ad.read_events(path), horizon, 'available_ns')[0]
    for d in (220, 50):
        rows = {name: losers(ctx, spans, d) for name, spans in views.items()}
        shared = set(rows['arm A']) & set(rows['unchanged TF (available_ns)']) & set(rows['adapted TF (available_ns)'])
        out['losers'][f'D{d}'] = dict(by_view={k: {str(i): n for i, n in sorted(v.items())} for k, v in rows.items()},
                                     in_all_three=sorted(shared),
                                     fixed_by_adapted_vs_unchanged=sorted(set(rows['unchanged TF (available_ns)']) - set(rows['adapted TF (available_ns)'])),
                                     new_under_adapted_vs_unchanged=sorted(set(rows['adapted TF (available_ns)']) - set(rows['unchanged TF (available_ns)'])))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    for dataset, rows in out['native_only_control'].items():
        for d, row in rows.items():
            print('native only', dataset, 'D', d, json.dumps({k: row[k] for k in ('coverage_pct', 'precision_pct', 'present_delta', 'wrong_removed_share',
                                                                                'gap_delta', 'labels_losing_present_or_longest', 'lost_share_of_current_present')}))
    for d, row in out['losers'].items():
        print(d, json.dumps(row))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
