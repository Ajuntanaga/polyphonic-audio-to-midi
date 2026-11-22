"""POST HOC anatomy of the cut-at-first-flag variant's present loss (ordinary recording).

NOT pre-registered.  Written and run after the pre-registered rapid-mute check (CLAUDE-M3-RAPID-MUTE-CHECK-PREREGISTRATION-20261122.md, commit 2fbefb6) had
produced its result, because that result put 1,077,990 present samples (8.0% of CURRENT's) behind the cut bound and the check did not say where they sit.
Descriptive only: no predictions, no policy, no threshold, nothing tuned, nothing promoted.  Saved data only (the pinned v5 trace's quiet column and the
saved CURRENT spans through the check script's own helpers); no audio, model run, job or native edit.

For every label that loses present output under the cut it reports the mechanism:
  merged_across_window  the CURRENT span containing the label began before the label and the cut point (a marked interval that starts inside that span)
                        lies before the label's annotated start: the label's whole present output from the cut point on is lost;
  window_inside_label   the cut point lies inside the label (a marked interval starts while the label is annotated);
  born_in_window        the span begins inside a marked interval and is only blanked at its head (what the mask does too).
It also reports the pitch relation to the labels that ended just before (what kind of earlier note the pre-label output of that pitch follows), the
oracle-restart ceiling (cut plus a perfect label-timed restart: every present sample restored, the cut's false output kept), and checks that the per-label
losses sum to the aggregate loss.

Usage: python3 -P -E CLAUDE-M3-RAPID-MUTE-CUT-ANATOMY-20261122.py --run
"""
import bisect
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
OUT = os.path.join(HERE, 'CLAUDE-M3-RAPID-MUTE-CUT-ANATOMY-20261122.json')


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rm = load('rm', 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py')       # importing does not run its main
fr, ad = rm.fr, rm.ad
PREVIOUS_WINDOW = 19200                                          # 200 ms at 96 kHz: labels that ended in this window before a label's start are its "previous chord"


def relation(interval):
    """Pitch relation of a label to an earlier label (semitones, label minus earlier)."""
    d = abs(interval)
    if d == 0:
        return 'same pitch'
    if d % 12 == 0:
        return 'octave'
    if d in (7, 19):
        return 'fifth'
    if d == 1:
        return 'semitone'
    if d == 2:
        return 'whole tone'
    return 'other'


def main():
    ctx = ad.dataset_context('ordinary')
    horizon, rate, labels = ctx['horizon'], ctx['rate'], ctx['labels']
    last, audit = rm.read_quiet('ordinary')
    marked = rm.marked_runs(last, horizon)
    cur_p = fr.by_pitch(ctx['cur_spans'], horizon)
    cut_p = {p: rm.cut_at_first_flag(v, marked) for p, v in cur_p.items()}
    cur_row, _, cur_cmp = rm.variant(ctx, cur_p)
    cut_row, _, cut_cmp = rm.variant(ctx, cut_p)

    # oracle restart: the cut plus every CURRENT sample that lies inside a same-pitch label (all present output); a ceiling, not a design
    by_label = {}
    for lab in labels:
        by_label.setdefault(lab['midi_note'], []).append([lab['start_sample'], lab['end_sample']])
    oracle_p = {}
    for p, spans in cur_p.items():
        inside = fr.isect(spans, rm.merge_runs(by_label.get(p, [])))
        oracle_p[p] = rm.merge_runs(list(cut_p.get(p, [])) + list(inside))
    oracle_row = rm.variant(ctx, oracle_p)[0]

    ends = [(lab['end_sample'], lab['start_sample'], lab['midi_note'], i) for i, lab in enumerate(labels)]
    rows, mismatches, ms = [], [], lambda x: round(x * 1000 / rate, 2)
    for i, lab in enumerate(labels):
        a, b, p = lab['start_sample'], lab['end_sample'], lab['midi_note']
        cur = cur_p.get(p, [])
        present = fr.isect(cur, [[a, b]])
        kept = fr.isect(cut_p.get(p, []), [[a, b]])
        lost = rm.subtract(present, kept)
        delta = cut_cmp['label_deltas'][i]
        scorer_lost = -delta['present_samples_delta']
        if fr.size(present) != delta['current_present_samples'] or fr.size(lost) != scorer_lost:
            mismatches.append(dict(label=i, mine=[fr.size(present), fr.size(lost)], scorer=[delta['current_present_samples'], scorer_lost]))
        if not lost:
            continue
        overlapping = [s for s in cur if s[0] < b and s[1] > a]
        span_lo, span_hi = overlapping[0][0], overlapping[-1][1]
        result = rm.cut_at_first_flag([[span_lo, span_hi]], marked)
        cut_at = result[-1][1] if result else None
        truncated = cut_at is not None and cut_at < span_hi
        born_blank = (not result) or result[0][0] > span_lo
        if truncated and cut_at < a:
            category = 'merged_across_window'
        elif truncated and a <= cut_at < b:
            category = 'window_inside_label'
        elif born_blank:
            category = 'born_in_window'
        else:
            category = 'other'
        same_pitch_labels = sum(1 for other in labels if other['midi_note'] == p and other['start_sample'] < span_hi and other['end_sample'] > span_lo)
        previous = sorted({(q, a - e) for e, s0, q, j in ends if j != i and a - PREVIOUS_WINDOW <= e <= a + 1})
        relations = sorted({relation(p - q) for q, _ in previous})
        rows.append(dict(label=i, midi=p, start=a, end=b, current_present=delta['current_present_samples'], lost=fr.size(lost), lost_share_pct=round(100 * fr.size(lost) / delta['current_present_samples'], 1),
                         category=category, span_start_before_label_ms=ms(a - span_lo) if span_lo < a else 0.0, span_end_after_label_ms=ms(span_hi - b) if span_hi > b else 0.0,
                         cut_point_vs_label_start_ms=ms(cut_at - a) if cut_at is not None else None, same_pitch_labels_in_span=same_pitch_labels,
                         previous_chord_pitches=[q for q, _ in previous], previous_relations=relations, over_budget=any(o['label_index'] == i for o in cut_row['budget']['over_budget_labels'])))
    total_lost = sum(r['lost'] for r in rows)
    tally = {}
    for r in rows:
        t = tally.setdefault(r['category'], dict(labels=0, lost=0, labels_over_budget=0, wholly_lost=0))
        t['labels'] += 1
        t['lost'] += r['lost']
        t['labels_over_budget'] += int(r['over_budget'])
        t['wholly_lost'] += int(r['lost'] == r['current_present'])
    rel_tally = {}
    for r in rows:
        if r['category'] == 'merged_across_window':
            for rel in r['previous_relations'] or ['none in the previous 200 ms']:
                rel_tally[rel] = rel_tally.get(rel, 0) + 1
    out = dict(schema='m3_rapid_mute_cut_anatomy_v1', post_hoc=True, trace_raw_sha256=audit['raw_sha256'], marked_runs=len(marked),
               aggregate=dict(current_present=cur_row['present'], cut_present=cut_row['present'], aggregate_loss=cur_row['present'] - cut_row['present'],
                              per_label_loss_sum=total_lost, sums_match=total_lost == cur_row['present'] - cut_row['present'],
                              cut_failing_labels=[o['label_index'] for o in cut_row['budget']['over_budget_labels']]),
               scorer_mismatches=mismatches, labels_losing_present=len(rows), tally_by_category=tally, merged_previous_relation_tally=rel_tally,
               oracle_restart=dict(present=oracle_row['present'], wrong=oracle_row['wrong'], gap=oracle_row['gap'], false=oracle_row['false'], precision_pct=oracle_row['precision_pct'],
                                   runs=oracle_row['runs'], budget_passes=oracle_row['budget']['passes'], cut_false=cut_row['false'], current_false=cur_row['false']),
               rows=rows)
    if os.path.exists(OUT):
        raise SystemExit('refusing to overwrite ' + OUT)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    print('aggregate', json.dumps(out['aggregate']))
    print('mismatches', mismatches)
    print('labels losing present', len(rows), 'tally', json.dumps(tally))
    print('previous-relation tally (merged_across_window)', json.dumps(rel_tally))
    print('oracle restart', json.dumps(out['oracle_restart']))
    for r in sorted(rows, key=lambda r: -r['lost']):
        print(json.dumps(r))


if __name__ == '__main__':
    if sys.argv[1:] == ['--run']:
        main()
    else:
        raise SystemExit(__doc__)
