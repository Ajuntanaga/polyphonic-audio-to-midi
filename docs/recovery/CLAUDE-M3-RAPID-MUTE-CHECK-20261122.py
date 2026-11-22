"""Independent check of Codex's rapid-mute cue screen, what the mask removes, how it stacks with the L/E/A support filters, and a cut-at-first-flag bound.

Saved data only.  Plan, definitions, identity checks I0-I3, predictions P1-P7 and the reading rule are fixed in
CLAUDE-M3-RAPID-MUTE-CHECK-PREREGISTRATION-20261122.md, committed before the real run.

The cue and the mask are those of CODEX-M3-RAPID-MUTE-PLAN-20261122.md, written here from the plan's wording (Codex's script is deliberately not read before
this derivation is finished): at each completed 512-sample callback take only the last decision's quiet disposition; mark the following callback interval
[B, B + 512) when it is 5 (rapid_mute_ratio), where B = ceil((s + 1) / 512) * 512 for the decision at zero-based post-sample s; clip to the common horizon; the
diagnostic mask is CURRENT minus the marked intervals.  Beyond identity this script adds (all descriptive, nothing tuned, nothing promoted):
  * the class split (orphan / tail / head / between, CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py) of what the mask removes;
  * the mask stacked on the L / E / A support arms of CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py (the marginal false and present volume it adds);
  * where inside each label the mask's present loss sits;
  * how the marked runs sit against the annotated timeline (a recording-protocol effect would cap generalisation);
  * a cut-at-first-flag occupancy bound: each CURRENT span is truncated at the first marked interval that starts inside it, with no resume.

Usage: python3 -P -E CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py --selftest
       python3 -P -E CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py --run
No audio, model run, job or native edit.
"""
import bisect
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chk = load('chk', 'CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py')   # pins, L/E/A support derivation, budget; verified equal to Codex's L/E/A screen
fr, ad = chk.fr, chk.ad

