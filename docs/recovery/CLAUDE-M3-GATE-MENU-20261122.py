"""A decision aid for the label-clause question: what each saved candidate gives, and how many labels each per-label tolerance would reject.

NOT a gate and NOT a pass.  The tolerance grid X in {0, 1, 5, 10, 25, 50}% of a label's own CURRENT present time (and of its longest hold) is
fixed here before the run so no value is chosen after looking; the user picks the rule, and Codex's frozen gates are not touched.  Saved
data only: no audio, model run, job or native edit.

Candidates (ordinary, common horizon; extended-middle where a span source exists):
  CURRENT                                  the saved reference
  Basic Pitch arm A, replacement           the saved ONNX offline causal run used alone (not a real-time measurement)
  CURRENT union arm A                      additive: nothing CURRENT emits is removed
  filter arm A + native, D = 220 / 50      CURRENT intersect (arm A union native confirmation held D ms)
  filter adapted + native, D = 220 / 50    the same with Codex's adapted-TF events (zero-compute availability clock, content only)
For each: coverage, precision, wrong-pitch and gap-voice change against CURRENT, exact-set share of annotated samples, runs, the largest single
label loss, and the number of labels that lose more than X of their own present time or longest hold.

Usage: python3 -P -E CLAUDE-M3-GATE-MENU-20261122.py ORD_ADAPTED_EVENTS EXT_ADAPTED_EVENTS
Writes CLAUDE-M3-GATE-MENU-20261122.json next to this file.
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

OUT = os.path.join(HERE, 'CLAUDE-M3-GATE-MENU-20261122.json')
TOLERANCES = (0.0, 0.01, 0.05, 0.10, 0.25, 0.50)


def filtered(ctx, model_spans, d):
    support = union_spans([*model_spans, *ctx['native']], sample_count=ctx['horizon'])
    held = ad.dil.dilate(support, int(d * ctx['rate'] / 1000), ctx['horizon'])
    return union_spans(intersect_spans(ctx['cur_spans'], held, sample_count=ctx['horizon']), sample_count=ctx['horizon'])


def evaluate(ctx, spans):
    cur = ctx['current']
    sc = score(spans, ctx['labels'], **ctx['clock'])
    ct, t = cur['pitch_sets']['totals'], sc['pitch_sets']['totals']
    cg, g = cur['pitch_sets']['unlabeled_gap_voice_samples'], sc['pitch_sets']['unlabeled_gap_voice_samples']
    cmp = compare(cur, sc)
    by = {lab['label_index']: lab for lab in cur['labels']}
    shares = []
    for r in cmp['label_deltas']:
        lab = by[r['label_index']]
        p, lp = lab['present_samples'], lab['longest_present_samples']
        s1 = max(0, -r['present_samples_delta']) / p if p else 0.0
        s2 = max(0, -r['longest_present_samples_delta']) / lp if lp else 0.0
        shares.append(max(s1, s2))
    false = t['extra_pitch_voice_samples'] + g
    return dict(
        coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 2),
        precision_pct=round(100 * t['present_pitch_samples'] / max(1, t['present_pitch_samples'] + false), 2),
        wrong_change_pct=round(100 * (t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples']) / max(1, ct['extra_pitch_voice_samples']), 1),
        gap_change_pct=round(100 * (g - cg) / max(1, cg), 1),
        exact_set_pct_of_annotated=round(100 * t['exact_pitch_set_samples'] / max(1, t['annotated_samples']), 2),
        runs=len(spans), runs_vs_current_pct=round(100 * (len(spans) - len(ctx['cur_spans'])) / max(1, len(ctx['cur_spans'])), 1),
        labels_losing_any=sum(1 for s in shares if s > 0), largest_label_loss_share=round(max(shares, default=0.0), 4),
        labels_over_tolerance={f'{int(x * 100)}%': sum(1 for s in shares if s > x) for x in TOLERANCES})


def candidates(ctx, adapted_spans):
    cands = {'CURRENT': ctx['cur_spans']}
    if ctx['arm_a'] is not None:
        cands['Basic Pitch arm A, replacement'] = ctx['arm_a']
        cands['CURRENT union arm A'] = union_spans([*ctx['cur_spans'], *ctx['arm_a']], sample_count=ctx['horizon'])
        for d in (220, 50):
            cands[f'filter arm A + native, D={d}'] = filtered(ctx, ctx['arm_a'], d)
    if adapted_spans is not None:
        cands['adapted TF (availability), replacement'] = adapted_spans
        for d in (220, 50):
            cands[f'filter adapted + native, D={d}'] = filtered(ctx, adapted_spans, d)
    return cands


def main(ord_adapted, ext_adapted):
    out = {'tolerances': [f'{int(x * 100)}%' for x in TOLERANCES]}
    for dataset, path in (('ordinary', ord_adapted), ('extended-middle', ext_adapted)):
        ctx = ad.dataset_context(dataset)
        adapted = ad.spans_from_events(ad.read_events(path), ctx['horizon'], 'available_ns')[0]
        out[dataset] = {}
        for name, spans in candidates(ctx, adapted).items():
            row = evaluate(ctx, spans)
            out[dataset][name] = row
            print(dataset, '|', name, '|', json.dumps(row))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
