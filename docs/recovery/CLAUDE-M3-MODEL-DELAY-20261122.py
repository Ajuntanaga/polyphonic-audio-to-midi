"""Model-delay sensitivity: what each model-supported candidate keeps if the model's events arrive L ms later than the saved arm A spans.

Plan and the seven predictions were committed first (CLAUDE-M3-MODEL-DELAY-PREREGISTRATION-20261122.md).  Saved data only: no audio, model run, job
or native edit.  Not a gate, not a delay or throughput measurement of any model.

Every arm A span (l, r, p) is shifted to (l + L, r + L, p) and clipped to the common horizon; CURRENT and the native confirmation are not shifted.
Candidates: the union (CURRENT union shifted arm A) and the cleanup filter (CURRENT intersect (shifted arm A union native), held D ms) at D = 220
and D = 50, plus a native-only control (no model support at all) at the same D.  Scored with the committed gate-menu evaluator.

Usage: python3 -P -E CLAUDE-M3-MODEL-DELAY-20261122.py     (no arguments; reads the saved evidence the other M3 scripts read)
Writes CLAUDE-M3-MODEL-DELAY-20261122.json next to this file.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('gm', os.path.join(HERE, 'CLAUDE-M3-GATE-MENU-20261122.py'))
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)
ad = gm.ad
from tools.pitch_detector_comparison import union_spans  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-MODEL-DELAY-20261122.json')
GRID_MS = (0, 50, 100, 250, 500, 1000, 2000)
POSTHOC_MS = (150, 200)


def shifted(spans, delay_samples, horizon):
    out = []
    for l, r, p in spans:
        l2, r2 = l + delay_samples, min(r + delay_samples, horizon)
        if l2 < horizon and r2 > l2:
            out.append((l2, r2, p))
    return union_spans(out, sample_count=horizon)


def main():
    out = {'grid_ms': list(GRID_MS)}
    for dataset in ('ordinary', 'extended-middle'):
        ctx = ad.dataset_context(dataset)
        horizon, rate = ctx['horizon'], ctx['rate']
        rows = {'CURRENT': gm.evaluate(ctx, ctx['cur_spans'])}
        for d in (220, 50):
            rows[f'native-only control, D={d}'] = gm.evaluate(ctx, gm.filtered(ctx, [], d))
        base_cov = rows['CURRENT']['coverage_pct']
        for ms in GRID_MS:
            arm = shifted(ctx['arm_a'], int(ms * rate / 1000), horizon)
            row = {'union': gm.evaluate(ctx, union_spans([*ctx['cur_spans'], *arm], sample_count=horizon))}
            for d in (220, 50):
                row[f'filter D={d}'] = gm.evaluate(ctx, gm.filtered(ctx, arm, d))
            rows[f'L={ms}'] = row
        gain0 = rows['L=0']['union']['coverage_pct'] - base_cov
        for ms in GRID_MS:
            u = rows[f'L={ms}']['union']
            u['gain_share_of_L0'] = round((u['coverage_pct'] - base_cov) / gain0, 3) if gain0 else None
        out[dataset] = rows
        print(dataset, 'CURRENT', json.dumps(rows['CURRENT']))
        for k in (k for k in rows if k.startswith('native')):
            print(dataset, k, json.dumps(rows[k]))
        for ms in GRID_MS:
            for name, r in rows[f'L={ms}'].items():
                print(dataset, f'L={ms}', name, json.dumps(r))
    # POST HOC (not in the pre-registered grid): finer union-only steps on ordinary to locate where precision crosses CURRENT's.
    ctx = ad.dataset_context('ordinary')
    out['posthoc_union_ordinary'] = {}
    for ms in POSTHOC_MS:
        arm = shifted(ctx['arm_a'], int(ms * ctx['rate'] / 1000), ctx['horizon'])
        row = gm.evaluate(ctx, union_spans([*ctx['cur_spans'], *arm], sample_count=ctx['horizon']))
        out['posthoc_union_ordinary'][f'L={ms}'] = row
        print('POST HOC ordinary', f'L={ms}', 'union', json.dumps(row))
    half = [ms for ms in GRID_MS if (out['ordinary'][f'L={ms}']['union']['gain_share_of_L0'] or 0) >= 0.5]
    out['half_gain_delay_ms_ordinary'] = max(half) if half else None
    print('half-gain delay (ordinary, largest grid L keeping >= 50% of the L=0 union coverage gain):', out['half_gain_delay_ms_ordinary'])
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
    main()
