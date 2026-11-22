"""Independent check of Codex's frozen L/E/A callback screen, and what E and A bring back.  Saved data only.

Plan, definitions, identity checks I0-I3, predictions P1-P5 and the reading rule are fixed in
CLAUDE-M3-SUPPORT-EVENTS-CHECK-PREREGISTRATION-20261122.md, committed before the real run.  The three arms are those of
CODEX-M3-SUPPORT-EVENTS-PLAN-20261122.md: L = the last decision of each 512-sample callback, E = every direct observation in the callback, A = E plus a
selected, active, pooled note with onset_observed = 1 and a strictly positive onset.  This script re-derives their support from the pinned v5 trace with its
own code, compares support spans, filtered spans, per-label comparisons and budget verdicts with CODEX-M3-SUPPORT-EVENTS-20261122.json and its saved span
files, then classifies every arm's output into the orphan / tail / head / between classes of CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py and measures how
much of CURRENT's present and false output each added source covers before the 220 ms hold.  Nothing is tuned, nothing is promoted.

Usage: python3 -P -E CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py --selftest
       python3 -P -E CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.py --run
No audio, model run, job or native edit.
"""
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fr = load('fr', 'CLAUDE-M3-FILTER-RESIDUAL-ANATOMY-20261122.py')
ad = fr.ad
from tools.candidate_outcome_analysis import _candidates  # noqa: E402  (the repo's own trace parser)

CALLBACK, D_MS = 512, 220
OUT = os.path.join(HERE, 'CLAUDE-M3-SUPPORT-EVENTS-CHECK-20261122.json')
CODEX_JSON = os.path.join(HERE, 'CODEX-M3-SUPPORT-EVENTS-20261122.json')
ARMS = ('L', 'E', 'A')
CLASSES = fr.CLASSES
EVENTS_DIR = os.path.join(ROOT, 'build/github-results/basic-pitch-temporal-crop-45034216124/claude-range-members')
PINS = {   # the pins of CODEX-M3-SUPPORT-EVENTS-PLAN-20261122.md
    'ordinary': dict(
        trace='build/github-results/unfiltered-observation-44835727027/evidence/github-results/unfiltered-observation/ordinary-current-on-512-outcome-v5.tsv.gz',
        sha='b664c7ff0ce80bd4e544b647ce48688ecf181918cb7e36643370bab2eccfbd93',
        events='adapted_cropped__ordinary-events.json', events_sha='4e0601c42dbdccffe32c245a74ce80a9ae24be825f0b21e010b37f33f8ac9e92'),
    'extended-middle': dict(
        trace='build/github-results/extended-middle-unfiltered-45062999189/evidence/github-results/unfiltered-observation/extended-middle-current-on-512-outcome-v5.tsv.gz',
        sha='78929974b9cc914f71ef3fa58759728dda93f4a53fea16af17f3217adb6ac267',
        events='adapted_cropped__extended-middle-events.json', events_sha='1eea72fdc62b0d2e1f09f871d3a0f1b6cf8b4490cb4413f7862fa42986f688e3'),
}


