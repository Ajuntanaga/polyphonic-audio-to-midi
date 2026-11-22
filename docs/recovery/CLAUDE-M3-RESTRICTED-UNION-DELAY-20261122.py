"""Restricted union (CURRENT union arm A spans with pitch >= 60) under model delay.  Plan and six predictions committed first
(CLAUDE-M3-RESTRICTED-UNION-DELAY-PREREGISTRATION-20261122.md).  Saved data only: no audio, model run, job or native edit; not a gate.

Each arm A span with pitch >= CUT is shifted by L ms (onset and offset together) and clipped to the common horizon, then unioned with CURRENT's
spans.  Scored with the committed gate-menu evaluator, next to the full union rows from CLAUDE-M3-MODEL-DELAY-20261122.json.  The combined false
change is (wrong-pitch voice + unlabeled gap voice) against CURRENT's, computed here from the same score() totals.

Usage: python3 -P -E CLAUDE-M3-RESTRICTED-UNION-DELAY-20261122.py     (no arguments)
Writes CLAUDE-M3-RESTRICTED-UNION-DELAY-20261122.json next to this file.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('md', os.path.join(HERE, 'CLAUDE-M3-MODEL-DELAY-20261122.py'))
md = importlib.util.module_from_spec(spec)
spec.loader.exec_module(md)
gm, ad = md.gm, md.ad
from tools.pitch_detector_comparison import score, union_spans  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-RESTRICTED-UNION-DELAY-20261122.json')
CUT = 60
GRID_MS = (0, 50, 100, 150, 200, 250, 500, 1000)


def false_samples(ctx, spans):
    sc = score(spans, ctx['labels'], **ctx['clock'])
    return sc['pitch_sets']['totals']['extra_pitch_voice_samples'] + sc['pitch_sets']['unlabeled_gap_voice_samples']


def main():
    full = json.load(open(os.path.join(HERE, 'CLAUDE-M3-MODEL-DELAY-20261122.json')))
    out = {'cut': CUT, 'grid_ms': list(GRID_MS)}
    for dataset in ('ordinary', 'extended-middle'):
        ctx = ad.dataset_context(dataset)
        horizon, rate = ctx['horizon'], ctx['rate']
        base_cov = gm.evaluate(ctx, ctx['cur_spans'])['coverage_pct']
        base_false = false_samples(ctx, ctx['cur_spans'])
        rows = {}
        for ms in GRID_MS:
            arm = md.shifted([s for s in ctx['arm_a'] if s[2] >= CUT], int(ms * rate / 1000), horizon)
            spans = union_spans([*ctx['cur_spans'], *arm], sample_count=horizon)
            row = gm.evaluate(ctx, spans)
            row['combined_false_change_pct'] = round(100 * (false_samples(ctx, spans) - base_false) / max(1, base_false), 1)
            rows[f'L={ms}'] = row
        gain0 = rows['L=0']['coverage_pct'] - base_cov
        for ms in GRID_MS:
            r = rows[f'L={ms}']
            r['gain_share_of_L0'] = round((r['coverage_pct'] - base_cov) / gain0, 3) if gain0 else None
            f = full.get(dataset, {}).get(f'L={ms}', {}).get('union')
            if f is None and dataset == 'ordinary':
                f = full.get('posthoc_union_ordinary', {}).get(f'L={ms}')   # the 150 and 200 ms rows are post hoc in the delay sweep
            r['full_union_coverage_pct'] = f['coverage_pct'] if f else None
            r['full_union_precision_pct'] = f['precision_pct'] if f else None
            print(dataset, f'L={ms}', json.dumps(r))
        out[dataset] = rows
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    main()