CALLBACK, RAPID_MUTE, HEAD_WINDOW = 512, 5, 1024
OUT = os.path.join(HERE, 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.json')
CODEX_JSON = os.path.join(HERE, 'CODEX-M3-RAPID-MUTE-20261122.json')
CLASSES, ARMS = fr.CLASSES, chk.ARMS
ORDINARY = 'ordinary'


# ---------------------------------------------------------------- interval helpers (sorted, disjoint [lo, hi) lists)
def merge_runs(intervals):
    out = []
    for lo, hi in sorted([int(a), int(b)] for a, b in intervals):
        if hi <= lo:
            continue
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def subtract(a, b):
    """a minus b."""
    out, j = [], 0
    for lo, hi in a:
        cur = lo
        while j < len(b) and b[j][1] <= cur:
            j += 1
        k = j
        while k < len(b) and b[k][0] < hi:
            if b[k][0] > cur:
                out.append([cur, b[k][0]])
            cur = max(cur, b[k][1])
            if cur >= hi:
                break
            k += 1
        if cur < hi:
            out.append([cur, hi])
    return out


def cut_at_first_flag(spans, marked):
    """Truncate each span at the first marked interval that starts inside it.  A span that begins inside a marked interval is blanked until that interval ends
    (as the mask does) and is then truncated at the next marked interval that starts inside it; nothing is resumed after a truncation."""
    ends = [m[1] for m in marked]
    out = []
    for lo, hi in spans:
        cur = lo
        i = bisect.bisect_right(ends, lo)          # first marked interval ending after the span starts
        if i < len(marked) and marked[i][0] <= lo:
            cur = marked[i][1]
            i += 1
            if cur >= hi:
                continue
        if i < len(marked) and marked[i][0] < hi:
            if marked[i][0] > cur:
                out.append([cur, marked[i][0]])
        else:
            out.append([cur, hi])
    return out


def cut_changes(cur_p, marked):
    """How many CURRENT spans the cut rule shortens and how many it removes entirely."""
    changed = removed = 0
    for spans in cur_p.values():
        for span in spans:
            result = cut_at_first_flag([span], marked)
            if result != [list(span)]:
                changed += 1
                removed += int(not result)
    return dict(spans_changed=changed, spans_removed_entirely=removed)


def triples(per_pitch):
    return [(lo, hi, p) for p in sorted(per_pitch) for lo, hi in per_pitch[p]]


def total(per_pitch):
    return sum(fr.size(v) for v in per_pitch.values())


# ---------------------------------------------------------------- the cue
def read_quiet(name):
    """One streaming pass.  Per completed callback the quiet disposition of its last decision, keyed by the callback's end boundary B (= s + 1 for s = 511 mod 512)."""
    pin, sha = chk.PINS[name], hashlib.sha256()
    last, counts, previous, rows = {}, [0] * 8, None, 0
    with gzip.open(os.path.join(ROOT, pin['trace']), 'rb') as stream:
        def lines():
            for raw in stream:
                sha.update(raw)
                yield raw.decode('utf-8')
        text = lines()
        if next(text).strip() != '# m3_candidate_outcome_v5':
            raise SystemExit('not the complete v5 trace')
        for row in csv.DictReader(text, delimiter='\t'):
            s, tick, quiet = int(row['sample']), int(row['tick']), int(row['quiet'])
            if previous is not None and (s != previous[0] + 64 or tick != previous[1] + 1):
                raise SystemExit('tick grid is not contiguous')
            if not 0 <= quiet <= 7:
                raise SystemExit(f'quiet disposition {quiet} outside 0..7')
            previous, rows = (s, tick), rows + 1
            counts[quiet] += 1
            if (s + 1) % CALLBACK == 0:
                last[s + 1] = quiet
    audit = dict(rows=rows, quiet_counts=counts, raw_sha256=sha.hexdigest(), last_sample=previous[0])
    if audit['raw_sha256'] != pin['sha']:
        raise SystemExit(f'{name}: raw trace hash differs from the pin')
    boundaries = sorted(last)
    if boundaries != list(range(CALLBACK, CALLBACK * (len(boundaries) + 1), CALLBACK)):
        raise SystemExit(f'{name}: completed callbacks are not contiguous from the first')
    return last, audit


def marked_runs(last, horizon):
    """Callback intervals [B, B + 512) following a last decision with disposition 5, clipped to the horizon and merged into runs."""
    return merge_runs((b, min(b + CALLBACK, horizon)) for b in sorted(last) if last[b] == RAPID_MUTE and b < horizon)


# ---------------------------------------------------------------- scoring one variant
def variant(ctx, per_pitch, geo_bundle=None):
    horizon, rate = ctx['horizon'], ctx['rate']
    measured = fr.score(triples(per_pitch), ctx['labels'], **ctx['clock'])
    cmp = json.loads(json.dumps(ad.compare(ctx['current'], measured)))
    t = measured['pitch_sets']['totals']
    gap = measured['pitch_sets']['unlabeled_gap_voice_samples']
    present, wrong = t['present_pitch_samples'], t['extra_pitch_voice_samples']
    row = dict(present=present, wrong=wrong, gap=gap, false=wrong + gap, precision_pct=round(100 * present / (present + wrong + gap), 3),
               coverage_pct=cmp['model_pitch_coverage_percent'], runs=sum(len(v) for v in per_pitch.values()), budget=chk.budget(cmp, rate),
               volume=total(per_pitch))
    if geo_bundle is not None:
        exp, annotated, geo = geo_bundle
        agg = fr.aggregate(fr.tally(per_pitch, exp, annotated, geo))
        fr.check_sums(agg, measured, 'variant')
        row['classes'] = agg
    return row, measured, cmp


def removal(base, cut):
    """Volume (all pitches) in base that is not in cut, by class: CURRENT-style tallies."""
    b, c = base['all'], cut['all']
    d = {k: b[k] - c[k] for k in CLASSES}
    d.update(present=b['present'] - c['present'], false=b['false'] - c['false'], total=b['total'] - c['total'])
    d['false_per_present'] = round(d['false'] / d['present'], 1) if d['present'] else None
    return d


def label_anatomy(ctx, cur_p, marked, cmp, codex_cmp):
    """Where inside each label the mask removes present output, against the scorer's per-label present deltas."""
    rows, mismatches = [], []
    for i, lab in enumerate(ctx['labels']):
        a, b, p = lab['start_sample'], lab['end_sample'], lab['midi_note']
        present = fr.isect(cur_p.get(p, []), [[a, b]])
        lost = fr.isect(present, marked)
        delta = cmp['label_deltas'][i]
        scorer_lost = -delta['present_samples_delta']
        if fr.size(present) != delta['current_present_samples'] or fr.size(lost) != scorer_lost:
            mismatches.append(dict(label=i, mine=[fr.size(present), fr.size(lost)], scorer=[delta['current_present_samples'], scorer_lost]))
        if codex_cmp is not None and codex_cmp['label_deltas'][i]['present_samples_delta'] != delta['present_samples_delta']:
            mismatches.append(dict(label=i, codex_delta=codex_cmp['label_deltas'][i]['present_samples_delta'], mine=delta['present_samples_delta']))
        if not lost:
            continue
        first, last_end = lost[0][0] - a, lost[-1][1] - a
        where = 'head' if last_end <= HEAD_WINDOW else ('end' if lost[0][0] >= b - HEAD_WINDOW else 'other')
        rows.append(dict(label=i, midi=p, start=a, end=b, current_present=delta['current_present_samples'], lost=fr.size(lost), pieces=len(lost),
                         first_offset=first, last_offset=last_end, where=where,
                         longest_delta=delta['longest_present_samples_delta']))
    return rows, mismatches


def protocol(marked, annotated, horizon, rate):
    """Marked runs against the annotated timeline (union of all labels): blocks, interior gaps, which gaps hold a run start."""
    starts = [a for a, _ in annotated]
    in_block = lambda x: (lambda i: i >= 0 and annotated[i][0] <= x < annotated[i][1])(bisect.bisect_right(starts, x) - 1)
    run_rows = [dict(start=m0, end=m1, length=m1 - m0, start_in_label=bool(in_block(m0))) for m0, m1 in marked]
    gaps = [(annotated[k][1], annotated[k + 1][0]) for k in range(len(annotated) - 1) if annotated[k + 1][0] > annotated[k][1]]
    with_run, offsets, tails = 0, [], []
    for g0, g1 in gaps:
        inside = [r for r in marked if g0 <= r[0] < g1]
        if inside:
            with_run += 1
            offsets.append(inside[0][0] - g0)
            tails.append(g1 - inside[-1][1])
    ms = lambda x: round(x * 1000 / rate, 2)
    med = lambda v: ms(statistics.median(v)) if v else None
    return dict(runs=len(marked), runs_start_outside_labels=sum(1 for r in run_rows if not r['start_in_label']),
                runs_start_inside_labels=sum(1 for r in run_rows if r['start_in_label']), blocks=len(annotated), interior_gaps=len(gaps),
                gaps_with_a_run_start=with_run, gap_median_ms=med([g1 - g0 for g0, g1 in gaps]), run_length_median_ms=med([r['length'] for r in run_rows]),
                run_start_after_gap_start_median_ms=med(offsets), gap_end_after_last_run_end_median_ms=med(tails),
                run_start_inside_label_offsets_ms=[ms(r['start'] - annotated[bisect.bisect_right(starts, r['start']) - 1][0]) for r in run_rows if r['start_in_label']][:40])


def unit_checks():
    """Plumbing on synthetic inputs: run merging, subtraction, the marking rule, the cut rule."""
    ok = []
    ok.append(merge_runs([(5, 9), (0, 3), (3, 4), (8, 12), (20, 20)]) == [[0, 4], [5, 12]])
    ok.append(subtract([[0, 10], [20, 30]], [[2, 4], [8, 22], [28, 40]]) == [[0, 2], [4, 8], [22, 28]])
    ok.append(subtract([[0, 10]], []) == [[0, 10]] and subtract([], [[0, 5]]) == [] and subtract([[3, 6]], [[0, 10]]) == [])
    last = {512: 0, 1024: 5, 1536: 5, 2048: 2, 2560: 5, 3072: 5}
    ok.append(marked_runs(last, 3000) == [[1024, 2048], [2560, 3000]])       # [B, B+512), merged, past-horizon boundary dropped, clipped
    ok.append(marked_runs(last, 1024) == [])                                  # a flag at boundary 1024 marks [1024, ...) which is beyond a horizon of 1024
    marked = [[100, 150], [300, 320]]
    ok.append(cut_at_first_flag([[0, 90]], marked) == [[0, 90]])              # no window
    ok.append(cut_at_first_flag([[0, 200]], marked) == [[0, 100]])            # window starts inside: cut, nothing resumed
    ok.append(cut_at_first_flag([[0, 400]], marked) == [[0, 100]])            # a second window changes nothing
    ok.append(cut_at_first_flag([[120, 400]], marked) == [[150, 300]])        # born inside the first window: blanked until it ends, cut at the second
    ok.append(cut_at_first_flag([[120, 140]], marked) == [])                  # entirely inside a window
    ok.append(cut_at_first_flag([[150, 250]], marked) == [[150, 250]])        # starts where the window ends
    ok.append(cut_at_first_flag([[0, 100]], marked) == [[0, 100]])            # ends where the window starts
    ok.append(cut_at_first_flag([[0, 50], [200, 400]], marked) == [[0, 50], [200, 300]])
    return all(ok), ok


def selftest():
    """Plumbing only: unit checks and the pinned trace hashes, tick grids and callback completeness (no mute counts, no comparison with Codex)."""
    good, parts = unit_checks()
    print('unit checks', 'PASS' if good else 'FAIL', parts)
    ok = good
    for name in chk.PINS:
        ctx = ad.dataset_context(name)
        last, audit = read_quiet(name)
        cur_p = fr.by_pitch(ctx['cur_spans'], ctx['horizon'])
        t = ctx['current']['pitch_sets']['totals']
        volume = total(cur_p)
        same = volume == t['present_pitch_samples'] + t['extra_pitch_voice_samples'] + ctx['current']['pitch_sets']['unlabeled_gap_voice_samples']
        above = max(last) >= ctx['horizon']
        print(f"{name}: rows {audit['rows']:,} sha ok; completed callbacks {len(last):,}; last completed boundary {max(last):,} >= horizon {ctx['horizon']:,}: {above}; "
              f"sum of quiet counts {sum(audit['quiet_counts']):,}; CURRENT volume equals the scorer's present + extra + gap: {same}")
        ok = ok and above and same and sum(audit['quiet_counts']) == audit['rows']
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok


def guarded(fn, *args):
    try:
        return bool(fn(*args))
    except SystemExit as exc:
        print('IDENTITY MISMATCH:', exc)
        return False


def main():
    codex = json.load(open(CODEX_JSON))
    out = dict(schema='m3_rapid_mute_check_v1', callback_samples=CALLBACK, datasets={}, identity={}, hold_ms=chk.D_MS)
    keep = {}
    for name, pin in chk.PINS.items():
        ctx = ad.dataset_context(name)
        horizon, rate = ctx['horizon'], ctx['rate']
        theirs = codex['datasets'][name]
        last, audit = read_quiet(name)
        marked = marked_runs(last, horizon)
        cur_p = fr.by_pitch(ctx['cur_spans'], horizon)
        geo_bundle = fr.geometry(ctx['cur_spans'], ctx['labels'], horizon) if name == ORDINARY else None
        mask_p = {p: subtract(v, marked) for p, v in cur_p.items()}
        cut_p = {p: cut_at_first_flag(v, marked) for p, v in cur_p.items()}
        subset = all(fr.size(fr.isect(mask_p[p], cur_p[p])) == fr.size(mask_p[p]) and fr.size(fr.isect(cut_p[p], mask_p[p])) == fr.size(cut_p[p]) for p in cur_p)
        cur_row, cur_measured, _ = variant(ctx, cur_p, geo_bundle)
        variants = {'CURRENT': (cur_row, cur_p)}
        mask_row, mask_measured, mask_cmp = variant(ctx, mask_p, geo_bundle)
        variants['mask'] = (mask_row, mask_p)
        cut_row, _, cut_cmp = variant(ctx, cut_p, geo_bundle)
        variants['cut'] = (cut_row, cut_p)
        # the three support arms (verified equal to Codex's L/E/A screen) and the cue stacked on them
        callbacks, _ = chk.read_trace(name)
        mine = chk.arm_support(callbacks, horizon)
        events_path = os.path.join(chk.EVENTS_DIR, pin['events'])
        if ad.sha256(events_path) != pin['events_sha']:
            raise SystemExit(f'{name}: event hash differs from the pin')
        model = ad.spans_from_events(ad.read_events(events_path), horizon, 'emitted_ns')[0]
        for arm in ARMS:
            arm_p = fr.by_pitch(chk.filtered_spans(ctx, model, mine[arm]), horizon)
            variants[arm] = (variant(ctx, arm_p, geo_bundle)[0], arm_p)
            stack_mask = {p: subtract(v, marked) for p, v in arm_p.items()}
            stack_cut = {p: fr.isect(v, cut_p.get(p, [])) for p, v in arm_p.items()}
            variants[arm + '+mask'] = (variant(ctx, stack_mask, geo_bundle)[0], stack_mask)
            variants[arm + '+cut'] = (variant(ctx, stack_cut, geo_bundle)[0], stack_cut)
        # identity against Codex's saved rapid-mute JSON
        overlap_scorer = dict(present=cur_row['present'] - mask_row['present'], wrong_pitch=cur_row['wrong'] - mask_row['wrong'], gap=cur_row['gap'] - mask_row['gap'])
        overlap_geometry = sum(fr.size(fr.isect(v, marked)) for v in cur_p.values())
        ident = dict(
            trace_audit_equal=audit == theirs['trace_audit'],
            horizon_equal=horizon == theirs['horizon'], rate_equal=rate == theirs['rate'],
            marked_intervals_equal=marked == [list(x) for x in theirs['marked_intervals']],
            marked_samples_equal=fr.size(marked) == theirs['marked_samples'], marked_runs_equal=len(marked) == theirs['marked_runs'],
            current_totals_equal=dict(present=cur_row['present'], wrong_pitch=cur_row['wrong'], gap=cur_row['gap']) == dict(
                present=theirs['current']['present_pitch_samples'], wrong_pitch=theirs['current']['wrong_pitch_samples'], gap=theirs['current']['gap_extra_pitch_samples']),
            masked_totals_equal=dict(present=mask_row['present'], wrong_pitch=mask_row['wrong'], gap=mask_row['gap']) == dict(
                present=theirs['masked']['present_pitch_samples'], wrong_pitch=theirs['masked']['wrong_pitch_samples'], gap=theirs['masked']['gap_extra_pitch_samples']),
            overlap_equal=dict(present=overlap_scorer['present'], wrong_pitch=overlap_scorer['wrong_pitch'], gap=overlap_scorer['gap'],
                               total=sum(overlap_scorer.values())) == {k: theirs['overlap'][k] for k in ('present', 'wrong_pitch', 'gap', 'total')},
            overlap_geometry_equals_scorer=overlap_geometry == sum(overlap_scorer.values()),
            comparison_equal=mask_cmp == theirs['comparison'], budget_equal=mask_row['budget'] == {k: theirs['budget'][k] for k in mask_row['budget']},
            runs_equal=dict(current=cur_row['runs'], masked=mask_row['runs']) == theirs['occupancy_runs'],
            mask_inside_current_and_cut_inside_mask=bool(subset))
        out['identity'][name] = ident
        print(name, 'identity', json.dumps(ident))
        entry = dict(horizon=horizon, rate=rate, audit=audit, marked_runs=len(marked), marked_samples=fr.size(marked),
                     overlap=dict(scorer=overlap_scorer, geometry_total=overlap_geometry),
                     variants={k: v[0] for k, v in variants.items()},
                     cut_changes=cut_changes(cur_p, marked))
        entry['protocol'] = protocol(marked, geo_bundle[1] if geo_bundle else fr.geometry(ctx['cur_spans'], ctx['labels'], horizon)[1], horizon, rate)
        if name == ORDINARY:
            rows, mismatches = label_anatomy(ctx, cur_p, marked, mask_cmp, theirs['comparison'])
            entry['label_anatomy'] = rows
            entry['label_anatomy_mismatches'] = mismatches
            exp, annotated, geo = geo_bundle
            C = variants['CURRENT'][0]['classes']
            entry['removal'] = {k: removal(C, variants[k][0]['classes']) for k in ('mask', 'cut', 'L', 'E', 'A')}
            entry['removal_over_arm'] = {arm + '+' + how: removal(variants[arm][0]['classes'], variants[arm + '+' + how][0]['classes'])
                                         for arm in ARMS for how in ('mask', 'cut')}
            entry['band_removal'] = {k: {band: {c: C[band][c] - variants[k][0]['classes'][band][c] for c in (*CLASSES, 'present', 'false')} for band in fr.BANDS}
                                     for k in ('mask', 'cut')}
            keep = dict(C=C, removal=entry['removal'], rows=rows, mismatches=mismatches, entry=entry)
        out['datasets'][name] = entry
    i0 = all(all(v for k, v in r.items() if k in ('trace_audit_equal', 'horizon_equal', 'rate_equal', 'marked_intervals_equal', 'marked_samples_equal', 'marked_runs_equal'))
             for r in out['identity'].values())
    i1 = all(r['current_totals_equal'] and r['masked_totals_equal'] and r['overlap_equal'] and r['overlap_geometry_equals_scorer'] for r in out['identity'].values())
    i2 = all(r['comparison_equal'] and r['budget_equal'] and r['runs_equal'] for r in out['identity'].values())
    i3 = all(r['mask_inside_current_and_cut_inside_mask'] for r in out['identity'].values()) and not keep['mismatches']
    ent, C, rem = keep['entry'], keep['C'], keep['removal']
    mask_false = rem['mask']['false']
    over_l = out['datasets'][ORDINARY]['removal_over_arm']['L+mask']
    lab = keep['rows']
    preds = {
        'P1 the largest class of the false output the mask removes is tail': max(CLASSES, key=lambda k: rem['mask'][k]) == 'tail',
        'P2 the mask removes under 25% of CURRENT tail volume': rem['mask']['tail'] < 0.25 * C['all']['tail'],
        'P3 the L filter already removes under 25% of the mask overlap false volume (the mask adds at least 75% of it over L)': over_l['false'] >= 0.75 * mask_false,
        'P4 the cut-at-first-flag variant removes at least 3x the mask false volume': rem['cut']['false'] >= 3 * mask_false,
        'P5 the cut-at-first-flag variant loses under 50,000 present samples': rem['cut']['present'] < 50000,
        'P6 at least 80% of the marked runs start where no label is annotated': ent['protocol']['runs_start_outside_labels'] >= 0.8 * ent['protocol']['runs'],
        'P7 at least 12 of the labels that lose present output under the mask lose it only within the first 1,024 samples of their annotated start': sum(1 for r in lab if r['where'] == 'head') >= 12,
    }
    reading = dict(identity_all_pass=bool(i0 and i1 and i2 and i3), I0_cue=i0, I1_volumes=i1, I2_comparison_budget_runs=i2, I3_nesting_and_label_anatomy=i3,
                   labels_with_loss=len(lab), labels_head=sum(1 for r in lab if r['where'] == 'head'), labels_end=sum(1 for r in lab if r['where'] == 'end'),
                   labels_other=sum(1 for r in lab if r['where'] == 'other'))
    out.update(predictions=preds, reading=reading, codex_json_sha256=hashlib.sha256(open(CODEX_JSON, 'rb').read()).hexdigest(),
               inputs={n: dict(trace_sha256=chk.PINS[n]['sha'], events_sha256=chk.PINS[n]['events_sha']) for n in chk.PINS})
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    print('predictions', json.dumps(preds, indent=1))
    print('reading', json.dumps(reading))
    for name, e in out['datasets'].items():
        print(f"{name}: marked runs {e['marked_runs']} samples {e['marked_samples']:,} overlap {e['overlap']}")
        for k, v in e['variants'].items():
            print(f"  {k:9s} present {v['present']:,} wrong {v['wrong']:,} gap {v['gap']:,} precision {v['precision_pct']} runs {v['runs']} budget passes {v['budget']['passes']} "
                  f"over {[o['label_index'] for o in v['budget']['over_budget_labels']]}")
    print('removal (ordinary)', json.dumps(rem))
    print('protocol (ordinary)', json.dumps({k: v for k, v in ent['protocol'].items() if k != 'run_start_inside_label_offsets_ms'}))
    print('label anatomy', json.dumps(lab))


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        raise SystemExit(0 if selftest() else 1)
    if sys.argv[1:] == ['--run']:
        if os.path.exists(OUT):
            raise SystemExit('refusing to overwrite ' + OUT)
        main()
    else:
        raise SystemExit(__doc__)