def boundary_of(sample):
    """A decision at sample s (zero-based, post-sample) can first affect output at the end of its callback: no backfill, no negative shift."""
    return (sample // CALLBACK + 1) * CALLBACK


def read_trace(name):
    """One streaming pass.  Per callback boundary: [direct set of the last decision, union of every decision's direct set, onset-cue set]."""
    pin, sha = PINS[name], hashlib.sha256()
    callbacks, audit, previous = {}, dict(rows=0, candidate_rows=0, quiet_rows=0), None
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
            if previous is None:
                audit.update(first_sample=s, first_tick=tick)
            previous = (s, tick)
            cands = _candidates({'candidate_text': row['candidates']})
            audit['rows'] += 1
            audit['candidate_rows'] += len(cands)
            audit['quiet_rows'] += int(quiet != 0)
            direct, onset = set(), set()
            for note, c in cands.items():
                for key in ('selector_pool_member', 'direct', 'active', 'onset_observed'):
                    if c.get(key) not in (0, 1):
                        raise SystemExit(f'missing or invalid {key}')
                if quiet == 0:
                    if c['selector_pool_member'] == 1 and c['direct'] == 1:
                        direct.add(note)
                    if (c['selector_pool_member'] == 1 and c['active'] == 1 and c['selection'] == 4
                            and c['onset_observed'] == 1 and c['onset'] > 0):
                        onset.add(note)
            slot = callbacks.setdefault(boundary_of(s), [set(), set(), set()])
            slot[0] = direct          # L: the last decision of the callback overwrites
            slot[1] |= direct         # E: every direct observation
            slot[2] |= onset          # onset-cue notes, joined to E for A
    audit.update(raw_sha256=sha.hexdigest(), last_sample=previous[0], last_tick=previous[1])
    if audit['raw_sha256'] != pin['sha']:
        raise SystemExit(f'{name}: raw trace hash differs from the pin')
    return callbacks, audit


def arm_support(callbacks, horizon):
    """Per-arm native support: every positive callback supplies one callback of support starting at its boundary (clipped to the horizon)."""
    items = {arm: [] for arm in ARMS}
    for b in sorted(callbacks):
        if b >= horizon:
            continue
        hi = min(b + CALLBACK, horizon)
        last, anyd, ons = callbacks[b]
        for arm, notes in (('L', last), ('E', anyd), ('A', anyd | ons)):
            items[arm].extend((b, hi, n) for n in sorted(notes))
    return {arm: fr.union_spans(v, sample_count=horizon) for arm, v in items.items()}


def sources(callbacks, horizon):
    """The callbacks each source contributes, per pitch: L (last-decision direct), E_add (direct seen earlier in the callback only), A_add (onset cue only)."""
    out = {'L': {}, 'E_add': {}, 'A_add': {}}
    for b in sorted(callbacks):
        if b >= horizon:
            continue
        hi = min(b + CALLBACK, horizon)
        last, anyd, ons = callbacks[b]
        for key, notes in (('L', last), ('E_add', anyd - last), ('A_add', ons - anyd)):
            for n in notes:
                out[key].setdefault(n, []).append([b, hi])
    return out


def filtered_spans(ctx, model, native):
    """CURRENT intersect (model union native, held forward 220 ms), merged per pitch."""
    horizon, rate = ctx['horizon'], ctx['rate']
    support = fr.union_spans([*model, *native], sample_count=horizon)
    held = ad.dil.dilate(support, D_MS * rate // 1000, horizon)
    return fr.union_spans(fr.intersect_spans(ctx['cur_spans'], held, sample_count=horizon), sample_count=horizon)


def augmented_comparison(ctx, measured):
    """compare() output with the five per-label fields the plan records (first-present delay and segment counts), JSON-normalised."""
    cmp = ad.compare(ctx['current'], measured)
    for row, before, after in zip(cmp['label_deltas'], ctx['current']['labels'], measured['labels']):
        old, new = before['first_present_delay_samples'], after['first_present_delay_samples']
        row.update(current_first_present_delay_samples=old, candidate_first_present_delay_samples=new,
                   first_present_delay_delta_samples=None if old is None or new is None else new - old,
                   current_present_segments=before['present_segments'], candidate_present_segments=after['present_segments'])
    return json.loads(json.dumps(cmp))


def budget(cmp, rate):
    """The frozen label budget (CLAUDE-M3-LABEL-RULE-DECISION-20261122.md): per label, present-time and longest-hold loss at most 25 ms AND at most 5% of that
    label's own CURRENT value; no newly missed label; no wrong-pitch or gap growth; no exact-set or all-expected loss."""
    over, missed = [], []
    for r in cmp['label_deltas']:
        found = []
        for field in ('present_samples', 'longest_present_samples'):
            lost, before = max(0, -r[field + '_delta']), r['current_' + field]
            if lost * 1000 > 25 * rate:
                found.append(field + ':25ms')
            if lost * 100 > 5 * before:
                found.append(field + ':5pct')
        if found:
            over.append(dict(label_index=r['label_index'], violations=found))
        if r['current_present_samples'] > 0 and r['model_present_samples'] == 0:
            missed.append(r['label_index'])
    d = cmp['sample_deltas']
    safe = (d['extra_pitch_voice_samples'] <= 0 and cmp['extra_gap_pitch_samples_delta'] <= 0
            and d['exact_pitch_set_samples'] >= 0 and d['all_expected_pitches_samples'] >= 0)
    return dict(over_budget_labels=over, newly_missed_labels=missed, aggregate_pitch_safety=bool(safe), passes=bool(not over and not missed and safe))


def listify(spans):
    return [[int(x) for x in s] for s in spans]


def merged(spans, horizon):
    return listify(fr.union_spans([tuple(s) for s in spans], sample_count=horizon))


def codex_spans(name):
    with gzip.open(os.path.join(HERE, f'CODEX-M3-SUPPORT-EVENTS-20261122-{name}-spans.json.gz'), 'rb') as stream:
        return json.loads(stream.read())


def guarded(fn, *args):
    """check_sums raises SystemExit on a mismatch; record it as a failed identity check instead of aborting."""
    try:
        return bool(fn(*args))
    except SystemExit as exc:
        print('IDENTITY MISMATCH:', exc)
        return False


def class_tally(spans, geo, exp, annotated, horizon):
    return fr.aggregate(fr.tally(fr.by_pitch(spans, horizon), exp, annotated, geo))


def source_coverage(src, geo, exp, annotated, cur_agg):
    """Volume of each source's callbacks inside CURRENT (before the 220 ms hold), by class, as a fraction of CURRENT's own volume of that class."""
    out = {}
    for key, per_pitch in src.items():
        rows = {}
        for p, ivals in per_pitch.items():
            if p in geo:
                clip = fr.isect(ivals, geo[p]['span'])
                if clip:
                    rows[p] = clip
        agg = fr.aggregate(fr.tally(rows, exp, annotated, geo))
        res = {}
        for band in fr.BANDS:
            v, c = agg[band], cur_agg[band]
            cov_present = v['present'] / c['present'] if c['present'] else None
            cov_false = v['false'] / c['false'] if c['false'] else None
            res[band] = dict(volume=v['total'], present=v['present'], false=v['false'], classes={k: v[k] for k in CLASSES},
                             coverage_present=cov_present, coverage_false=cov_false,
                             coverage_class={k: (v[k] / c[k] if c[k] else None) for k in CLASSES},
                             lift=(cov_present / cov_false) if cov_present is not None and cov_false else None)
        out[key] = res
    return out


def unit_checks():
    """Plumbing on synthetic inputs: the callback boundary, the three projections, source decomposition and horizon clipping."""
    ok = [boundary_of(0) == 512, boundary_of(63) == 512, boundary_of(511) == 512, boundary_of(512) == 1024, boundary_of(1023) == 1024]
    cb = {512: [{60}, {60, 62}, {60, 62, 64}], 1024: [set(), {60}, {60, 70}], 2048: [{60}, {60}, {60}], 4096: [{61}, {61}, {61}]}
    sup = arm_support(cb, 2560)       # callback 4096 is past the horizon and is dropped; 2048 + 512 is clipped to 2560
    as_set = lambda spans: sorted(tuple(s) for s in listify(spans))
    ok.append(as_set(sup['L']) == [(512, 1024, 60), (2048, 2560, 60)])
    ok.append(as_set(sup['E']) == [(512, 1024, 62), (512, 1536, 60), (2048, 2560, 60)])
    ok.append(as_set(sup['A']) == [(512, 1024, 62), (512, 1024, 64), (512, 1536, 60), (1024, 1536, 70), (2048, 2560, 60)])
    src = sources(cb, 2560)
    ok.append(src['L'] == {60: [[512, 1024], [2048, 2560]]} and src['E_add'] == {62: [[512, 1024]], 60: [[1024, 1536]]}
              and src['A_add'] == {64: [[512, 1024]], 70: [[1024, 1536]]})
    return all(ok), ok


def selftest():
    """Plumbing only: unit checks, the pinned trace hashes and tick grids, and L equal to the saved native confirmation (an input, not a Codex result)."""
    good, parts = unit_checks()
    print('unit checks', 'PASS' if good else 'FAIL', parts)
    ok = good
    for name in PINS:
        ctx = ad.dataset_context(name)
        callbacks, audit = read_trace(name)
        spans = arm_support(callbacks, ctx['horizon'])
        same = merged(spans['L'], ctx['horizon']) == merged(ctx['native'], ctx['horizon'])
        nested = all(callbacks[b][0] <= callbacks[b][1] for b in callbacks)
        print(f"{name}: rows {audit['rows']:,} candidates {audit['candidate_rows']:,} quiet {audit['quiet_rows']:,} sha ok; callbacks {len(callbacks):,}; "
              f"L equals the saved native confirmation: {same}; L within E in every callback: {nested}; spans L/E/A {len(spans['L'])}/{len(spans['E'])}/{len(spans['A'])}")
        ok = ok and same and nested
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok


def main():
    codex = json.load(open(CODEX_JSON))
    results, ident, summary = {}, {}, {}
    for name, pin in PINS.items():
        ctx = ad.dataset_context(name)
        horizon, rate = ctx['horizon'], ctx['rate']
        callbacks, audit = read_trace(name)
        mine = arm_support(callbacks, horizon)
        saved, theirs = codex_spans(name), codex['datasets'][name]
        events_path = os.path.join(EVENTS_DIR, pin['events'])
        if ad.sha256(events_path) != pin['events_sha']:
            raise SystemExit(f'{name}: event hash differs from the pin')
        model = ad.spans_from_events(ad.read_events(events_path), horizon, 'emitted_ns')[0]
        row = dict(trace_audit_equal=audit == theirs['trace'],
                   L_equals_saved_native=merged(mine['L'], horizon) == merged(ctx['native'], horizon),
                   support_equal={}, support_raw_equal={}, filtered_equal={}, filtered_raw_equal={}, comparison_equal={}, key_fields_equal={}, budget_equal={},
                   outputs_nested=None, L_filter_equals_committed_filter=None)
        arms, summary[name] = {}, {}
        for arm in ARMS:
            row['support_equal'][arm] = merged(mine[arm], horizon) == merged(saved['native_support'][arm], horizon)
            row['support_raw_equal'][arm] = listify(mine[arm]) == listify(saved['native_support'][arm])
            out = filtered_spans(ctx, model, mine[arm])
            row['filtered_equal'][arm] = listify(out) == merged(saved['filtered'][arm], horizon)
            row['filtered_raw_equal'][arm] = listify(out) == listify(saved['filtered'][arm])
            measured = fr.score(out, ctx['labels'], **ctx['clock'])
            cmp = augmented_comparison(ctx, measured)
            mb, cb = budget(cmp, rate), theirs['arms'][arm]
            row['comparison_equal'][arm] = cmp == cb['comparison']
            row['key_fields_equal'][arm] = ([(r['label_index'], r['present_samples_delta'], r['longest_present_samples_delta'], r['first_present_delay_delta_samples'])
                                             for r in cmp['label_deltas']]
                                            == [(r['label_index'], r['present_samples_delta'], r['longest_present_samples_delta'], r['first_present_delay_delta_samples'])
                                                for r in cb['comparison']['label_deltas']]
                                            and cmp['sample_deltas'] == cb['comparison']['sample_deltas']
                                            and cmp['extra_gap_pitch_samples_delta'] == cb['comparison']['extra_gap_pitch_samples_delta'])
            row['budget_equal'][arm] = mb == {k: cb['budget'][k] for k in mb}
            totals = ctx['current']['pitch_sets']['totals']
            t = measured['pitch_sets']['totals']
            summary[name][arm] = dict(present=t['present_pitch_samples'], wrong=t['extra_pitch_voice_samples'], gap=measured['pitch_sets']['unlabeled_gap_voice_samples'],
                                      wrong_removed_share=-cmp['sample_deltas']['extra_pitch_voice_samples'] / totals['extra_pitch_voice_samples'],
                                      coverage_pct=cmp['model_pitch_coverage_percent'], runs=len(out), budget=mb)
            arms[arm] = dict(out=out, measured=measured, cmp=cmp, budget=mb)
        # outputs nest by construction (support nests): check at sample level, per pitch
        nested = True
        for small, big in (('L', 'E'), ('E', 'A')):
            a, b = fr.by_pitch(arms[small]['out'], horizon), fr.by_pitch(arms[big]['out'], horizon)
            nested = nested and all(fr.size(fr.isect(a[p], b.get(p, []))) == fr.size(a[p]) for p in a)
        row['outputs_nested'] = nested
        committed = fr.filter_spans(ctx, model, D_MS)
        row['L_filter_equals_committed_filter'] = listify(arms['L']['out']) == merged(committed, horizon)
        ident[name] = row
        results[name] = dict(ctx=ctx, arms=arms, callbacks=callbacks, audit=audit)
        print(name, 'identity', json.dumps(row))
    i0 = all(r['trace_audit_equal'] and r['L_equals_saved_native'] and all(r['support_equal'].values()) for r in ident.values())
    i1 = all(all(r['filtered_equal'].values()) and r['L_filter_equals_committed_filter'] for r in ident.values())
    i2 = all(all(r['budget_equal'].values()) and all(r['key_fields_equal'].values()) for r in ident.values())

    # classes, ordinary only (the extended-middle recording has six labels, all MIDI 52: safety only)
    ctx = results['ordinary']['ctx']
    horizon, rate = ctx['horizon'], ctx['rate']
    exp, annotated, geo, cur_p, cur_agg, _, _, _ = fr.current_part(ctx)
    tallies = {'CURRENT': cur_agg}
    i3 = guarded(fr.check_sums, cur_agg, ctx['current'], 'CURRENT')
    for arm in ARMS:
        tallies[arm] = class_tally(results['ordinary']['arms'][arm]['out'], geo, exp, annotated, horizon)
        i3 = guarded(fr.check_sums, tallies[arm], results['ordinary']['arms'][arm]['measured'], arm) and i3
    i3 = i3 and all(r['outputs_nested'] for r in ident.values())
    C, Lq, E, A = cur_agg['all'], tallies['L']['all'], tallies['E']['all'], tallies['A']['all']

    def step(hi, lo):
        d = {k: hi[k] - lo[k] for k in CLASSES}
        d.update(present=hi['present'] - lo['present'], false=hi['false'] - lo['false'], extra=hi['extra'] - lo['extra'], gap=hi['gap'] - lo['gap'])
        d['false_per_present'] = round(d['false'] / d['present'], 1) if d['present'] else None
        return d

    readmit = {'E_over_L': step(E, Lq), 'A_over_E': step(A, E), 'A_over_L': step(A, Lq), 'L_removed_from_CURRENT': {k: C[k] - Lq[k] for k in CLASSES}}
    pool = readmit['L_removed_from_CURRENT']
    share = {arm: {k: ((tallies[arm]['all'][k] - Lq[k]) / pool[k] if pool[k] else None) for k in CLASSES} for arm in ('E', 'A')}
    removal = {arm: {k: round(1 - tallies[arm]['all'][k] / C[k], 4) for k in CLASSES} for arm in ARMS}
    coverage = source_coverage(sources(results['ordinary']['callbacks'], horizon), geo, exp, annotated, cur_agg)
    lift = {key: coverage[key]['all']['lift'] for key in coverage}
    e_over_l = readmit['E_over_L']
    largest_e = max(CLASSES, key=lambda k: e_over_l[k])
    preds = {
        'P1 E over L: tail is the largest class of the false output E re-admits': largest_e == 'tail',
        'P2 A re-admits at least as large a share of the L-removed orphan pool as of the L-removed tail pool': (
            share['A']['orphan'] is not None and share['A']['tail'] is not None and share['A']['orphan'] >= share['A']['tail']),
        'P3 lift of the L-direct source (present coverage / false coverage, before the hold) at least 2.0': lift['L'] is not None and lift['L'] >= 2.0,
        'P4 lift of the onset-only source (A_add) under 1.5': lift['A_add'] is not None and lift['A_add'] < 1.5,
        'P5 lift of the extra direct source (E_add) below the lift of the L-direct source': (
            lift['E_add'] is not None and lift['L'] is not None and lift['E_add'] < lift['L']),
    }
    identity_all = bool(i0 and i1 and i2 and i3)
    reading = dict(identity_all_pass=identity_all, I0_support=i0, I1_filtered=i1, I2_budget_and_labels=i2, I3_classes=i3,
                   largest_class_E_over_L=largest_e, largest_class_A_over_L=max(CLASSES, key=lambda k: readmit['A_over_L'][k]),
                   lifts=lift, share_of_L_removed_pool_readmitted=share)
    out = dict(schema='m3_support_events_check_v1', hold_ms=D_MS, callback_samples=CALLBACK, identity=ident, arm_summary=summary, tallies=tallies,
               removal_share=removal, readmitted=readmit, coverage=coverage, predictions=preds, reading=reading,
               audit={n: results[n]['audit'] for n in results},
               inputs={n: dict(trace_sha256=PINS[n]['sha'], events_sha256=PINS[n]['events_sha']) for n in PINS},
               codex_json_sha256=hashlib.sha256(open(CODEX_JSON, 'rb').read()).hexdigest())
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    print('predictions', json.dumps(preds, indent=1))
    print('reading', json.dumps(reading))
    for name in summary:
        for arm in ARMS:
            s = summary[name][arm]
            print(f"{name} {arm}: present {s['present']:,} wrong {s['wrong']:,} gap {s['gap']:,} wrong removed {100 * s['wrong_removed_share']:.3f}% coverage {s['coverage_pct']:.4f}% "
                  f"runs {s['runs']} budget passes {s['budget']['passes']} over {[(o['label_index'], o['violations']) for o in s['budget']['over_budget_labels']]}")
    print('removal share', json.dumps(removal))
    print('re-admitted', json.dumps(readmit))
    for key, res in coverage.items():
        a = res['all']
        print(f"coverage {key}: volume {a['volume']:,} present {a['present']:,} false {a['false']:,} cov_present {a['coverage_present']:.4f} "
              f"cov_false {a['coverage_false']:.4f} lift {a['lift']}  by class {a['classes']}")


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        raise SystemExit(0 if selftest() else 1)
    if sys.argv[1:] == ['--run']:
        if os.path.exists(OUT):
            raise SystemExit('refusing to overwrite ' + OUT)
        main()
    else:
        raise SystemExit(__doc__)
